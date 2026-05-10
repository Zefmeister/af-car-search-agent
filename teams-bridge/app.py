"""
Teams Bridge — HTTP server that receives Bot Framework webhook callbacks
and routes them through the CarSearchBot handler to the Foundry agent.

Run locally:  python app.py
Deploy to:    Azure App Service or Azure Functions
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

from aiohttp import web
from botbuilder.core import BotFrameworkAdapterSettings, BotFrameworkAdapter
from botbuilder.schema import Activity
from botframework.connector.auth import SimpleChannelProvider

from bot import CarSearchBot

# Bot Framework auth settings
SETTINGS = BotFrameworkAdapterSettings(
    app_id=os.environ.get("MICROSOFT_APP_ID", ""),
    app_password=os.environ.get("MICROSOFT_APP_PASSWORD", ""),
    channel_auth_tenant=os.environ.get("MICROSOFT_APP_TENANT_ID", ""),
    channel_provider=SimpleChannelProvider(),
)

ADAPTER = BotFrameworkAdapter(SETTINGS)

# Error handler
async def on_error(context, error):
    print(f"[on_error] {error}", file=sys.stderr)
    await context.send_activity("Sorry, something went wrong.")

ADAPTER.on_turn_error = on_error

BOT = CarSearchBot()


async def messages(req: web.Request) -> web.Response:
    """Main endpoint — Bot Framework sends POST here."""
    if req.content_type == "application/json":
        body = await req.json()
    else:
        return web.Response(status=415)

    activity = Activity().deserialize(body)
    auth_header = req.headers.get("Authorization", "")

    response = await ADAPTER.process_activity(activity, auth_header, BOT.on_turn)
    if response:
        return web.json_response(data=response.body, status=response.status)
    return web.Response(status=201)


async def health(req: web.Request) -> web.Response:
    """Health check endpoint."""
    return web.json_response({"status": "ok", "service": "car-search-teams-bridge"})


app = web.Application()
app.router.add_post("/api/messages", messages)
app.router.add_get("/health", health)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3978))
    print(f"Teams bridge starting on port {port}...")
    web.run_app(app, host="0.0.0.0", port=port)
