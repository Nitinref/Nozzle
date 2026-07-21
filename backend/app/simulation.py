from __future__ import annotations

import hashlib
import os
import re
import time
from dataclasses import dataclass
from typing import Literal

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from .llm import OpenRouterClient, OpenRouterResult
from .models import CallRecord

INPUT_COST_PER_1K_TOKENS = float(os.getenv("OPENROUTER_ESTIMATED_INPUT_COST_PER_1K", "0.003"))
OUTPUT_COST_PER_1K_TOKENS = float(os.getenv("OPENROUTER_ESTIMATED_OUTPUT_COST_PER_1K", "0.015"))
CLIENT = OpenRouterClient()
TRACER = trace.get_tracer("per-customer-ai-cost-radar.simulation")


@dataclass
class SpikeState:
    multiplier: float = 1.0
    remaining_calls: int = 0


class SpikeRegistry:
    def __init__(self) -> None:
        self._by_customer: dict[str, SpikeState] = {}

    def trigger(self, customer_id: str, multiplier: float, remaining_calls: int) -> SpikeState:
        state = SpikeState(multiplier=multiplier, remaining_calls=remaining_calls)
        self._by_customer[customer_id] = state
        return state

    def consume(self, customer_id: str) -> SpikeState:
        state = self._by_customer.get(customer_id)
        if state is None:
            state = SpikeState()
            self._by_customer[customer_id] = state
            return state

        if state.remaining_calls > 0:
            state.remaining_calls -= 1
        if state.remaining_calls <= 0:
            state.multiplier = 1.0
            state.remaining_calls = 0
        return state


SPIKES = SpikeRegistry()


