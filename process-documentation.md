# Hosted Agent Deployment to Azure Foundry — Process Documentation

**Project:** Car Search AI Agent  
**Date:** May 9, 2026  
**Author:** Aditya Vemuri  
**Status:** ✅ Successfully Deployed  
**Audience:** Azure Administrators, Architects, Technical Leads  

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture Overview](#2-architecture-overview)
3. [Azure Resource Inventory](#3-azure-resource-inventory)
4. [Phase 1 — Application Development](#4-phase-1--application-development)
5. [Phase 2 — Model Deployment](#5-phase-2--model-deployment)
6. [Phase 3 — Local Testing](#6-phase-3--local-testing)
7. [Phase 4 — Container Build & Push to ACR](#7-phase-4--container-build--push-to-acr)
8. [Phase 5 — Hosted Agent Deployment (The Hard Part)](#8-phase-5--hosted-agent-deployment-the-hard-part)
9. [Root Cause Analysis — Image Pull Failure](#9-root-cause-analysis--image-pull-failure)
10. [Final Working Configuration](#10-final-working-configuration)
11. [Cost Analysis](#11-cost-analysis)
12. [Lessons Learned](#12-lessons-learned)
13. [Phase 6 — Teams Integration (Bot Service Bridge)](#13-phase-6--teams-integration-bot-service-bridge)
14. [Root Cause Analysis — Foundry Hosted Agent Endpoint Discovery](#14-root-cause-analysis--foundry-hosted-agent-endpoint-discovery)
15. [Enterprise Alternative — M365 Declarative Agent](#15-enterprise-alternative--m365-declarative-agent)
16. [Appendix A — Complete Command Reference](#appendix-a--complete-command-reference)
17. [Appendix B — Identity & RBAC Matrix](#appendix-b--identity--rbac-matrix)
18. [Appendix C — Troubleshooting Decision Tree](#appendix-c--troubleshooting-decision-tree)

---

## 1. Executive Summary

This document details the end-to-end process of deploying a custom AI agent (car search assistant) to **Azure Foundry** as a **hosted agent**. The agent uses the **Microsoft Agent Framework** (Python), is containerized with Docker, hosted in **Azure Container Registry (ACR)**, and served by the Foundry Agent Service platform.

### What Took Time

The application code was straightforward. **~80% of the debugging effort was spent on Azure identity and permission configuration** — specifically, understanding which managed identity the Foundry platform uses to pull container images from ACR. This document captures every dead end so your team doesn't repeat them.

### The One-Line Root Cause

> **The Foundry _project_ has its own system-assigned managed identity, separate from the Foundry _account_ (Cognitive Services resource) managed identity. ACR pull permissions must be assigned to the _project_ MI, not the account MI.**

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Azure Foundry                         │
│                                                          │
│  ┌──────────────────────┐    ┌────────────────────────┐ │
│  │  Foundry Account     │    │  Azure Container       │ │
│  │  (Cognitive Services)│    │  Registry (ACR)        │ │
│  │                      │    │                        │ │
│  │  MI: <account-mi>...     │    │  Image:                │ │
│  │  (NOT used for pull) │    │  car-search-agent:tag  │ │
│  │                      │    │                        │ │
│  │  ┌────────────────┐  │    └────────────────────────┘ │
│  │  │ Foundry Project│  │              ▲                 │
│  │  │ "car-search"   │  │              │ AcrPull         │
│  │  │                │  │              │                 │
│  │  │ MI: <project-mi>.. │──┘──────────────┘                 │
│  │  │ (THIS pulls!)  │                                   │
│  │  │                │                                   │
│  │  │ ┌────────────┐ │     ┌────────────────────────┐   │
│  │  │ │Hosted Agent│ │     │  Model Deployment      │   │
│  │  │ │            │ │────▶│  gpt-4.1-mini          │   │
│  │  │ │Agent MI:   │ │     └────────────────────────┘   │
│  │  │ │<agent-mi>... │ │                                   │
│  │  │ └────────────┘ │                                   │
│  │  └────────────────┘                                   │
│  └──────────────────────┘                                │
│                                                          │
│  ┌──────────────────────┐                                │
│  │  Capability Host     │                                │
│  │  (default)           │                                │
│  │  kind: Agents        │                                │
│  └──────────────────────┘                                │
└─────────────────────────────────────────────────────────┘
```

### Key Identities (Three Separate Managed Identities!)

| Identity | Principal ID | What It Is | What It Does |
|----------|-------------|------------|--------------|
| **Account MI** | `<account-mi-principal-id>` | Cognitive Services system-assigned MI | Model inference at account level. Does NOT pull images. |
| **Project MI** | `<project-mi-principal-id>` | Project system-assigned MI | **Pulls container images from ACR**. This is the critical one. |
| **Agent MI** | `<agent-mi-principal-id>` | Per-agent identity (created by platform) | Runtime identity for the agent container. Needs Azure AI User on the project. |
| **Blueprint MI** | `<blueprint-mi-principal-id>` | Agent blueprint identity | Companion identity for agent. Also needs Azure AI User on the project. |

> **⚠️ Critical Insight:** The Foundry project is a child ARM resource of the Cognitive Services account (`Microsoft.CognitiveServices/accounts/projects/car-search`). It has its **own** system-assigned managed identity. This is not obvious from the Azure Portal, and the two are easily confused.

---

## 3. Azure Resource Inventory

| Resource | Type | Name | Resource Group | Region | SKU |
|----------|------|------|---------------|--------|-----|
| Foundry Account | Microsoft.CognitiveServices/accounts | car-search-resource | foundry-experimentation | eastus2 | S0 |
| Foundry Project | Microsoft.CognitiveServices/accounts/projects | car-search | foundry-experimentation | eastus2 | — |
| Container Registry | Microsoft.ContainerRegistry/registries | adityaacr | foundry-experimentation | eastus2 | **Basic** |
| Model Deployment | (within account) | gpt-4.1-mini | — | eastus2 | GlobalStandard |
| Capability Host | Microsoft.CognitiveServices/accounts/capabilityHosts | default | — | — | — |

**Subscription:** `<your-subscription-id>`  
**Tenant:** `<your-tenant-id>`

---

## 4. Phase 1 — Application Development

### 4.1 Technology Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Language | Python 3.12 | Best SDK support for Microsoft Agent Framework |
| Framework | Microsoft Agent Framework | Official Foundry agent SDK |
| Protocol | Responses v1.0.0 | Conversational chatbot pattern with streaming |
| Model | gpt-4.1-mini | Most cost-effective for function calling ($0.15/1M input tokens) |
| Data Source | Mock data (500 listings) | Learning project; clean interface for future real API swap |

### 4.2 Project Structure

```
af-car-search-agent/
├── main.py              # Agent definition, tools, server startup
├── car_data.py          # Mock car listing service (500 listings, haversine distance)
├── agent.yaml           # Agent metadata for Foundry
├── Dockerfile           # Container image definition
├── requirements.txt     # Python dependencies
├── .env                 # Local environment variables
└── .vscode/
    ├── tasks.json       # Run task with Azure CLI on PATH
    └── launch.json      # Debug attach configuration (debugpy on 5679)
```

### 4.3 Key Files Created

**requirements.txt:**
```
agent-framework
agent-framework-foundry-hosting
azure-identity
python-dotenv
pydantic
debugpy
agent-dev-cli
```

**Dockerfile:**
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . user_agent/
WORKDIR /app/user_agent
RUN if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
EXPOSE 8088
CMD ["python", "main.py"]
```

> **Why port 8088?** The Foundry hosted agent platform expects containers to serve traffic on port 8088. This is not configurable.

**agent.yaml:**
```yaml
name: car-search-agent
description: AI-powered car search assistant
template:
  kind: hosted
  protocols:
    responses: "1.0.0"    # Must be "1.0.0", NOT "1.0"
  environment_variables:
    - name: AZURE_AI_MODEL_DEPLOYMENT_NAME
      description: Model deployment name
```

> **⚠️ Protocol Version:** The version must be `"1.0.0"` (semantic version). Using `"1.0"` causes a silent deployment failure. We initially had `"1.0"` and had to fix it.

> **⚠️ FOUNDRY_PROJECT_ENDPOINT:** Do NOT declare this in `agent.yaml` or `environment_variables`. It is a **platform-injected** reserved variable that Foundry sets automatically at runtime. Declaring it manually causes conflicts.

---

## 5. Phase 2 — Model Deployment

### What We Ran

```bash
# Deploy gpt-4.1-mini to the Foundry account
az cognitiveservices account deployment create \
  --name car-search-resource \
  --resource-group foundry-experimentation \
  --deployment-name gpt-4.1-mini \
  --model-name gpt-4.1-mini \
  --model-version "2025-04-14" \
  --model-format OpenAI \
  --sku-capacity 10 \
  --sku-name "GlobalStandard"
```

**Result:** ✅ Succeeded. Model deployed and accessible via the project endpoint.

### Why This Model

| Model | Input Cost (1M tokens) | Output Cost (1M tokens) | Function Calling | Monthly Cost Estimate |
|-------|----------------------|------------------------|-----------------|----------------------|
| gpt-4.1-mini | $0.40 | $1.60 | ✅ Excellent | ~$1-5/month |
| gpt-4o-mini | $0.15 | $0.60 | ✅ Good | ~$0.50-3/month |
| gpt-4o | $2.50 | $10.00 | ✅ Excellent | ~$10-30/month |

We chose **gpt-4.1-mini** for the best balance of capability and cost. For a car search agent with function calling, it performs equivalently to larger models at a fraction of the cost.

---

## 6. Phase 3 — Local Testing

### 6.1 Setting Up the Python Environment

```powershell
# Create virtual environment
python -m venv .venv

# Activate
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

**Result:** ✅ All packages installed successfully.

### 6.2 Azure CLI Authentication

```powershell
# Login to Azure (device code flow for environments without browser redirect)
az login --use-device-code
```

**Result:** ✅ Authenticated successfully.

### 6.3 PATH Issue with Azure CLI

**Problem:** `DefaultAzureCredential` failed because `az` was not on PATH in the VS Code terminal.

```
DefaultAzureCredential failed to retrieve a token from the included credentials.
```

**Fix:** Added Azure CLI to PATH in the VS Code task configuration:

```json
// .vscode/tasks.json
{
  "label": "Run Agent HTTP Server",
  "type": "shell",
  "command": "python main.py",
  "options": {
    "env": {
      "PATH": "C:\\Program Files\\Microsoft SDKs\\Azure\\CLI2\\wbin;${env:PATH}"
    }
  }
}
```

### 6.4 Running the Agent Locally

```powershell
# With Azure CLI on PATH
$env:PATH = "C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin;$env:PATH"
python main.py
```

**Result:** ✅ Agent started on `http://localhost:8088`.

### 6.5 End-to-End Local Test

```powershell
# Test the Responses protocol endpoint
Invoke-RestMethod -Uri "http://localhost:8088/responses" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"input": "Find Honda SUVs near 90210 under $30000", "stream": false}'
```

**Result:** ✅ Agent called `search_cars` tool, returned 3 Honda results with prices, distances, and dealer info.

### 6.6 Debug with AI Toolkit Agent Inspector

```powershell
# F5 launch with debugpy attach on port 5679
# Agent Inspector provides interactive UI for testing tool calls
```

**Result:** ✅ Full debug loop working — breakpoints, tool inspection, streaming responses.

---

## 7. Phase 4 — Container Build & Push to ACR

### 7.1 Creating the Azure Container Registry

```powershell
az acr create --name adityaacr --resource-group foundry-experimentation `
  --location eastus2 --sku Basic
```

**Result:** ✅ ACR created. Initially created as **Standard**, later downgraded to **Basic** (sufficient for hosted agents, saves ~$15/month).

> **Note on SKU:** Basic ACR is sufficient for hosted agents. The platform only needs to pull the image — it doesn't require geo-replication, content trust, or other premium features. **Basic = ~$5/month, Standard = ~$20/month**.

### 7.2 Building the Docker Image

```powershell
# Build for linux/amd64 (REQUIRED — Foundry platform is x86_64)
docker build --platform linux/amd64 -t car-search-agent:latest .
```

**Result:** ✅ Image built successfully.

> **⚠️ Platform Requirement:** If building on Apple Silicon (M1/M2) or ARM-based machines, you MUST specify `--platform linux/amd64`. The Foundry hosting platform only supports x86_64 images.

### 7.3 Logging into ACR

```powershell
az acr login --name adityaacr
```

**Result:** ✅ Login succeeded.

### 7.4 Tagging and Pushing the Image

```powershell
# Tag with timestamp for reproducible deployments (avoid :latest)
$tag = Get-Date -Format "yyyyMMddHHmm"
docker tag car-search-agent:latest adityaacr.azurecr.io/car-search-agent:$tag
docker push adityaacr.azurecr.io/car-search-agent:$tag
```

**Result:** ✅ Image pushed. Final image: `adityaacr.azurecr.io/car-search-agent:202605091850`

### 7.5 Verifying the Image in ACR

```powershell
az acr repository show-tags --name adityaacr --repository car-search-agent -o table
```

**Result:** ✅ Tags `202605091808` and `202605091850` visible.

---

## 8. Phase 5 — Hosted Agent Deployment (The Hard Part)

This section documents the iterative debugging process. **This is where 80% of the time was spent.**

### 8.1 Initial Agent Creation — ❌ FAILED

```python
# Via Foundry MCP tool (equivalent to SDK create_version call)
agent_create(
    agentName="car-search-agent",
    definition={
        "kind": "hosted",
        "image": "adityaacr.azurecr.io/car-search-agent:202605091850",
        "cpu": "1",
        "memory": "2Gi",
        "container_protocol_versions": [
            {"protocol": "responses", "version": "1.0.0"}
        ],
        "environment_variables": {
            "AZURE_AI_MODEL_DEPLOYMENT_NAME": "gpt-4.1-mini"
        }
    }
)
```

**Error:**
```json
{
  "error": {
    "code": "agent_version_failed",
    "message": "Agent version provisioning failed: [ImageError] Failed to pull container image. Please check the image URI and ACR permissions, then retry. (image: adityaacr.azurecr.io)"
  }
}
```

**Observation:** The error shows the ACR hostname but truncates the repository and tag — indicating the platform couldn't even authenticate to the registry, let alone find the specific image.

---

### 8.2 Debugging Attempt 1: ACR Admin Credentials — ❌ DID NOT HELP

**Hypothesis:** Maybe the platform needs admin credentials to pull images.

```powershell
# Enable admin user on ACR
az acr update --name adityaacr --admin-enabled true

# Get admin credentials
az acr credential show --name adityaacr
```

**What we tried:** Created a connection with `authType: CustomKeys` using admin username/password.

```json
{
  "properties": {
    "category": "ContainerRegistry",
    "target": "https://adityaacr.azurecr.io",
    "authType": "CustomKeys",
    "credentials": {
      "keys": {
        "username": { "value": "adityaacr" },
        "password": { "value": "<admin-password>" }
      }
    }
  }
}
```

**Result:** ❌ Still failed with same `ImageError`. The platform does not use admin credentials — it uses managed identity RBAC.

**Why this was wrong:** The official Microsoft documentation explicitly states: "Admin user should NOT be enabled." The platform authenticates via managed identity + RBAC role assignments, not username/password.

**Cleanup:**
```powershell
az acr update --name adityaacr --admin-enabled false
```

---

### 8.3 Debugging Attempt 2: AcrPull on Account MI — ❌ WRONG IDENTITY

**Hypothesis:** The Cognitive Services account's managed identity needs AcrPull on the ACR.

```powershell
# Assigned AcrPull to account MI (<account-mi>)
az role assignment create \
  --assignee "<account-mi-principal-id>" \
  --role "AcrPull" \
  --scope "/subscriptions/.../Microsoft.ContainerRegistry/registries/adityaacr"
```

**Result:** ❌ Still failed. The account MI is NOT the identity that pulls images.

**Why this was wrong:** We assumed the Cognitive Services account was the identity pulling images. In reality, the **Foundry project** (a child resource) has its own managed identity, and THAT is what the platform uses for image pulls. The Azure Portal makes this confusing because the project doesn't surface prominently in the IAM blade.

---

### 8.4 Debugging Attempt 3: AcrPull on Agent MI — ❌ WRONG IDENTITY

**Hypothesis:** Maybe the per-agent managed identity pulls the image.

```powershell
# Assigned AcrPull to per-agent MI (<agent-mi>)
az role assignment create \
  --assignee "<agent-mi-principal-id>" \
  --role "AcrPull" \
  --scope "/subscriptions/.../Microsoft.ContainerRegistry/registries/adityaacr"

# Also assigned to blueprint MI (<blueprint-mi>)
az role assignment create \
  --assignee "<blueprint-mi-principal-id>" \
  --role "AcrPull" \
  --scope "/subscriptions/.../Microsoft.ContainerRegistry/registries/adityaacr"
```

**Result:** ❌ Still failed. The agent identity is the **runtime** identity the container uses after it starts. It is NOT used to pull the image.

**Why this was wrong:** The agent identity is created by the platform when the agent is first created. It's the identity injected into the running container. The image pull happens BEFORE the container starts, so it uses a different identity — the project MI.

---

### 8.5 Debugging Attempt 4: ABAC / Container Registry Repository Reader — ❌ WRONG MODE

**Hypothesis:** Maybe the ACR needs ABAC mode enabled for the "Container Registry Repository Reader" data-action role.

```powershell
# Switch ACR to ABAC repository permissions
az acr update --name adityaacr --role-assignment-mode AbacRepositoryPermissions

# Assign Container Registry Repository Reader to account MI
az role assignment create \
  --assignee "<account-mi-principal-id>" \
  --role "Container Registry Repository Reader" \
  --scope "/subscriptions/.../Microsoft.ContainerRegistry/registries/adityaacr"
```

**Result:** ❌ The role assignment succeeded, but the image pull still failed because we were still assigning to the wrong identity (account MI instead of project MI).

**Why we tried this:** The official docs say "Container Registry Repository Reader (preferred because it models the pull as a data action)." This role requires ABAC mode. But ABAC vs Legacy mode is orthogonal to the identity issue — even with the right mode, the wrong identity won't work.

**Cleanup:**
```powershell
# Reverted to legacy mode (simpler, AcrPull works without ABAC)
az acr update --name adityaacr --role-assignment-mode LegacyRegistryPermissions
```

---

### 8.6 Debugging Attempt 5: Anonymous Pull — ❌ NOT RECOMMENDED

**Hypothesis:** As a brute-force test, enable anonymous pull to see if the image itself is reachable.

```powershell
az acr update --name adityaacr --sku Standard --anonymous-pull-enabled true
```

> **Note:** Anonymous pull requires Standard SKU or higher (not available on Basic).

**Result:** ❌ Still failed because the Foundry platform doesn't use anonymous pull — it expects to authenticate via the project MI.

**Why this was wrong:** Anonymous pull bypasses authentication entirely, which isn't how the platform works. It also violates security best practices. Even if it had worked, it would have been the wrong solution.

**Cleanup:**
```powershell
az acr update --name adityaacr --anonymous-pull-enabled false
az acr update --name adityaacr --sku Basic  # Downgrade back to save cost
```

---

### 8.7 Debugging Attempt 6: ACR Connections — Tried Multiple Formats

We tried three different connection types between the Foundry project and ACR:

#### Connection Type A: CustomKeys (admin credentials) — ❌

```json
{
  "authType": "CustomKeys",
  "credentials": {
    "keys": {
      "username": { "value": "adityaacr" },
      "password": { "value": "<admin-password>" }
    }
  }
}
```

**Result:** ❌ Platform doesn't use credential-based auth.

#### Connection Type B: ManagedIdentity with workspace MI — ❌ (Still wrong identity)

```json
{
  "authType": "AAD",
  "credentials": {
    "clientId": "8e68668d-28da-4a42-871b-b533fa21581a"
  },
  "metadata": {
    "ResourceId": "/subscriptions/.../registries/adityaacr"
  },
  "useWorkspaceManagedIdentity": true
}
```

**Result:** ❌ Used the account MI, not the project MI.

#### Connection Type C: AAD (final working version) — ✅

```json
{
  "authType": "AAD",
  "category": "ContainerRegistry",
  "target": "https://adityaacr.azurecr.io",
  "isSharedToAll": true,
  "metadata": {
    "ResourceId": "/subscriptions/.../registries/adityaacr"
  }
}
```

**Result:** ✅ This connection format works, BUT it only works when combined with the correct RBAC on the project MI (see Section 8.9).

> **Note:** The connection alone is insufficient. You need BOTH the connection AND the RBAC role assignment on the correct identity.

---

### 8.8 Debugging Attempt 7: Capability Host — ✅ REQUIRED

**Discovery:** The Foundry account needs a **Capability Host** resource to enable hosted agent infrastructure.

```powershell
# Check if capability host exists
$token = az account get-access-token --resource https://management.azure.com --query accessToken -o tsv

Invoke-RestMethod -Uri "https://management.azure.com/subscriptions/<your-subscription-id>/providers/Microsoft.CognitiveServices/accounts/car-search-resource/capabilityHosts/default?api-version=2025-04-01-preview" `
  -Headers @{ Authorization = "Bearer $token" }
```

**Result:** 404 — Capability host did not exist!

**Fix:**
```powershell
$body = @{
  properties = @{
    capabilityHostKind = "Agents"
  }
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Uri "https://management.azure.com/subscriptions/<your-subscription-id>/providers/Microsoft.CognitiveServices/accounts/car-search-resource/capabilityHosts/default?api-version=2025-04-01-preview" `
  -Headers @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" } `
  -Method PUT `
  -Body $body
```

**Result:** ✅ Capability host created. `provisioningState: Succeeded`.

**Why this is needed:** The capability host enables the agent hosting infrastructure within the Foundry account. Without it, the platform cannot provision container instances for your hosted agents. This is a one-time setup per Foundry account.

> **Note:** The `enablePublicHostingEnvironment` property was mentioned in some documentation but did not appear in our created capability host. It may be set to `true` by default for public-network scenarios.

---

### 8.9 THE FIX — Assigning AcrPull to the Project MI — ✅ SUCCESS

**The breakthrough:** Discovering that the Foundry project has its OWN system-assigned managed identity, separate from the account.

```powershell
# Step 1: Discover the project's managed identity
$token = az account get-access-token --resource https://management.azure.com --query accessToken -o tsv

$projUrl = "https://management.azure.com/subscriptions/<your-subscription-id>/providers/Microsoft.CognitiveServices/accounts/car-search-resource/projects/car-search?api-version=2025-04-01-preview"

$proj = Invoke-RestMethod -Uri $projUrl -Headers @{ Authorization = "Bearer $token" }
$proj.identity

# Output:
# principalId: <project-mi-principal-id>  ← THIS IS THE KEY!
# tenantId: <your-tenant-id>
# type: SystemAssigned
```

```powershell
# Step 2: Assign AcrPull to the PROJECT MI on the ACR
az role assignment create `
  --assignee "<project-mi-principal-id>" `
  --role "AcrPull" `
  --scope "/subscriptions/<your-subscription-id>/resourceGroups/foundry-experimentation/providers/Microsoft.ContainerRegistry/registries/adityaacr"
```

**Result:** ✅ Role assignment created.

```powershell
# Step 3: Also assign Azure AI User to agent identities at PROJECT scope
az role assignment create `
  --assignee "<agent-mi-principal-id>" `
  --role "Azure AI User" `
  --scope "/subscriptions/.../accounts/car-search-resource/projects/car-search"

az role assignment create `
  --assignee "<blueprint-mi-principal-id>" `
  --role "Azure AI User" `
  --scope "/subscriptions/.../accounts/car-search-resource/projects/car-search"
```

**Result:** ✅ Both role assignments created.

```powershell
# Step 4: Assign Azure AI User to project MI at ACCOUNT scope (for model inference proxy)
az role assignment create `
  --assignee "<project-mi-principal-id>" `
  --role "Azure AI User" `
  --scope "/subscriptions/.../providers/Microsoft.CognitiveServices/accounts/car-search-resource"
```

**Result:** ✅ Role assignment created.

```powershell
# Step 5: Wait for RBAC propagation (~60 seconds)
Start-Sleep -Seconds 60
```

```powershell
# Step 6: Create a new agent version to trigger a fresh image pull
# (Via Foundry API — agent_update creates a new version)
```

**Result:** ✅ Version 6 created. Status transitioned to `active` within 10 seconds!

---

### 8.10 Successful Invocation — ✅ WORKING

```powershell
# Invoke the deployed agent
# POST to the agent endpoint via Foundry API
{
  "agentName": "car-search-agent",
  "inputText": "Search near zip code 90210, Honda SUVs under $30000",
  "sessionId": "sess-success-001"
}
```

**Result:**
```
Found 2 Honda SUVs near zip code 90210 under $30,000:

1. 2019 Honda CR-V
   - Price: $18,785
   - Mileage: 13,514 miles
   - Color: Black
   - Fuel: Gas
   - Dealer: Suburban Motors (Los Angeles, CA)
   - Distance: 9.7 miles away

2. 2023 Honda CR-V Hybrid
   - Price: $27,936
   - Mileage: 24,739 miles
   - Color: Yellow
   - Fuel: Hybrid
   - Dealer: Asbury Automotive (Calabasas, CA)
   - Distance: 20.8 miles away
```

✅ Tool calling worked. ✅ Mock data returned. ✅ Agent formatted response correctly.

---

## 9. Root Cause Analysis — Image Pull Failure

### The Problem

For approximately 2 hours, every agent version failed with:

```
[ImageError] Failed to pull container image. Please check the image URI and ACR permissions, then retry. (image: adityaacr.azurecr.io)
```

### Why It Was Hard to Diagnose

1. **Three managed identities** — Account MI, Project MI, and Agent MI all exist. The Azure Portal shows the account identity prominently but the project identity is a child resource that requires an ARM API call to discover.

2. **Misleading documentation examples** — Some docs reference "the project managed identity" but don't clarify that it's different from the account identity. When you go to "Identity" in the Azure Portal for the Cognitive Services resource, you see the ACCOUNT identity.

3. **Error message lacks detail** — The error truncates the image path (shows `adityaacr.azurecr.io` without the repo:tag), doesn't specify which identity was used for the pull attempt, and doesn't distinguish between "can't authenticate" vs "image not found."

4. **Agent status shows `active` even when image pull fails** — The version status can show `active` on a `GET` but then fail on `invoke` with `agent_version_failed`. The status field is not always a reliable indicator.

### How to Find the Project MI

The project MI is **not visible** in the Azure Portal under the Cognitive Services resource's "Identity" blade. You must query the ARM API directly:

```powershell
$token = az account get-access-token --resource https://management.azure.com --query accessToken -o tsv

$url = "https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.CognitiveServices/accounts/{account}/projects/{project}?api-version=2025-04-01-preview"

$proj = Invoke-RestMethod -Uri $url -Headers @{ Authorization = "Bearer $token" }
$proj.identity.principalId  # ← This is the MI that pulls images
```

### The Fix (Summary)

Assign `AcrPull` to the **project** managed identity on the ACR registry:

```powershell
az role assignment create \
  --assignee "<project-MI-principalId>" \
  --role "AcrPull" \
  --scope "/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.ContainerRegistry/registries/{acr}"
```

---

## 10. Final Working Configuration

### ACR Configuration

```powershell
az acr show --name adityaacr --query "{sku:sku.name, adminEnabled:adminUserEnabled, publicAccess:publicNetworkAccess, anonPull:anonymousPullEnabled}" -o table
```

| Property | Value | Notes |
|----------|-------|-------|
| SKU | **Basic** | Sufficient for hosted agents. Saves ~$15/month vs Standard. |
| Admin User | **Disabled** | Not needed. Platform uses RBAC. |
| Public Network Access | **Enabled** | **Required.** Private ACR is not supported for hosted agents. |
| Anonymous Pull | **Disabled** | Not needed when RBAC is configured correctly. |
| ARM Token Auth | **Enabled** | Default. Required for MI-based authentication. |
| Role Assignment Mode | **LegacyRegistryPermissions** | Simpler. AcrPull role works without ABAC. |

### RBAC Assignments

| Identity | Role | Scope | Purpose |
|----------|------|-------|---------|
| Project MI (`<project-mi>...`) | **AcrPull** | ACR registry | Image pull (THE critical one) |
| Project MI (`<project-mi>...`) | **Azure AI User** | Foundry account | Model inference proxy |
| Agent MI (`<agent-mi>...`) | **Azure AI User** | Foundry project | Runtime model access |
| Blueprint MI (`<blueprint-mi>...`) | **Azure AI User** | Foundry project | Runtime model access |

### Connection Configuration

| Property | Value |
|----------|-------|
| Name | adityaacr |
| Category | ContainerRegistry |
| Auth Type | AAD |
| Target | `https://adityaacr.azurecr.io` |
| Is Shared To All | true |
| Metadata.ResourceId | Full ACR ARM resource ID |

### Capability Host

| Property | Value |
|----------|-------|
| Name | default |
| capabilityHostKind | Agents |
| provisioningState | Succeeded |

---

## 11. Cost Analysis

### Monthly Estimated Cost

| Resource | Cost | Notes |
|----------|------|-------|
| ACR Basic | ~$5/month | 10 GB storage included |
| gpt-4.1-mini | ~$1-5/month | Based on ~100-500 conversations/month |
| Foundry hosting | $0 | Compute deprovisioned after 15 min inactivity |
| **Total** | **~$6-10/month** | Well within $30/month budget |

### Cost Optimization Decisions

1. **ACR Basic over Standard** — Saves $15/month. Basic is sufficient for image storage and pull operations.
2. **gpt-4.1-mini over gpt-4o** — 6x cheaper for input tokens, equivalent function-calling capability.
3. **Foundry hosting** — No idle compute cost. Agent infrastructure scales to zero after 15 minutes.

---

## 12. Lessons Learned

### For Azure Administrators

1. **The Foundry project has its own managed identity.** This is separate from the Cognitive Services account identity. When docs say "project managed identity," they mean the child resource's MI, not the parent account's MI.

2. **Query the project MI via ARM API.** It's not visible in the Portal's Identity blade for the parent Cognitive Services resource. Use:
   ```
   GET /subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.CognitiveServices/accounts/{account}/projects/{project}?api-version=2025-04-01-preview
   ```

3. **ACR Basic is sufficient.** Don't pay for Standard or Premium unless you need geo-replication, content trust, or private endpoints (which aren't supported for hosted agents anyway).

4. **Admin credentials are irrelevant.** The platform uses managed identity RBAC exclusively. Don't enable admin user.

5. **Create a Capability Host.** This is a one-time setup per Foundry account. Without it, hosted agent infrastructure cannot be provisioned.

### For Architects

1. **Three-identity model:**
   - **Account MI** → Account-level operations (model management)
   - **Project MI** → Infrastructure operations (image pull, telemetry)
   - **Agent MI** → Runtime operations (model inference, tool access)

2. **RBAC propagation takes ~60 seconds.** After assigning roles, wait before creating new agent versions.

3. **`agent.yaml` protocol version must be semantic versioning** — `"1.0.0"`, not `"1.0"`.

4. **Don't declare `FOUNDRY_PROJECT_ENDPOINT`** in environment_variables — it's platform-injected.

5. **The ACR connection is required** even when RBAC is properly configured. The platform uses both the connection AND the RBAC assignment.

### For Developers

1. **Use timestamped image tags**, not `:latest`, for reproducible deployments.
2. **Build with `--platform linux/amd64`** if you're on ARM hardware.
3. **Port 8088 is mandatory** — the Foundry gateway routes to this port.
4. **`DefaultAzureCredential` needs `az` on PATH** — add the CLI path to your VS Code task or terminal profile.
5. **Test locally first** with `POST http://localhost:8088/responses` before pushing to ACR.

---

## Appendix A — Complete Command Reference

### One-Time Infrastructure Setup

```powershell
# 1. Create ACR (Basic SKU)
az acr create --name <acr-name> --resource-group <rg> --location <region> --sku Basic

# 2. Get Project MI
$token = az account get-access-token --resource https://management.azure.com --query accessToken -o tsv
$proj = Invoke-RestMethod `
  -Uri "https://management.azure.com/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>?api-version=2025-04-01-preview" `
  -Headers @{ Authorization = "Bearer $token" }
$projectMI = $proj.identity.principalId
Write-Host "Project MI: $projectMI"

# 3. Assign AcrPull to Project MI
az role assignment create --assignee $projectMI --role "AcrPull" `
  --scope "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.ContainerRegistry/registries/<acr>"

# 4. Assign Azure AI User to Project MI on Account
az role assignment create --assignee $projectMI --role "Azure AI User" `
  --scope "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>"

# 5. Create Capability Host
$body = '{"properties":{"capabilityHostKind":"Agents"}}' 
Invoke-RestMethod `
  -Uri "https://management.azure.com/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>/capabilityHosts/default?api-version=2025-04-01-preview" `
  -Headers @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" } `
  -Method PUT -Body $body

# 6. Create ACR Connection at Project Level
$connBody = @{
  properties = @{
    category = "ContainerRegistry"
    target = "https://<acr-name>.azurecr.io"
    authType = "AAD"
    isSharedToAll = $true
    metadata = @{
      ResourceId = "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.ContainerRegistry/registries/<acr>"
    }
  }
} | ConvertTo-Json -Depth 5

Invoke-RestMethod `
  -Uri "https://management.azure.com/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>/connections/<acr-name>?api-version=2025-04-01-preview" `
  -Headers @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" } `
  -Method PUT -Body $connBody
```

### Per-Deployment Commands

```powershell
# 1. Build image
docker build --platform linux/amd64 -t <agent-name>:latest .

# 2. Login to ACR
az acr login --name <acr-name>

# 3. Tag and push
$tag = Get-Date -Format "yyyyMMddHHmm"
docker tag <agent-name>:latest <acr-name>.azurecr.io/<agent-name>:$tag
docker push <acr-name>.azurecr.io/<agent-name>:$tag

# 4. Create/update agent version (via SDK or REST)
# See Section 8.10 for API details

# 5. After agent creation, assign Azure AI User to agent identity at Project scope
# The agent identity principal_id is returned in the create response
az role assignment create --assignee <agent-MI> --role "Azure AI User" `
  --scope "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>"
```

---

## Appendix B — Identity & RBAC Matrix

### How to Find Each Identity

| Identity | How to Find | Azure Portal Location |
|----------|------------|----------------------|
| Account MI | `az cognitiveservices account show --name <acct> -g <rg> --query identity.principalId` | Cognitive Services → Identity → System assigned |
| Project MI | ARM API only: `GET .../accounts/<acct>/projects/<proj>?api-version=2025-04-01-preview` → `.identity.principalId` | **Not visible in Portal!** |
| Agent MI | Returned in `agent_create` / `agent_get` response → `.instance_identity.principal_id` | Foundry Portal → Agents |
| Blueprint MI | Returned in `agent_create` / `agent_get` response → `.blueprint.principal_id` | Foundry Portal → Agents |

### Complete RBAC Matrix

```
┌──────────────────┬────────────────┬────────────────────────────┬──────────────────────┐
│     Identity     │      Role      │           Scope            │       Purpose        │
├──────────────────┼────────────────┼────────────────────────────┼──────────────────────┤
│ Project MI       │ AcrPull        │ ACR Registry               │ Container image pull │
│ Project MI       │ Azure AI User  │ Foundry Account            │ Model inference proxy│
│ Agent MI         │ Azure AI User  │ Foundry Project            │ Runtime model access │
│ Blueprint MI     │ Azure AI User  │ Foundry Project            │ Runtime model access │
│ Your User        │ Azure AI User  │ Foundry Project            │ Agent invocation     │
│ Your User        │ Owner/Contrib  │ Resource Group             │ Resource management  │
└──────────────────┴────────────────┴────────────────────────────┴──────────────────────┘
```

---

## Appendix C — Troubleshooting Decision Tree

```
Agent version fails with ImageError
│
├─ Can you see the full image:tag in the error message?
│  │
│  ├─ NO (truncated to just ACR hostname)
│  │  └─ Authentication failure. Check:
│  │     1. Is AcrPull assigned to the PROJECT MI? (most common issue)
│  │     2. Does an ACR connection exist at the project level?
│  │     3. Is ACR public network access enabled?
│  │     4. Has RBAC propagated? (Wait 60 seconds, create new version)
│  │
│  └─ YES (shows full path like adityaacr.azurecr.io/repo:tag)
│     └─ Image not found. Check:
│        1. Does the repository exist? `az acr repository list`
│        2. Does the tag exist? `az acr repository show-tags`
│        3. Was image built for linux/amd64?
│
├─ Error code is "RegistryNotFound"
│  └─ ACR DNS unreachable. Check:
│     1. Is ACR name spelled correctly?
│     2. Is public network access enabled?
│     3. Is ACR in the same region?
│
├─ Error code is "InvalidAcrPullCredentials"
│  └─ MI can't authenticate. Check:
│     1. Is ARM token auth enabled on ACR?
│     2. Is AcrPull on the correct identity (PROJECT MI)?
│
└─ Agent status is "active" but invoke returns agent_version_failed
   └─ Stale version. Create a new version to trigger fresh pull.
```

---

## 13. Phase 6 — Teams Integration (Bot Service Bridge)

### 13.1 Architecture — Option A: Bot Service Bridge (Personal / Non-M365 Accounts)

This pattern connects Microsoft Teams to the Foundry hosted agent through Azure Bot Service and an Azure Function bridge. It works **without** an M365 Copilot license.

```
┌──────────┐     ┌──────────────────┐     ┌─────────────────────┐     ┌─────────────────┐
│  Teams   │────▶│  Azure Bot       │────▶│  Azure Function     │────▶│  Foundry Hosted │
│  User    │◀────│  Service         │◀────│  (Bridge)           │◀────│  Agent          │
│          │     │  car-search-bot  │     │  car-search-bridge  │     │  /responses     │
└──────────┘     └──────────────────┘     └─────────────────────┘     └─────────────────┘
                   F0 (free)               Consumption plan             Port 8088
                   SingleTenant            Python 3.12 / Linux          gpt-4.1-mini
```

**Data Flow:**
1. User sends message in Teams chat
2. Teams routes to Azure Bot Service (via Bot Framework protocol)
3. Bot Service sends HTTP POST to bridge Function (`/api/messages`)
4. Bridge authenticates via Bot Framework SDK, extracts user text
5. Bridge calls Foundry agent endpoint-scoped route with Bearer token (managed identity)
6. Foundry agent processes query, calls tools, returns Responses protocol output
7. Bridge extracts text from response, sends back to Teams via Bot Framework

### 13.2 Azure Resources Created

| Resource | Type | Name | Resource Group | SKU/Tier | Monthly Cost |
|----------|------|------|---------------|----------|--------------|
| Entra ID App Registration | Microsoft.Graph/applications | CarSearchBot | — | — | Free |
| Azure Bot Service | Microsoft.BotService/botServices | car-search-bot | foundry-experimentation | F0 (free) | $0 |
| Azure Function App | Microsoft.Web/sites | car-search-bridge | teams-bridge-rg | Consumption | ~$0.05 |
| Storage Account | Microsoft.Storage/storageAccounts | carsearchbridgest | teams-bridge-rg | Standard_LRS | ~$0.10 |

**Total additional cost: ~$0.15/month**

### 13.3 Step-by-Step Implementation

#### Step 1: Entra ID App Registration

```powershell
# Create SingleTenant app registration for the bot
az ad app create \
  --display-name "CarSearchBot" \
  --sign-in-audience "AzureADMyOrg"

# Note the appId from output
# Generate a client secret
az ad app credential reset \
  --id <appId> \
  --append
```

**Key values:**
- App (client) ID: `<your-bot-app-id>`
- Tenant ID: `<your-tenant-id>`
- Client secret: (stored in Function App settings)

> **⚠️ SingleTenant vs MultiTenant:** Use `SingleTenant` for enterprise deployments where the bot only serves one org. `MultiTenant` is deprecated for new bot registrations via `az bot create`.

#### Step 2: Azure Bot Service

```powershell
az bot create \
  --resource-group foundry-experimentation \
  --name car-search-bot \
  --app-type SingleTenant \
  --appid <your-bot-app-id> \
  --tenant-id <your-tenant-id> \
  --sku F0

# Enable Teams channel
az bot msteams create \
  --resource-group foundry-experimentation \
  --name car-search-bot
```

#### Step 3: Azure Function App (Bridge)

**Problem encountered:** Linux consumption plan for Python requires a **separate resource group** from any existing Windows App Service plans.

```powershell
# Create dedicated resource group
az group create --name teams-bridge-rg --location eastus2

# Create storage account (must be in same RG)
az storage account create \
  --name carsearchbridgest \
  --resource-group teams-bridge-rg \
  --location eastus2 \
  --sku Standard_LRS

# Create Function App
az functionapp create \
  --resource-group teams-bridge-rg \
  --consumption-plan-location eastus2 \
  --runtime python --runtime-version 3.12 \
  --functions-version 4 \
  --name car-search-bridge \
  --storage-account carsearchbridgest \
  --os-type Linux
```

> **⚠️ Linux Dynamic Workers Error:** If you get "Linux dynamic workers are not available in resource group", create a new resource group. Existing RGs with Windows plans block Linux consumption plan creation.

#### Step 4: Bridge Code

**Project structure:**
```
teams-bridge/
├── function_app.py      # Azure Functions v2 entry point (HTTP triggers)
├── host.json            # Functions host configuration
├── requirements.txt     # Python dependencies
├── .funcignore          # Files to exclude from deployment
├── bot/
│   ├── __init__.py      # Exports CarSearchBot
│   └── car_search_bot.py  # ActivityHandler → Foundry agent bridge
└── teams-manifest/
    ├── manifest.json    # Teams app manifest
    ├── color.png        # 192x192 app icon
    └── outline.png      # 32x32 outline icon
```

**function_app.py** — Azure Functions v2 HTTP triggers:
```python
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
    body = req.get_json()
    activity = Activity().deserialize(body)
    auth_header = req.headers.get("Authorization", "")
    response = await ADAPTER.process_activity(activity, auth_header, BOT.on_turn)
    if response:
        return func.HttpResponse(body=json.dumps(response.body), status_code=response.status)
    return func.HttpResponse(status_code=201)
```

**car_search_bot.py** — Foundry agent bridge:
```python
from botbuilder.core import ActivityHandler, TurnContext
from botbuilder.schema import Activity, ActivityTypes
from azure.identity import ManagedIdentityCredential, DefaultAzureCredential

# Use ManagedIdentityCredential in Azure, fall back to DefaultAzureCredential locally
try:
    _credential = ManagedIdentityCredential()
    _credential.get_token("https://ai.azure.com/.default")
except Exception:
    _credential = DefaultAzureCredential()

class CarSearchBot(ActivityHandler):
    async def on_message_activity(self, turn_context: TurnContext):
        user_text = turn_context.activity.text or ""
        conversation_id = turn_context.activity.conversation.id
        
        # Send typing indicator (MUST use Activity object, not dict)
        await turn_context.send_activity(Activity(type=ActivityTypes.typing))
        
        # Get Foundry token via managed identity
        # ⚠️ Scope MUST be https://ai.azure.com/.default (NOT cognitiveservices)
        token = _credential.get_token("https://ai.azure.com/.default")
        
        # Call Foundry hosted agent via endpoint-scoped route
        # ⚠️ Path: /agents/{name}/endpoint/protocols/openai/responses
        # ⚠️ api-version=v1 (NOT Azure preview dates)
        # ⚠️ Foundry-Features header required for hosted agents
        resp = requests.post(
            f"{FOUNDRY_PROJECT_ENDPOINT}/agents/{AGENT_NAME}/endpoint/protocols/openai/responses",
            headers={
                "Authorization": f"Bearer {token.token}",
                "Content-Type": "application/json",
                "Foundry-Features": "hosted-agents",
            },
            params={"api-version": "v1"},
            json={"input": user_text, "stream": False},
        )
        
        # Extract text from Responses protocol output
        data = resp.json()
        texts = []
        for item in data.get("output", []):
            if item.get("type") == "message":
                for part in item.get("content", []):
                    if part.get("type") == "output_text":
                        texts.append(part.get("text", ""))
        
        await turn_context.send_activity("\n".join(texts))
```

#### Step 5: Deploy Bridge

```powershell
# Enable Python v2 programming model (REQUIRED)
az functionapp config appsettings set \
  -g teams-bridge-rg -n car-search-bridge \
  --settings AzureWebJobsFeatureFlags=EnableWorkerIndexing

# Deploy with func CLI (remote build installs pip packages on Linux)
func azure functionapp publish car-search-bridge --python --build remote
```

> **⚠️ Python v2 Programming Model:** Without `AzureWebJobsFeatureFlags=EnableWorkerIndexing`, the runtime looks for `function.json` files (v1 model) and won't discover decorator-based functions in `function_app.py`. Functions will deploy successfully but return 404.

> **⚠️ Import Errors Kill Function Discovery:** If any module-level code in `function_app.py` or its imports raises an exception (e.g., `os.environ["KEY"]` for a missing key), the entire function host fails to load and no functions are registered. Use `os.environ.get()` with defaults for all env vars read at import time.

#### Step 6: Configure App Settings

```powershell
az functionapp config appsettings set \
  -g teams-bridge-rg -n car-search-bridge \
  --settings \
    MICROSOFT_APP_ID=<your-bot-app-id> \
    MICROSOFT_APP_PASSWORD="<client-secret>" \
    MICROSOFT_APP_TENANT_ID=<your-tenant-id> \
    FOUNDRY_PROJECT_ENDPOINT="https://car-search-resource.services.ai.azure.com/api/projects/car-search" \
    AGENT_NAME=car-search-agent
```

#### Step 7: Enable Managed Identity & RBAC

```powershell
# Enable system-assigned MI on Function App
az functionapp identity assign \
  -g teams-bridge-rg -n car-search-bridge

# Grant THREE roles on the Foundry account (Cognitive Services resource)
FOUNDRY_SCOPE="/subscriptions/.../providers/Microsoft.CognitiveServices/accounts/car-search-resource"
FUNC_MI="<function-app-MI-principalId>"

az role assignment create --assignee $FUNC_MI --role "Cognitive Services User" --scope $FOUNDRY_SCOPE
az role assignment create --assignee $FUNC_MI --role "Azure AI Developer" --scope $FOUNDRY_SCOPE
az role assignment create --assignee $FUNC_MI --role "Azure AI User" --scope $FOUNDRY_SCOPE
```

> **⚠️ All three roles are required.** `Cognitive Services User` alone is insufficient for the endpoint-scoped hosted agent route. The `Azure AI Developer` and `Azure AI User` roles grant access to the agent invocation pipeline.

**Function App MI:** `<func-app-mi-principal-id>`

#### Step 7b: Create Service Principal for Bot App Registration

```powershell
# ⚠️ CRITICAL: The Entra ID app registration from Step 1 does NOT
# automatically create an Enterprise Application (service principal)
# in the tenant. The Bot Framework SDK needs this to acquire tokens
# when sending replies back through Bot Service.
az ad sp create --id <your-bot-app-id>
```

> **Without this step,** the bridge receives messages successfully and calls the Foundry agent, but all replies fail with `AADSTS7000229: The client application is missing service principal in the tenant`. The bot appears to silently drop messages.

#### Step 8: Update Bot Messaging Endpoint

```powershell
az bot update \
  --resource-group foundry-experimentation \
  --name car-search-bot \
  --endpoint "https://car-search-bridge.azurewebsites.net/api/messages"
```

#### Step 9: Test via Web Chat

1. Azure Portal → `car-search-bot` → **Test in Web Chat**
2. Type: "Find Honda SUVs near 90210 under $30,000"
3. Verify: Response shows car listings with prices and distances

> **Note:** Web Chat tests the exact same pipeline as Teams (Bot Service → Function bridge → Foundry agent). If Web Chat works, Teams integration is validated.

#### Step 10: Teams App Manifest (for M365-licensed tenants)

```json
{
  "$schema": "https://developer.microsoft.com/en-us/json-schemas/teams/v1.17/MicrosoftTeams.schema.json",
  "manifestVersion": "1.17",
  "id": "<your-bot-app-id>",
  "name": { "short": "CarFinder" },
  "description": { "short": "AI-powered car search assistant" },
  "bots": [{
    "botId": "<your-bot-app-id>",
    "scopes": ["personal", "team", "groupChat"]
  }],
  "validDomains": ["car-search-bridge.azurewebsites.net"]
}
```

Package `manifest.json` + `color.png` (192×192) + `outline.png` (32×32) into a `.zip` and sideload via **Teams → Apps → Upload a custom app**.

> **Prerequisite:** Sideloading requires the Teams admin to enable "Upload custom apps" AND the user must have an M365 license that includes Teams. Free/personal Teams accounts cannot sideload custom apps.

### 13.4 Debugging Lessons (Bridge-Specific)

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| `BotFrameworkAdapterSettings` has no `app_type` | botbuilder-core 4.17.1 doesn't support `app_type` parameter | Use `channel_provider=SimpleChannelProvider()` instead |
| `SimpleChannelProvider(is_government=False)` error | Constructor doesn't accept kwargs in this version | Use `SimpleChannelProvider()` with no arguments |
| `az bot create --app-type MultiTenant` fails | MultiTenant deprecated for new bots | Use `SingleTenant` with `--tenant-id` |
| App Service F1 plan "no quota" | Subscription has 0 free VM quota | Use Azure Functions consumption plan instead |
| Linux consumption plan "not available in RG" | Existing Windows plans in RG block Linux dynamic workers | Create a new resource group |
| Functions deploy but return 404 | Missing `AzureWebJobsFeatureFlags=EnableWorkerIndexing` | Set app setting for Python v2 model |
| Functions deploy but show 0 functions | `os.environ["KEY"]` at import time raises KeyError | Use `os.environ.get("KEY", "")` for all import-time env reads |
| `func` command not found after npm install | func.exe not on system PATH | Use full path: `npm root -g`/azure-functions-core-tools/bin/func.exe |
| `AADSTS7000229: missing service principal` | App registration exists but no Enterprise App (SP) in tenant | Run `az ad sp create --id <appId>` |
| `audience is incorrect (https://ai.azure.com)` | Token scope `cognitiveservices.azure.com` wrong for Foundry | Use scope `https://ai.azure.com/.default` |
| 401 on `/agents/{name}/responses` | Standard Responses path doesn't work for hosted agents | Use endpoint-scoped route: `/agents/{name}/endpoint/protocols/openai/responses?api-version=v1` with `Foundry-Features: hosted-agents` header |
| 400 `API version not supported` | Azure preview API versions (`2025-xx-xx-preview`) rejected | Use `api-version=v1` (the hosted agent route uses its own versioning) |
| `'dict' object has no attribute 'channel_id'` | Typing indicator sent as `{"type": "typing"}` dict | Use `Activity(type=ActivityTypes.typing)` object |
| Bot receives message but no reply appears | Multiple causes: missing SP, wrong token scope, wrong URL | Check diagnostic endpoint; fix SP + scope + endpoint path |

### 13.5 Complete Identity & RBAC Matrix (Updated)

| Identity | Principal ID | Role | Scope | Purpose |
|----------|-------------|------|-------|---------|
| Foundry Project MI | `<project-mi>-...` | AcrPull | ACR `adityaacr` | Pull container images |
| Agent MI | `<agent-mi>-...` | Azure AI User | Foundry project | Runtime agent identity |
| Blueprint MI | `<blueprint-mi>-...` | Azure AI User | Foundry project | Agent blueprint identity |
| **Function App MI** | `<func-app-mi>-...` | **Cognitive Services User** | Foundry account | **Bridge calls Foundry agent API** |
| **Function App MI** | `<func-app-mi>-...` | **Azure AI Developer** | Foundry account | **Hosted agent endpoint access** |
| **Function App MI** | `<func-app-mi>-...` | **Azure AI User** | Foundry account | **Agent invocation pipeline** |
| **Bot App Registration SP** | `<bot-sp-id>-...` | *(none — service principal only)* | Tenant | **Bot SDK acquires reply tokens** |

---

## 14. Root Cause Analysis — Foundry Hosted Agent Endpoint Discovery

### 14.1 The Problem

After deploying the bridge, the Function App could authenticate (get tokens) but every call to the Foundry agent returned errors: `401 Unauthorized`, `400 API version not supported`, `404 Not Found`, or `DeploymentNotFound`.

### 14.2 What We Tried (All Failed)

| Endpoint Pattern | api-version | Result |
|-----------------|------------|--------|
| `.../agents/{name}/responses` | `2025-05-01-preview` | 400 — API version not supported |
| `.../agents/{name}/responses` | `2024-12-01-preview` | 400 — API version not supported |
| `.../agents/{name}/responses` | `2024-10-01-preview` | 400 — API version not supported |
| `.../agents/{name}/responses` | *(none)* | 400 — Missing required query parameter: api-version |
| `.../openai/v1/responses` | *(none)* | 404 — DeploymentNotFound (agent name is not a model deployment) |
| `.../openai/v1/responses` | `2025-05-15-preview` | 400 — api-version not allowed when using /v1 path |
| `.../agents/{name}/openai/responses` | `2025-05-15-preview` | 404 — empty |
| `.../agents/{name}/versions/latest/responses` | `2025-05-15-preview` | 404 — empty |
| `.../agents/{name}/runs` | `2025-05-15-preview` | 404 — empty |
| `.../agents/{name}/endpoint/openai/responses` | `2025-05-15-preview` | 404 — empty |

### 14.3 How We Found the Answer

1. **MCP `agent_invoke` tool worked** — confirming the agent itself was healthy
2. **Searched the `microsoft/agent-framework` GitHub repository** for endpoint construction logic
3. **Found the pattern in source code:**
   - `FoundryAgent.cs` → `ParseAgentEndpoint()` expects: `https://<host>/.../projects/<project>/agents/<agentName>/endpoint/protocols/openai`
   - `FoundryAgentTests.cs` → `Assert.Contains("/agents/it-happy-path/endpoint/protocols/openai/responses", path)` and `Assert.Contains("api-version=v1", capturedUri.Query)`
   - `HostedAgentFixture.cs` → "The Foundry-Features header is also required on the invocation pipeline for hosted agents"
   - `call_server.py` sample → Uses `FOUNDRY_AGENT_ENDPOINT` = `https://<resource>.services.ai.azure.com/api/projects/<project>/agents/<agent-name>`

### 14.4 The Correct Pattern

```
POST {project_endpoint}/agents/{agent_name}/endpoint/protocols/openai/responses?api-version=v1

Headers:
  Authorization: Bearer <token>          # scope: https://ai.azure.com/.default
  Content-Type: application/json
  Foundry-Features: hosted-agents        # Required feature flag header

Body:
  {"input": "user message", "stream": false}
```

**Key differences from standard Azure OpenAI:**
- **Path**: Uses `/endpoint/protocols/openai/responses` suffix (NOT just `/responses`)
- **api-version**: `v1` (NOT Azure preview date strings like `2025-05-01-preview`)
- **Token scope**: `https://ai.azure.com/.default` (NOT `https://cognitiveservices.azure.com/.default`)
- **Header**: `Foundry-Features: hosted-agents` is required
- **Agent name ≠ model deployment**: The agent name is NOT a model deployment — you cannot use `/openai/v1/responses` with it

### 14.5 The One-Line Summary

> **Foundry hosted agents use an endpoint-scoped route (`/agents/{name}/endpoint/protocols/openai/responses?api-version=v1`) with a `Foundry-Features: hosted-agents` header — this is NOT documented in standard Azure API docs and must be discovered from the Agent Framework SDK source code.**

### 14.6 Three Simultaneous Issues

The debugging was complicated because **three issues were masking each other:**

1. **Wrong token scope** → 401 ("audience is incorrect") — fixed first
2. **Missing RBAC roles** → 401 even with correct scope — fixed by adding Azure AI Developer + Azure AI User
3. **Wrong endpoint path** → 400/404 even with valid auth — fixed last by discovering the endpoint-scoped route

Additionally, a **fourth issue** only became visible once the agent call succeeded:

4. **Missing service principal** → Bot received messages and called the agent successfully, but replies failed silently because the Bot SDK couldn't acquire a token to send replies back to Bot Service

---

## 15. Enterprise Alternative — M365 Declarative Agent

### 15.1 When to Use This Pattern

**Option B: M365 Declarative Agent via Agents Toolkit** is the preferred approach for enterprise deployments where users already have M365 Copilot licenses. This section documents the pattern for future Schneider implementation.

### 15.2 Architecture — Option B

```
┌──────────┐     ┌──────────────────────┐     ┌─────────────────┐
│  Teams   │────▶│  M365 Copilot        │────▶│  Foundry Hosted │
│  User    │◀────│  (Declarative Agent) │◀────│  Agent          │
│  +M365   │     │  via Agents Toolkit   │     │  /responses     │
│  license │     └──────────────────────┘     └─────────────────┘
└──────────┘       No bridge needed!
```

**Key difference:** No Azure Function bridge needed. The M365 Copilot platform natively connects to the Foundry agent via the Agents Toolkit VS Code extension.

### 15.3 Prerequisites (Enterprise)

| Requirement | Personal Account | Enterprise (Schneider) |
|------------|-----------------|----------------------|
| M365 Copilot license | ❌ Not available | ✅ Available to licensed users |
| Agents Toolkit VS Code extension | ✅ Available | ✅ Available |
| Teams admin sideload policy | ❌ No admin control | ✅ Controlled by IT |
| Azure Bot Service | ✅ Required (bridge) | ❌ Not required |
| Azure Function bridge | ✅ Required | ❌ Not required |
| Managed Identity RBAC | Complex (4 identities) | Simpler (direct connection) |

### 15.4 Implementation Steps (Enterprise)

1. **Install Agents Toolkit** VS Code extension
2. **Create Declarative Agent** project via Agents Toolkit scaffold
3. **Configure API Plugin** pointing to the Foundry agent's `/responses` endpoint
4. **Package and deploy** via Agents Toolkit to M365 Admin Center
5. **Publish** to Teams App Catalog (org-wide or targeted)
6. Users access via M365 Copilot in Teams — no sideloading required

### 15.5 Cost Comparison

| Component | Option A (Bot Service Bridge) | Option B (M365 Declarative Agent) |
|-----------|-------------------------------|----------------------------------|
| Bot Service | $0 (F0) | Not needed |
| Function App | ~$0.05/mo | Not needed |
| Storage Account | ~$0.10/mo | Not needed |
| M365 Copilot License | Not required | ~$30/user/mo (usually org-wide) |
| **Bridge infrastructure** | **Yes** (additional code to maintain) | **No** (native platform connection) |
| **Total added infra cost** | **~$0.15/mo** | **$0** (covered by M365 license) |

### 15.6 Decision Matrix

| Factor | Option A (Bot Service) | Option B (M365 Declarative) |
|--------|----------------------|---------------------------|
| M365 Copilot license required | No | Yes |
| Custom bridge code to maintain | Yes | No |
| Works with free/personal accounts | Yes (Web Chat) | No |
| Works in Teams | Needs M365 Teams license | Needs M365 Copilot license |
| Deployment complexity | Medium (Function + Bot + RBAC) | Low (Agents Toolkit wizard) |
| Enterprise IT approval | Bot Service + Function App | App Catalog publish |
| Multi-turn conversation | Manual session tracking | Built-in |
| Rich card responses | Manual Adaptive Cards | Native Copilot UI |

**Recommendation:**
- **Personal / POC / learning:** Option A (Bot Service bridge) — works without M365 license
- **Enterprise production:** Option B (M365 Declarative Agent) — less code, native experience, IT-managed

---

## Document History

| Date | Author | Change |
|------|--------|--------|
| 2026-05-09 | Aditya Vemuri | Initial creation — complete deployment process documented |
| 2026-05-10 | Aditya Vemuri | Added Phase 6 — Teams integration via Bot Service bridge pattern |
| 2026-05-10 | Aditya Vemuri | Phase 6 debugging: Fixed hosted agent endpoint (endpoint-scoped route), token scope (ai.azure.com), missing service principal, typing indicator, additional RBAC roles |
