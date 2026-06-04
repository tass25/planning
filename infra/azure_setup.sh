#!/bin/bash
# azure_setup.sh — One-time Azure infrastructure setup for Codara
# Run this locally ONCE after cloning the repo.
# After this, GitHub Actions handles everything via OIDC.
#
# Prerequisites:
#   az login --tenant <TENANT_ID>
#   az account set --subscription <SUBSCRIPTION_ID>
#
# Usage:
#   bash infra/azure_setup.sh

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
RESOURCE_GROUP="rg-codara"
LOCATION="polandcentral"
APP_INSIGHTS="ai-codara"
KEY_VAULT="codara-kv-pl"
CONTAINER_APP_ENV="cae-codara"
CONTAINER_APP_BACKEND="ca-codara-backend"
CONTAINER_APP_FRONTEND="ca-codara-frontend"
CONTAINER_APP_REDIS="codara-redis"
MANAGED_IDENTITY="id-codara-ci"
GITHUB_REPO="tass25/Stage"

SUBSCRIPTION_ID=$(az account show --query id -o tsv)
KV_URI="https://${KEY_VAULT}.vault.azure.net"

echo "=== Verifying resource group: $RESOURCE_GROUP ==="
az group show --name "$RESOURCE_GROUP" --output table

echo ""
echo "=== Creating Application Insights (FREE) ==="
az monitor app-insights component create \
  --app "$APP_INSIGHTS" \
  --location "$LOCATION" \
  --resource-group "$RESOURCE_GROUP" \
  --application-type web \
  --output table

CONN_STR=$(az monitor app-insights component show \
  --app "$APP_INSIGHTS" \
  --resource-group "$RESOURCE_GROUP" \
  --query connectionString -o tsv)

echo ""
echo "=== Creating Key Vault ==="
az keyvault create \
  --name "$KEY_VAULT" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --sku standard \
  --enable-rbac-authorization true \
  --output table

echo ""
echo "=== Storing secrets in Key Vault ==="
echo "Enter your secrets when prompted (leave blank to skip):"

read -rsp "AZURE_OPENAI_API_KEY: " AOAI_KEY && echo
[ -n "$AOAI_KEY" ] && az keyvault secret set --vault-name "$KEY_VAULT" --name "azure-openai-key" --value "$AOAI_KEY" -o none

read -rp "AZURE_OPENAI_ENDPOINT (e.g. https://your-resource.cognitiveservices.azure.com/): " AOAI_ENDPOINT
[ -n "$AOAI_ENDPOINT" ] && az keyvault secret set --vault-name "$KEY_VAULT" --name "azure-openai-endpoint" --value "$AOAI_ENDPOINT" -o none

read -rp "AZURE_OPENAI_DEPLOYMENT_MINI (e.g. gpt-5.4): " AOAI_DEPLOY_MINI
[ -n "$AOAI_DEPLOY_MINI" ] && az keyvault secret set --vault-name "$KEY_VAULT" --name "azure-openai-deployment-mini" --value "$AOAI_DEPLOY_MINI" -o none

read -rsp "GROQ_API_KEY: " GROQ_KEY && echo
[ -n "$GROQ_KEY" ] && az keyvault secret set --vault-name "$KEY_VAULT" --name "groq-api-key" --value "$GROQ_KEY" -o none

read -rsp "GEMINI_API_KEY (leave blank to skip): " GEMINI_KEY && echo
[ -n "$GEMINI_KEY" ] && az keyvault secret set --vault-name "$KEY_VAULT" --name "gemini-api-key" --value "$GEMINI_KEY" -o none

read -rsp "OLLAMA_API_KEY (leave blank to skip): " OLLAMA_KEY && echo
[ -n "$OLLAMA_KEY" ] && az keyvault secret set --vault-name "$KEY_VAULT" --name "ollama-api-key" --value "$OLLAMA_KEY" -o none

read -rp "OLLAMA_BASE_URL (leave blank to skip): " OLLAMA_URL
[ -n "$OLLAMA_URL" ] && az keyvault secret set --vault-name "$KEY_VAULT" --name "ollama-base-url" --value "$OLLAMA_URL" -o none

