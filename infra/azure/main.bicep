// =============================================================================
// SKY-114 - Skyrict Azure deployment (root template)
//
// Composition of the seven modules:
//   environment   VNet (10.16.0.0/16) + Log Analytics + Container Apps
//                 Environment (Consumption, vnet-integrated, scale-to-zero)
//   security      Key Vault (RBAC, soft delete + purge protection) + UAMI
//   registry      Azure Container Registry (Standard, admin disabled)
//   data          PostgreSQL Flexible Server (B1ms, v16, private VNet) +
//                 conditional Azure Cache for Redis C0 (private endpoint)
//   apps          three Container Apps + db-init + three migration jobs
//                 (gated on deployWorkloads for the two-phase rollout)
//   observability subscription cost-budget alerts (50/80/90%)
//
// Two-phase rollout (the CD enforces it):
//   phase 1  deployWorkloads=false  -> env/security/registry/data + KV +
//            budgets. The CD then seeds the KV secrets (JWT keypair, MFA
//            key, sync/ingest tokens) because the apps' Key Vault secret
//            references must exist before their revisions are created.
//   phase 2  deployWorkloads=true + imageTag -> apps + jobs; then CD runs
//            db-init -> identity -> core -> ai-agent migrations.
//
// while deployWorkloads=false the apps module still outputs the job names,
// so phase 1 outputs are stable for the CD to act on.
// =============================================================================

targetScope = 'resourceGroup'

// ---------------------------------------------------------------------------
// Common
// ---------------------------------------------------------------------------

@description('Resource name prefix. Defaults to "skyrict".')
param prefix string = 'skyrict'

@description('Deployment environment name (beta/staging/production).')
param envName string

@description('Azure region for all resources.')
param location string

@description('Key Vault name. Defaults to kv-<prefix>-<env>. Override when the conventional name is held by a soft-deleted vault with purge protection, which can never be reused or purged.')
param keyVaultName string = ''

// An empty override means "use the conventional name". Resolved here because a
// module parameter default would be overridden by an empty string passed down.
var resolvedKeyVaultName = empty(keyVaultName) ? 'kv-${prefix}-${envName}' : keyVaultName

@description('Tags merged onto every resource.')
param tags object = {}

// ---------------------------------------------------------------------------
// Network / environment
// ---------------------------------------------------------------------------

@description('VNet address space (CIDR) - also the TRUSTED_PROXIES value the apps use for real-client-IP extraction.')
param vnetAddressPrefix string = '10.16.0.0/16'

@description('Subnet prefix for the CAE infrastructure subnet (delegated to Microsoft.App/environments).')
param infraSubnetPrefix string = '10.16.0.0/23'

@description('Subnet prefix for the PostgreSQL Flexible Server subnet (delegated to Microsoft.DBforPostgreSQL/flexibleServers).')
param postgresSubnetPrefix string = '10.16.2.0/24'

@description('Subnet prefix for private endpoints.')
param peSubnetPrefix string = '10.16.3.0/24'

@description('Log Analytics retention period in days - capped to control beta cost.')
@minValue(7)
@maxValue(90)
param logRetentionDays int = 30

// The Consumption workload profile accepts neither minimumCount nor maximumCount,
// so there is no environment-level node cap. Per-app maxReplicas (below) is the
// cap that actually applies.

// ---------------------------------------------------------------------------
// Registry
// ---------------------------------------------------------------------------

@description('ACR SKU: Standard is free for 12 months on the Azure free account; scale to Basic after year 1.')
@allowed([
  'Basic'
  'Standard'
  'Premium'
])
param registrySku string = 'Standard'

@description('Optional globally-unique ACR name (lowercase alphanumeric, no dashes). Defaults to <prefix><envName>.')
param registryNameOverride string = ''

@description('Principal ID of the deployment principal (GitHub Actions OIDC service principal) that pushes images - granted AcrPush at registry scope.')
param deployPrincipalId string = ''

// ---------------------------------------------------------------------------
// Data
// ---------------------------------------------------------------------------

@description('Flexible Server administrator login.')
param postgresLogin string = 'skyrict'

@secure()
@description('Flexible Server administrator password. Bicep never logs or outputs it. CD overrides this from the AZURE_POSTGRES_ADMIN_PASSWORD GitHub secret.')
param postgresPassword string

@description('Flexible Server compute SKU - Standard_B1ms is the 12-month free tier.')
param postgresSku string = 'Standard_B1ms'

@description('Flexible Server SKU tier (Burstable for the free-tier SKU).')
param postgresSkuTier string = 'Burstable'

@description('PostgreSQL major version - 16 matches the CI image (postgres:16).')
@allowed([
  '15'
  '16'
  '17'
])
param postgresVersion string = '16'

@description('Storage size in GB - 32 is the 12-month free allotment.')
@minValue(32)
@maxValue(1024)
param postgresStorageGB int = 32

@description('Backup retention in days.')
@minValue(7)
@maxValue(35)
param backupRetentionDays int = 7

@description('Name of the shared application database inside the server.')
param postgresDbName string = 'skyrict_identity'

