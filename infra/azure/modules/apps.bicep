// =============================================================================
// SKY-114 - Apps + jobs module
//
// Three Container Apps on the shared Consumption-profile environment:
//   identity  external  :8000  (JWT issuance, sessions, MFA, billing)
//   core      external  :8001  (ERP/HR/finance/reporting monolith)
//   ai-agent  internal  :8000  (RAG/agents - only reachable inside the VNet)
//
// One-shot Container Apps Jobs (deploy-time, run in-VNet by CD):
//   db-init   postgres:16-alpine - creates skyrict_identity + pgvector/pg_trgm
//   identity  alembic upgrade head  (FIRST: creates tenants + current_tenant_id)
//   core      alembic upgrade head  (alembic_version_core)
//   ai-agent  alembic upgrade head  (alembic_version_ai)
//
// Secret architecture:
//   * database-url / redis-url are plain ACA secrets computed from secure
//     params (admin password) + listKeys() - no committed secret material.
//   * jwt-* / mfa / sync-token / ingest-token are Key Vault secret
//     references resolved with the user-assigned identity (clientId).
//     The CD seeds those KV secrets BEFORE deploying workloads.
//   * JWT key files are mounted as SECRET VOLUMES because the services read
//     the PEM files at settings-load time (load_rsa_keys, sys.exit on miss).
//
// Two independent guards, and the split is load-bearing rather than cosmetic:
//
//   deployWorkloads  everything in this module. False during phase 1, which is
//                    infra + data + Key Vault only.
//   deployApps       the four container apps. False in phase 2's FIRST apply.
//
// Phase 2 is therefore two applies around the migrations, and the order is not
// negotiable. The three services call verify_startup_dependencies() during
// FastAPI startup, check_database() raises out of the lifespan when the
// database is absent, and the process exits - it does not come up degraded and
// it does not answer 503 and wait. Observed live on all three backends:
//
//   asyncpg.exceptions.InvalidCatalogNameError: database "skyrict_identity"
//   does not exist
//   -> startup.verification_failed -> Application startup failed. Exiting.
//
// So an app deployed before db-init is not a slow-starting app, it is a
// crash-looping one, and whether it ever recovers depends on how long ACA keeps
// retrying the restart. Creating the apps only after db-init and the alembic
// runs means the first container start is the one that succeeds.
//
// This is invisible in resource state, which is why it is worth a parameter: the
// apps and jobs both report provisioningState Succeeded and their revisions
// report Provisioned while every replica sits at runningState NotRunning. Only
// `az containerapp replica list` shows it.
// =============================================================================

@description('Resource name prefix. Defaults to "skyrict".')
param prefix string = 'skyrict'

@description('Deployment environment name (beta/staging/production).')
param envName string

@description('Azure region for all resources.')
param location string

@description('Tags merged onto every resource.')
param tags object = {}

@description('Deploy the apps and jobs. False during phase 1 infra+KV+data rollout.')
param deployWorkloads bool = true

@description('Deploy the four container apps. False in phase 2 until db-init and the alembic migrations have run, because the services exit at startup when the database does not exist. The jobs deploy on deployWorkloads; the apps additionally require this.')
param deployApps bool = true

@description('Resource ID of the Container Apps Environment.')
param caeId string

@description('Container Apps Environment name. Used as the parent of the managed certificate.')
param environmentName string

@description('Container Apps Environment default domain (e.g. bluesky-957ace7a.westus.azurecontainerapps.io). Azure generates this per environment; it is NOT the environment name. Internal app FQDNs are <app>.internal.<this>.')
param environmentDefaultDomain string

@description('ACR login server (e.g. skyrictbeta.azurecr.io).')
param acrLoginServer string

@description('Resource ID of the user-assigned identity used for ACR pull + Key Vault. Key Vault secret references need the RESOURCE ID, not the client ID - see sharedSecrets below.')
param uamiId string

@description('Key Vault URI used to build secret references (e.g. https://kv-skyrict-beta.vault.azure.net/).')
param kvUri string

@description('Image tag for all three services (git SHA from CD).')
param imageTag string

@description('Application ENVIRONMENT value - one of the four app enum values, staging for beta.')
@allowed([
  'dev'
  'test'
  'staging'
  'production'
])
param appEnvironment string = 'staging'

@description('PostgreSQL server FQDN from the data module.')
param postgresFqdn string

@description('PostgreSQL administrator login.')
param postgresLogin string

@description('Name of the shared application database.')
param postgresDbName string

@secure()
@description('PostgreSQL administrator password - used only to build the database-url secret.')
param postgresPassword string

@description('Managed Azure Redis is deployed for month 1 (true = build URL from listKeys, false = use redisUrlOverride).')
param deployManagedRedis bool = true

@description('Azure Redis name (when deployManagedRedis).')
param redisName string = ''

@description('Azure Redis resource ID (when deployManagedRedis).')
param redisId string = ''

@secure()
@description('Redis connection URL override (Upstash Serverless Redis after the month-1 swap). Required when deployManagedRedis=false.')
param redisUrlOverride string = ''

@description('Explicit CORS origins for all three services (JSON array string). Never "*".')
param corsOrigins array = []

@description('Trusted proxy CIDRs (VNet prefix) - used for real client IP extraction.')
param trustedProxies array = ['10.16.0.0/16']

@description('BASE_DOMAIN required by every service in staging/production.')
param baseDomain string

@description('JWT issuer claim shared by identity/core/ai-agent.')
param jwksIssuer string

@description('JWT audience claim shared by identity/core/ai-agent.')
param jwksAudience string

@description('The single public API hostname (e.g. api.skyrict.in). Served by the gateway once customDomainStage is "hostname" or "certificate". Empty serves only the generated FQDN.')
param apiHostname string = ''

@description('How far to take the gateway custom domain. "none" (default) serves only the generated FQDN. "hostname" registers apiHostname with bindingType Disabled and no certificateId, which is the first of the two applies ACA requires. "certificate" then creates the managed certificate and rebinds the hostname SniEnabled against it. The two cannot be combined into one apply: ACA rejects a managed certificate for a hostname not already registered on the app (RequireCustomHostnameInEnvironment), and the customDomains entry references that same certificate. Ignored when apiHostname is empty. See docs/runbooks/azure-iac.md section 11.')
param customDomainStage string = 'none'

@description('Cloudflare Turnstile site key. Public by design - it is rendered into the sign-up page, so it stays a plain app-config value and is not a secret.')
param turnstileSiteKey string = ''

@description('True when the CD workflow has written the "turnstile-secret-key" secret into Key Vault. Guards the secretRef: a secretRef pointing at a secret that was never provisioned makes the container fail to start, so the reference must not be emitted at all when the value is absent.')
param turnstileSecretConfigured bool = false