read -rsp "CODARA_JWT_SECRET (leave blank to auto-generate): " JWT_SECRET && echo
if [ -z "$JWT_SECRET" ]; then
  JWT_SECRET=$(openssl rand -hex 32)
  echo "Auto-generated JWT secret."
fi
az keyvault secret set --vault-name "$KEY_VAULT" --name "jwt-secret" --value "$JWT_SECRET" -o none

# Redis URL — points to the internal Container App we create below
az keyvault secret set --vault-name "$KEY_VAULT" --name "redis-url" --value "redis://codara-redis:6379/0" -o none

# AppInsights connection string
az keyvault secret set --vault-name "$KEY_VAULT" --name "appinsights-conn-str" --value "$CONN_STR" -o none

echo "All secrets stored."

echo ""
echo "=== Creating managed identity for GitHub Actions OIDC ==="
az identity create \
  --name "$MANAGED_IDENTITY" \
  --resource-group "$RESOURCE_GROUP" \
  --output table

IDENTITY_CLIENT_ID=$(az identity show \
  --name "$MANAGED_IDENTITY" \
  --resource-group "$RESOURCE_GROUP" \
  --query clientId -o tsv)

IDENTITY_PRINCIPAL=$(az identity show \
  --name "$MANAGED_IDENTITY" \
  --resource-group "$RESOURCE_GROUP" \
  --query principalId -o tsv)

IDENTITY_RESOURCE_ID=$(az identity show \
  --name "$MANAGED_IDENTITY" \
  --resource-group "$RESOURCE_GROUP" \
  --query id -o tsv)

RG_ID=$(az group show --name "$RESOURCE_GROUP" --query id -o tsv)
KV_ID=$(az keyvault show --name "$KEY_VAULT" --resource-group "$RESOURCE_GROUP" --query id -o tsv)

# Contributor on the resource group — lets CI deploy container apps
az role assignment create \
  --assignee "$IDENTITY_PRINCIPAL" \
  --role Contributor \
  --scope "$RG_ID" \
  --output table

# Key Vault Secrets User — lets the managed identity read secrets
az role assignment create \
  --assignee "$IDENTITY_PRINCIPAL" \
  --role "Key Vault Secrets User" \
  --scope "$KV_ID" \
  --output table

echo "Managed identity granted Contributor + Key Vault Secrets User"

# Federate the identity with GitHub so Actions can authenticate without storing credentials
az identity federated-credential create \
  --name "github-main" \
  --identity-name "$MANAGED_IDENTITY" \
  --resource-group "$RESOURCE_GROUP" \
  --issuer "https://token.actions.githubusercontent.com" \
  --subject "repo:${GITHUB_REPO}:ref:refs/heads/main" \
  --audience "api://AzureADTokenExchange" \
  --output table

echo ""
echo "=== Creating Container Apps Environment ==="
az containerapp env create \
  --name "$CONTAINER_APP_ENV" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --output table

echo ""
echo "=== Creating Redis Container App (internal) ==="
az containerapp create \
  --name "$CONTAINER_APP_REDIS" \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$CONTAINER_APP_ENV" \
  --image redis:7-alpine \
  --target-port 6379 \
  --ingress internal \
  --transport tcp \
  --min-replicas 1 \
  --max-replicas 1 \
  --cpu 0.25 \
  --memory 0.5Gi \
  --output table

echo ""
echo "=== Creating Backend Container App ==="

kv_ref() {
  echo "keyvaultref:${KV_URI}/secrets/$1,identityref:${IDENTITY_RESOURCE_ID}"
}

