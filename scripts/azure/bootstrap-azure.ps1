<#
.SYNOPSIS
    Bootstraps the Skyrict Azure beta (SKY-114): Azure login, resource group,
    GitHub Actions OIDC federated identity, RBAC, and all GitHub environment
    secrets that cd-azure-beta.yml needs.

.DESCRIPTION
    Creates (idempotently) everything that must exist BEFORE the first Bicep
    deployment can run, and generates the operational secrets that the CD
    workflow seeds into Key Vault (the vault itself is created by Bicep).

    The service principal gets:
      - Contributor on the RESOURCE GROUP  - control-plane deployments
      - Key Vault Administrator on the RG  - data-plane secret seeding (KV
        RBAC role, assigned at RG scope so it covers the vault once Bicep
        creates it)
      - Contributor at SUBSCRIPTION scope - the observability module deploys
        Microsoft.Consumption/budgets at subscription scope; a nested
        subscription deployment requires deployments/write there

    ACR data-plane push (AcrPush) is NOT granted here: registry.bicep grants
    it to the deploy principal during phase 1 using the AZURE_DEPLOY_PRINCIPAL_ID
    secret, keeping the whole registry grant inside the IaC.

    Secrets are never written to the repository or printed to the console.
    Re-running this script reuses the existing app registration and rotates
    the secrets (documented in docs/runbooks/azure-iac.md).

.PARAMETER EnvironmentName
    GitHub Actions environment for the CD secrets/variables. Default azure-beta.

.PARAMETER ResourceGroupName
    Azure resource group for the deployment. Default skyrict-beta.

.PARAMETER Location
    Azure region. Default eastus.

.PARAMETER GitHubRepo
    Owner/repo that owns the environment (gh must be authenticated). Default
    nkswalih/skyrict.

.PARAMETER AppDisplayName
    Display name of the Azure AD app registration used for OIDC. If an app
    with this name exists it is reused; otherwise it is created.

.EXAMPLE
    ./scripts/azure/bootstrap-azure.ps1

.EXAMPLE
    ./scripts/azure/bootstrap-azure.ps1 -Location westeurope -ResourceGroupName skyrict-beta
#>
[CmdletBinding()]
param(
    [string]$EnvironmentName = 'azure-beta',
    [string]$ResourceGroupName = 'skyrict-beta',
    [string]$Location = 'eastus',
    [string]$GitHubRepo = 'nkswalih/skyrict',
    [string]$AppDisplayName = 'skyrict-azure-cd',
    [string]$Prefix = 'skyrict'
)

$ErrorActionPreference = 'Stop'

# ExportPkcs8PrivateKeyPem()/ExportSubjectPublicKeyInfoPem() require .NET 5+
# (PowerShell 7). Fail fast instead of an obscure member-not-found error.
if ($PSVersionTable.PSVersion.Major -lt 7) {
    throw "This script requires PowerShell 7 (.NET 5+). Current: $($PSVersionTable.PSVersion) - run it with pwsh instead."
}

function Assert-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required CLI '$Name' not found on PATH. Install it and retry."
    }
}

function New-UrlSafeToken {
    param([int]$Bytes = 32)
    # URL-safe base64 (RFC 4648) with no '=' padding - safe in connection
    # strings and env vars, and in az CLI --parameters key=value syntax.
    # NOTE: the local is named $raw, not $bytes - PowerShell variable names
    # are case-insensitive, so '$bytes' would alias the [int]-typed parameter
    # $Bytes and the Byte[] assignment would throw a conversion error.
    $raw = New-Object byte[] $Bytes
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($raw)
    $b64 = [Convert]::ToBase64String($raw)
    return ($b64 -replace '\+', '-' -replace '/', '_' -replace '=', '')
}

function New-FernetKey {
    # Fernet.generate_key() = urlsafe_b64encode(32 random bytes). Prefer the
    # repo's uv environment (guarantees the cryptography version the services
    # import), falling back to a system python.
    $code = "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        $key = (uv run python -c $code 2>$null)
        if ($LASTEXITCODE -eq 0 -and $key) { return $key.Trim() }
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        $key = (python -c $code 2>$null)
        if ($LASTEXITCODE -eq 0 -and $key) { return $key.Trim() }
    }
    throw "Could not generate a Fernet key: run 'uv sync --group dev' first so cryptography is available, then retry."
}

