#!/bin/bash

set -e  # stop on any error

RESOURCE_GROUP="cc-chatbot-rg"
LOCATION="uksouth"
REGISTRY_NAME="ccbotregistry"
APP_NAME="cc-chatbot-app"
ENV_NAME="cc-chatbot-env"
INSIGHTS_NAME="cc-chatbot-insights"

echo "=== Step 1: Create resource group ==="

az group create \
  --name $RESOURCE_GROUP \
  --location $LOCATION
echo "✅ Resource group created: $RESOURCE_GROUP"

echo ""
echo "=== Step 2: Create Azure Container Registry ==="

az acr create \
  --resource-group $RESOURCE_GROUP \
  --name $REGISTRY_NAME \
  --sku Basic \
  --admin-enabled true
echo "✅ Container Registry created: $REGISTRY_NAME"

echo ""
echo "=== Step 3: Create Application Insights ==="

az monitor app-insights component create \
  --app $INSIGHTS_NAME \
  --location $LOCATION \
  --resource-group $RESOURCE_GROUP \
  --application-type web
echo "✅ Application Insights created: $INSIGHTS_NAME"

echo ""
echo "=== Step 4: Create Container Apps environment ==="

az containerapp env create \
  --name $ENV_NAME \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION
echo "✅ Container Apps environment created: $ENV_NAME"

echo ""
echo "=== Step 5: Create Container App (initial empty deploy) ==="

az containerapp create \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --environment $ENV_NAME \
  --image mcr.microsoft.com/azuredocs/containerapps-helloworld:latest \
  --target-port 8501 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 3 \
  --cpu 1.0 \
  --memory 2.0Gi
echo "✅ Container App created: $APP_NAME"

echo ""
echo "=== Step 6: Create service principal for GitHub Actions ==="
SUBSCRIPTION_ID=$(az account show --query id -o tsv)
SP_OUTPUT=$(az ad sp create-for-rbac \
  --name "cc-chatbot-github-actions" \
  --role contributor \
  --scopes /subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP \
  --sdk-auth)
echo "✅ Service principal created"


echo ""
echo "============================================================"
echo "=== SAVE THESE VALUES - You need them for GitHub Secrets ==="
echo "============================================================"

echo ""
echo "--- AZURE_CREDENTIALS ---"
echo "Copy this entire JSON block (including the curly braces):"
echo "$SP_OUTPUT"

echo ""
echo "--- ACR_LOGIN_SERVER ---"
az acr show --name $REGISTRY_NAME --query loginServer -o tsv

echo ""
echo "--- ACR_USERNAME ---"
az acr credential show --name $REGISTRY_NAME --query username -o tsv

echo ""
echo "--- ACR_PASSWORD ---"
az acr credential show --name $REGISTRY_NAME --query passwords[0].value -o tsv

echo ""
echo "--- APPINSIGHTS_CONNECTION_STRING ---"
az monitor app-insights component show \
  --app $INSIGHTS_NAME \
  --resource-group $RESOURCE_GROUP \
  --query connectionString -o tsv

echo ""
echo "============================================================"
echo "=== Setup complete! Now add GitHub Secrets as shown above ==="
echo "============================================================"