@description('Keep identity and core at minReplicas 1 instead of scaling to zero. The gateway fronts them, so a cold backend is a cold public API.')
param keepBackendsWarm bool = true

@description('Max replicas for the gateway. Sized by concurrent long-lived streams rather than by request rate - see the comment on gatewayConcurrentRequests.')
param gatewayMaxReplicas int = 3

@description('Concurrent requests per gateway replica before ACA scales it out. Deliberately far higher than the backends` concurrentRequests: one open agent chat is a single in-flight HTTP request that occupies a connection for the whole turn, so a backend-shaped threshold here would scale the gateway out on chat traffic alone.')
param gatewayConcurrentRequests int = 500

@description('Max replicas per app (scale-to-zero from minReplicas 0).')
param maxReplicas int = 2

@description('Per-container CPU (vCPU) - Consumption profile.')
param containerCpu string = '0.25'

@description('Per-container memory - Consumption profile.')
param containerMemory string = '0.5Gi'

@description('Max concurrent HTTP requests per replica before scaling out.')
param concurrentRequests int = 100

@description('DB connection pool size per replica - lowered for the B1ms free tier.')
param dbPoolSize int = 3

@description('DB connection pool max overflow - 0 keeps B1ms headroom.')
param dbMaxOverflow int = 0

var allTags = union(
  {
    environment: envName
    service: prefix
    managedBy: 'bicep'
  },
  tags
)

var resourceName = '${prefix}-${envName}'
var dbUrl = 'postgresql+asyncpg://${postgresLogin}:${postgresPassword}@${postgresFqdn}:5432/${postgresDbName}?ssl=require'
var redisUrl = deployManagedRedis
  ? 'rediss://:${listKeys(redisId, '2023-08-01').primaryKey}@${redisName}.redis.cache.windows.net:6380/0'
  : redisUrlOverride

// ---------------------------------------------------------------------------
// Public API origin
//
// Azure Container Apps ingress is host-based and cannot route on path, so the
// /api/v1/* -> identity|core split is done by the nginx gateway. Under the
// single-origin design the gateway is the ONLY externally-reachable app:
// identity and core set external: false below and are reachable solely through
// it. That is what makes one hostname possible, and it is also what stops a
// second, unmediated entry point existing alongside the audited one.
// ---------------------------------------------------------------------------

var identityAppName = 'app-identity-${resourceName}'
var coreAppName = 'app-core-${resourceName}'
var aiAgentAppName = 'app-ai-agent-${resourceName}'
var gatewayAppName = 'app-gateway-${resourceName}'

// ACA's internal DNS name for an app in the same environment.
//
// The FQDN is '<appName>.internal.<defaultDomain>'. defaultDomain is a value
// Azure GENERATES for the environment (skyrict-beta currently resolves to
// bluesky-957ace7a.westus.azurecontainerapps.io) and it is not derivable from
// any input this template has, so it is passed in as a parameter from the
// environment module's `cae.properties.defaultDomain` output. Do not rebuild it
// from environmentName: that produced
//   app-identity-skyrict-beta.cae-skyrict-beta.azurecontainerapps.io
// which is wrong twice over - the domain is generated, not the environment's
// resource name, and the internal form carries an `internal` label. Neither
// variant resolves, so the gateway reached nothing and the failure was invisible
// in the resource state.
//
// The gateway is given the full internal FQDNs rather than the short aliases:
// short names are a documented convenience of the DEFAULT environment only and
// are not registered in a VNet-integrated environment like this one. The FQDN is
// also what ACA's internal ingress matches on, so it is the value that has to
// appear in the Host header.
//
// No port suffix. For HTTP ingress the ACA endpoint is always 443, and 80 as
// well once allowInsecure is true - never the container's own targetPort.
// targetPort is where ingress forwards TO, not a port ingress listens on, so
// ':8000' connected to nothing.
var identityInternalFqdn = '${identityAppName}.internal.${environmentDefaultDomain}'
var coreInternalFqdn = '${coreAppName}.internal.${environmentDefaultDomain}'
var aiAgentInternalFqdn = '${aiAgentAppName}.internal.${environmentDefaultDomain}'

// The certificate and the custom-domain entry cannot be created in the same
// deployment. ACA refuses a managed certificate for a hostname that is not
// already registered on a container app:
//   RequireCustomHostnameInEnvironment: Creating managed certificate requires
//   hostname 'api.skyrict.in' added as a custom hostname to a container app...
// and the customDomains entry references that same certificate, so a single
// template cannot satisfy both halves.
//
// customDomainStage splits it into two applies of the SAME template:
//   'none'       - no custom domain, gateway serves only its generated FQDN
//   'hostname'   - registers apiHostname with bindingType 'Disabled' and NO
//                  certificateId. The 2026-01-01 CustomDomain type requires only
//                  'name', and 'Disabled' is a legal BindingType, so this
//                  registers the hostname without binding anything to it.
//   'certificate'- additionally creates the managed certificate and rebinds the
//                  same hostname SniEnabled against it.
//
// Both non-default stages are gated on apiHostname being non-empty, so an
// environment without a custom domain still deploys and stays reachable on its
// generated FQDN. Unknown values fall back to 'none' rather than throwing: a
// typo in a parameters file must not be able to take the gateway's ingress down.
var customDomainStageEffective = empty(apiHostname)
  ? 'none'
  : (customDomainStage == 'hostname' || customDomainStage == 'certificate' ? customDomainStage : 'none')

// Only the 'certificate' stage creates the certificate. At 'hostname' there must
// be no managedCertificates resource in the deployment at all, or it is rejected
// with RequireCustomHostnameInEnvironment.
var enableManagedCertificate = customDomainStageEffective == 'certificate'

// The hostname is registered from 'hostname' onward, and only bound to the
// certificate at 'certificate'.
var registerCustomHostname = customDomainStageEffective == 'hostname' || enableManagedCertificate

var managedCertificateName = 'env-cert-${resourceName}'

// ---------------------------------------------------------------------------
// Shared ACA secrets (all apps/jobs declare the same set)
//
// `identity` on a keyVaultUrl secret is the managed identity's ARM RESOURCE ID,
// not its client ID. ACA looks the value up as a resource ID and fails the
// revision with "Managed identity with resource ID '<guid>' was not found" when
// handed a client ID - the two are both bare GUIDs, so the mistake is silent in
// review and only surfaces at provisioning time.
//
// Proven, not assumed: two otherwise-identical container apps were created in
// the beta environment against the same Key Vault secret, differing only in this
// field. Client ID -> Failed. Resource ID -> Succeeded.
// ---------------------------------------------------------------------------

