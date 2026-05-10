# Hosted Agent Deployment — Step-by-Step Runbook

**Purpose:** Two-persona guide for deploying an Azure Foundry hosted agent with Bot Service bridge, from zero access to production.

**Personas:**

| Persona | Access Level | Responsibilities |
|---------|-------------|-----------------|
| **☁️ Cloud Architect** | Owner/Contributor on Azure subscription, Entra ID admin | Creates infrastructure, assigns RBAC, manages identity |
| **👨‍💻 Developer** | Read-only Azure Portal (initially), writes code | Builds agent, tests locally, deploys via VS Code and CI/CD |

**Prerequisites:**
- Azure subscription (pay-as-you-go or enterprise)
- GitHub repository for agent source code
- Docker Desktop installed on developer machine (for local builds/testing)
- Python 3.12+ installed on developer machine

---

## Phase 0 — Access & Infrastructure Bootstrap

> **Who:** ☁️ Cloud Architect (all steps in this phase)

### Step 0.1: Create Resource Group

```powershell
az group create --name <resource-group> --location eastus2
```

### Step 0.2: Create Azure Foundry Account (Cognitive Services)

```powershell
az cognitiveservices account create \
  --name <foundry-account-name> \
  --resource-group <resource-group> \
  --kind AIServices \
  --sku S0 \
  --location eastus2
```

### Step 0.3: Create Foundry Project