az containerapp create \
  --name "$CONTAINER_APP_BACKEND" \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$CONTAINER_APP_ENV" \
  --user-assigned "$IDENTITY_RESOURCE_ID" \
  --image "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest" \
  --target-port 8000 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 2 \
  --cpu 1.0 \
  --memory 2.0Gi \
  --secrets \
    "azure-openai-key=$(kv_ref azure-openai-key)" \
    "azure-openai-endpoint=$(kv_ref azure-openai-endpoint)" \
    "azure-openai-deployment-mini=$(kv_ref azure-openai-deployment-mini)" \
    "groq-api-key=$(kv_ref groq-api-key)" \
    "gemini-api-key=$(kv_ref gemini-api-key)" \
    "ollama-api-key=$(kv_ref ollama-api-key)" \
    "ollama-base-url=$(kv_ref ollama-base-url)" \
    "redis-url=$(kv_ref redis-url)" \
    "jwt-secret=$(kv_ref jwt-secret)" \
    "appinsights-conn-str=$(kv_ref appinsights-conn-str)" \
  --env-vars \
    "APP_ENV=production" \
    "OLLAMA_MODEL=nemotron-3-super:cloud" \
    "CORS_ORIGINS=*" \
    "AZURE_OPENAI_API_VERSION=2024-10-21" \
    "AZURE_OPENAI_DEPLOYMENT_FULL=gpt-5.4" \
    "AZURE_OPENAI_API_KEY=secretref:azure-openai-key" \
    "AZURE_OPENAI_ENDPOINT=secretref:azure-openai-endpoint" \
    "AZURE_OPENAI_DEPLOYMENT_MINI=secretref:azure-openai-deployment-mini" \
    "GROQ_API_KEY=secretref:groq-api-key" \
    "GEMINI_API_KEY=secretref:gemini-api-key" \
    "OLLAMA_API_KEY=secretref:ollama-api-key" \
    "OLLAMA_BASE_URL=secretref:ollama-base-url" \
    "REDIS_URL=secretref:redis-url" \
    "CODARA_JWT_SECRET=secretref:jwt-secret" \
    "APPLICATIONINSIGHTS_CONNECTION_STRING=secretref:appinsights-conn-str" \
  --output table

BACKEND_FQDN=$(az containerapp show \
  --name "$CONTAINER_APP_BACKEND" \
  --resource-group "$RESOURCE_GROUP" \
  --query "properties.configuration.ingress.fqdn" -o tsv)

echo "Backend FQDN: $BACKEND_FQDN"

echo ""
echo "=== Creating Frontend Container App ==="
az containerapp create \
  --name "$CONTAINER_APP_FRONTEND" \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$CONTAINER_APP_ENV" \
  --image "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest" \
  --target-port 80 \
  --ingress external \
  --min-replicas 0 \
  --max-replicas 2 \
  --cpu 0.25 \
  --memory 0.5Gi \
  --env-vars "BACKEND_FQDN=$BACKEND_FQDN" \
  --output table

FRONTEND_FQDN=$(az containerapp show \
  --name "$CONTAINER_APP_FRONTEND" \
  --resource-group "$RESOURCE_GROUP" \
  --query "properties.configuration.ingress.fqdn" -o tsv)

echo "Frontend FQDN: $FRONTEND_FQDN"

echo ""
echo "=== Updating backend CORS with frontend URL ==="
az containerapp update \
  --name "$CONTAINER_APP_BACKEND" \
  --resource-group "$RESOURCE_GROUP" \
  --set-env-vars "CORS_ORIGINS=https://$FRONTEND_FQDN,http://localhost:5173" \
  --output table

echo ""
echo "============================================"
echo "  Azure setup complete!"
echo "============================================"
echo ""
echo "  Frontend: https://$FRONTEND_FQDN"
echo "  Backend:  https://$BACKEND_FQDN"
echo "  Health:   https://$BACKEND_FQDN/api/health"
echo ""
echo "Add these to GitHub Secrets (Settings → Secrets → Actions):"
echo ""
echo "  AZURE_CLIENT_ID:        $IDENTITY_CLIENT_ID"
echo "  AZURE_TENANT_ID:        $(az account show --query tenantId -o tsv)"
echo "  AZURE_SUBSCRIPTION_ID:  $SUBSCRIPTION_ID"
echo "  AZURE_RESOURCE_GROUP:   $RESOURCE_GROUP"
echo ""
echo "That's it. Push to main — GitHub Actions will deploy automatically."
echo "Secrets rotate in Key Vault only; no other files need updating."
