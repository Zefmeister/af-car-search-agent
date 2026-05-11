# Copyright (c) 2026. Car Advisor — Multi-agent orchestration system.
# Orchestrator + Car Finder + Safety Checker + Price Estimator via HandoffBuilder.

import os

from agent_framework.foundry import FoundryChatClient
from agent_framework.orchestrations import HandoffBuilder
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from agents import (
    create_car_finder_agent,
    create_orchestrator_agent,
    create_price_estimator_agent,
    create_safety_checker_agent,
)

# Load environment variables from .env file.
# override=False so Foundry-injected env vars take precedence at runtime.
load_dotenv(override=False)

# ── Patch: HandoffAgentUserRequest is not JSON-serializable (framework bug) ──
import json
from typing import Any, Mapping

import agent_framework_foundry_hosting._responses as _resp

_orig_arguments_to_str = _resp._arguments_to_str


def _patched_arguments_to_str(arguments: str | Mapping[str, Any] | None) -> str:
    if arguments is None:
        return ""
    if isinstance(arguments, str):
        return arguments
    try:
        return json.dumps(arguments)
    except TypeError:
        # HandoffAgentUserRequest (and similar) — serialize via __dict__
        return json.dumps(arguments, default=lambda o: getattr(o, "__dict__", str(o)))


_resp._arguments_to_str = _patched_arguments_to_str

# ── Patch: FileCheckpointStorage missing allowed_checkpoint_types (framework bug) ──
from agent_framework._workflows._checkpoint import FileCheckpointStorage

_orig_fcs_init = FileCheckpointStorage.__init__


def _patched_fcs_init(self, storage_path, *, allowed_checkpoint_types=None):
    # Pass None to disable type restrictions entirely — the framework's
    # allowlist is too restrictive for handoff workflows (blocks MessageRole,
    # HandoffAgentUserRequest, GenericAlias, etc.).
    _orig_fcs_init(self, storage_path, allowed_checkpoint_types=None)
    self._allowed_types = None


FileCheckpointStorage.__init__ = _patched_fcs_init

# ── Patch: Handoff pending_requests poison multi-turn continuation ────────────
# After checkpoint restore, internal handoff events populate pending_requests.
# The next run() then crashes because _extract_function_responses expects
# FunctionCallOutput content but receives the user's plain text message.
# Fix: clear pending_requests after restore so user text is treated normally.
import agent_framework_foundry_hosting._responses as _host_resp

_orig_handle_inner_workflow = _host_resp.ResponsesHostServer._handle_inner_workflow


async def _patched_handle_inner_workflow(self, request, context):
    async for event in _orig_handle_inner_workflow(self, request, context):
        yield event


