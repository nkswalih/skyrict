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
// Everything in this module is guarded by deployWorkloads so the CD can do
// a two-phase rollout: infra+data+KV first, seed KV secrets, then workloads.
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

@description('Resource ID of the Container Apps Environment.')
param caeId string

@description('Container Apps Environment name. Needed for the internal FQDNs the gateway calls and as the parent of the managed certificate.')
param environmentName string

@description('ACR login server (e.g. skyrictbeta.azurecr.io).')
param acrLoginServer string

@description('Resource ID of the user-assigned identity used for ACR pull + Key Vault.')
param uamiId string

@description('Client ID of the user-assigned identity (required for KV secret references).')
param uamiClientId string

@description('Key Vault URI used to build secret references (e.g. https://kv-skyrict-beta.vault.azure.net/).')
param kvUri string

@description('Log Analytics workspace ID for app diagnostic settings.')
param logAnalyticsWorkspaceId string

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

@description('The single public API hostname (e.g. api.skyrict.in). When set AND bindCustomDomain is true, the gateway binds a managed certificate and serves this host. Empty serves only the generated FQDN.')
param apiHostname string = ''

@description('Bind apiHostname as an SNI custom domain with an ACA managed certificate. Off by default, and it cannot simply be switched on in one pass. ACA refuses to create a managed certificate for a hostname that is not already registered on a container app (RequireCustomHostnameInEnvironment), while the certificate is what the customDomains entry references - so the two have to be applied in two deployments. It also cannot be created at all before the domain resolves, so a first rollout must run with this off. See docs/runbooks/azure-iac.md section 11.')
param bindCustomDomain bool = false

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

// ACA's internal DNS name for an app in the same environment. The gateway is
// given the full internal FQDNs rather than the short aliases: short names
// ("identity", "core") are a documented ACA convenience, but pinning the FQDN
// makes the target unambiguous and survives an environment where the alias is
// not registered. The FQDN is also what ACA's internal ingress matches on, so
// it is the value that has to appear in the Host header.
var identityInternalFqdn = '${identityAppName}.${environmentName}.azurecontainerapps.io'
var coreInternalFqdn = '${coreAppName}.${environmentName}.azurecontainerapps.io'

var enableManagedCertificate = bindCustomDomain && !empty(apiHostname)
var managedCertificateName = 'env-cert-${resourceName}'

// ---------------------------------------------------------------------------
// Shared ACA secrets (all apps/jobs declare the same set)
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
    identity: uamiClientId
  }
  {
    name: 'jwt-public-key'
    keyVaultUrl: '${kvUri}secrets/jwt-public-key'
    identity: uamiClientId
  }
  {
    name: 'mfa-encryption-key'
    keyVaultUrl: '${kvUri}secrets/mfa-encryption-key'
    identity: uamiClientId
  }
  {
    name: 'sync-token'
    keyVaultUrl: '${kvUri}secrets/sync-token'
    identity: uamiClientId
  }
  {
    name: 'ingest-token'
    keyVaultUrl: '${kvUri}secrets/ingest-token'
    identity: uamiClientId
  }
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

resource identityApp 'Microsoft.App/containerApps@2026-01-01' = if (deployWorkloads) {
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
        allowInsecure: false
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

resource coreApp 'Microsoft.App/containerApps@2026-01-01' = if (deployWorkloads) {
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
        allowInsecure: false
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
              // Short-form app name - resolves inside the CAE without
              // requiring the environment-unique FQDN suffix (no Bicep
              // cycle between core and ai-agent).
              value: 'http://app-ai-agent-${resourceName}'
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

resource aiAgentApp 'Microsoft.App/containerApps@2026-01-01' = if (deployWorkloads) {
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
        external: false
        targetPort: 8000
        transport: 'http'
        allowInsecure: false
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
              name: 'AI_INVENTORY_SERVICE_URL'
              value: 'http://app-core-${resourceName}'
            }
            {
              name: 'AI_REPORT_SERVICE_URL'
              value: 'http://app-core-${resourceName}'
            }
            {
              name: 'AI_CORE_DOCUMENT_URL'
              value: 'http://app-core-${resourceName}'
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
// Guarded by bindCustomDomain as well as apiHostname, and the second condition
// is not optional. ACA requires the hostname to be registered on a container app
// before a certificate can exist for it:
//   RequireCustomHostnameInEnvironment: Creating managed certificate requires
//   hostname 'api.skyrict.in' added as a custom hostname to a container app...
// In phase 1 the gateway does not exist yet, so an unguarded certificate fails
// the deployment there and nothing downstream can run.
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
    // CNAME matches what the runbook tells the operator to add: a CNAME at
    // _acme-challenge.api.skyrict.in. Until that record exists the certificate
    // stays in a pending state, which does NOT fail the deployment - the app
    // is reachable on its generated FQDN meanwhile.
    validationMethod: 'CNAME'
  }
}

resource gatewayApp 'Microsoft.App/containerApps@2026-01-01' = if (deployWorkloads) {
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
        customDomains: enableManagedCertificate
          ? [
              {
                name: apiHostname
                bindingType: 'SniEnabled'
                certificateId: gatewayCert.id
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
            // Full internal FQDNs, not the "identity"/"core" short aliases.
            //
            // Two reasons, both load-bearing. ACA's internal ingress matches the
            // Host header against the target app's FQDN, and the gateway sends
            // that name in Host (see the gateway.conf template) - an alias that
            // ACA does not recognise as a routable host produces a 404 from
            // ACA itself, not from the backend. And the entrypoint validates
            // these values, so a typo fails the container at boot with a named
            // error instead of 502ing every request.
            {
              name: 'SKYRRICT_IDENTITY_BACKEND'
              value: 'http://${identityInternalFqdn}:8000'
            }
            {
              name: 'SKYRRICT_IDENTITY_HOST'
              value: identityInternalFqdn
            }
            {
              name: 'SKYRRICT_CORE_BACKEND'
              value: 'http://${coreInternalFqdn}:8001'
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
// Diagnostic settings -> Log Analytics (console + system logs)
// ---------------------------------------------------------------------------

resource identityDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (deployWorkloads) {
  scope: identityApp
  name: 'diag-to-law-${resourceName}'
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      {
        category: 'ContainerAppConsoleLogs'
        enabled: true
      }
      {
        category: 'ContainerAppSystemLogs'
        enabled: true
      }
    ]
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
        retentionPolicy: {
          enabled: false
          days: 0
        }
      }
    ]
  }
}

resource coreDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (deployWorkloads) {
  scope: coreApp
  name: 'diag-to-law-${resourceName}'
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      {
        category: 'ContainerAppConsoleLogs'
        enabled: true
      }
      {
        category: 'ContainerAppSystemLogs'
        enabled: true
      }
    ]
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
        retentionPolicy: {
          enabled: false
          days: 0
        }
      }
    ]
  }
}

