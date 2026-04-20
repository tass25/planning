#!/bin/bash
# azure_setup.sh — One-time Azure infrastructure setup
# Run this locally ONCE after cloning the repo.
# After this, GitHub Actions handles everything via OIDC — only the image changes on each push.
#
# Prerequisites:
#   az login
#   az account set --subscription YOUR_SUBSCRIPTION_ID
#
# Usage:
#   bash infra/azure_setup.sh

set -euo pipefail

RESOURCE_GROUP="rg-codara"
LOCATION="westeurope"
APP_INSIGHTS="ai-codara"
KEY_VAULT="kv-codara"
CONTAINER_APP_ENV="cae-codara"
CONTAINER_APP="ca-codara-backend"
MANAGED_IDENTITY="id-codara-ci"
GITHUB_REPO="tass25/Stage"  # GitHub user/repo

SUBSCRIPTION_ID=$(az account show --query id -o tsv)
KV_URI="https://${KEY_VAULT}.vault.azure.net"

echo "=== Creating resource group ==="
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output table

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

read -rsp "AZURE_OPENAI_ENDPOINT: " AOAI_ENDPOINT && echo
[ -n "$AOAI_ENDPOINT" ] && az keyvault secret set --vault-name "$KEY_VAULT" --name "azure-openai-endpoint" --value "$AOAI_ENDPOINT" -o none

read -rsp "AZURE_OPENAI_DEPLOYMENT_MINI (e.g. gpt-4o-mini): " AOAI_DEPLOY_MINI && echo
[ -n "$AOAI_DEPLOY_MINI" ] && az keyvault secret set --vault-name "$KEY_VAULT" --name "azure-openai-deployment-mini" --value "$AOAI_DEPLOY_MINI" -o none

read -rsp "GROQ_API_KEY: " GROQ_KEY && echo
[ -n "$GROQ_KEY" ] && az keyvault secret set --vault-name "$KEY_VAULT" --name "groq-api-key" --value "$GROQ_KEY" -o none

read -rsp "GEMINI_API_KEY: " GEMINI_KEY && echo
[ -n "$GEMINI_KEY" ] && az keyvault secret set --vault-name "$KEY_VAULT" --name "gemini-api-key" --value "$GEMINI_KEY" -o none

read -rsp "OLLAMA_API_KEY: " OLLAMA_KEY && echo
[ -n "$OLLAMA_KEY" ] && az keyvault secret set --vault-name "$KEY_VAULT" --name "ollama-api-key" --value "$OLLAMA_KEY" -o none

read -rsp "OLLAMA_BASE_URL (e.g. https://your-ollama-host/v1): " OLLAMA_URL && echo
[ -n "$OLLAMA_URL" ] && az keyvault secret set --vault-name "$KEY_VAULT" --name "ollama-base-url" --value "$OLLAMA_URL" -o none

read -rsp "FRONTEND_URL (e.g. https://app.codara.dev — used for CORS): " FRONTEND_URL && echo

read -rsp "REDIS_URL (e.g. redis://your-redis-host:6379/0): " REDIS_URL_VAL && echo
[ -n "$REDIS_URL_VAL" ] && az keyvault secret set --vault-name "$KEY_VAULT" --name "redis-url" --value "$REDIS_URL_VAL" -o none

read -rsp "CODARA_JWT_SECRET (leave blank to auto-generate): " JWT_SECRET && echo
if [ -z "$JWT_SECRET" ]; then
  JWT_SECRET=$(openssl rand -hex 32)
  echo "Auto-generated JWT secret."
fi
az keyvault secret set --vault-name "$KEY_VAULT" --name "jwt-secret" --value "$JWT_SECRET" -o none

# AppInsights is auto-generated above — store it too
az keyvault secret set --vault-name "$KEY_VAULT" --name "appinsights-conn-str" --value "$CONN_STR" -o none

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

# Key Vault Secrets User — lets the managed identity (and therefore the Container App) read secrets
az role assignment create \
  --assignee "$IDENTITY_PRINCIPAL" \
  --role "Key Vault Secrets User" \
  --scope "$KV_ID" \
  --output table

echo "Managed identity granted Key Vault Secrets User on $KEY_VAULT"

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
echo "=== Creating Container App with Key Vault secret references ==="
# Secrets are stored as Key Vault references — the managed identity reads them at runtime.
# This way rotating a secret in Key Vault takes effect on the next restart,
# and no secret value ever touches CI logs or environment variables.

# Build the Key Vault reference URI for each secret
kv_ref() {
  echo "keyvaultref:${KV_URI}/secrets/$1,identityref:${IDENTITY_RESOURCE_ID}"
}

az containerapp create \
  --name "$CONTAINER_APP" \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$CONTAINER_APP_ENV" \
  --user-assigned "$IDENTITY_RESOURCE_ID" \
  --image "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest" \
  --target-port 8000 \
  --ingress external \
  --min-replicas 0 \
  --max-replicas 2 \
  --cpu 0.5 \
  --memory 1.0Gi \
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
    "CORS_ORIGINS=${FRONTEND_URL:-https://app.codara.dev},http://localhost:5173" \
    "AZURE_OPENAI_API_VERSION=2024-10-21" \
    "AZURE_OPENAI_DEPLOYMENT_FULL=gpt-4o" \
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

echo ""
echo "=== Azure setup complete! ==="
echo ""
echo "Add these three values to GitHub Secrets (Settings → Secrets → Actions):"
echo ""
echo "  AZURE_CLIENT_ID:       $IDENTITY_CLIENT_ID"
echo "  AZURE_TENANT_ID:       $(az account show --query tenantId -o tsv)"
echo "  AZURE_SUBSCRIPTION_ID: $SUBSCRIPTION_ID"
echo ""
echo "That's it. Push to main — GitHub Actions will deploy automatically."
echo "Secrets rotate in Key Vault only; no other files need updating."
