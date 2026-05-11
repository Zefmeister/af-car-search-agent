"""
Teams Bridge — Bot Framework adapter that forwards messages to the Foundry hosted agent.

Architecture:
  Teams User → Azure Bot Service → this bridge (aiohttp) → Foundry Agent /responses endpoint
"""

import os
import json
import logging
import requests

from botbuilder.core import ActivityHandler, TurnContext
from botbuilder.schema import Activity, ActivityTypes
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential

logger = logging.getLogger("teams-bridge.bot")

FOUNDRY_PROJECT_ENDPOINT = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "")
AGENT_NAME = os.environ.get("AGENT_NAME", "car-search-agent")

# Use ManagedIdentityCredential in Azure, fall back to DefaultAzureCredential for local dev
try:
    _credential = ManagedIdentityCredential()
    _credential.get_token("https://ai.azure.com/.default")
    logger.info("Using ManagedIdentityCredential")
except Exception:
    _credential = DefaultAzureCredential()
    logger.info("Falling back to DefaultAzureCredential")

# In-memory session map: Teams conversation ID → Foundry conversation ID
_sessions: dict[str, str] = {}


def _get_foundry_token() -> str:
    """Get an access token for the Foundry API."""
    token = _credential.get_token("https://ai.azure.com/.default")
    return token.token


def _invoke_agent(user_message: str, conversation_id: str) -> str:
    """Send a message to the Foundry hosted agent and return the text response."""
    # Endpoint-scoped route for hosted agents (from Agent Framework SDK source)
    url = f"{FOUNDRY_PROJECT_ENDPOINT}/agents/{AGENT_NAME}/endpoint/protocols/openai/responses"
    token = _get_foundry_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Foundry-Features": "hosted-agents",
    }

    body = {
        "input": user_message,
        "stream": False,
    }

    # Attach conversation_id for multi-turn if we have one
    foundry_conv_id = _sessions.get(conversation_id)
    if foundry_conv_id:
        body["previous_response_id"] = foundry_conv_id

    logger.info(f"[_invoke_agent] POST {url}")
    resp = requests.post(url, headers=headers, json=body, params={"api-version": "v1"}, timeout=120)
    logger.info(f"[_invoke_agent] Response status: {resp.status_code}")
    if resp.status_code != 200:
        logger.error(f"[_invoke_agent] Response body: {resp.text[:500]}")
    resp.raise_for_status()
    data = resp.json()

    # Store conversation ID for multi-turn
    if "id" in data:
        _sessions[conversation_id] = data["id"]

    # Extract text from the Responses protocol output
    output_items = data.get("output", [])
    texts = []
    for item in output_items:
        if item.get("type") == "message":
            for content_part in item.get("content", []):
                if content_part.get("type") == "output_text":
                    texts.append(content_part.get("text", ""))
    
    return "\n".join(texts) if texts else "I couldn't generate a response. Please try again."


class CarSearchBot(ActivityHandler):
    """Bot that bridges Teams messages to the Foundry car search agent."""

    async def on_message_activity(self, turn_context: TurnContext):
        user_text = turn_context.activity.text or ""
        if not user_text.strip():
            return

        conversation_id = turn_context.activity.conversation.id

        # Send typing indicator
        await turn_context.send_activity(
            Activity(type=ActivityTypes.typing)
        )

        try:
            reply_text = _invoke_agent(user_text, conversation_id)
        except requests.exceptions.HTTPError as e:
            reply_text = f"Sorry, I encountered an error calling the agent: {e.response.status_code}"
        except Exception as e:
            reply_text = f"Sorry, something went wrong: {str(e)}"

        await turn_context.send_activity(reply_text)

    async def on_members_added_activity(self, members_added, turn_context: TurnContext):
        for member in members_added:
            if member.id != turn_context.activity.recipient.id:
                await turn_context.send_activity(
                    "Hi! I'm **Car Advisor** -- your all-in-one vehicle research assistant.\n\n"
                    "I can help you search inventory, check safety data, and estimate prices. Try:\n"
                    "- *Find me a used SUV under $25k near Chicago*\n"
                    "- *Are there any recalls on a 2021 Honda Civic?*\n"
                    "- *What's a 2020 Toyota Camry with 45k miles worth?*\n"
                    "- *Decode VIN 1HGBH41JXMN109186*\n"
                    "- *Show me safety ratings for a 2024 RAV4*"
                )
