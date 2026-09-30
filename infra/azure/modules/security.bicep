// =============================================================================
// SKY-114 - Security module
//
// User-assigned managed identity (shared by all Container Apps for ACR pull,
// Key Vault secret resolution, and ACA-native Key Vault references) and the
// Key Vault itself (RBAC data plane, soft delete + purge protection).
//
// Secrets are DATA, not infrastructure: the OIDC bootstrap and the CD
// workflow create/seed them (JWT keypair, Fernet MFA key, sync tokens). This
// module only guarantees the vault exists with the right posture.
// =============================================================================

@description('Resource name prefix. Defaults to "skyrict".')
param prefix string = 'skyrict'

@description('Deployment environment name (beta/staging/production).')
param envName string

@description('Azure region for all resources.')
param location string

@description('Tags merged onto every resource.')
param tags object = {}

var allTags = union(
  {
    environment: envName
    service: prefix
    managedBy: 'bicep'
  },
  tags
)

var resourceName = '${prefix}-${envName}'

@description('Key Vault name. Leave empty for the conventional kv-<prefix>-<env>. Override when that name is taken by a vault that is soft-deleted WITH purge protection: such a name can never be reused and purging is refused, so the only way forward is a different name. A parameter default may not reference a var, so the fallback is resolved by resolvedKeyVaultName below.')
param keyVaultName string = ''

var resolvedKeyVaultName = empty(keyVaultName) ? 'kv-${resourceName}' : keyVaultName

resource uami 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${resourceName}'
  location: location
  tags: allTags
}

resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: resolvedKeyVaultName
  location: location
  tags: allTags
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    enablePurgeProtection: true
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Allow'
    }
  }
}

// Key Vault Secrets User (built-in): 4633458b-17de-408a-b874-0445c86b69e6
var kvSecretsUserRoleDefinitionId = '4633458b-17de-408a-b874-0445c86b69e6'

resource kvUamiSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(kv.id, uami.id, kvSecretsUserRoleDefinitionId)
  scope: kv
  properties: {
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', kvSecretsUserRoleDefinitionId)
    description: 'Grants the Skyrict Container Apps user-assigned identity read access to Key Vault secrets (secret volumes + env references).'
  }
}

output kvId string = kv.id
output kvName string = kv.name
output kvUri string = kv.properties.vaultUri
output uamiId string = uami.id
output uamiPrincipalId string = uami.properties.principalId
output uamiClientId string = uami.properties.clientId
