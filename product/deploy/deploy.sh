#!/usr/bin/env bash
# Deploys LevelBlue Lake Hunt with the Azure CLI (same steps as deploy.ps1).
# Usage:
#   ./deploy.sh -g rg-lakehunt -l canadacentral [-n lakehunt] [-m demo|live] \
#     [--ws-sub <id>] [--ws-rg rg-sentinel] [--ws-name law-sentinel] [--ws-id <workspace guid>] [--ws-location <region>]
set -euo pipefail
NAME=lakehunt MODE=demo TAG=1.0.0 RG="" LOC="" WS_SUB="" WS_RG="" WS_NAME="" WS_ID="" WS_LOC=""
while [ $# -gt 0 ]; do
  case "$1" in
    -g) RG=$2; shift 2;; -l) LOC=$2; shift 2;; -n) NAME=$2; shift 2;; -m) MODE=$2; shift 2;;
    --ws-sub) WS_SUB=$2; shift 2;; --ws-rg) WS_RG=$2; shift 2;; --ws-name) WS_NAME=$2; shift 2;;
    --ws-id) WS_ID=$2; shift 2;; --ws-location) WS_LOC=$2; shift 2;; --tag) TAG=$2; shift 2;;
    *) echo "unknown option $1"; exit 1;;
  esac
done
[ -n "$RG" ] && [ -n "$LOC" ] || { echo "need -g and -l"; exit 1; }
if [ "$MODE" = live ] && { [ -z "$WS_RG" ] || [ -z "$WS_NAME" ] || [ -z "$WS_ID" ]; }; then
  echo "live mode needs --ws-rg, --ws-name and --ws-id"; exit 1; fi
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(dirname "$HERE")"
WS_SUB=${WS_SUB:-$(az account show --query id -o tsv)}; WS_LOC=${WS_LOC:-$LOC}

echo "== Resource group and registry"
az group create -n "$RG" -l "$LOC" -o none
ACR=$(echo -n "${NAME}$(az group show -n "$RG" --query id -o tsv | sha256sum | cut -c1-8)" | tr -cd 'a-z0-9')
az acr create -g "$RG" -n "$ACR" --sku Basic -o none
az acr build -r "$ACR" -t "lakehunt:$TAG" "$ROOT"
IMAGE="$(az acr show -n "$ACR" --query loginServer -o tsv)/lakehunt:$TAG"

echo "== Entra ID app registration"
DISPLAY="LevelBlue Lake Hunt ($NAME)"
APP_ID=$(az ad app list --display-name "$DISPLAY" --query "[0].appId" -o tsv)
if [ -z "$APP_ID" ]; then
  APP_ID=$(az ad app create --display-name "$DISPLAY" --sign-in-audience AzureADMyOrg \
    --app-roles "@$HERE/app-roles.json" --enable-id-token-issuance true --query appId -o tsv)
  az ad sp create --id "$APP_ID" -o none
fi
az ad app update --id "$APP_ID" --identifier-uris "api://$APP_ID"
OBJ=$(az ad app show --id "$APP_ID" --query id -o tsv)
if [ "$(az ad app show --id "$APP_ID" --query "api.oauth2PermissionScopes[?value=='access_as_user'] | length(@)" -o tsv)" = 0 ]; then
  az rest --method PATCH --uri "https://graph.microsoft.com/v1.0/applications/$OBJ" --headers "Content-Type=application/json" \
    --body "{\"api\":{\"requestedAccessTokenVersion\":2,\"oauth2PermissionScopes\":[{\"id\":\"$(cat /proc/sys/kernel/random/uuid)\",\"value\":\"access_as_user\",\"type\":\"User\",\"adminConsentDisplayName\":\"Use Lake Hunt\",\"adminConsentDescription\":\"Use Lake Hunt as the signed-in user\",\"isEnabled\":true}]}}"
fi
SECRET=$(az ad app credential reset --id "$APP_ID" --append --display-name lakehunt-easyauth --years 1 --query password -o tsv)

echo "== Deploy infrastructure"
OUT=$(az deployment group create -g "$RG" -f "$HERE/main.bicep" --query properties.outputs -o json -p \
  name="$NAME" image="$IMAGE" registryName="$ACR" mode="$MODE" authClientId="$APP_ID" authClientSecret="$SECRET" \
  workspaceSubscriptionId="$WS_SUB" workspaceResourceGroup="$WS_RG" workspaceName="$WS_NAME" workspaceId="$WS_ID" \
  workspaceLocation="$WS_LOC")
URL=$(echo "$OUT" | python3 -c "import sys,json;print(json.load(sys.stdin)['url']['value'])")
PRINCIPAL=$(echo "$OUT" | python3 -c "import sys,json;print(json.load(sys.stdin)['identityPrincipalId']['value'])")
az ad app update --id "$APP_ID" --web-redirect-uris "$URL/.auth/login/aad/callback"

cat <<EOF

Lake Hunt is deployed: $URL

Remaining steps (manual):
 1. Entra ID > Enterprise applications > '$DISPLAY' > Users and groups: assign LakeHunt.Admin, .Analyst, .Viewer.
 2. Live mode only: in the Defender portal, give the managed identity ($PRINCIPAL) a role that can read the
    Sentinel data lake (Microsoft Defender XDR unified RBAC, data lake permissions). Confirm in a lab first.
 3. Open $URL, sign in, and follow Overview > Sources.
EOF
