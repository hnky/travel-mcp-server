#!/usr/bin/env bash
# Provision Contoso Travel MCP server on Azure Container Apps.
#
# Required env: nothing (uses sensible defaults; override below).
# Prereqs: az login already done, Docker not required (uses ACR build).
set -euo pipefail

RG="${RG:-DEM330-RG}"
LOCATION="${LOCATION:-eastus2}"
SUFFIX="${SUFFIX:-$(date +%s | tail -c 5)}"   # 4-digit suffix to avoid global-name clashes
STORAGE_ACCOUNT="${STORAGE_ACCOUNT:-contosotravel${SUFFIX}}"
ACR_NAME="${ACR_NAME:-contosotravelacr${SUFFIX}}"
ENV_NAME="${ENV_NAME:-contoso-travel-env}"
APP_NAME="${APP_NAME:-contoso-travel}"
IMAGE_TAG="${IMAGE_TAG:-v1}"
IMAGE="contoso-travel:${IMAGE_TAG}"

echo "Resource group : $RG ($LOCATION)"
echo "Storage account: $STORAGE_ACCOUNT"
echo "ACR            : $ACR_NAME"
echo "Container App  : $APP_NAME (env: $ENV_NAME)"

az group create -n "$RG" -l "$LOCATION" -o none

echo "==> Registering required providers (idempotent)"
for ns in Microsoft.App Microsoft.OperationalInsights Microsoft.ContainerRegistry Microsoft.Storage; do
    az provider register --namespace "$ns" -o none || true
done

echo "==> Creating Storage account for Table Storage"
az storage account create \
    -g "$RG" -n "$STORAGE_ACCOUNT" -l "$LOCATION" \
    --sku Standard_LRS --kind StorageV2 -o none

STORAGE_CS=$(az storage account show-connection-string \
    -g "$RG" -n "$STORAGE_ACCOUNT" --query connectionString -o tsv)

echo "==> Seeding tables"
AZURE_STORAGE_CONNECTION_STRING="$STORAGE_CS" python -m contoso_travel.seed --reset

echo "==> Creating ACR + building image"
az acr create -g "$RG" -n "$ACR_NAME" --sku Basic --admin-enabled true -o none
az acr build -r "$ACR_NAME" -t "$IMAGE" . -o none

echo "==> Creating Container Apps environment"
az containerapp env create -g "$RG" -n "$ENV_NAME" -l "$LOCATION" -o none

ACR_LOGIN_SERVER=$(az acr show -n "$ACR_NAME" --query loginServer -o tsv)
ACR_USER=$(az acr credential show -n "$ACR_NAME" --query username -o tsv)
ACR_PASS=$(az acr credential show -n "$ACR_NAME" --query passwords[0].value -o tsv)

echo "==> Deploying Container App"
az containerapp create \
    -g "$RG" -n "$APP_NAME" \
    --environment "$ENV_NAME" \
    --image "${ACR_LOGIN_SERVER}/${IMAGE}" \
    --registry-server "$ACR_LOGIN_SERVER" \
    --registry-username "$ACR_USER" \
    --registry-password "$ACR_PASS" \
    --ingress external --target-port 8000 --transport auto \
    --min-replicas 1 --max-replicas 1 \
    --cpu 0.5 --memory 1.0Gi \
    --secrets "storage-cs=${STORAGE_CS}" \
    --env-vars "AZURE_STORAGE_CONNECTION_STRING=secretref:storage-cs" "MCP_HOST=0.0.0.0" "MCP_PORT=8000" \
    -o none

FQDN=$(az containerapp show -g "$RG" -n "$APP_NAME" --query properties.configuration.ingress.fqdn -o tsv)
echo
echo "Deployment complete."
echo "MCP SSE endpoint: https://${FQDN}/sse"