@description('Deploy the managed Azure Cache for Redis (true for month 1; false after the Upstash swap).')
param deployManagedRedis bool = true

@description('Azure Cache for Redis SKU family/name (C0 = Standard tier, 250 MB).')
@allowed([
  'Basic'
  'Standard'
  'Premium'
])
param redisSku string = 'Standard'

@description('Azure Cache for Redis capacity for the SKU (0 = C0 for Basic/Standard).')
param redisCapacity int = 0

@secure()
@description('Redis connection URL override (Upstash Serverless Redis after the month-1 swap). Required when deployManagedRedis=false.')
param redisUrlOverride string = ''

// ---------------------------------------------------------------------------
// Apps + jobs
// ---------------------------------------------------------------------------

@description('Deploy the apps and jobs. False during phase 1 infra+KV+data rollout.')
param deployWorkloads bool = false

@description('Image tag for all three services (git SHA from CD).')
param imageTag string = ''

@description('Application ENVIRONMENT value - one of the four app enum values, staging for beta.')
@allowed([
  'dev'
  'test'
  'staging'
  'production'
])
param appEnvironment string = 'staging'

@description('Explicit CORS origins for all three services (JSON array string). Never "*".')
param corsOrigins array = []

@description('Trusted proxy CIDRs. Empty defaults to the VNet prefix.')
param trustedProxies array = []

@description('BASE_DOMAIN required by every service in staging/production. CD preflight fails when workloads are deployed without it.')
param baseDomain string = ''

@description('JWT issuer claim shared by identity/core/ai-agent.')
param jwksIssuer string = ''

@description('JWT audience claim shared by identity/core/ai-agent.')
param jwksAudience string = ''

@description('The single public API hostname, e.g. "api.skyrict.in". Binds the managed certificate, sets ingress.customDomains and the CORS allow-list. Empty means the generated *.azurecontainerapps.io FQDN only.')
param apiHostname string = ''

@description('Cloudflare Turnstile site key. Empty in beta, which blocks all self-service signup - see docs/runbooks/pre-release-audit-2026-09.md finding 23.')
param turnstileSiteKey string = ''

@description('Set true when the CD workflow has written the "turnstile-secret-key" secret into Key Vault. The secret VALUE never enters Bicep: it would land in the readable env config of the container app, where anything holding Reader on the app could read it. The flag only decides whether the Key Vault reference is emitted at all, which is required because a secretRef to a missing secret makes the container fail to start.')
param turnstileSecretConfigured bool = false

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

// ---------------------------------------------------------------------------
// Observability (budgets)
// ---------------------------------------------------------------------------

@description('Monthly budget amount in USD that triggers the percent alerts. Defaults to the free-trial allotment so the 50/80/90% thresholds fire at meaningful amounts.')
param budgetAmount int = 200

@description('Percent thresholds at which to fire budget alerts.')
param budgetThresholds array = [
  50
  80
  90
]

@description('Email addresses receiving the budget alerts (leave empty during bootstrap).')
param budgetContactEmails array = []

@description('Budget start date (YYYY-MM-DD). The CD passes the first of the current month for idempotent re-applies.')
param budgetStartDate string = utcNow('yyyy-MM-01')

@description('Budget end date - open-ended by default.')
param budgetEndDate string = '2099-12-31'

// ---------------------------------------------------------------------------
// Modules
//
// NOTE ON DEPLOYMENT GUARDS: several parameter combinations produce a
// *silently broken* environment rather than a failed deployment - most
// seriously an empty TURNSTILE_SECRET_KEY, which makes identity reject 100% of
// self-service signups while the web UI has already shown "Verified". Bicep
// `assert` is still behind an experimental feature flag in the pinned CLI, so
// these invariants are enforced by the `Preflight` step in
// .github/workflows/cd-azure-beta.yml instead, which fails the run with a
// readable message before anything is deployed. See
// docs/runbooks/pre-release-audit-2026-09.md findings 6, 7, 8 and 23.
// ---------------------------------------------------------------------------

var trustedProxyCidrs = empty(trustedProxies) ? [vnetAddressPrefix] : trustedProxies

module environment 'modules/environment.bicep' = {
  name: 'environment'
  params: {
    prefix: prefix
    envName: envName
    location: location
    tags: tags
    vnetAddressPrefix: vnetAddressPrefix
    infraSubnetPrefix: infraSubnetPrefix
    postgresSubnetPrefix: postgresSubnetPrefix
    peSubnetPrefix: peSubnetPrefix
    logRetentionDays: logRetentionDays
  }
}

module security 'modules/security.bicep' = {
  name: 'security'
  params: {
    prefix: prefix
    envName: envName
    location: location
    keyVaultName: resolvedKeyVaultName
    tags: tags
  }
}

module registry 'modules/registry.bicep' = {
  name: 'registry'
  params: {
    prefix: prefix
    envName: envName
    location: location
    tags: tags
    uamiPrincipalId: security.outputs.uamiPrincipalId
    registryNameOverride: registryNameOverride
    registrySku: registrySku
    deployPrincipalId: deployPrincipalId
  }
}