var sharedSecrets = [
  {
    name: 'database-url'
    value: dbUrl
  }
  {
    name: 'redis-url'
    value: redisUrl
  }
  {
    name: 'jwt-private-key'
    keyVaultUrl: '${kvUri}secrets/jwt-private-key'
    identity: uamiId
  }
  {
    name: 'jwt-public-key'
    keyVaultUrl: '${kvUri}secrets/jwt-public-key'
    identity: uamiId
  }
  {
    name: 'mfa-encryption-key'
    keyVaultUrl: '${kvUri}secrets/mfa-encryption-key'
    identity: uamiId
  }
  {
    name: 'sync-token'
    keyVaultUrl: '${kvUri}secrets/sync-token'
    identity: uamiId
  }
  {
    name: 'ingest-token'
    keyVaultUrl: '${kvUri}secrets/ingest-token'
    identity: uamiId
  }
  // Present ONLY when the CD actually wrote the secret. Two failure modes make
  // this conditional rather than unconditional:
  //
  //  - Absent name: the identity app's env references 'turnstile-secret-key' by
  //    secretRef, and a secretRef whose name is not in this list fails the whole
  //    app with ContainerAppSecretRefNotFound.
  //  - Present but empty: identity would read a blank credential and reject
  //    every self-service signup, which is exactly what the gate on
  //    turnstileSecretConfigured exists to prevent.
  //
  // Absent is therefore the only honest encoding of "not provisioned".
  ...(turnstileSecretConfigured
    ? [
        {
          name: 'turnstile-secret-key'
          keyVaultUrl: '${kvUri}secrets/turnstile-secret-key'
          identity: uamiId
        }
      ]
    : [])
]

// ---------------------------------------------------------------------------
// Secret volumes - the services read PEM key files at settings-load time
// ---------------------------------------------------------------------------

var jwtVolumeIdentity = {
  name: 'jwtkeys'
  storageType: 'Secret'
  secrets: [
    {
      secretRef: 'jwt-private-key'
      path: 'jwt-private.pem'
    }
    {
      secretRef: 'jwt-public-key'
      path: 'jwt-public.pem'
    }
  ]
}

var jwtVolumePublic = {
  name: 'jwtkeys'
  storageType: 'Secret'
  secrets: [
    {
      secretRef: 'jwt-public-key'
      path: 'jwt-public.pem'
    }
  ]
}

// ---------------------------------------------------------------------------
// identity - external, :8000
// ---------------------------------------------------------------------------

resource identityApp 'Microsoft.App/containerApps@2026-01-01' = if (deployApps) {
  name: identityAppName
  location: location
  tags: allTags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${uamiId}': {}
    }
  }
  properties: {
    environmentId: caeId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        // Internal only. The gateway is the single public entry point for the
        // API; leaving identity externally reachable as well would create a
        // second origin with no CORS gateway, no tenant-host enforcement and no
        // route map in front of it.
        external: false
        targetPort: 8000
        transport: 'http'
        // Insecure allowed, and it costs nothing in exposure: external: false
        // means this ingress is not reachable from the internet at all, so the
        // only clients are the gateway and ai-agent inside the same environment.
        // ACA's default (false) redirects plain HTTP on port 80 to HTTPS on 443,
        // and neither nginx nor httpx follows a redirect it receives from an
        // upstream - so every gateway call came back as a redirect to the browser
        // instead of a response from the API. The hop never leaves the
        // environment, so terminating TLS on it would add cost and CPU for
        // nothing.
        allowInsecure: true
        traffic: [
          {
            latestRevision: true
            weight: 100
          }
        ]
      }
      registries: [
        {
          server: acrLoginServer
          identity: uamiId
        }
      ]
      maxInactiveRevisions: 5
      secrets: sharedSecrets
    }
    template: {
      containers: [
        {
          image: '${acrLoginServer}/identity:${imageTag}'
          name: 'identity'
          volumeMounts: [
            {
              volumeName: 'jwtkeys'
              mountPath: '/secrets'
            }
          ]
          resources: {
            cpu: json(containerCpu)
            memory: containerMemory
          }
          env: [
            {
              name: 'IDENTITY_ENVIRONMENT'
              value: appEnvironment
            }
            {
              name: 'IDENTITY_DATABASE_URL'
              secretRef: 'database-url'
            }
            {
              name: 'IDENTITY_REDIS_URL'
              secretRef: 'redis-url'
            }
            {
              name: 'IDENTITY_JWT_PRIVATE_KEY_PATH'
              value: '/secrets/jwt-private.pem'
            }
            {
              name: 'IDENTITY_JWT_PUBLIC_KEY_PATH'
              value: '/secrets/jwt-public.pem'
            }
            {
              name: 'IDENTITY_MFA_ENCRYPTION_KEY'
              secretRef: 'mfa-encryption-key'
            }
            {
              name: 'IDENTITY_JWKS_ISSUER'
              value: jwksIssuer
            }
            {
              name: 'IDENTITY_JWKS_AUDIENCE'
              value: jwksAudience
            }
            {
              name: 'IDENTITY_CORS_ORIGINS'
              value: string(corsOrigins)
            }
            {
              name: 'IDENTITY_TRUSTED_PROXIES'
              value: string(trustedProxies)
            }
            {
              name: 'IDENTITY_BASE_DOMAIN'
              value: baseDomain
            }
            {
              name: 'IDENTITY_DB_POOL_SIZE'
              value: string(dbPoolSize)
            }
            {
              name: 'IDENTITY_DB_MAX_OVERFLOW'
              value: string(dbMaxOverflow)
            }
            {
              // Public by design: the site key is rendered into the sign-up page
              // for the browser to execute, so it cannot be a secret. It is
              // useless on its own - the server-side secret below is what makes
              // the challenge verifiable.
              name: 'IDENTITY_TURNSTILE_SITE_KEY'
              value: turnstileSiteKey
            }
            // The secret is a Key Vault reference, not a literal.
            //
            // A literal would sit in the container app's configuration, readable
            // by anyone holding Reader on the app and visible in `az containerapp
            // show` output. The reference is resolved at runtime by the app's
            // user-assigned identity, which already holds Key Vault Secrets User
            // (see security.bicep).
            //
            // Spread rather than a conditional value: a secretRef to a secret
            // that does not exist makes the container fail to START, so the
            // entry must be absent entirely - not present-and-empty - whenever
            // the value was never provisioned.
            ...(turnstileSecretConfigured
              ? [
                  {
                    name: 'IDENTITY_TURNSTILE_SECRET_KEY'
                    secretRef: 'turnstile-secret-key'
                  }
                ]
              : [])
          ]
          probes: [
            {
              // /api/v1/ready, NOT /api/v1/health.
              //
              // The two are deliberately different. /health is liveness - "this
              // process is up", with no dependency checks at all, so it answers
              // 200 the moment uvicorn binds the socket. /ready is 503 until the
              // lifespan has verified every required dependency (Postgres, and
              // whatever else the service needs to serve traffic at all).
              //
              // Probing /health here meant a replica that booted with a broken
              // database connection was declared ready and put in rotation, so
              // the failure surfaced as 502/500 under real load - during exactly
              // the rollout where nobody is watching. Readiness has to be the
              // endpoint that reflects the ability to serve.
              type: 'Readiness'
              httpGet: {
                path: '/api/v1/ready'
                port: 8000
              }
              initialDelaySeconds: 5
              periodSeconds: 10
              failureThreshold: 3
            }
            {
              // Liveness stays on /health on purpose. If liveness depended on
              // the database, a database blip would fail the probe and ACA would
              // restart-loop every replica - turning a recoverable dependency
              // outage into a total crash. Restart the process only when the
              // process itself is broken.
              type: 'Liveness'
              httpGet: {
                path: '/api/v1/health'
                port: 8000
              }
              initialDelaySeconds: 20
              periodSeconds: 30
              failureThreshold: 5
            }
          ]
        }
      ]
      scale: {
        // minReplicas 1 rather than 0. The gateway fronts identity and core, so
        // a scale-to-zero backend is a cold PUBLIC api: the first request after
        // an idle period pays a cold start that can outlast the gateway's own
        // probe timeouts, and /readyz reports the whole origin unhealthy while
        // it happens. ai-agent is the same argument one hop further out - core
        // calls it synchronously, so a cold ai-agent adds cold-start latency to
        // the first AI turn of every session rather than just the first request.
        //
        // Set keepBackendsWarm=false to restore scale-to-zero. Do that only for a
        // throwaway environment: the managed certificate for apiHostname also
        // needs a running replica to complete domain validation, so a scaled-to-
        // zero environment cannot have its certificate issued.
        minReplicas: keepBackendsWarm ? 1 : 0
        maxReplicas: maxReplicas
        rules: [
          {
            name: 'http-scale'
            http: {
              metadata: {
                concurrentRequests: string(concurrentRequests)
              }
            }
          }
        ]
      }
      volumes: [jwtVolumeIdentity]
    }
  }
}

