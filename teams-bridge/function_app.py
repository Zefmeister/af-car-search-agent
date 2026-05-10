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

logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)
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

# Store last message processing result for diagnostics
_last_message_result = {"status": "no messages received yet"}

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


@app.route(route="messages", methods=["POST"])
async def messages(req: func.HttpRequest) -> func.HttpResponse:
    """Main endpoint — Bot Framework sends POST here."""
    global _last_message_result
    import time
    start = time.time()
    
    ct = req.headers.get("Content-Type", "")
    auth_present = bool(req.headers.get("Authorization"))
    _last_message_result = {"timestamp": time.time(), "auth_present": auth_present, "content_type": ct}
    
    logger.info(f"[messages] Received request. Content-Type: {ct}")
    logger.info(f"[messages] Auth header present: {auth_present}")
    
    if "application/json" not in ct:
        _last_message_result["error"] = f"bad content-type: {ct}"
        return func.HttpResponse(status_code=415)

    body = req.get_json()
    activity_type = body.get("type", "")
    activity_text = body.get("text", "")[:100]
    _last_message_result["activity_type"] = activity_type
    _last_message_result["activity_text"] = activity_text
    logger.info(f"[messages] Activity type: {activity_type}, text: {activity_text}")
    
    activity = Activity().deserialize(body)
    auth_header = req.headers.get("Authorization", "")

    try:
        response = await ADAPTER.process_activity(activity, auth_header, BOT.on_turn)
        elapsed = time.time() - start
        _last_message_result["process_activity_result"] = str(response)
        _last_message_result["elapsed_seconds"] = round(elapsed, 2)
        _last_message_result["status"] = "success"
        logger.info(f"[messages] process_activity returned: {response} in {elapsed:.1f}s")
        if response:
            return func.HttpResponse(
                body=json.dumps(response.body),
                status_code=response.status,
                mimetype="application/json",
            )
        return func.HttpResponse(status_code=201)
    except Exception as e:
        elapsed = time.time() - start
        _last_message_result["error"] = str(e)
        _last_message_result["error_type"] = type(e).__name__
        _last_message_result["traceback"] = traceback.format_exc()
        _last_message_result["elapsed_seconds"] = round(elapsed, 2)
        _last_message_result["status"] = "error"
        logger.error(f"[messages] Exception: {e}")
        logger.error(traceback.format_exc())
        return func.HttpResponse(
            body=json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json",
        )


@app.route(route="last-message", methods=["GET"])
async def last_message(req: func.HttpRequest) -> func.HttpResponse:
    """Returns the result of the last /api/messages invocation."""
    return func.HttpResponse(
        body=json.dumps(_last_message_result, indent=2, default=str),
        status_code=200,
        mimetype="application/json",
    )


@app.route(route="health", methods=["GET"])
async def health(req: func.HttpRequest) -> func.HttpResponse:
    """Health check endpoint."""
    return func.HttpResponse(
        body=json.dumps({"status": "ok", "service": "car-search-teams-bridge"}),
        status_code=200,
        mimetype="application/json",
    )


@app.route(route="test-agent", methods=["GET"])
async def test_agent(req: func.HttpRequest) -> func.HttpResponse:
    """Diagnostic endpoint — tests Foundry agent connectivity directly."""
    from bot.car_search_bot import _invoke_agent, _credential, FOUNDRY_PROJECT_ENDPOINT, AGENT_NAME
    
    results = {
        "foundry_endpoint": FOUNDRY_PROJECT_ENDPOINT,
        "agent_name": AGENT_NAME,
        "app_id_set": bool(os.environ.get("MICROSOFT_APP_ID")),
        "app_password_set": bool(os.environ.get("MICROSOFT_APP_PASSWORD")),
        "tenant_id_set": bool(os.environ.get("MICROSOFT_APP_TENANT_ID")),
        "credential_type": type(_credential).__name__,
    }
    
    # Test token acquisition separately
    try:
        token = _credential.get_token("https://ai.azure.com/.default")
        results["token_obtained"] = True
        results["token_first_20"] = token.token[:20] + "..."
    except Exception as e:
        results["token_obtained"] = False
        results["token_error"] = str(e)
    
    try:
        import requests as req_lib
        token = _credential.get_token("https://ai.azure.com/.default")
        base = FOUNDRY_PROJECT_ENDPOINT
        agent = AGENT_NAME
        
        # Try multiple endpoint patterns and API versions
        attempts = []
        acct = FOUNDRY_PROJECT_ENDPOINT.split("/api/")[0] if FOUNDRY_PROJECT_ENDPOINT else ""
        patterns = [
            # Endpoint-scoped route (from Agent Framework SDK source)
            ("POST", f"{base}/agents/{agent}/endpoint/protocols/openai/responses", "v1",
             {"input": "hi", "stream": False},
             {"Foundry-Features": "hosted-agents"}),
        ]
        
        for method, url_pattern, api_ver, req_body, extra_headers in patterns:
            params = {"api-version": api_ver} if api_ver else {}
            hdrs = {"Authorization": f"Bearer {token.token}", "Content-Type": "application/json"}
            hdrs.update(extra_headers)
            if method == "GET":
                r = req_lib.get(
                    url_pattern,
                    headers=hdrs,
                    params=params,
                    timeout=30,
                )
            else:
                r = req_lib.post(
                    url_pattern,
                    headers=hdrs,
                    json=req_body,
                    params=params,
                    timeout=60,
                )
            attempts.append({
                "method": method,
                "url": url_pattern,
                "api_version": api_ver,
                "status": r.status_code,
                "body_preview": r.text[:500],
            })
            # Don't break - try all patterns
        
        results["attempts"] = attempts
        results["agent_status"] = "DISCOVERY"
    except Exception as e:
        results["agent_error"] = str(e)
        results["agent_traceback"] = traceback.format_exc()
        results["agent_status"] = "FAILED"
    
    return func.HttpResponse(
        body=json.dumps(results, indent=2),
        status_code=200,
        mimetype="application/json",
    )