function New-RsaKeypair {
    # PKCS#8 private ("BEGIN PRIVATE KEY") + SPKI public ("BEGIN PUBLIC KEY")
    # PEMs, 2048-bit - exactly what identity's verify_jwt_keys_usable() loads
    # (load_pem_private_key / load_pem_public_key, >= 2048 bits enforced).
    $rsa = [System.Security.Cryptography.RSA]::Create(2048)
    try {
        return @{
            PrivatePem = $rsa.ExportPkcs8PrivateKeyPem()
            PublicPem  = $rsa.ExportSubjectPublicKeyInfoPem()
        }
    }
    finally {
        $rsa.Dispose()
    }
}

Write-Host "== Skyrict Azure beta bootstrap ==" -ForegroundColor Cyan

# ---------------------------------------------------------------------------
# Prerequisites
# ---------------------------------------------------------------------------
Assert-Command 'az'
Assert-Command 'gh'

Write-Host "Checking Azure CLI login..."
az account show --output none 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "No active Azure login - launching interactive login..."
    az login
    if ($LASTEXITCODE -ne 0) { throw "az login failed" }
}

Write-Host "Checking GitHub CLI login..."
gh auth status --hostname github.com *> $null
if ($LASTEXITCODE -ne 0) { throw "gh is not authenticated to github.com - run 'gh auth login' first" }

$subscriptionId = (az account show --query id -o tsv)
$tenantId = (az account show --query tenantId -o tsv)
Write-Host "Subscription: $subscriptionId"
Write-Host "Tenant:       $tenantId"

# ---------------------------------------------------------------------------
# Resource group
# ---------------------------------------------------------------------------
# NOTE: use `az group show` (exit code), not `az group exists`: the latter
# prints the literal strings "true"/"false", and every non-empty string is
# truthy in PowerShell - a missing group would still report "already exists".
az group show --name $ResourceGroupName --subscription $subscriptionId --output none 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "Resource group '$ResourceGroupName' already exists (reusing)."
}
else {
    Write-Host "Creating resource group '$ResourceGroupName' in $Location..."
    az group create --name $ResourceGroupName --location $Location --tags environment=beta managedBy=bicep --subscription $subscriptionId
    if ($LASTEXITCODE -ne 0) {
        throw "az group create failed for '$ResourceGroupName' in subscription $subscriptionId - cannot continue."
    }
    az group show --name $ResourceGroupName --subscription $subscriptionId --output none
    if ($LASTEXITCODE -ne 0) {
        throw "Resource group '$ResourceGroupName' was not found after creation - cannot continue."
    }
    Write-Host "  Created resource group '$ResourceGroupName'."
}

# ---------------------------------------------------------------------------
# App registration + service principal + OIDC federated credential
# ---------------------------------------------------------------------------
Write-Host "Ensuring app registration '$AppDisplayName'..."
$apps = az ad app list --display-name $AppDisplayName --query "[?displayName=='$AppDisplayName']" -o json | ConvertFrom-Json
if ($apps.Count -gt 0) {
    $appId = $apps[0].appId
    Write-Host "Reusing existing app registration (appId $appId)."
}
else {
    $app = az ad app create --display-name $AppDisplayName --sign-in-audience AzureADMyOrg -o json | ConvertFrom-Json
    $appId = $app.appId
    Write-Host "Created app registration (appId $appId)."
}

Write-Host "Ensuring service principal..."
$sp = az ad sp show --id $appId -o json 2>$null | ConvertFrom-Json
if (-not $sp) {
    $sp = az ad sp create --id $appId -o json | ConvertFrom-Json
    Write-Host "Created service principal."
}
$spObjectId = $sp.id

Write-Host "Ensuring OIDC federated credential for environment '$EnvironmentName'..."
$credName = "cd-${EnvironmentName}"

# GitHub's `sub` claim is NOT "owner/repo:ref". Both segments carry a
# numeric id:
#
#   repo:nkswalih@235286854/skyrict@1307605788:environment:azure-beta
#
# That shape landed in 2023, when GitHub added the ids to stop one
# repository presenting another repository's token to a federation. The
# "owner/repo" form matches no token GitHub issues, and the failure
# surfaces as AADSTS700213 at the `az login` step - after the workflow has
# already started and printed a plausible-looking federated token, so
# nothing in the log points at the credential.
#
# Both ids are resolved at run time rather than written down: they are
# properties of this repository, and a literal would be silently wrong
# after a transfer - the same class of bug as the value it replaces.
$owner, $repo = $GitHubRepo.Split('/')
$ownerId = gh api "users/${owner}" --jq '.id'
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($ownerId)) { throw "could not resolve the owner id for ${owner}" }
$repoId = gh api "repos/${GitHubRepo}" --jq '.id'
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($repoId)) { throw "could not resolve the repository id for ${GitHubRepo}" }
$subject = "repo:${owner}@${ownerId}/${repo}@${repoId}:environment:${EnvironmentName}"
Write-Host "  OIDC subject: $subject"

