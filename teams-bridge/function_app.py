"""
Teams Bridge — Azure Functions v2 entry point.

Receives Bot Framework webhook callbacks at /api/messages
and routes them through the CarSearchBot handler to the Foundry agent.
"""

import os
import sys
import json
import logging
import traceback
import azure.functions as func
from botbuilder.core import BotFrameworkAdapterSettings, BotFrameworkAdapter
from botbuilder.schema import Activity
from botframework.connector.auth import SimpleChannelProvider

from bot import CarSearchBot

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("teams-bridge")

# Bot Framework auth settings
SETTINGS = BotFrameworkAdapterSettings(
    app_id=os.environ.get("MICROSOFT_APP_ID", ""),
    app_password=os.environ.get("MICROSOFT_APP_PASSWORD", ""),
    channel_auth_tenant=os.environ.get("MICROSOFT_APP_TENANT_ID", ""),
    channel_provider=SimpleChannelProvider(),
)

ADAPTER = BotFrameworkAdapter(SETTINGS)


async def on_error(context, error):
    logger.error(f"[on_error] {error}")
    logger.error(traceback.format_exc())
    await context.send_activity("Sorry, something went wrong.")


ADAPTER.on_turn_error = on_error

BOT = CarSearchBot()

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


@app.route(route="messages", methods=["POST"])
async def messages(req: func.HttpRequest) -> func.HttpResponse:
    """Main endpoint — Bot Framework sends POST here."""
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
        logger.error(f"[messages] Exception: {e}")
        logger.error(traceback.format_exc())
        return func.HttpResponse(status_code=500)


@app.route(route="health", methods=["GET"])
async def health(req: func.HttpRequest) -> func.HttpResponse:
    """Health check endpoint."""
    return func.HttpResponse(
        body=json.dumps({"status": "ok", "service": "car-search-teams-bridge"}),
        status_code=200,
        mimetype="application/json",
    )
