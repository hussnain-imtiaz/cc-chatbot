#!/bin/bash
# Run this AFTER azure_setup.sh to push your secrets into Container Apps
# So the app can read them at runtime without them ever being in code or GitHub
#
# Usage:
#   export OPENAI_API_KEY="sk-..."
#   export SNOWFLAKE_ACCOUNT="abc12345"
#   export SNOWFLAKE_USER="myuser"
#   export SNOWFLAKE_PASSWORD="mypassword"
#   export APPINSIGHTS_CONN_STR="InstrumentationKey=..."
#   ./infra/set_secrets.sh

set -e

APP_NAME="cc-chatbot-app"
RESOURCE_GROUP="cc-chatbot-rg"

echo "Setting secrets in Azure Container Apps..."

az containerapp secret set \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --secrets \
    "openai-api-key=$OPENAI_API_KEY" \
    "snowflake-account=$SNOWFLAKE_ACCOUNT" \
    "snowflake-user=$SNOWFLAKE_USER" \
    "snowflake-password=$SNOWFLAKE_PASSWORD" \
    "appinsights-conn-str=$APPINSIGHTS_CONN_STR"

echo "✅ Secrets set. They are encrypted at rest in Azure - never visible in logs."