$creds = az ad app federated-credential list --id $appId --query "[?name=='$credName']" -o json | ConvertFrom-Json
if ($creds.Count -eq 0) {
    $body = @{
        name = $credName
        issuer = 'https://token.actions.githubusercontent.com'
        subject = $subject
        description = "GitHub Actions OIDC for $GitHubRepo environment $EnvironmentName"
        audiences = @('api://AzureADTokenExchange')
    } | ConvertTo-Json -Depth 5
    az ad app federated-credential create --id $appId --parameters $body | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "federated-credential create failed" }
    Write-Host "Created federated credential with subject '$subject'."
}
elseif ((@($creds)[0].subject) -ne $subject) {
    # Reuse BY NAME is what let a stale subject survive. The script reported
    # "already exists" and exited zero while leaving a credential that cannot
    # authenticate anything, so re-running the bootstrap - the documented
    # remedy for a broken deployment identity - could never repair it. The name
    # is a lookup key, not evidence that the credential is correct.
    $existing = @($creds)[0]
    $updateBody = @{
        issuer = 'https://token.actions.githubusercontent.com'
        subject = $subject
        description = "GitHub Actions OIDC for $GitHubRepo environment $EnvironmentName"
        audiences = @('api://AzureADTokenExchange')
    } | ConvertTo-Json -Depth 5
    # `name` is immutable on this resource, so it is not sent here.
    az ad app federated-credential update --id $appId --federated-credential-id $existing.id --parameters $updateBody | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "federated-credential update failed" }
    Write-Host "  REPAIRED subject on existing credential '$credName'."
    Write-Host "    was: $($existing.subject)"
    Write-Host "    now: $subject"
}
else {
    Write-Host "Federated credential '$credName' already exists with the expected subject."
}

# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------
Write-Host "Assigning RBAC (idempotent)..."
$rgId = "/subscriptions/$subscriptionId/resourceGroups/$ResourceGroupName"
$subId = "/subscriptions/$subscriptionId"

function Test-RoleAssignment {
    param([string]$PrincipalId, [string]$Scope, [string]$Role)
    $assignments = az role assignment list --assignee $PrincipalId --scope $Scope --role $Role --query "[?principalId=='$PrincipalId']" -o json 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "az role assignment list failed for role '$Role' at scope '$Scope'."
    }
    $parsed = $assignments | ConvertFrom-Json
    return ($null -ne $parsed -and $parsed.Count -gt 0)
}

function Grant-Role {
    param([string]$PrincipalId, [string]$Role, [string]$Scope, [string]$Label)
    if (Test-RoleAssignment -PrincipalId $PrincipalId -Scope $Scope -Role $Role) {
        Write-Host "  $Label already assigned."
        return
    }
    az role assignment create --assignee-object-id $PrincipalId --assignee-principal-type ServicePrincipal --role $Role --scope $Scope
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to assign role '$Role' at scope '$Scope'. Your account needs Microsoft.Authorization/roleAssignments/write at or above that scope."
    }
    Write-Host "  $Label assigned."
}

Grant-Role -PrincipalId $spObjectId -Role 'Contributor' -Scope $rgId -Label "Contributor on $ResourceGroupName"
Grant-Role -PrincipalId $spObjectId -Role 'Key Vault Administrator' -Scope $rgId -Label "Key Vault Administrator on $ResourceGroupName"
Grant-Role -PrincipalId $spObjectId -Role 'Contributor' -Scope $subId -Label "Contributor on the subscription (required for subscription-scoped budgets)"

# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------
Write-Host "Generating operational secrets..."
$keys = New-RsaKeypair
$jwtPrivate = $keys.PrivatePem
$jwtPublic = $keys.PublicPem
$mfaKey = New-FernetKey
$syncToken = New-UrlSafeToken 48
$ingestToken = New-UrlSafeToken 48
$postgresPassword = New-UrlSafeToken 24

Write-Host "Ensuring GitHub environment '$EnvironmentName'..."
gh api -X PUT "repos/$GitHubRepo/environments/$EnvironmentName" --silent
if ($LASTEXITCODE -ne 0) { throw "could not create GitHub environment $EnvironmentName" }