// ---------------------------------------------------------------------------
// core - internal only, :8001. Reached exclusively through the gateway.
// ---------------------------------------------------------------------------

resource coreApp 'Microsoft.App/containerApps@2026-01-01' = if (deployApps) {
  name: coreAppName
  location: location
  tags: allTags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${uamiId}': {}
    }
  }
  properties: {
    environmentId: caeId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        // Internal only, for the same reason as identity: one public origin,
        // one place where the route map and the tenant contract are enforced.
        external: false
        targetPort: 8001
        transport: 'http'
        // See the identity app: internal-only ingress plus a plain-HTTP caller
        // is exactly the case ACA's allowInsecure: false default breaks.
        allowInsecure: true
        traffic: [
          {
            latestRevision: true
            weight: 100
          }
        ]
      }
      registries: [
        {
          server: acrLoginServer
          identity: uamiId
        }
      ]
      maxInactiveRevisions: 5
      secrets: sharedSecrets
    }
    template: {
      containers: [
        {
          image: '${acrLoginServer}/core:${imageTag}'
          name: 'core'
          volumeMounts: [
            {
              volumeName: 'jwtkeys'
              mountPath: '/secrets'
            }
          ]
          resources: {
            cpu: json(containerCpu)
            memory: containerMemory
          }
          env: [
            {
              name: 'CORE_ENVIRONMENT'
              value: appEnvironment
            }
            {
              name: 'CORE_DATABASE_URL'
              secretRef: 'database-url'
            }
            {
              name: 'CORE_JWT_PUBLIC_KEY_PATH'
              value: '/secrets/jwt-public.pem'
            }
            {
              name: 'CORE_JWKS_ISSUER'
              value: jwksIssuer
            }
            {
              name: 'CORE_JWKS_AUDIENCE'
              value: jwksAudience
            }
            {
              name: 'CORE_CORS_ORIGINS'
              value: string(corsOrigins)
            }
            {
              name: 'CORE_BASE_DOMAIN'
              value: baseDomain
            }
            {
              name: 'CORE_AI_AGENT_URL'
              // Full internal FQDN, no port - see identityInternalFqdn. The short
              // form was used here to dodge a Bicep cycle, but there is no cycle:
              // both apps are declared in this one module and only depend on the
              // environment. Short-name resolution is a convenience of the
              // default environment and is not registered in a VNet-integrated
              // environment, so the short form does not resolve and core's agent
              // calls fail at runtime.
              value: 'http://${aiAgentInternalFqdn}'
            }
            {
              name: 'CORE_AI_SYNC_TOKEN'
              secretRef: 'sync-token'
            }
            {
              name: 'CORE_AI_INGEST_TOKEN'
              secretRef: 'ingest-token'
            }
            {
              name: 'CORE_DB_POOL_SIZE'
              value: string(dbPoolSize)
            }
            {
              name: 'CORE_DB_MAX_OVERFLOW'
              value: string(dbMaxOverflow)
            }
          ]
          probes: [
            {
              // /api/v1/ready, NOT /api/v1/health - see the identical block on
              // identity for why. A replica with a broken database must not be
              // declared ready.
              type: 'Readiness'
              httpGet: {
                path: '/api/v1/ready'
                port: 8001
              }
              initialDelaySeconds: 5
              periodSeconds: 10
              failureThreshold: 3
            }
            {
              type: 'Liveness'
              httpGet: {
                path: '/api/v1/health'
                port: 8001
              }
              initialDelaySeconds: 20
              periodSeconds: 30
              failureThreshold: 5
            }
          ]
        }
      ]
      scale: {
        // minReplicas 1 rather than 0. The gateway fronts identity and core, so
        // a scale-to-zero backend is a cold PUBLIC api: the first request after
        // an idle period pays a cold start that can outlast the gateway's own
        // probe timeouts, and /readyz reports the whole origin unhealthy while
        // it happens. ai-agent is the same argument one hop further out - core
        // calls it synchronously, so a cold ai-agent adds cold-start latency to
        // the first AI turn of every session rather than just the first request.
        //
        // Set keepBackendsWarm=false to restore scale-to-zero. Do that only for a
        // throwaway environment: the managed certificate for apiHostname also
        // needs a running replica to complete domain validation, so a scaled-to-
        // zero environment cannot have its certificate issued.
        minReplicas: keepBackendsWarm ? 1 : 0
        maxReplicas: maxReplicas
        rules: [
          {
            name: 'http-scale'
            http: {
              metadata: {
                concurrentRequests: string(concurrentRequests)
              }
            }
          }
        ]
      }
      volumes: [jwtVolumePublic]
    }
  }
}