async def _handle_inner_workflow_fixed(self, request, context):
    import os as _os
    from agent_framework._workflows._checkpoint import FileCheckpointStorage as _FCS
    from agent_framework._workflows._agent import WorkflowAgent as _WA

    input_items = await context.get_input_items()
    input_messages = await _host_resp._items_to_messages(input_items)
    is_streaming = request.stream is not None and request.stream is True

    context_id = request.previous_response_id or context.conversation_id

    latest_checkpoint_id = None
    restore_storage = None
    if context_id is not None:
        restore_storage = _FCS(_os.path.join(self._checkpoint_storage_path, context_id))
        latest_checkpoint = await restore_storage.get_latest(workflow_name=self._agent.workflow.name)
        if latest_checkpoint is not None:
            latest_checkpoint_id = latest_checkpoint.checkpoint_id

    write_context_id = context.conversation_id or context.response_id
    write_storage = _FCS(_os.path.join(self._checkpoint_storage_path, write_context_id))

    # ── Reset workflow running flag ──
    # If a previous SSE stream was interrupted (e.g. Agent Inspector refresh),
    # the singleton workflow's _is_running flag may still be True because
    # _run_cleanup never fired.  Force-reset so the next run() isn't blocked.
    self._agent.workflow._is_running = False

    # Restore checkpoint (drain events silently)
    if latest_checkpoint_id is not None:
        if is_streaming:
            async for _ in self._agent.run(
                stream=True,
                checkpoint_id=latest_checkpoint_id,
                checkpoint_storage=restore_storage,
            ):
                pass
        else:
            await self._agent.run(
                stream=False,
                checkpoint_id=latest_checkpoint_id,
                checkpoint_storage=restore_storage,
            )
        pass  # pending_requests cleared below

    # ── THE FIX: ALWAYS clear handoff-poisoned pending_requests ──
    # WorkflowAgent is a shared singleton; stale pending_requests from ANY
    # prior conversation/restore will crash the next run() call.
    self._agent.pending_requests.clear()

    # ── Also clear per-executor caches when starting a fresh conversation ──
    # Without this, agent executors retain message history from prior sessions
    # and the LLM may hallucinate answers from old context or fail with
    # "No tool output found for function call" errors.
    if latest_checkpoint_id is None:
        from agent_framework._workflows._agent_executor import AgentExecutor as _AE
        for executor in self._agent.workflow.executors.values():
            if isinstance(executor, _AE):
                executor._cache.clear()
                executor._full_conversation.clear()
                executor._pending_agent_requests.clear()
                executor._pending_responses_to_agent.clear()
                # Reset the agent session to drop dangling tool call history
                executor._session = executor._agent.create_session()

    response_event_stream = _host_resp.ResponseEventStream(
        response_id=context.response_id, model=request.model
    )
    yield response_event_stream.emit_created()
    yield response_event_stream.emit_in_progress()

    tracker = _host_resp._OutputItemTracker(response_event_stream)

    # Reset running flag again (checkpoint restore run above may have left it set)
    self._agent.workflow._is_running = False

    async for update in self._agent.run(
        input_messages,
        stream=True,
        checkpoint_storage=write_storage,
    ):
        for content in update.contents:
            for event in tracker.handle(content):
                yield event
            if tracker.needs_async:
                async for item in _host_resp._to_outputs(response_event_stream, content):
                    yield item
                tracker.needs_async = False

    for event in tracker.close():
        yield event

    await self._delete_not_latest_checkpoints(write_storage, self._agent.workflow.name)
    yield response_event_stream.emit_completed()


_host_resp.ResponsesHostServer._handle_inner_workflow = _handle_inner_workflow_fixed

# ── Multi-agent workflow assembly ─────────────────────────────────────────────


def main():
    # Shared model client — one model, one cost line.
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=DefaultAzureCredential(),
    )

    # Create specialist agents
    orchestrator = create_orchestrator_agent(client)
    car_finder = create_car_finder_agent(client)
    safety_checker = create_safety_checker_agent(client)
    price_estimator = create_price_estimator_agent(client)

    # Build handoff topology — orchestrator is the hub.
    workflow_agent = (
        HandoffBuilder(
            name="car_advisor",
            participants=[orchestrator, car_finder, safety_checker, price_estimator],
        )
        .with_start_agent(orchestrator)
        # Orchestrator routes to specialists
        .add_handoff(orchestrator, [car_finder], description="Search car inventory listings by make, model, price, mileage, location. Use ONLY for finding cars to buy.")
        .add_handoff(orchestrator, [safety_checker], description="NHTSA safety data: recalls, complaints, crash ratings, VIN decoding. Use for ANY question about recalls, safety, or VIN lookup.")
        .add_handoff(orchestrator, [price_estimator], description="Estimate fair market value using depreciation model. Use for pricing, valuation, or worth questions.")
        # Specialists return to orchestrator when done
        .add_handoff(car_finder, [orchestrator], description="Return after search complete")
        .add_handoff(safety_checker, [orchestrator], description="Return after safety check")
        .add_handoff(price_estimator, [orchestrator], description="Return after estimation")
        .build()
        .as_agent()
    )

    # Host the workflow — ResponsesHostServer natively supports WorkflowAgent.
    server = ResponsesHostServer(workflow_agent)
    server.run()


if __name__ == "__main__":
    main()