module data 'modules/data.bicep' = {
  name: 'data'
  params: {
    prefix: prefix
    envName: envName
    location: location
    tags: tags
    vnetId: environment.outputs.vnetId
    postgresSubnetId: environment.outputs.postgresSubnetId
    peSubnetId: environment.outputs.peSubnetId
    postgresLogin: postgresLogin
    postgresPassword: postgresPassword
    postgresSku: postgresSku
    postgresSkuTier: postgresSkuTier
    postgresVersion: postgresVersion
    postgresStorageGB: postgresStorageGB
    backupRetentionDays: backupRetentionDays
    postgresDbName: postgresDbName
    deployManagedRedis: deployManagedRedis
    redisSku: redisSku
    redisCapacity: redisCapacity
  }
}

module apps 'modules/apps.bicep' = {
  name: 'apps'
  params: {
    prefix: prefix
    envName: envName
    location: location
    tags: tags
    deployWorkloads: deployWorkloads
    caeId: environment.outputs.environmentId
    environmentName: environment.outputs.environmentName
    acrLoginServer: registry.outputs.loginServer
    uamiId: security.outputs.uamiId
    uamiClientId: security.outputs.uamiClientId
    kvUri: security.outputs.kvUri
    logAnalyticsWorkspaceId: environment.outputs.lawId
    imageTag: imageTag
    appEnvironment: appEnvironment
    postgresFqdn: data.outputs.postgresFqdn
    postgresLogin: data.outputs.postgresLogin
    postgresDbName: data.outputs.postgresDbName
    postgresPassword: postgresPassword
    deployManagedRedis: deployManagedRedis
    redisName: data.outputs.redisName
    redisId: data.outputs.redisId
    redisUrlOverride: redisUrlOverride
    corsOrigins: corsOrigins
    trustedProxies: trustedProxyCidrs
    baseDomain: baseDomain
    jwksIssuer: jwksIssuer
    jwksAudience: jwksAudience
    apiHostname: apiHostname
    turnstileSiteKey: turnstileSiteKey
    turnstileSecretConfigured: turnstileSecretConfigured
    maxReplicas: maxReplicas
    containerCpu: containerCpu
    containerMemory: containerMemory
    concurrentRequests: concurrentRequests
    dbPoolSize: dbPoolSize
    dbMaxOverflow: dbMaxOverflow
  }
}

module observability 'modules/observability.bicep' = {
  name: 'observability'
  scope: subscription()
  params: {
    envName: envName
    budgetAmount: budgetAmount
    budgetThresholds: budgetThresholds
    budgetContactEmails: budgetContactEmails
    budgetStartDate: budgetStartDate
    budgetEndDate: budgetEndDate
  }
}

// ---------------------------------------------------------------------------
// Outputs (consumed by the CD workflow, bootstrap script, and runbook)
// ---------------------------------------------------------------------------

output uamiPrincipalId string = security.outputs.uamiPrincipalId
output uamiClientId string = security.outputs.uamiClientId
output kvName string = security.outputs.kvName
output kvUri string = security.outputs.kvUri

output acrLoginServer string = registry.outputs.loginServer
output registryName string = registry.outputs.registryName

output caeId string = environment.outputs.environmentId
output caeName string = environment.outputs.environmentName
output lawName string = environment.outputs.lawName

output postgresName string = data.outputs.postgresName
output postgresFqdn string = data.outputs.postgresFqdn
output postgresDbName string = data.outputs.postgresDbName
output postgresLogin string = data.outputs.postgresLogin

output identityFqdn string = apps.outputs.identityFqdn
output coreFqdn string = apps.outputs.coreFqdn
output aiAgentFqdn string = apps.outputs.aiAgentFqdn

// The gateway is the only externally-reachable app, so the CD's smoke tests
// probe apiFqdn - the gateway's generated FQDN, which gets an ACA-managed
// certificate immediately, unlike apiHostname, which stays pending until the
// CNAME exists. The identity and core app NAMES are read for the same reason
// one hop later: both have internal ingress and cannot be HTTP-probed from a
// runner at all, so the workflow asserts revision state and running replica
// count instead.
//
// These four have to be re-exported here explicitly, because Bicep does not
// forward module outputs. The failure mode is quiet and total: `jq -r` against
// a deployment whose top-level outputs lack a key does not error, it prints
// the string "null", and that then becomes a literal hostname in
// `curl https://null/...` and `az containerapp show --name null`. Every
// earlier job passes and the run dies in verify. ci-infra.yml now fails a PR
// that reintroduces a consumed-but-unexported output.
output apiFqdn string = apps.outputs.apiFqdn
output identityAppName string = apps.outputs.identityAppName
output coreAppName string = apps.outputs.coreAppName
output gatewayAppName string = apps.outputs.gatewayAppName
output aiAgentAppName string = apps.outputs.aiAgentAppName

output dbInitJobName string = apps.outputs.dbInitJobName
output identityMigrateJobName string = apps.outputs.identityMigrateJobName
output coreMigrateJobName string = apps.outputs.coreMigrateJobName
output aiAgentMigrateJobName string = apps.outputs.aiAgentMigrateJobName