// ---------------------------------------------------------------------------
// ai-agent - INTERNAL only, :8000
// ---------------------------------------------------------------------------

resource aiAgentApp 'Microsoft.App/containerApps@2026-01-01' = if (deployApps) {
  name: aiAgentAppName
  location: location
  tags: allTags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${uamiId}': {}
    }
  }
  properties: {
    environmentId: caeId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        // ai-agent is internal-only: it is not in the gateway's public route map
        // and is called by core over the environment's internal network only.
        external: false
        targetPort: 8000
        transport: 'http'
        // See the identity app: internal-only ingress plus a plain-HTTP caller
        // is exactly the case ACA's allowInsecure: false default breaks.
        allowInsecure: true
        traffic: [
          {
            latestRevision: true
            weight: 100
          }
        ]
      }
      registries: [
        {
          server: acrLoginServer
          identity: uamiId
        }
      ]
      maxInactiveRevisions: 5
      secrets: sharedSecrets
    }
    template: {
      containers: [
        {
          image: '${acrLoginServer}/ai-agent:${imageTag}'
          name: 'ai-agent'
          volumeMounts: [
            {
              volumeName: 'jwtkeys'
              mountPath: '/secrets'
            }
          ]
          resources: {
            cpu: json(containerCpu)
            memory: containerMemory
          }
          env: [
            {
              name: 'AI_ENVIRONMENT'
              value: appEnvironment
            }
            {
              name: 'AI_DATABASE_URL'
              secretRef: 'database-url'
            }
            {
              name: 'AI_REDIS_URL'
              secretRef: 'redis-url'
            }
            {
              name: 'AI_JWT_PUBLIC_KEY_PATH'
              value: '/secrets/jwt-public.pem'
            }
            {
              name: 'AI_JWKS_ISSUER'
              value: jwksIssuer
            }
            {
              name: 'AI_JWKS_AUDIENCE'
              value: jwksAudience
            }
            {
              name: 'AI_CORS_ORIGINS'
              value: string(corsOrigins)
            }
            {
              name: 'AI_BASE_DOMAIN'
              value: baseDomain
            }
            {
              // Full internal FQDN, no port - see identityInternalFqdn. The
              // short form does not resolve in a VNet-integrated environment.
              name: 'AI_INVENTORY_SERVICE_URL'
              value: 'http://${coreInternalFqdn}'
            }
            {
              name: 'AI_REPORT_SERVICE_URL'
              value: 'http://${coreInternalFqdn}'
            }
            {
              name: 'AI_CORE_DOCUMENT_URL'
              value: 'http://${coreInternalFqdn}'
            }
            {
              name: 'AI_INGEST_TOKEN'
              secretRef: 'ingest-token'
            }
            {
              name: 'AI_INVENTORY_SYNC_TOKEN'
              secretRef: 'sync-token'
            }
            {
              name: 'AI_DOCUMENT_SYNC_TOKEN'
              secretRef: 'sync-token'
            }
            {
              name: 'AI_DB_POOL_SIZE'
              value: string(dbPoolSize)
            }
            {
              name: 'AI_DB_MAX_OVERFLOW'
              value: string(dbMaxOverflow)
            }
          ]
          probes: [
            {
              // /api/v1/ready, NOT /api/v1/health.
              //
              // The two are deliberately different. /health is liveness - "this
              // process is up", with no dependency checks at all, so it answers
              // 200 the moment uvicorn binds the socket. /ready is 503 until the
              // lifespan has verified every required dependency (Postgres, and
              // whatever else the service needs to serve traffic at all).
              //
              // Probing /health here meant a replica that booted with a broken
              // database connection was declared ready and put in rotation, so
              // the failure surfaced as 502/500 under real load - during exactly
              // the rollout where nobody is watching. Readiness has to be the
              // endpoint that reflects the ability to serve.
              type: 'Readiness'
              httpGet: {
                path: '/api/v1/ready'
                port: 8000
              }
              initialDelaySeconds: 5
              periodSeconds: 10
              failureThreshold: 3
            }
            {
              // Liveness stays on /health on purpose. If liveness depended on
              // the database, a database blip would fail the probe and ACA would
              // restart-loop every replica - turning a recoverable dependency
              // outage into a total crash. Restart the process only when the
              // process itself is broken.
              type: 'Liveness'
              httpGet: {
                path: '/api/v1/health'
                port: 8000
              }
              initialDelaySeconds: 20
              periodSeconds: 30
              failureThreshold: 5
            }
          ]
        }
      ]
      scale: {
        // minReplicas 1 rather than 0. The gateway fronts identity and core, so
        // a scale-to-zero backend is a cold PUBLIC api: the first request after
        // an idle period pays a cold start that can outlast the gateway's own
        // probe timeouts, and /readyz reports the whole origin unhealthy while
        // it happens. ai-agent is the same argument one hop further out - core
        // calls it synchronously, so a cold ai-agent adds cold-start latency to
        // the first AI turn of every session rather than just the first request.
        //
        // Set keepBackendsWarm=false to restore scale-to-zero. Do that only for a
        // throwaway environment: the managed certificate for apiHostname also
        // needs a running replica to complete domain validation, so a scaled-to-
        // zero environment cannot have its certificate issued.
        minReplicas: keepBackendsWarm ? 1 : 0
        maxReplicas: maxReplicas
        rules: [
          {
            name: 'http-scale'
            http: {
              metadata: {
                concurrentRequests: string(concurrentRequests)
              }
            }
          }
        ]
      }
      volumes: [jwtVolumePublic]
    }
  }
}

// ---------------------------------------------------------------------------
// gateway - the single public API origin (api.skyrict.in), :8080
// ---------------------------------------------------------------------------

// Declared `existing` so the managed certificate can be created as a child of
// the environment. The managedCertificates resource lives at environment scope,
// not under the container app, so it cannot be nested inside gatewayApp.
resource containerEnv 'Microsoft.App/managedEnvironments@2026-01-01' existing = {
  name: environmentName
}

