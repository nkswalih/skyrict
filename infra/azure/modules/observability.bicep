// =============================================================================
// SKY-114 - Observability module
//
// Cost-budget alerts at SUBSCRIPTION scope. Costs are the #1 risk for a
// free-trial beta running on a fixed $200 allotment for a single month: the
// floor is NOT ~$0/month. Always-on work is what costs money here - four
// Container Apps replicas held at minReplicas 1, a Flexible Server, a Redis
// cache and a container registry all bill by the hour whether or not anyone
// is logged in - so this module alerts at 50% / 80% / 90% of a configurable
// monthly amount and lets the operator set that amount to what the
// environment actually costs. (Microsoft.Consumption/budgets only exists at
// subscription or billing scope - it cannot be scoped to the resource group,
// which is why the deployment principal gets subscription-level Contributor
// in bootstrap-azure.ps1.)
//
// Budgets are skipped entirely when budgetContactEmails is empty - see the
// guard on the resource below. A budget that cannot notify anyone is worse
// than no budget: it looks like a safeguard in the portal while alerting
// nobody.
//
// budgetStartDate is a parameter the CD passes as the first of the current
// month so re-applies within the same month are idempotent (a utcNow()
// fallback changes once per month boundary and is documented as the only
// intentional non-idempotent default).
// =============================================================================

targetScope = 'subscription'

@description('Deployment environment name (beta/staging/production) - used in alert names.')
param envName string

@description('Monthly budget amount in USD that triggers the percent alerts. Defaults to the free-trial allotment ($200) so the 50/80/90% thresholds fire at $100/$160/$180 - a real spend curve, not an amount that is below the first day of running costs.')
param budgetAmount int = 200

@description('Percent thresholds at which to fire budget alerts.')
param budgetThresholds array = [
  50
  80
  90
]

@description('Email addresses receiving the budget alerts.')
param budgetContactEmails array = []

@description('Budget start date (YYYY-MM-DD). The CD passes the first of the current month for idempotent re-applies.')
param budgetStartDate string = utcNow('yyyy-MM-01')

@description('Budget end date - open-ended by default. Set when migrating to a committed period.')
param budgetEndDate string = '2099-12-31'

// The guard is `if (length(budgetContactEmails) > 0)` and it is not optional
// decoration. Microsoft.Consumption/budgets validates every notification as:
// "Must have at least one contact email or contact group specified at the
// Subscription or Resource Group scopes" (Budgets - Create Or Update, REST).
// This module is targetScope = 'subscription', so a budget declared with an
// empty contactEmails array is rejected by the resource provider and the whole
// deployment fails - after Bicep has compiled clean and every other check has
// passed. An empty list therefore cannot be allowed to reach the resource: it
// skips the budget instead, and cd-azure-beta.yml's Preflight step warns that
// no spend alert exists.
resource budget 'Microsoft.Consumption/budgets@2021-10-01' = [
  for threshold in budgetThresholds: if (length(budgetContactEmails) > 0) {
    name: 'skyrict-${envName}-budget-${threshold}pct'
    properties: {
      amount: budgetAmount
      category: 'Cost'
      timeGrain: 'Monthly'
      timePeriod: {
        startDate: budgetStartDate
        endDate: budgetEndDate
      }
      notifications: {
        'alert${threshold}pct': {
          enabled: true
          operator: 'GreaterThanOrEqualTo'
          threshold: threshold
          thresholdType: 'Actual'
          contactEmails: budgetContactEmails
        }
      }
    }
  }
]
