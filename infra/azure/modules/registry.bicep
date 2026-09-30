// =============================================================================
// SKY-114 - Registry module
//
// Azure Container Registry with the admin account DISABLED. Images are pushed
// from GitHub Actions via OIDC (azure/docker-login) and pulled by the
// Container Apps using the user-assigned identity (AcrPull) - no registry
// passwords ever appear in repo, CI logs, or app configuration.
//
// SKU: default "Standard" because the Azure free account includes one
// Standard-tier registry (100 GB storage, 10 webhooks) free for 12 months.
// Scale down to "Basic" after year 1 via the registrySku parameter.
//
// Note: Basic/Standard SKUs have no private endpoint; the registry is
// reachable over the public endpoint with Azure-services bypass. Pulls are
// authenticated via managed identity, so no anonymous access is exposed. A
// private endpoint (Premium SKU) is documented as post-trial hardening.
// =============================================================================

@description('Resource name prefix. Defaults to "skyrict".')
param prefix string = 'skyrict'

@description('Deployment environment name (beta/staging/production).')
param envName string

@description('Azure region for all resources.')
param location string

@description('Tags merged onto every resource.')
param tags object = {}

@description('Principal ID of the user-assigned identity granted AcrPull (from the security module).')
param uamiPrincipalId string

@description('Optional principal ID of the deployment principal (OIDC GitHub Actions service principal) granted AcrPush so CI/CD can push images. Empty disables the assignment.')
param deployPrincipalId string = ''

@description('Optional globally-unique ACR name (lowercase alphanumeric, no dashes). Defaults to <prefix><envName>.')
param registryNameOverride string = ''

@description('ACR SKU: Standard is free for 12 months on the Azure free account; scale to Basic after year 1.')
@allowed([
  'Basic'
  'Standard'
  'Premium'
])
param registrySku string = 'Standard'

var allTags = union(
  {
    environment: envName
    service: prefix
    managedBy: 'bicep'
  },
  tags
)

var registryName = registryNameOverride == '' ? '${prefix}${envName}' : registryNameOverride

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: registryName
  location: location
  tags: allTags
  sku: {
    name: registrySku
  }
  properties: {
    adminUserEnabled: false
    dataEndpointEnabled: false
  }
}

// AcrPull (built-in): 7f951dda-4ed3-4680-a7ca-43fe172d538d
var acrPullRoleDefinitionId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

resource acrUamiPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, uamiPrincipalId, acrPullRoleDefinitionId)
  scope: acr
  properties: {
    principalId: uamiPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleDefinitionId)
    description: 'Grants the Container Apps user-assigned identity pull access to this registry.'
  }
}

// AcrPush (built-in): 8311e382-0749-4cb8-b61a-304f252e45ec
var acrPushRoleDefinitionId = '8311e382-0749-4cb8-b61a-304f252e45ec'

resource acrDeployPush 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (deployPrincipalId != '') {
  name: guid(acr.id, deployPrincipalId, acrPushRoleDefinitionId)
  scope: acr
  properties: {
    principalId: deployPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPushRoleDefinitionId)
    description: 'Grants the deployment principal (GitHub Actions OIDC) push access to this registry.'
  }
}

output registryId string = acr.id
output registryName string = acr.name
output loginServer string = acr.properties.loginServer