// ACA issues and renews this certificate automatically once the domain
// validates. It is a prerequisite for the custom domain below, which is why the
// gateway depends on it: binding a customDomain whose certificateId does not
// exist yet is rejected outright.
//
// The resource DOES carry a location. It is a child of the environment, but
// unlike an ordinary child resource it does not inherit one: deploying without
// it fails the whole nested `apps` deployment with
//   LocationRequired: The location property is required for this definition.
// The BCP035 linter warning that used to be suppressed here was a TRUE
// positive, and the comment claiming ACA rejects a location on this resource
// was simply wrong - it cost a full CD cycle to disprove, so do not reinstate
// it.
//
// Guarded by customDomainStage reaching 'certificate', which also requires
// apiHostname to be non-empty. ACA requires the hostname to already be
// registered on a container app before a certificate can exist for it:
//   RequireCustomHostnameInEnvironment: Creating managed certificate requires
//   hostname 'api.skyrict.in' added as a custom hostname to a container app...
// Reproduced against the live beta environment with no hostname registered, so
// this is a verified ACA behaviour, not a precaution. That is what makes the
// stage split above necessary: the 'hostname' apply must emit this resource
// NOTHING, or it is rejected. In phase 1 the gateway does not exist yet, so an
// unguarded certificate would also fail the deployment there and nothing
// downstream could run.
//
// No subjectAlternativeNames either: ManagedCertificateProperties in this API
// version does not accept it, and a single-name certificate does not need one.
// The corollary is that this must stay a SINGLE-level subdomain - api.skyrict.in
// is fine, but a.b.skyrict.in would need a SAN, and a *.skyrict.in wildcard
// would not cover a second level, which is also why digicert's validation check
// fails against the intermediate CNAMEs a multi-level name requires.
resource gatewayCert 'Microsoft.App/managedEnvironments/managedCertificates@2026-01-01' = if (enableManagedCertificate) {
  parent: containerEnv
  name: managedCertificateName
  location: location
  properties: {
    subjectName: apiHostname
    // Must be stated explicitly. Left unset, ACA does not default to one of
    // its own methods and the deployment is rejected with
    //   InvalidValidationMethod: Invalid validation method for domain
    //   'api.skyrict.in'. Supported: CNAME, HTTP, TXT.
    //
    // CNAME is satisfied by the registrar CNAME that already points
    // api.skyrict.in at the gateway's generated FQDN, so it issues with no
    // further record to add. Confirmed live: the certificate for api.skyrict.in
    // reached provisioningState Succeeded on that CNAME alone. Until it
    // validates the certificate stays Pending, which does NOT fail the
    // deployment - the app stays reachable on its generated FQDN meanwhile.
    //
    // The property is `domainControlValidation`, not `validationMethod`. The
    // latter is not a member of ManagedCertificateProperties in this API
    // version, and bicep reports that as a BCP037 warning while STILL emitting
    // the key into the compiled ARM - so the resource deploys with an
    // unrecognised property and the failure only appears as a provisioning
    // error at apply time. Caught by `bicep build` and fixed here.
    domainControlValidation: 'CNAME'
  }
}

resource gatewayApp 'Microsoft.App/containerApps@2026-01-01' = if (deployApps) {
  name: gatewayAppName
  location: location
  tags: allTags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${uamiId}': {}
    }
  }
  // gatewayCert is not listed: referencing gatewayCert.id in customDomains
  // already creates the dependency, and Bicep's no-unnecessary-dependson rule
  // flags an explicit entry as redundant. identityApp and coreApp are listed
  // because the dependency on them is by name only - nothing in the gateway's
  // properties references them, they are baked into string values.
  dependsOn: [
    identityApp
    coreApp
  ]
  properties: {
    environmentId: caeId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8080
        transport: 'http'
        // No allowInsecure. The managed certificate is a real TLS certificate,
        // and ACA will not issue or renew it for a hostname that still accepts
        // plaintext on the same app.
        allowInsecure: false
        // Present only when apiHostname is set, so an environment without a
        // custom domain still deploys and is reachable on its generated FQDN.
        // Bicep omits the property when the value is an empty array, which is
        // what an env without a domain should do.
        // At 'hostname' the entry carries bindingType 'Disabled' and NO
        // certificateId - that is what registers the name on the app so the
        // next apply is allowed to create the certificate for it. Referencing
        // gatewayCert.id here at that stage would put the certificate back in
        // the same deployment and reintroduce RequireCustomHostnameInEnvironment.
        // certificateId is genuinely optional on the 2026-01-01 CustomDomain
        // type (only 'name' is required) and 'Disabled' is a legal BindingType,
        // both verified against the published Microsoft.App 2026-01-01 schema.
        customDomains: registerCustomHostname
          ? enableManagedCertificate
              ? [
                  {
                    name: apiHostname
                    bindingType: 'SniEnabled'
                    certificateId: gatewayCert.id
                  }
                ]
              : [
                  {
                    name: apiHostname
                    bindingType: 'Disabled'
                  }
                ]
          : []
        traffic: [
          {
            latestRevision: true
            weight: 100
          }
        ]
      }
      registries: [
        {
          server: acrLoginServer
          identity: uamiId
        }
      ]
      maxInactiveRevisions: 5
    }
    template: {
      containers: [
        {
          image: '${acrLoginServer}/gateway:${imageTag}'
          name: 'gateway'
          resources: {
            cpu: json(containerCpu)
            memory: containerMemory
          }
          env: [
            // Full internal FQDNs, not the short aliases - see the comment on
            // identityInternalFqdn. No port: the ACA endpoint is 443 (or 80 with
            // allowInsecure), never the container's targetPort.
            //
            // Two reasons, both load-bearing. ACA's internal ingress matches the
            // Host header against the target app's FQDN, and the gateway sends
            // that name in Host (see the gateway.conf template) - an alias that
            // ACA does not recognise as a routable host produces a 404 from
            // ACA itself, not from the backend. And the entrypoint validates
            // these values, so a typo fails the container at boot with a named
            // error instead of 502ing every request.
            //
            // http:// rather than https:// because the backends are internal-only
            // (external: false, so unreachable from the internet) and have
            // allowInsecure: true, which is what keeps ACA serving plain HTTP on
            // port 80 here instead of redirecting to 443. nginx does not follow
            // a redirect it receives from an upstream, so an http:// call to an
            // app with allowInsecure: false hands the browser a 301 and the
            // request dies at the gateway.
            {
              name: 'SKYRRICT_IDENTITY_BACKEND'
              value: 'http://${identityInternalFqdn}'
            }
            {
              name: 'SKYRRICT_IDENTITY_HOST'
              value: identityInternalFqdn
            }
            {
              name: 'SKYRRICT_CORE_BACKEND'
              value: 'http://${coreInternalFqdn}'
            }
            {
              name: 'SKYRRICT_CORE_HOST'
              value: coreInternalFqdn
            }
          ]
          probes: [
            {
              // Readiness proxies a real request to each backend, so the gateway
              // only stays in rotation when the API can actually be served. The
              // backends' own probes report their failures separately, so this
              // cannot mask a single backend being down.
              type: 'Readiness'
              httpGet: {
                path: '/readyz'
                port: 8080
              }
              initialDelaySeconds: 3
              periodSeconds: 10
              failureThreshold: 3
            }
            {
              // Liveness is nginx's own health and never touches a backend. If
              // it did, a core rollout would fail the gateway's liveness and
              // ACA would restart-loop the gateway instead of waiting for core.
              type: 'Liveness'
              httpGet: {
                path: '/healthz'
                port: 8080
              }
              initialDelaySeconds: 10
              periodSeconds: 30
              failureThreshold: 5
            }
          ]
        }
      ]
      scale: {
        // The gateway is stateless, so replicas are interchangeable and ACA can
        // spread them. Unlike the backends there is nothing to warm up - a new
        // replica only has to parse its config, which the entrypoint does before
        // exec'ing nginx - so there is no cold-start reason to run only one.
        minReplicas: 1
        maxReplicas: gatewayMaxReplicas
        rules: [
          {
            name: 'http-scale'
            http: {
              metadata: {
                concurrentRequests: string(gatewayConcurrentRequests)
              }
            }
          }
        ]
      }
    }
  }
}