// The gateway's access log is the only place a misrouted request is visible:
// its format ends with `up=$skyrict_api_backend`, so the log line says which
// backend served a request whose response looked like someone else's 404. It
// goes to the same workspace as the backends so one query spans the whole hop.
resource gatewayDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (deployWorkloads) {
  scope: gatewayApp
  name: 'diag-to-law-${resourceName}'
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      {
        category: 'ContainerAppConsoleLogs'
        enabled: true
      }
      {
        category: 'ContainerAppSystemLogs'
        enabled: true
      }
    ]
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
        retentionPolicy: {
          enabled: false
          days: 0
        }
      }
    ]
  }
}

resource aiAgentDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (deployWorkloads) {
  scope: aiAgentApp
  name: 'diag-to-law-${resourceName}'
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      {
        category: 'ContainerAppConsoleLogs'
        enabled: true
      }
      {
        category: 'ContainerAppSystemLogs'
        enabled: true
      }
    ]
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
        retentionPolicy: {
          enabled: false
          days: 0
        }
      }
    ]
  }
}

// ---------------------------------------------------------------------------
// db-init job - creates the shared database + extensions (idempotent)
// ---------------------------------------------------------------------------

var dbInitScript = '''
set -euo pipefail
if ! psql -v ON_ERROR_STOP=1 -tAc "SELECT 1 FROM pg_database WHERE datname = '$SKYRICT_DB'" | grep -q 1; then
  psql -v ON_ERROR_STOP=1 -c "CREATE DATABASE $SKYRICT_DB"
fi
psql -d $SKYRICT_DB -v ON_ERROR_STOP=1 -c "CREATE EXTENSION IF NOT EXISTS vector"
psql -d $SKYRICT_DB -v ON_ERROR_STOP=1 -c "CREATE EXTENSION IF NOT EXISTS pg_trgm"
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
          command: [
            'alembic'
            '-c'
            '/app/services/identity/alembic.ini'
            'upgrade'
            'head'
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
          command: [
            'alembic'
            '-c'
            '/app/services/core/alembic.ini'
            'upgrade'
            'head'
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
          command: [
            'alembic'
            '-c'
            '/app/services/ai-agent/alembic.ini'
            'upgrade'
            'head'
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

output identityFqdn string = deployWorkloads ? identityApp!.properties.configuration.ingress.fqdn : ''
output coreFqdn string = deployWorkloads ? coreApp!.properties.configuration.ingress.fqdn : ''
output aiAgentFqdn string = deployWorkloads ? aiAgentApp!.properties.configuration.ingress.fqdn : ''
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
output apiFqdn string = deployWorkloads ? gatewayApp!.properties.configuration.ingress.fqdn : ''
output gatewayAppName string = gatewayAppName

// The value for the `TXT asuid.api` record that proves domain ownership before
// ACA will issue the certificate is deliberately NOT an output.
//
// The 2026-01-01 API's CustomDomain type exposes only name, bindingType and
// certificateId - there is no customDomainVerificationId to read, so an output
// claiming to surface it would always be empty. The value is available from the
// CLI, which is what the runbook uses:
//
//   az containerapp hostname show -n <gatewayAppName> -g <rg>
//     --query customDomains[0].validationTxtRecord
//
// or, to have ACA create the binding and print both records at once:
//
//   az containerapp hostname add -n <gatewayAppName> -g <rg> \
//     --hostname <apiHostname> --type cname --validation-method CNAME
//
// See docs/runbooks/azure-iac.md section 11.
output gatewayCustomDomainName string = enableManagedCertificate ? apiHostname : ''
