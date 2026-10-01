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
// budgetStartDate is FIXED and must never be derived from the current date.
// It was previously passed as the first of the current month, which was
// idempotent only within that month. On the 1st of each month the value rolled
// forward and Azure rejected the update outright:
//   400 "Start date of budgets cannot be updated. Please delete and create a
//   new budget."
// That is a hard rejection, not a tolerated Modify - and "delete and create" is
// not available, because deleting a budget discards its alert history. The
// value is pinned in the parameter file instead, so every re-apply sends the
// date the budget was created with and the resource is left untouched.
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

@description('Budget start date (YYYY-MM-DD, or a full ISO-8601 timestamp). MUST be a fixed value matching the already-created budget - never derive it from the current date. Azure rejects any update that changes a budget start date ("Start date of budgets cannot be updated. Please delete and create a new budget."), so a date that rolls forward breaks the next apply and deleting the budget is not an option here.')
param budgetStartDate string = '2026-09-01'

@description('Budget end date - open-ended by default. Set when migrating to a committed period. YYYY-MM-DD or a full ISO-8601 timestamp.')
param budgetEndDate string = '2099-12-31'

// ARM normalises the budget timePeriod dates to a full ISO-8601 timestamp on
// write, and what-if then compares the template string against that STORED
// value literally. A date-only template value therefore reports a Modify on
// every single what-if, forever: "2026-09-01" in the template never matches
// "2026-09-01T00:00:00Z" in ARM. That made the CD idempotency gate report three
// permanent changes and fail, even though every apply had written the correct
// value - the gate was failing on a formatting artefact, not on real drift.
//
// Emitting the exact stored form is what actually converges. Proven against the
// live beta environment: with these two variables all three budgets leave the
// what-if report entirely and real_changes_after_reapply goes 3 -> 0.
//
// The contains() guard passes an already-ISO value straight through, so
// appending unconditionally cannot produce the invalid '...ZT00:00:00Z'.
var budgetStartDateIso = contains(budgetStartDate, 'T') ? budgetStartDate : '${budgetStartDate}T00:00:00Z'
var budgetEndDateIso = contains(budgetEndDate, 'T') ? budgetEndDate : '${budgetEndDate}T00:00:00Z'

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
        startDate: budgetStartDateIso
        endDate: budgetEndDateIso
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
