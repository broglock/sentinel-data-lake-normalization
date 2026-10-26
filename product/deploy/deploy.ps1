<#
.SYNOPSIS
  Deploys LevelBlue Lake Hunt into a customer subscription with the Azure CLI.

.DESCRIPTION
  1. Creates the resource group and an Azure Container Registry, and builds the image in the registry.
  2. Creates the Entra ID app registration (sign-in, API audience, app roles) and a client secret.
  3. Deploys main.bicep: identity, storage, Container Apps environment, the app, Entra sign-in,
     and role assignments on the Sentinel workspace resource group.
  4. Sets the sign-in redirect URI and prints the remaining manual steps.

  Run from the deploy folder after `az login` with Owner (or Contributor + User Access Administrator)
  on the target subscription and rights to create app registrations.

.EXAMPLE
  ./deploy.ps1 -ResourceGroup rg-lakehunt -Location canadacentral -Mode demo

.EXAMPLE
  ./deploy.ps1 -ResourceGroup rg-lakehunt -Location canadacentral -Mode live `
    -WorkspaceResourceGroup rg-sentinel -WorkspaceName law-sentinel -WorkspaceId 00000000-0000-0000-0000-000000000000
#>
param(
  [Parameter(Mandatory)] [string] $ResourceGroup,
  [Parameter(Mandatory)] [string] $Location,
  [string] $Name = "lakehunt",
  [ValidateSet("demo", "live")] [string] $Mode = "demo",
  [string] $WorkspaceSubscriptionId = "",
  [string] $WorkspaceResourceGroup = "",
  [string] $WorkspaceName = "",
  [string] $WorkspaceId = "",
  [string] $WorkspaceLocation = "",
  [string] $ImageTag = "1.0.0"
)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $here

if ($Mode -eq "live" -and (-not $WorkspaceResourceGroup -or -not $WorkspaceName -or -not $WorkspaceId)) {
  throw "Live mode needs -WorkspaceResourceGroup, -WorkspaceName and -WorkspaceId"
}
if (-not $WorkspaceSubscriptionId) { $WorkspaceSubscriptionId = (az account show --query id -o tsv) }
if (-not $WorkspaceLocation) { $WorkspaceLocation = $Location }
$tenant = az account show --query tenantId -o tsv

Write-Host "== Resource group and registry"
az group create -n $ResourceGroup -l $Location -o none
$rgId = az group show -n $ResourceGroup --query id -o tsv
$sha = [System.Security.Cryptography.SHA256]::Create()
$hash = ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($rgId))) -replace "-", "").Substring(0, 8).ToLower()
$acr = ($Name.ToLower() + $hash) -replace "[^a-z0-9]", ""
az acr create -g $ResourceGroup -n $acr --sku Basic -o none
az acr build -r $acr -t "lakehunt:$ImageTag" $root
$image = "$(az acr show -n $acr --query loginServer -o tsv)/lakehunt:$ImageTag"

Write-Host "== Entra ID app registration"
$display = "LevelBlue Lake Hunt ($Name)"
$appId = az ad app list --display-name $display --query "[0].appId" -o tsv
if (-not $appId) {
  $appId = az ad app create --display-name $display --sign-in-audience AzureADMyOrg `
    --app-roles "@$here/app-roles.json" --enable-id-token-issuance true --query appId -o tsv
  az ad sp create --id $appId -o none
}
az ad app update --id $appId --identifier-uris "api://$appId"
# Delegated scope so users' tools (for example MCP clients) can request tokens for the API
$objId = az ad app show --id $appId --query id -o tsv
$scopeId = [guid]::NewGuid().ToString()
$body = @{ api = @{ requestedAccessTokenVersion = 2; oauth2PermissionScopes = @(@{ id = $scopeId; value = "access_as_user"; type = "User";
  adminConsentDisplayName = "Use Lake Hunt"; adminConsentDescription = "Use Lake Hunt as the signed-in user"; isEnabled = $true }) } } | ConvertTo-Json -Depth 6 -Compress
$existing = az ad app show --id $appId --query "api.oauth2PermissionScopes[?value=='access_as_user'] | length(@)" -o tsv
if ($existing -eq "0") { az rest --method PATCH --uri "https://graph.microsoft.com/v1.0/applications/$objId" --headers "Content-Type=application/json" --body $body }
$secret = az ad app credential reset --id $appId --append --display-name "lakehunt-easyauth" --years 1 --query password -o tsv

Write-Host "== Deploy infrastructure"
$out = az deployment group create -g $ResourceGroup -f "$here/main.bicep" --query properties.outputs -o json -p `
  name=$Name image=$image registryName=$acr mode=$Mode authClientId=$appId authClientSecret=$secret `
  workspaceSubscriptionId=$WorkspaceSubscriptionId workspaceResourceGroup=$WorkspaceResourceGroup `
  workspaceName=$WorkspaceName workspaceId=$WorkspaceId workspaceLocation=$WorkspaceLocation | ConvertFrom-Json
$url = $out.url.value
az ad app update --id $appId --web-redirect-uris "$url/.auth/login/aad/callback"

Write-Host ""
Write-Host "Lake Hunt is deployed: $url"
Write-Host ""
Write-Host "Remaining steps (manual):"
Write-Host " 1. Entra ID > Enterprise applications > '$display' > Users and groups: assign LakeHunt.Admin, .Analyst, .Viewer."
Write-Host " 2. Live mode only: in the Defender portal, give the managed identity ($($out.identityPrincipalId)) a role that can"
Write-Host "    read the Sentinel data lake (Microsoft Defender XDR unified RBAC, data lake permissions). Confirm in a lab first."
Write-Host " 3. Open $url, sign in, and follow Overview > Sources."
