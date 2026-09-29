// =============================================================================
// SKY-114 - Environment module
//
// VNet + Log Analytics workspace + Container Apps Environment (Consumption
// profile, scale-to-zero, vnet-integrated, logs to Log Analytics).
//
// Topology (all CIDRs parameterized, defaults chosen to avoid colliding with
// common 10.0/10.1 dev networks):
//   10.16.0.0/16  vnet
//   10.16.0.0/23  infra     - delegated to Microsoft.App/environments (CAE)
//   10.16.2.0/24  postgres  - delegated to Microsoft.DBforPostgreSQL/flexibleServers
//   10.16.3.0/24  pe        - private endpoint subnet (no delegation)
// =============================================================================

@description('Resource name prefix. Defaults to "skyrict".')
param prefix string = 'skyrict'

@description('Deployment environment name (beta/staging/production).')
param envName string

@description('Azure region for all resources.')
param location string

@description('Tags merged onto every resource.')
param tags object = {}

@description('VNet address space (CIDR).')
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

var allTags = union(
  {
    environment: envName
    service: prefix
    managedBy: 'bicep'
  },
  tags
)

var resourceName = '${prefix}-${envName}'

resource vnet 'Microsoft.Network/virtualNetworks@2025-01-01' = {
  name: 'vnet-${resourceName}'
  location: location
  tags: allTags
  properties: {
    addressSpace: {
      addressPrefixes: [vnetAddressPrefix]
    }
    subnets: [
      {
        name: 'infra'
        properties: {
          addressPrefix: infraSubnetPrefix
          delegations: [
            {
              name: 'infra'
              properties: {
                serviceName: 'Microsoft.App/environments'
              }
            }
          ]
        }
      }
      {
        name: 'postgres'
        properties: {
          addressPrefix: postgresSubnetPrefix
          delegations: [
            {
              name: 'postgres'
              properties: {
                serviceName: 'Microsoft.DBforPostgreSQL/flexibleServers'
              }
            }
          ]
        }
      }
      {
        name: 'pe'
        properties: {
          addressPrefix: peSubnetPrefix
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
    ]
  }
}

resource law 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: 'log-${resourceName}'
  location: location
  tags: allTags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: logRetentionDays
  }
}

resource cae 'Microsoft.App/managedEnvironments@2026-01-01' = {
  name: 'cae-${resourceName}'
  location: location
  tags: allTags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: law.properties.customerId
        sharedKey: law.listKeys().primarySharedKey
      }
    }
    vnetConfiguration: {
      infrastructureSubnetId: '${vnet.id}/subnets/infra'
    }
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
        // For Consumption workload profile, neither minimumCount nor maximumCount
        // are supported. Scaling is serverless (per-request).
      }
    ]
    zoneRedundant: false
  }
}

output environmentId string = cae.id
output environmentName string = cae.name
output lawId string = law.id
output lawName string = law.name
output vnetId string = vnet.id
output infraSubnetId string = '${vnet.id}/subnets/infra'
output postgresSubnetId string = '${vnet.id}/subnets/postgres'
output peSubnetId string = '${vnet.id}/subnets/pe'
output vnetAddressPrefix string = vnetAddressPrefix
