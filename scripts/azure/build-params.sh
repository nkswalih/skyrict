#!/usr/bin/env bash
# =============================================================================
# Build the runtime ARM parameters file from the committed template.
#
# Why this exists: some deployment parameters are operator identity, not source
# code. budgetContactEmails is the first of them - an alert address belongs in
# GitHub Secrets (AZURE_BUDGET_CONTACT_EMAILS), not in a file that every fork,
# fork-scoped workflow run and pull request can read.
#
# The committed template keeps its tracked path with an empty list, and this
# script writes a runtime copy beside it with the secret injected. Every
# `az deployment group` call and the CD Preflight step then read the runtime
# copy, so the warning about missing recipients reflects what actually deploys
# rather than what the template happens to say.
#
# An empty or unset secret deliberately yields []. An empty *string* is not an
# array, and handing ARM a string where it expects `string[]` fails the
# deployment - which is precisely the outage this wiring exists to prevent
# (Microsoft.Consumption/budgets also rejects a subscription-scope
# notification with no recipients at all).
#
# EMAIL_RELAY_CONFIG is the second such value: the transactional relay's host,
# port and SMTP login are operator identity, and the login in particular is a
# credential that must not be readable by every fork and pull request. It is
# supplied as a JSON object string and injected whole.
#
# An unset or blank value deliberately yields {}. Injecting the empty string
# would hand ARM a string where it expects an object and fail the deployment;
# {} is the documented "no relay configured" value, which leaves identity on
# its log-only transport.
#
# usage: BUDGET_CONTACT_EMAILS="a@b.com, c@d.com" \
#        EMAIL_RELAY_CONFIG='{"host":"...","port":587,...}' \
#        build-params.sh <template> <runtime>
# =============================================================================
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: $0 <template-path> <runtime-path>" >&2
  exit 2
fi

template="$1"
runtime="$2"

if [ ! -f "$template" ]; then
  echo "::error::parameters template not found: $template" >&2
  exit 1
fi

mkdir -p "$(dirname "$runtime")"

# `--arg` hands jq the raw value: no shell interpolation and no jq
# interpolation, so an address containing quotes, spaces or metacharacters
# cannot alter the filter.
jq --arg raw "${BUDGET_CONTACT_EMAILS:-}" --arg relay "${EMAIL_RELAY_CONFIG:-}" '
  .parameters.budgetContactEmails.value = (
    $raw
    | split(",")
    | map(sub("^[[:space:]]+"; "") | sub("[[:space:]]+$"; ""))
    | map(select(length > 0))
  )
  | .parameters.emailRelayConfig.value = (
      if ($relay | gsub("\\s"; "") | length) == 0 then {}
      else ($relay | fromjson)
      end
    )
' "$template" > "$runtime"

# Refuse to hand a malformed document to ARM. jq already guarantees parseable
# JSON; this checks the things that actually matter - that the runtime copy is a
# parameters document, that the injected value stayed an array, and that the
# relay stayed an object. A string in either place would fail ARM validation
# mid-deployment, after every other check had passed.
#
# fromjson in the filter above is what makes the relay check reachable: invalid
# JSON there aborts jq with a non-zero status under `set -e`, so a typo in
# EMAIL_RELAY_CONFIG stops the run here rather than as an opaque ARM error
# several minutes later.
jq -e '
  (.parameters | type) == "object"
  and ((.parameters | length) > 0)
  and ((.parameters.budgetContactEmails.value | type) == "array")
  and ((.parameters.emailRelayConfig.value | type) == "object")
' "$runtime" >/dev/null || {
  echo "::error::runtime parameters failed validation: $runtime" >&2
  exit 1
}

contacts=$(jq -r '.parameters.budgetContactEmails.value | length' "$runtime")
relay_host=$(jq -r '.parameters.emailRelayConfig.value.host // ""' "$runtime")
if [ -n "$relay_host" ]; then
  echo "runtime parameters written: $runtime ($contacts budget contact(s), email relay -> $relay_host)"
else
  echo "runtime parameters written: $runtime ($contacts budget contact(s), email relay not configured)"
fi
