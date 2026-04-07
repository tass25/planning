#!/bin/bash
# azure_setup.sh — One-time Azure infrastructure setup
# Run this locally ONCE after cloning the repo.
# After this, GitHub Actions handles everything via OIDC.
#
# Prerequisites:
#   az login
#   az account set --subscription YOUR_SUBSCRIPTION_ID
#
# Usage:
#   bash scripts/azure_setup.sh

set -euo pipefail

RESOURCE_GROUP="rg-codara"
LOCATION="westeurope"
APP_INSIGHTS="ai-codara"
KEY_VAULT="kv-codara"
CONTAINER_APP_ENV="cae-codara"
CONTAINER_APP="ca-codara-backend"
MANAGED_IDENTITY="id-codara-ci"
GITHUB_REPO="YOUR_GITHUB_USERNAME/YOUR_REPO_NAME"  # ← change this

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
echo "Application Insights connection string: $CONN_STR"

echo ""
echo "=== Creating Key Vault (FREE tier) ==="
az keyvault create \
  --name "$KEY_VAULT" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --sku standard \
  --output table

echo ""
echo "=== Storing secrets in Key Vault ==="
echo "Enter your secrets when prompted (leave blank to skip):"

read -rsp "AZURE_OPENAI_API_KEY: " AOAI_KEY && echo
[ -n "$AOAI_KEY" ] && az keyvault secret set --vault-name "$KEY_VAULT" --name "azure-openai-key" --value "$AOAI_KEY"

read -rsp "AZURE_OPENAI_ENDPOINT: " AOAI_ENDPOINT && echo
[ -n "$AOAI_ENDPOINT" ] && az keyvault secret set --vault-name "$KEY_VAULT" --name "azure-openai-endpoint" --value "$AOAI_ENDPOINT"

read -rsp "GROQ_API_KEY: " GROQ_KEY && echo
[ -n "$GROQ_KEY" ] && az keyvault secret set --vault-name "$KEY_VAULT" --name "groq-api-key" --value "$GROQ_KEY"

read -rsp "GEMINI_API_KEY: " GEMINI_KEY && echo
[ -n "$GEMINI_KEY" ] && az keyvault secret set --vault-name "$KEY_VAULT" --name "gemini-api-key" --value "$GEMINI_KEY"

read -rsp "CODARA_JWT_SECRET (leave blank to auto-generate): " JWT_SECRET && echo
if [ -z "$JWT_SECRET" ]; then
  JWT_SECRET=$(openssl rand -hex 32)
  echo "Auto-generated JWT secret."
fi
az keyvault secret set --vault-name "$KEY_VAULT" --name "jwt-secret" --value "$JWT_SECRET"

# Store AppInsights conn string
az keyvault secret set --vault-name "$KEY_VAULT" --name "appinsights-conn-str" --value "$CONN_STR"

echo ""
echo "=== Creating Container Apps Environment (FREE tier) ==="
az containerapp env create \
  --name "$CONTAINER_APP_ENV" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --output table

echo ""
echo "=== Setting up GitHub Actions OIDC (no stored secrets) ==="
az identity create \
  --name "$MANAGED_IDENTITY" \
  --resource-group "$RESOURCE_GROUP" \
  --output table

IDENTITY_PRINCIPAL=$(az identity show \
  --name "$MANAGED_IDENTITY" \
  --resource-group "$RESOURCE_GROUP" \
  --query principalId -o tsv)

RG_ID=$(az group show --name "$RESOURCE_GROUP" --query id -o tsv)

az role assignment create \
  --assignee "$IDENTITY_PRINCIPAL" \
  --role Contributor \
  --scope "$RG_ID" \
  --output table

# Federate with GitHub
az identity federated-credential create \
  --name "github-main" \
  --identity-name "$MANAGED_IDENTITY" \
  --resource-group "$RESOURCE_GROUP" \
  --issuer "https://token.actions.githubusercontent.com" \
  --subject "repo:${GITHUB_REPO}:ref:refs/heads/main" \
  --audience "api://AzureADTokenExchange" \
  --output table

echo ""
echo "=== Summary — Add these to GitHub Secrets ==="
echo ""
echo "AZURE_CLIENT_ID:      $(az identity show --name "$MANAGED_IDENTITY" --resource-group "$RESOURCE_GROUP" --query clientId -o tsv)"
echo "AZURE_TENANT_ID:      $(az account show --query tenantId -o tsv)"
echo "AZURE_SUBSCRIPTION_ID: $(az account show --query id -o tsv)"
echo ""
echo "Also add these directly as GitHub Secrets (not from Key Vault):"
echo "  AZURE_OPENAI_API_KEY"
echo "  AZURE_OPENAI_ENDPOINT"
echo "  AZURE_OPENAI_API_VERSION"
echo "  AZURE_OPENAI_DEPLOYMENT_MINI"
echo "  GROQ_API_KEY"
echo "  GEMINI_API_KEY"
echo "  APPLICATIONINSIGHTS_CONNECTION_STRING: $CONN_STR"
echo ""
echo "=== Azure setup complete! ==="
echo "Now push to main and the CI/CD pipeline will deploy automatically."