Create via Azure Foundry Portal (https://ai.azure.com) or ARM API:

```powershell
$token = az account get-access-token --resource https://management.azure.com --query accessToken -o tsv

$body = @{
  location = "eastus2"
  properties = @{}
  identity = @{ type = "SystemAssigned" }
} | ConvertTo-Json -Depth 5

Invoke-RestMethod `
  -Uri "https://management.azure.com/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<foundry-account-name>/projects/<project-name>?api-version=2025-04-01-preview" `
  -Headers @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" } `
  -Method PUT -Body $body
```

> **📌 Record the project managed identity principalId** — you'll need it in Step 0.8.

### Step 0.4: Create Capability Host

This enables hosted agent infrastructure on the Foundry account. One-time setup.

```powershell
$body = '{"properties":{"capabilityHostKind":"Agents"}}'

Invoke-RestMethod `
  -Uri "https://management.azure.com/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<foundry-account-name>/capabilityHosts/default?api-version=2025-04-01-preview" `
  -Headers @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" } `
  -Method PUT -Body $body
```

### Step 0.5: Deploy AI Model

```powershell
az cognitiveservices account deployment create \
  --name <foundry-account-name> \
  --resource-group <resource-group> \
  --deployment-name gpt-4.1-mini \
  --model-name gpt-4.1-mini \
  --model-version "2025-04-14" \
  --model-format OpenAI \
  --sku-capacity 10 \
  --sku-name "GlobalStandard"
```

### Step 0.6: Create Azure Container Registry (ACR)

```powershell
az acr create \
  --name <acr-name> \
  --resource-group <resource-group> \
  --location eastus2 \
  --sku Basic
```

### Step 0.7: Discover Project Managed Identity

```powershell
$token = az account get-access-token --resource https://management.azure.com --query accessToken -o tsv

$proj = Invoke-RestMethod `
  -Uri "https://management.azure.com/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<foundry-account-name>/projects/<project-name>?api-version=2025-04-01-preview" `
  -Headers @{ Authorization = "Bearer $token" }

Write-Host "Project MI: $($proj.identity.principalId)"
```

> **📌 Save this principalId** — it's the identity that pulls container images from ACR.

### Step 0.8: Assign RBAC — Project MI

```powershell
$projectMI = "<project-mi-principal-id>"
$acrScope = "/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.ContainerRegistry/registries/<acr-name>"
$accountScope = "/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<foundry-account-name>"

# Project MI → AcrPull on ACR (required for image pull)
az role assignment create --assignee $projectMI --role "AcrPull" --scope $acrScope

# Project MI → Azure AI User on Foundry Account (required for model inference)
az role assignment create --assignee $projectMI --role "Azure AI User" --scope $accountScope
```

### Step 0.9: Create ACR Connection at Project Level

```powershell
$connBody = @{
  properties = @{
    category = "ContainerRegistry"
    target = "https://<acr-name>.azurecr.io"
    authType = "AAD"
    isSharedToAll = $true
    metadata = @{
      ResourceId = "/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.ContainerRegistry/registries/<acr-name>"
    }
  }
} | ConvertTo-Json -Depth 5

Invoke-RestMethod `
  -Uri "https://management.azure.com/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<foundry-account-name>/connections/<acr-name>?api-version=2025-04-01-preview" `
  -Headers @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" } `
  -Method PUT -Body $connBody
```

### Step 0.10: Grant Developer Access

```powershell
$developerEmail = "<developer-email@company.com>"

# Azure Portal read access
az role assignment create \
  --assignee $developerEmail \
  --role "Reader" \
  --scope "/subscriptions/<subscription-id>/resourceGroups/<resource-group>"

# Foundry project — create/manage agents, invoke, view playground
az role assignment create \
  --assignee $developerEmail \
  --role "Azure AI Developer" \
  --scope "/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<foundry-account-name>"

# ACR — push images (for local dev; CI/CD will use its own identity)
az role assignment create \
  --assignee $developerEmail \
  --role "AcrPush" \
  --scope $acrScope
```

### Step 0.11: Set Up CI/CD Pipeline for Container Builds

Create a GitHub Actions workflow that:
1. Builds the Docker image on push to `main`
2. Pushes to ACR using a service principal or OIDC federation
3. Optionally triggers agent version update

**Architect creates service principal for CI/CD:**

```powershell
# Create SP for GitHub Actions
$sp = az ad sp create-for-rbac \
  --name "github-actions-<project-name>" \
  --role "AcrPush" \
  --scopes $acrScope \
  --sdk-auth

# Output JSON → store as GitHub Actions secret "AZURE_CREDENTIALS"
```

> **📌 Hand to Developer:** Share the following with the developer securely (e.g., Azure Key Vault, encrypted channel):
> - Subscription ID
> - Resource Group name
> - Foundry Account name
> - Foundry Project name
> - ACR name
> - Model deployment name (e.g., `gpt-4.1-mini`)
> - CI/CD service principal credentials (for GitHub Actions secrets)

---

### ✅ Phase 0 Checkpoint

| Item | Status |
|------|--------|
| Resource Group exists | ☐ |
| Foundry Account + Project created | ☐ |
| Capability Host provisioned | ☐ |
| Model deployed (gpt-4.1-mini) | ☐ |
| ACR created (Basic SKU) | ☐ |
| Project MI → AcrPull on ACR | ☐ |
| Project MI → Azure AI User on Account | ☐ |
| ACR Connection created at project level | ☐ |
| Developer granted Reader + Azure AI Developer + AcrPush | ☐ |
| CI/CD service principal created + shared | ☐ |
| Resource names shared with developer | ☐ |

---

## Phase 1 — Developer Environment Setup

> **Who:** 👨‍💻 Developer (all steps in this phase)

### Step 1.1: Install VS Code Extensions

Open VS Code → Extensions panel → Install:

1. **Azure AI Foundry** (`ms-azuretools.azure-ai-foundry`) — Foundry project explorer, agent management
2. **AI Toolkit** (`ms-windows-ai-studio.windows-ai-studio`) — Agent Inspector, debug UI
3. **Azure Account** (`ms-vscode.azure-account`) — Azure sign-in
4. **Azure Functions** (`ms-azuretools.vscode-azurefunctions`) — Function App development (for bridge)
5. **Python** (`ms-python.python`) — Python language support
6. **Docker** (`ms-azuretools.vscode-docker`) — Dockerfile support

### Step 1.2: Sign In to Azure

1. VS Code → Command Palette → `Azure: Sign In`
2. Complete browser authentication
3. Verify: VS Code status bar shows your subscription

### Step 1.3: Sign In via Azure CLI

```powershell
az login --use-device-code
az account set --subscription "<subscription-id>"
```

### Step 1.4: Validate Access

```powershell
# Verify you can see the resource group
az group show --name <resource-group> --query name -o tsv

# Verify you can see the Foundry account
az cognitiveservices account show --name <foundry-account-name> -g <resource-group> --query name -o tsv

# Verify you can see the ACR
az acr show --name <acr-name> --query name -o tsv

# Verify you can push to ACR
az acr login --name <acr-name>
```

> **🛑 If any command fails with 403/AuthorizationFailed:** Ask the Cloud Architect to verify role assignments from Step 0.10.

### Step 1.5: Validate Foundry Portal Access

1. Navigate to https://ai.azure.com
2. Select the project (e.g., `car-search`)
3. Verify you can see: **Models**, **Agents**, **Playground**
4. Open **Playground** → select the deployed model → send a test message

> **🛑 If you can't see the project or get "Access denied":** Ask the Cloud Architect to verify the `Azure AI Developer` role on the Foundry account.

### Step 1.6: Set Up Python Environment

```powershell
# Create project directory
mkdir <project-name>
cd <project-name>

# Create virtual environment
python -m venv .venv

# Activate
.\.venv\Scripts\Activate.ps1

# Verify
python --version  # Should be 3.12+
```

---

### ✅ Phase 1 Checkpoint

| Item | Status |
|------|--------|
| VS Code extensions installed | ☐ |
| Signed in to Azure (VS Code + CLI) | ☐ |
| Can see resource group, Foundry, ACR | ☐ |
| Foundry Playground works | ☐ |
| Python 3.12+ virtual environment created | ☐ |

---

## Phase 2 — Application Development

> **Who:** 👨‍💻 Developer (all steps in this phase)

### Step 2.1: Initialize Project Files

Create the following project structure:

```
<project-name>/
├── main.py              # Agent definition, tools, server startup
├── car_data.py          # Data service (mock or real API)
├── agent.yaml           # Agent metadata for Foundry
├── Dockerfile           # Container image definition
├── requirements.txt     # Python dependencies
├── .env                 # Local environment variables (gitignored)
├── .env.example         # Template for .env (committed)
├── .gitignore           # Excludes .venv, .env, __pycache__, etc.
└── .vscode/
    ├── tasks.json       # Run task with Azure CLI on PATH
    └── launch.json      # Debug configuration
```

### Step 2.2: Create requirements.txt

```
agent-framework
agent-framework-foundry-hosting
azure-identity
python-dotenv
pydantic
```

```powershell
pip install -r requirements.txt
```

### Step 2.3: Create agent.yaml

```yaml
name: <agent-name>
description: <agent description>
template:
  kind: hosted
  protocols:
    responses: "1.0.0"
  environment_variables:
    - name: AZURE_AI_MODEL_DEPLOYMENT_NAME
      description: Model deployment name
```

> **⚠️ Critical rules:**
> - Protocol version MUST be `"1.0.0"` (not `"1.0"`)
> - Do NOT declare `FOUNDRY_PROJECT_ENDPOINT` — it's platform-injected at runtime

### Step 2.4: Create .env

```
FOUNDRY_PROJECT_ENDPOINT=https://<foundry-account-name>.services.ai.azure.com/api/projects/<project-name>
AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-4.1-mini
```

### Step 2.5: Create Dockerfile

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . user_agent/
WORKDIR /app/user_agent
RUN if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
EXPOSE 8088
CMD ["python", "main.py"]
```

> **⚠️ Port 8088 is mandatory** — the Foundry hosting platform routes traffic to this port.

### Step 2.6: Write Agent Code (main.py)

Use the Microsoft Agent Framework to define your agent:

```python
import os
from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv(override=False)

# Define your tools with @tool decorator
@tool(approval_mode="never_require")
def your_tool(param: str) -> str:
    """Tool description for the model."""
    return "result"

# Create agent
agent = Agent(
    name="<agent-name>",
    instructions="Your agent system prompt here.",
    model=FoundryChatClient(
        endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        credential=DefaultAzureCredential(),
        model=os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4.1-mini"),
    ),
    tools=[your_tool],
)

# Serve as HTTP server for Foundry hosting
app = ResponsesHostServer(agent)
app.run(port=8088)
```

### Step 2.7: Write .gitignore

```
.venv/
__pycache__/
*.pyc
.env
.env.*
!.env.example
*.egg-info/
dist/
build/
.foundry/
*.zip
local.settings.json
.python_packages/
```

### Step 2.8: Test Locally

```powershell
# Ensure Azure CLI is on PATH (needed for DefaultAzureCredential)
$env:PATH = "C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin;$env:PATH"

# Run the agent
python main.py
```

Test with curl or PowerShell:

```powershell
Invoke-RestMethod -Uri "http://localhost:8088/responses" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"input": "Hello, what can you do?", "stream": false}'
```

> **🛑 If `DefaultAzureCredential` fails:** Ensure you ran `az login` and the Azure CLI path is correct.

### Step 2.9: Test with AI Toolkit Agent Inspector (Optional)

1. F5 in VS Code → launches agent with debugpy
2. Agent Inspector opens in browser → interactive tool testing and debugging

---

### ✅ Phase 2 Checkpoint

| Item | Status |
|------|--------|
| Project files created | ☐ |
| Dependencies installed | ☐ |
| Agent runs locally on port 8088 | ☐ |
| Tool calls work via local `/responses` endpoint | ☐ |
| Code committed to GitHub repository | ☐ |

---

## Phase 3 — Container Build & Deploy to Foundry

### Step 3.1: Build & Push Docker Image

> **Who:** 👨‍💻 Developer (local) or CI/CD pipeline

**Option A — Developer pushes manually (first time / debugging):**

```powershell
# Login to ACR
az acr login --name <acr-name>

# Build for linux/amd64 (REQUIRED — Foundry is x86_64)
docker build --platform linux/amd64 -t <agent-name>:latest .

# Tag with timestamp
$tag = Get-Date -Format "yyyyMMddHHmm"
docker tag <agent-name>:latest <acr-name>.azurecr.io/<agent-name>:$tag
docker push <acr-name>.azurecr.io/<agent-name>:$tag

Write-Host "Image: <acr-name>.azurecr.io/<agent-name>:$tag"
```

**Option B — CI/CD pipeline (recommended for ongoing deployments):**

The GitHub Actions workflow (set up by Cloud Architect in Step 0.11) handles this automatically on push to `main`.

> **⚠️ Always use timestamped tags**, not `:latest`, for reproducible deployments.

### Step 3.2: Create Hosted Agent in Foundry

> **Who:** 👨‍💻 Developer

Use the Foundry Portal or VS Code AI Toolkit:

**Via Foundry Portal:**
1. Navigate to https://ai.azure.com → your project
2. Go to **Agents** → **Create agent**
3. Select **Hosted agent** → provide:
   - Name: `<agent-name>`
   - Image: `<acr-name>.azurecr.io/<agent-name>:<tag>`
   - CPU: `1`, Memory: `2Gi`
   - Environment variable: `AZURE_AI_MODEL_DEPLOYMENT_NAME` = `gpt-4.1-mini`
   - Protocol: Responses v1.0.0

**Via CLI / SDK:**

```python
# Or use the Foundry MCP tool / REST API to create the agent version
# See process-documentation.md Section 8.1 for the full API call
```

### Step 3.3: Assign RBAC to Agent Identities

> **Who:** ☁️ Cloud Architect

After the agent is created, the platform generates **Agent MI** and **Blueprint MI** identities. These need `Azure AI User` at the project scope.

**Developer provides:** The agent and blueprint principal IDs (visible in Foundry Portal → Agents → agent details, or returned in the create API response).

```powershell
$projectScope = "/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<foundry-account-name>/projects/<project-name>"

# Agent MI → Azure AI User on Project
az role assignment create \
  --assignee "<agent-mi-principal-id>" \
  --role "Azure AI User" \
  --scope $projectScope

# Blueprint MI → Azure AI User on Project
az role assignment create \
  --assignee "<blueprint-mi-principal-id>" \
  --role "Azure AI User" \
  --scope $projectScope
```

> **⚠️ Wait ~60 seconds** for RBAC propagation before testing.

### Step 3.4: Validate Agent in Foundry Playground

> **Who:** 👨‍💻 Developer

1. Foundry Portal → your project → **Agents**
2. Select your agent → verify status is **Active**
3. Open **Playground** → select the agent → test with a message
4. Verify tool calls execute correctly

> **🛑 If status is `failed` with `ImageError`:** Ask the Cloud Architect to verify:
> - Project MI has `AcrPull` on ACR (Step 0.8)
> - ACR Connection exists (Step 0.9)
> - Image tag is correct and exists in ACR

> **🛑 If agent invocation fails with auth error:** Ask the Cloud Architect to verify:
> - Agent MI has `Azure AI User` on project (Step 3.3)
> - Project MI has `Azure AI User` on account (Step 0.8)

---

### ✅ Phase 3 Checkpoint

| Item | Status |
|------|--------|
| Docker image pushed to ACR | ☐ |
| Hosted agent created in Foundry | ☐ |
| Agent MI + Blueprint MI granted Azure AI User | ☐ |
| Agent status is Active | ☐ |
| Agent works in Foundry Playground | ☐ |

---

## Phase 4 — Bot Service Bridge (Teams / Web Chat Integration)

### Step 4.1: Create Entra ID App Registration

> **Who:** ☁️ Cloud Architect

```powershell
# Create SingleTenant app registration
az ad app create \
  --display-name "<bot-display-name>" \
  --sign-in-audience "AzureADMyOrg"

# Record the appId
$botAppId = "<app-id-from-output>"

# Generate a client secret
az ad app credential reset --id $botAppId --append

# CRITICAL: Create the service principal (Enterprise App)
# Without this, the bot can receive messages but cannot send replies
az ad sp create --id $botAppId
```

> **📌 Hand to Developer:** Share securely:
> - Bot App (client) ID
> - Client secret value
> - Tenant ID

### Step 4.2: Create Azure Bot Service

> **Who:** ☁️ Cloud Architect

```powershell
az bot create \
  --resource-group <resource-group> \
  --name <bot-name> \
  --app-type SingleTenant \
  --appid $botAppId \
  --tenant-id <tenant-id> \
  --sku F0

# Enable Teams channel
az bot msteams create \
  --resource-group <resource-group> \
  --name <bot-name>
```

### Step 4.3: Create Function App Infrastructure

> **Who:** ☁️ Cloud Architect

```powershell
# Create separate resource group (Linux consumption needs its own RG)
az group create --name <bridge-rg> --location eastus2

# Storage account
az storage account create \
  --name <bridge-storage-name> \
  --resource-group <bridge-rg> \
  --location eastus2 \
  --sku Standard_LRS

# Function App
az functionapp create \
  --resource-group <bridge-rg> \
  --consumption-plan-location eastus2 \
  --runtime python --runtime-version 3.12 \
  --functions-version 4 \
  --name <bridge-function-name> \
  --storage-account <bridge-storage-name> \
  --os-type Linux

# Enable Python v2 programming model (REQUIRED)
az functionapp config appsettings set \
  -g <bridge-rg> -n <bridge-function-name> \
  --settings AzureWebJobsFeatureFlags=EnableWorkerIndexing

# Enable system-assigned managed identity
az functionapp identity assign \
  -g <bridge-rg> -n <bridge-function-name>
```

> **📌 Record the Function App MI principalId** from the identity assign output.

### Step 4.4: Assign RBAC — Function App MI

> **Who:** ☁️ Cloud Architect

The Function App MI needs three roles on the Foundry account to call the hosted agent:

```powershell
$funcMI = "<function-app-mi-principal-id>"
$foundryAccountScope = "/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.CognitiveServices/accounts/<foundry-account-name>"

az role assignment create --assignee $funcMI --role "Cognitive Services User" --scope $foundryAccountScope
az role assignment create --assignee $funcMI --role "Azure AI Developer" --scope $foundryAccountScope
az role assignment create --assignee $funcMI --role "Azure AI User" --scope $foundryAccountScope
```

> **⚠️ All three roles are required.** `Cognitive Services User` alone is insufficient for the endpoint-scoped hosted agent route.

### Step 4.5: Configure App Settings

> **Who:** ☁️ Cloud Architect

```powershell
az functionapp config appsettings set \
  -g <bridge-rg> -n <bridge-function-name> \
  --settings \
    MICROSOFT_APP_ID="<bot-app-id>" \
    MICROSOFT_APP_PASSWORD="<client-secret>" \
    MICROSOFT_APP_TENANT_ID="<tenant-id>" \
    FOUNDRY_PROJECT_ENDPOINT="https://<foundry-account-name>.services.ai.azure.com/api/projects/<project-name>" \
    AGENT_NAME="<agent-name>"
```

### Step 4.6: Set Bot Messaging Endpoint

> **Who:** ☁️ Cloud Architect

```powershell
az bot update \
  --resource-group <resource-group> \
  --name <bot-name> \
  --endpoint "https://<bridge-function-name>.azurewebsites.net/api/messages"
```

### Step 4.7: Grant Developer Deploy Access to Function App

> **Who:** ☁️ Cloud Architect

```powershell
az role assignment create \
  --assignee "<developer-email@company.com>" \
  --role "Website Contributor" \
  --scope "/subscriptions/<subscription-id>/resourceGroups/<bridge-rg>/providers/Microsoft.Web/sites/<bridge-function-name>"
```

> **📌 Hand to Developer:**
> - Function App name
> - Bridge resource group name
> - Bot name (for Web Chat testing)

---

### ✅ Phase 4 Architect Checkpoint

| Item | Status |
|------|--------|
| Entra ID app registration created (with service principal!) | ☐ |
| Azure Bot Service created (F0, SingleTenant) | ☐ |
| Teams channel enabled on bot | ☐ |
| Function App created (Linux, Python 3.12, Consumption) | ☐ |
| Function App MI assigned 3 roles on Foundry account | ☐ |
| App settings configured (app ID, secret, tenant, endpoint, agent name) | ☐ |
| Bot messaging endpoint updated | ☐ |
| Developer granted Website Contributor on Function App | ☐ |
| Resource names + credentials shared with developer | ☐ |

---

### Step 4.8: Write Bridge Code

> **Who:** 👨‍💻 Developer

Create the bridge project:

```
teams-bridge/
├── function_app.py         # Azure Functions v2 entry point
├── host.json               # Functions host config
├── requirements.txt        # Python dependencies
├── .funcignore             # Exclude from deployment
├── bot/
│   ├── __init__.py         # Exports CarSearchBot
│   └── car_search_bot.py   # ActivityHandler → Foundry agent bridge
└── teams-manifest/
    ├── manifest.json       # Teams app manifest
    ├── color.png           # 192x192 icon
    └── outline.png         # 32x32 icon
```

**requirements.txt:**
```
azure-functions
botbuilder-core
botbuilder-integration-aiohttp
azure-identity
requests
```

**function_app.py:**
```python
import os
import json
import logging
import traceback
import azure.functions as func
from botbuilder.core import BotFrameworkAdapterSettings, BotFrameworkAdapter
from botbuilder.schema import Activity
from botframework.connector.auth import SimpleChannelProvider
from bot import CarSearchBot

SETTINGS = BotFrameworkAdapterSettings(
    app_id=os.environ.get("MICROSOFT_APP_ID", ""),
    app_password=os.environ.get("MICROSOFT_APP_PASSWORD", ""),
    channel_auth_tenant=os.environ.get("MICROSOFT_APP_TENANT_ID", ""),
    channel_provider=SimpleChannelProvider(),
)
ADAPTER = BotFrameworkAdapter(SETTINGS)
BOT = CarSearchBot()

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

@app.route(route="messages", methods=["POST"])
async def messages(req: func.HttpRequest) -> func.HttpResponse:
    ct = req.headers.get("Content-Type", "")
    if "application/json" not in ct:
        return func.HttpResponse(status_code=415)
    body = req.get_json()
    activity = Activity().deserialize(body)
    auth_header = req.headers.get("Authorization", "")
    try:
        response = await ADAPTER.process_activity(activity, auth_header, BOT.on_turn)
        if response:
            return func.HttpResponse(
                body=json.dumps(response.body),
                status_code=response.status,
                mimetype="application/json",
            )
        return func.HttpResponse(status_code=201)
    except Exception as e:
        logging.error(f"[messages] {e}")
        return func.HttpResponse(status_code=500)

@app.route(route="health", methods=["GET"])
async def health(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse(
        body=json.dumps({"status": "ok"}),
        status_code=200,
        mimetype="application/json",
    )
```

**car_search_bot.py:**
```python
import os
import json
import logging
import requests
from botbuilder.core import ActivityHandler, TurnContext
from botbuilder.schema import Activity, ActivityTypes
from azure.identity import ManagedIdentityCredential, DefaultAzureCredential

logger = logging.getLogger("teams-bridge.bot")

FOUNDRY_PROJECT_ENDPOINT = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "")
AGENT_NAME = os.environ.get("AGENT_NAME", "")

# ManagedIdentityCredential in Azure, DefaultAzureCredential for local dev
try:
    _credential = ManagedIdentityCredential()
    _credential.get_token("https://ai.azure.com/.default")
except Exception:
    _credential = DefaultAzureCredential()

# Multi-turn session tracking (in-memory; use Table Storage for production)
_sessions: dict[str, str] = {}


class CarSearchBot(ActivityHandler):
    async def on_message_activity(self, turn_context: TurnContext):
        user_text = turn_context.activity.text or ""
        conversation_id = turn_context.activity.conversation.id

        # Typing indicator (MUST be Activity object, not dict)
        await turn_context.send_activity(Activity(type=ActivityTypes.typing))

        # Call Foundry hosted agent
        reply_text = _invoke_agent(user_text, conversation_id)
        await turn_context.send_activity(reply_text)

    async def on_members_added_activity(self, members_added, turn_context: TurnContext):
        for member in members_added:
            if member.id != turn_context.activity.recipient.id:
                await turn_context.send_activity("Hello! I can help you search for cars. What are you looking for?")


def _invoke_agent(user_message: str, conversation_id: str) -> str:
    """Call the Foundry hosted agent and return the text response."""
    # ⚠️ Endpoint-scoped route (NOT just /responses)
    url = f"{FOUNDRY_PROJECT_ENDPOINT}/agents/{AGENT_NAME}/endpoint/protocols/openai/responses"

    token = _credential.get_token("https://ai.azure.com/.default")

    payload = {"input": user_message, "stream": False}

    # Multi-turn: include previous_response_id if exists
    prev_id = _sessions.get(conversation_id)
    if prev_id:
        payload["previous_response_id"] = prev_id

    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token.token}",
            "Content-Type": "application/json",
            "Foundry-Features": "hosted-agents",  # ⚠️ Required header
        },
        params={"api-version": "v1"},  # ⚠️ NOT Azure preview dates
        json=payload,
        timeout=120,
    )

    if resp.status_code != 200:
        logger.error(f"Agent returned {resp.status_code}: {resp.text[:500]}")
        return "Sorry, I couldn't process your request. Please try again."

    data = resp.json()

    # Store response ID for multi-turn
    if "id" in data:
        _sessions[conversation_id] = data["id"]

    # Extract text from Responses protocol output
    texts = []
    for item in data.get("output", []):
        if item.get("type") == "message":
            for part in item.get("content", []):
                if part.get("type") == "output_text":
                    texts.append(part.get("text", ""))

    return "\n".join(texts) if texts else "I received your message but had no response."
```

> **⚠️ Three critical patterns in the bot code:**
> 1. **Token scope:** `https://ai.azure.com/.default` (NOT `cognitiveservices.azure.com`)
> 2. **Endpoint path:** `/agents/{name}/endpoint/protocols/openai/responses` (NOT `/agents/{name}/responses`)
> 3. **Headers:** Must include `Foundry-Features: hosted-agents`

### Step 4.9: Deploy Bridge

> **Who:** 👨‍💻 Developer

```powershell
cd teams-bridge

# Install Azure Functions Core Tools (if not already installed)
npm install -g azure-functions-core-tools@4

# Deploy with remote build (installs pip packages on Linux)
func azure functionapp publish <bridge-function-name> --python --build remote
```

> **⚠️ If `func` not found:** Use full path: `& "$((npm root -g).Trim())\azure-functions-core-tools\bin\func.exe" azure functionapp publish ...`

### Step 4.10: Test via Web Chat

> **Who:** 👨‍💻 Developer

1. Azure Portal → `<bot-name>` → **Test in Web Chat**
2. Send a greeting → verify welcome message
3. Send a search query → verify agent responds with results
4. Send a follow-up → verify multi-turn context is maintained

> **🛑 If Web Chat shows no response (bot silently drops messages):**
>
> | Symptom | Likely Cause | Fix (ask Architect) |
> |---------|-------------|---------------------|
> | No response at all | Missing service principal | `az ad sp create --id <app-id>` (Step 4.1) |
> | "Sorry, something went wrong" | Wrong token scope or endpoint | Verify bot code uses `ai.azure.com` scope + endpoint-scoped route |
> | 401 errors in Function App logs | Missing RBAC roles | Verify 3 roles on Function App MI (Step 4.4) |
> | 400/404 from agent | Wrong endpoint path | Must use `/endpoint/protocols/openai/responses?api-version=v1` |

### Step 4.11: Teams App Manifest (Optional — requires M365 license)

> **Who:** 👨‍💻 Developer creates manifest, ☁️ Cloud Architect approves sideloading

**manifest.json:**
```json
{
  "$schema": "https://developer.microsoft.com/en-us/json-schemas/teams/v1.17/MicrosoftTeams.schema.json",
  "manifestVersion": "1.17",
  "version": "1.0.0",
  "id": "<bot-app-id>",
  "name": { "short": "<bot-display-name>" },
  "description": { "short": "<one-line description>" },
  "bots": [{
    "botId": "<bot-app-id>",
    "scopes": ["personal", "team", "groupChat"]
  }],
  "validDomains": ["<bridge-function-name>.azurewebsites.net"]
}
```

Package `manifest.json` + `color.png` (192×192) + `outline.png` (32×32) into a `.zip`.

**Cloud Architect:** Enable sideloading in Teams Admin Center → **Teams apps** → **Setup policies** → allow "Upload custom apps".

**Developer:** Teams → Apps → **Upload a custom app** → select the `.zip`.

---

### ✅ Phase 4 Checkpoint

| Item | Status |
|------|--------|
| Bridge code written and committed | ☐ |
| Bridge deployed to Function App | ☐ |
| Web Chat responds to messages | ☐ |
| Tool calls work end-to-end (search query returns results) | ☐ |
| Multi-turn conversation works | ☐ |
| Teams app sideloaded (if applicable) | ☐ |

---

## Quick Reference — Who Does What

| Step | ☁️ Cloud Architect | 👨‍💻 Developer |
|------|-------------------|---------------|
| Create Azure resources (RG, Foundry, ACR, Bot, Function App) | ✅ | |
| Assign RBAC roles | ✅ | |
| Create Entra ID app registration + service principal | ✅ | |
| Configure Function App settings (secrets) | ✅ | |
| Share resource names + credentials | ✅ | |
| Set up VS Code + extensions | | ✅ |
| Write agent code + tools | | ✅ |
| Test locally | | ✅ |
| Build + push Docker image (or CI/CD) | | ✅ |
| Create hosted agent in Foundry | | ✅ |
| Provide agent MI + blueprint MI IDs | | ✅ |
| Assign Azure AI User to agent MIs | ✅ | |
| Write bridge code | | ✅ |
| Deploy bridge via func CLI | | ✅ |
| Test Web Chat | | ✅ |
| Enable Teams sideloading policy | ✅ | |
| Sideload Teams app | | ✅ |

---

## Troubleshooting Quick Reference

| Error | Who Fixes | Action |
|-------|----------|--------|
| `AuthorizationFailed` on any `az` command | ☁️ Architect | Verify role assignments for developer |
| `ImageError` on agent creation | ☁️ Architect | Verify Project MI → AcrPull on ACR |
| Agent invoke returns auth error | ☁️ Architect | Verify Agent MI → Azure AI User on project |
| `DefaultAzureCredential` fails locally | 👨‍💻 Developer | Run `az login`, add Azure CLI to PATH |
| Bridge returns 404 | 👨‍💻 Developer | Set `AzureWebJobsFeatureFlags=EnableWorkerIndexing` |
| Bridge returns 500 | 👨‍💻 Developer | Check Function App logs; fix import errors |
| Bot receives messages but no reply | ☁️ Architect | Create service principal: `az ad sp create --id <app-id>` |
| 401 calling Foundry agent from bridge | ☁️ Architect | Verify 3 RBAC roles on Function App MI |
| 400/404 calling Foundry agent | 👨‍💻 Developer | Fix endpoint path + api-version + Foundry-Features header |
| Teams "app not available" | ☁️ Architect | Enable sideloading in Teams Admin Center |

---

## Appendix — Complete RBAC Summary

All role assignments required for the full deployment:

```
Developer (user):
  ├── Reader                    → Resource Group
  ├── Azure AI Developer        → Foundry Account
  └── AcrPush                   → ACR (or CI/CD SP instead)

CI/CD Service Principal:
  └── AcrPush                   → ACR

Foundry Project MI (auto-created):
  ├── AcrPull                   → ACR
  └── Azure AI User             → Foundry Account

Agent MI (auto-created on agent create):
  └── Azure AI User             → Foundry Project

Blueprint MI (auto-created on agent create):
  └── Azure AI User             → Foundry Project

Function App MI (auto-created on identity assign):
  ├── Cognitive Services User   → Foundry Account
  ├── Azure AI Developer        → Foundry Account
  └── Azure AI User             → Foundry Account

Bot App Registration:
  └── Service Principal created → Tenant (no role, just SP existence)
```

**Total role assignments: 12** (across 6 identities)