def _stable_seed(customer_id: str, message: str) -> int:
    digest = hashlib.sha256(f"{customer_id}|{message}".encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _estimate_cost(input_tokens: int, output_tokens: int) -> float:
    return round((input_tokens * INPUT_COST_PER_1K_TOKENS + output_tokens * OUTPUT_COST_PER_1K_TOKENS) / 1000.0, 6)


def _call_to_record(
    result: OpenRouterResult,
    *,
    call_type: Literal["llm_call", "tool_call", "retry"],
    notes: str | None = None,
    tool_name: str | None = None,
) -> CallRecord:
    return CallRecord(
        call_id=hashlib.sha256(f"{result.model}|{result.raw.get('created', '')}|{result.latency_ms}".encode("utf-8")).hexdigest()[:16],
        call_type=call_type,
        model=result.model,
        input_tokens=result.prompt_tokens,
        output_tokens=result.completion_tokens,
        cost_usd=_estimate_cost(result.prompt_tokens, result.completion_tokens),
        latency_ms=result.latency_ms,
        tool_name=tool_name,
        notes=notes,
    )


def _tool_lookup(customer_id: str, message: str) -> dict[str, object]:
    words = sorted({word.lower() for word in re.findall(r"[A-Za-z0-9_]+", message) if len(word) > 4})
    message_digest = hashlib.sha256(message.encode("utf-8")).hexdigest()[:12]
    with TRACER.start_as_current_span("tool.customer_context_lookup") as span:
        span.set_attribute("customer_id", customer_id)
        span.set_attribute("model", "local_tool:customer_context_lookup")
        span.set_attribute("call_type", "tool_call")
        span.set_attribute("input_tokens", 0)
        span.set_attribute("output_tokens", 0)
        span.set_attribute("cost_usd", 0.0)

        result = {
            "customer_id": customer_id,
            "message_digest": message_digest,
            "message_length": len(message),
            "keywords": words[:5],
            "urgency_score": min(10, 1 + len(words)),
        }
        span.set_attribute("keywords", ",".join(result["keywords"]))
        span.set_status(Status(StatusCode.OK))
        return result


def _system_prompt(customer_id: str, extra_instructions: str = "") -> str:
    suffix = f"\n{extra_instructions}" if extra_instructions else ""
    return (
        "You are a multi-tenant AI SaaS assistant. "
        "Respond directly to the customer, stay concise, and ground your answer in the provided context."
        f"\nCustomer ID: {customer_id}"
        f"{suffix}"
    )


def _user_prompt(message: str, tool_context: str | None = None) -> str:
    if tool_context:
        return f"User request: {message}\n\nTool context:\n{tool_context}"
    return f"User request: {message}"


def _run_llm(
    customer_id: str,
    message: str,
    *,
    call_type: Literal["llm_call", "retry"] = "llm_call",
    extra_instructions: str = "",
    tool_context: str | None = None,
) -> OpenRouterResult:
    messages = [
        {"role": "system", "content": _system_prompt(customer_id, extra_instructions=extra_instructions)},
        {"role": "user", "content": _user_prompt(message, tool_context=tool_context)},
    ]
    return CLIENT.chat(customer_id=customer_id, messages=messages, call_type=call_type)


def _scenario(customer_id: str, message: str) -> tuple[str, SpikeState, int]:
    seed = _stable_seed(customer_id, message)
    roll = seed % 100
    spike_state = SPIKES.consume(customer_id)
    if spike_state.multiplier > 1.0:
        retry_count = 3 + (seed % 3)
        return f"spike_retry_loop_{retry_count}_calls", spike_state, retry_count
    if roll < 28:
        retry_count = 2 + (seed % 4)
        return f"retry_loop_{retry_count}_calls", spike_state, retry_count
    if roll < 55:
        return "llm_plus_tool_call", spike_state, 1
    return "single_llm_call", spike_state, 1


def simulate_agent_run(customer_id: str, message: str) -> tuple[str, list[CallRecord], str, str, str, int, int, float, int]:
    if not CLIENT.configured:
        raise RuntimeError("OPENROUTER_API_KEY is not configured")

    started = time.perf_counter()
    scenario, spike_state, retry_count = _scenario(customer_id, message)
    calls: list[CallRecord] = []
    assistant_message = ""
    model_used = ""

    if scenario.startswith("retry_loop") or scenario.startswith("spike_retry_loop"):
        for attempt in range(retry_count):
            result = _run_llm(
                customer_id,
                message,
                call_type="retry",
                extra_instructions=(
                    f"Attempt {attempt + 1} of {retry_count}. "
                    "A previous attempt hit a transient upstream timeout. "
                    "Retry the response and keep it customer-facing."
                ),
            )
            assistant_message = result.content
            model_used = result.model
            calls.append(_call_to_record(result, call_type="retry", notes=f"retry attempt {attempt + 1}"))

        if spike_state.multiplier > 1.0:
            summary = f"Spike trigger active: the agent ran {retry_count} real OpenRouter calls in a retry loop."
        else:
            summary = f"The model needed {retry_count} real OpenRouter calls before returning a usable answer."

    elif scenario == "llm_plus_tool_call":
        first = _run_llm(customer_id, message, call_type="llm_call")
        assistant_message = first.content
        model_used = first.model
        calls.append(_call_to_record(first, call_type="llm_call"))

        tool_result = _tool_lookup(customer_id, message)
        tool_latency = int((time.perf_counter() - started) * 1000)
        calls.append(
            CallRecord(
                call_id=hashlib.sha256(f"{customer_id}|tool|{message}".encode("utf-8")).hexdigest()[:16],
                call_type="tool_call",
                model="local_tool:customer_context_lookup",
                input_tokens=0,
                output_tokens=0,
                cost_usd=0.0,
                latency_ms=max(1, tool_latency // 10),
                tool_name="customer_context_lookup",
                notes=f"keywords={tool_result['keywords']}",
            )
        )

        second = _run_llm(
            customer_id,
            message,
            call_type="llm_call",
            extra_instructions="Use the tool context to refine the answer.",
            tool_context=str(tool_result),
        )
        assistant_message = second.content
        model_used = second.model
        calls.append(_call_to_record(second, call_type="llm_call", notes="follow-up after tool lookup"))
        summary = "The assistant made one live model pass, one local tool lookup, and one follow-up model pass."

    else:
        result = _run_llm(customer_id, message)
        assistant_message = result.content
        model_used = result.model
        calls.append(_call_to_record(result, call_type="llm_call"))
        summary = "A single live OpenRouter call handled the request."

    total_input = sum(call.input_tokens for call in calls)
    total_output = sum(call.output_tokens for call in calls)
    total_cost = round(sum(call.cost_usd for call in calls), 6)
    total_latency = sum(call.latency_ms for call in calls)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return (
        scenario,
        calls,
        summary,
        assistant_message,
        model_used,
        total_input,
        total_output,
        total_cost,
        max(total_latency, elapsed_ms),
    )