$secrets = [ordered]@{
    AZURE_SUBSCRIPTION_ID        = $subscriptionId
    AZURE_TENANT_ID              = $tenantId
    AZURE_CLIENT_ID              = $appId
    AZURE_DEPLOY_PRINCIPAL_ID    = $spObjectId
    AZURE_POSTGRES_ADMIN_PASSWORD = $postgresPassword
    AZURE_JWT_PRIVATE_KEY        = $jwtPrivate
    AZURE_JWT_PUBLIC_KEY         = $jwtPublic
    AZURE_MFA_ENCRYPTION_KEY     = $mfaKey
    AZURE_SYNC_TOKEN             = $syncToken
    AZURE_INGEST_TOKEN           = $ingestToken
    # Optional; set later when swapping Azure Cache for Redis -> Upstash.
    AZURE_REDIS_URL_OVERRIDE     = ''
}
foreach ($entry in $secrets.GetEnumerator()) {
    # Skip empty values: unset GitHub secrets already expand to '' in the
    # workflow, and gh secret set --body '' can 422. AZURE_REDIS_URL_OVERRIDE
    # stays unset until the Upstash swap.
    if ([string]::IsNullOrWhiteSpace($entry.Value)) {
        Write-Host "  skipped $($entry.Key) (empty value)"
        continue
    }
    # --body "$env:gh_secret_value" preserves multi-line PEM newlines; a
    # multiline string cannot be passed directly on a PowerShell command line.
    $env:gh_secret_value = $entry.Value
    gh secret set $entry.Key --env $EnvironmentName --body $env:gh_secret_value
    if ($LASTEXITCODE -ne 0) { throw "gh secret set failed for $($entry.Key)" }
    Remove-Item env:gh_secret_value
    Write-Host "  set $($entry.Key) (value hidden)"
}

# CD gate: pushing to dev only deploys when the variable is true.
#
# REPOSITORY scope, deliberately not --env $EnvironmentName. The gate is a
# JOB-level `if` in cd-azure-beta.yml:
#
#   if: github.event_name == 'workflow_dispatch' || vars.CD_AZURE_BETA_ENABLED == 'true'
#
# A job-level `if` is evaluated before the job enters its environment, so
# the `vars` context there carries repository and organisation variables
# only - environment variables are not in scope yet. Writing this one with
# --env compiles into a gate that can never be true on a push: the run
# starts, provision-infra is skipped, and the rollout reports as
# completed/skipped within a couple of seconds. That is not a loud failure,
# so it reads as "nothing to deploy" rather than "the flag is in the wrong
# scope" - which is exactly how it was missed.
#
# The value is a boolean, not a credential, so repository scope costs
# nothing in exposure. The secrets above stay on the environment.
gh variable set CD_AZURE_BETA_ENABLED --body "true"
if ($LASTEXITCODE -ne 0) { throw "could not set CD_AZURE_BETA_ENABLED variable" }
Write-Host "  set CD_AZURE_BETA_ENABLED=true on the repository (the CD gate reads repo scope)"

# ---------------------------------------------------------------------------
# Seed Key Vault if the vault already exists (manual/local deploys)
# ---------------------------------------------------------------------------
$vaultName = "kv-${Prefix}-beta"  # matches the security module naming (envName=beta)
if (az keyvault show --name $vaultName --query name -o tsv 2>$null) {
    Write-Host "Key Vault '$vaultName' exists - seeding secrets (idempotent, rotates values)."
    az keyvault secret set --vault-name $vaultName --name jwt-private-key --value $jwtPrivate | Out-Null
    az keyvault secret set --vault-name $vaultName --name jwt-public-key --value $jwtPublic | Out-Null
    az keyvault secret set --vault-name $vaultName --name mfa-encryption-key --value $mfaKey | Out-Null
    az keyvault secret set --vault-name $vaultName --name sync-token --value $syncToken | Out-Null
    az keyvault secret set --vault-name $vaultName --name ingest-token --value $ingestToken | Out-Null
    Write-Host "  KV secrets seeded."
}

Write-Host ""
Write-Host "Bootstrap complete." -ForegroundColor Green
Write-Host @"

Next steps:
  1. (CD) Push to dev - cd-azure-beta.yml runs phase 1 + phase 2 and verifies.
     Or deploy manually: see docs/runbooks/azure-iac.md.
  2. After the first deploy, the apps are reachable at the external FQDNs
     printed by the CD (identity/app-core external, ai-agent internal-only).
  3. Set budget alert emails: pass budgetContactEmails to main.bicep or edit
     infra/azure/parameters/beta.parameters.json (do not commit secrets).
  4. Re-running this script ROTATES all secrets. The running services keep
     working until the next phase-2 apply picks up the new Key Vault values.
"@