// ---------------------------------------------------------------------------
// db-init job - creates the shared database + extensions (idempotent)
//
// vector, pg_trgm and pgcrypto. pgcrypto is here because two of the three
// migrations create it (identity 0001, core 0010) to back the tamper-evident
// audit hash chain, so creating it here fails the job whose name says
// 'db-init' rather than failing midway through a service's first migration.
// ON_ERROR_STOP=1 is what makes that difference: without it psql reports
// success for a statement that failed.
// ---------------------------------------------------------------------------

var dbInitScript = '''
set -euo pipefail
if ! psql -v ON_ERROR_STOP=1 -tAc "SELECT 1 FROM pg_database WHERE datname = '$SKYRICT_DB'" | grep -q 1; then
  psql -v ON_ERROR_STOP=1 -c "CREATE DATABASE $SKYRICT_DB"
fi
psql -d $SKYRICT_DB -v ON_ERROR_STOP=1 -c "CREATE EXTENSION IF NOT EXISTS vector"
psql -d $SKYRICT_DB -v ON_ERROR_STOP=1 -c "CREATE EXTENSION IF NOT EXISTS pg_trgm"
psql -d $SKYRICT_DB -v ON_ERROR_STOP=1 -c "CREATE EXTENSION IF NOT EXISTS pgcrypto"
'''

resource dbInitJob 'Microsoft.App/jobs@2026-01-01' = if (deployWorkloads) {
  name: 'job-db-init-${resourceName}'
  location: location
  tags: allTags
  properties: {
    environmentId: caeId
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 300
      replicaRetryLimit: 2
      secrets: [
        {
          name: 'postgres-password'
          value: postgresPassword
        }
      ]
    }
    template: {
      containers: [
        {
          image: 'postgres:16-alpine'
          name: 'db-init'
          command: [
            '/bin/sh'
            '-c'
            dbInitScript
          ]
          env: [
            {
              name: 'PGHOST'
              value: postgresFqdn
            }
            {
              name: 'PGUSER'
              value: postgresLogin
            }
            {
              name: 'PGPASSWORD'
              secretRef: 'postgres-password'
            }
            {
              name: 'PGDATABASE'
              value: 'postgres'
            }
            {
              name: 'PGSSLMODE'
              value: 'require'
            }
            {
              name: 'SKYRICT_DB'
              value: postgresDbName
            }
          ]
          resources: {
            cpu: json(containerCpu)
            memory: containerMemory
          }
        }
      ]
    }
  }
}

// ---------------------------------------------------------------------------
// Migration jobs - one-shot, run by CD in this order: identity -> core -> ai
// ---------------------------------------------------------------------------

resource identityMigrateJob 'Microsoft.App/jobs@2026-01-01' = if (deployWorkloads) {
  name: 'job-identity-${resourceName}'
  location: location
  tags: allTags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${uamiId}': {}
    }
  }
  properties: {
    environmentId: caeId
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 600
      replicaRetryLimit: 2
      registries: [
        {
          server: acrLoginServer
          identity: uamiId
        }
      ]
      secrets: sharedSecrets
    }
    template: {
      containers: [
        {
          image: '${acrLoginServer}/identity:${imageTag}'
          name: 'migrate'
          // The `cd` is load-bearing. alembic resolves a RELATIVE
          // script_location against the process working directory, not against
          // the -c config file, and this ini says `script_location = alembic`
          // and `prepend_sys_path = src`. The image WORKDIR is /app, so running
          // alembic from there fails immediately with "Path doesn't exist:
          // alembic" and the job never applies a single migration. Verified in
          // the built image: from /app it fails, from the service directory the
          // migration graph loads and reports head 0033.
          //
          // A container `workingDir` would express this directly but is not a
          // member of the jobs Container type - BCP037, and bicep drops it from
          // the compiled ARM, so it would look applied and change nothing. The
          // shell form is what dbInitJob above already uses.
          command: [
            '/bin/sh'
            '-c'
            'cd /app/services/identity && alembic -c /app/services/identity/alembic.ini upgrade head'
          ]
          volumeMounts: [
            {
              volumeName: 'jwtkeys'
              mountPath: '/secrets'
            }
          ]
          env: [
            {
              name: 'IDENTITY_ENVIRONMENT'
              value: appEnvironment
            }
            {
              name: 'IDENTITY_DATABASE_URL'
              secretRef: 'database-url'
            }
            {
              name: 'IDENTITY_REDIS_URL'
              secretRef: 'redis-url'
            }
            {
              name: 'IDENTITY_JWT_PRIVATE_KEY_PATH'
              value: '/secrets/jwt-private.pem'
            }
            {
              name: 'IDENTITY_JWT_PUBLIC_KEY_PATH'
              value: '/secrets/jwt-public.pem'
            }
            {
              name: 'IDENTITY_MFA_ENCRYPTION_KEY'
              secretRef: 'mfa-encryption-key'
            }
            {
              name: 'IDENTITY_JWKS_ISSUER'
              value: jwksIssuer
            }
            {
              name: 'IDENTITY_JWKS_AUDIENCE'
              value: jwksAudience
            }
            {
              name: 'IDENTITY_BASE_DOMAIN'
              value: baseDomain
            }
          ]
          resources: {
            cpu: json(containerCpu)
            memory: containerMemory
          }
        }
      ]
      volumes: [jwtVolumeIdentity]
    }
  }
}

resource coreMigrateJob 'Microsoft.App/jobs@2026-01-01' = if (deployWorkloads) {
  name: 'job-core-${resourceName}'
  location: location
  tags: allTags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${uamiId}': {}
    }
  }
  properties: {
    environmentId: caeId
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 600
      replicaRetryLimit: 2
      registries: [
        {
          server: acrLoginServer
          identity: uamiId
        }
      ]
      secrets: sharedSecrets
    }
    template: {
      containers: [
        {
          image: '${acrLoginServer}/core:${imageTag}'
          name: 'migrate'
          // See the identity job above: relative script_location resolves
          // against the working directory, not against the -c config file.
          command: [
            '/bin/sh'
            '-c'
            'cd /app/services/core && alembic -c /app/services/core/alembic.ini upgrade head'
          ]
          volumeMounts: [
            {
              volumeName: 'jwtkeys'
              mountPath: '/secrets'
            }
          ]
          env: [
            {
              name: 'CORE_ENVIRONMENT'
              value: appEnvironment
            }
            {
              name: 'CORE_DATABASE_URL'
              secretRef: 'database-url'
            }
            {
              name: 'CORE_JWT_PUBLIC_KEY_PATH'
              value: '/secrets/jwt-public.pem'
            }
            {
              name: 'CORE_JWKS_ISSUER'
              value: jwksIssuer
            }
            {
              name: 'CORE_JWKS_AUDIENCE'
              value: jwksAudience
            }
            {
              name: 'CORE_BASE_DOMAIN'
              value: baseDomain
            }
          ]
          resources: {
            cpu: json(containerCpu)
            memory: containerMemory
          }
        }
      ]
      volumes: [jwtVolumePublic]
    }
  }
}

resource aiAgentMigrateJob 'Microsoft.App/jobs@2026-01-01' = if (deployWorkloads) {
  name: 'job-ai-agent-${resourceName}'
  location: location
  tags: allTags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${uamiId}': {}
    }
  }
  properties: {
    environmentId: caeId
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 600
      replicaRetryLimit: 2
      registries: [
        {
          server: acrLoginServer
          identity: uamiId
        }
      ]
      secrets: sharedSecrets
    }
    template: {
      containers: [
        {
          image: '${acrLoginServer}/ai-agent:${imageTag}'
          name: 'migrate'
          // See the identity job above: relative script_location resolves
          // against the working directory, not against the -c config file.
          command: [
            '/bin/sh'
            '-c'
            'cd /app/services/ai-agent && alembic -c /app/services/ai-agent/alembic.ini upgrade head'
          ]
          volumeMounts: [
            {
              volumeName: 'jwtkeys'
              mountPath: '/secrets'
            }
          ]
          env: [
            {
              name: 'AI_ENVIRONMENT'
              value: appEnvironment
            }
            {
              name: 'AI_DATABASE_URL'
              secretRef: 'database-url'
            }
            {
              name: 'AI_REDIS_URL'
              secretRef: 'redis-url'
            }
            {
              name: 'AI_JWT_PUBLIC_KEY_PATH'
              value: '/secrets/jwt-public.pem'
            }
            {
              name: 'AI_JWKS_ISSUER'
              value: jwksIssuer
            }
            {
              name: 'AI_JWKS_AUDIENCE'
              value: jwksAudience
            }
            {
              name: 'AI_BASE_DOMAIN'
              value: baseDomain
            }
          ]
          resources: {
            cpu: json(containerCpu)
            memory: containerMemory
          }
        }
      ]
      volumes: [jwtVolumePublic]
    }
  }
}

// ---------------------------------------------------------------------------
// Outputs (for main.bicep / CD / runbook)
// ---------------------------------------------------------------------------

// The FQDNs are guarded on deployApps, not deployWorkloads, because they are
// read off the app resources: with deployApps=false the apps do not exist, and
// the `!` null-assert on a resource that was never created fails the deployment
// rather than yielding ''.
//
// The NAMES below are deliberately NOT guarded. They are string
// interpolations, not resource properties, so they are correct in every phase -
// which is why phase 1 can publish all four job names and the migrate steps
// never hardcode one.
output identityFqdn string = deployApps ? identityApp!.properties.configuration.ingress.fqdn : ''
output coreFqdn string = deployApps ? coreApp!.properties.configuration.ingress.fqdn : ''
output aiAgentFqdn string = deployApps ? aiAgentApp!.properties.configuration.ingress.fqdn : ''
output identityAppName string = identityAppName
output coreAppName string = coreAppName
output aiAgentAppName string = aiAgentAppName
output dbInitJobName string = 'job-db-init-${resourceName}'
output identityMigrateJobName string = 'job-identity-${resourceName}'
output coreMigrateJobName string = 'job-core-${resourceName}'
output aiAgentMigrateJobName string = 'job-ai-agent-${resourceName}'

// --- Public API origin -----------------------------------------------------
// identityFqdn/coreFqdn stay in the output set for phase-1 debugging only.
// They are internal now, so they are not reachable from outside the environment.

// The generated hostname. Always present, and the target of the GoDaddy CNAME
// when apiHostname is unset. When apiHostname IS set this is still the name ACA
// validated the domain against, so the CNAME has to point at THIS, not at
// api.skyrict.in - the custom domain is an alias of this hostname, not a
// replacement for it.
output apiFqdn string = deployApps ? gatewayApp!.properties.configuration.ingress.fqdn : ''
output gatewayAppName string = gatewayAppName

// The value for the `TXT asuid.api` record that proves domain ownership before
// ACA will issue the certificate is deliberately NOT an output.
//
// The 2026-01-01 API's CustomDomain type exposes only name, bindingType and
// certificateId - there is no customDomainVerificationId to read, so an output
// claiming to surface it would always be empty. The value is available from the
// CLI, which is what the runbook uses:
//
//   az rest --method post \
//     --url "https://management.azure.com/subscriptions/<sub>/providers/Microsoft.App/getCustomDomainVerificationId?api-version=2026-01-01"
//
// There is deliberately no `az containerapp hostname show`: the command does not
// exist. The `hostname` command group only has add, bind, delete and list, and
// asking for `show` fails with "'show' is misspelled or not recognized by the
// system." Anything in this repo that told an operator to run it was wrong.
//
// Registering the hostname by hand is also unnecessary now that the template has
// a 'hostname' stage, and doing it out of band would leave state the template
// does not declare. See docs/runbooks/azure-iac.md section 11.
output gatewayCustomDomainName string = enableManagedCertificate ? apiHostname : ''
