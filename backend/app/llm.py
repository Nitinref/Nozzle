from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import httpx
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode


DEFAULT_OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")
DEFAULT_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
DEFAULT_HTTP_REFERER = os.getenv("OPENROUTER_HTTP_REFERER", "http://localhost:8000")
DEFAULT_APP_TITLE = os.getenv("OPENROUTER_APP_TITLE", "Per-Customer AI Cost Radar")
TRACER = trace.get_tracer("per-customer-ai-cost-radar.llm")
INPUT_COST_PER_1K_TOKENS = float(os.getenv("OPENROUTER_ESTIMATED_INPUT_COST_PER_1K", "0.003"))
OUTPUT_COST_PER_1K_TOKENS = float(os.getenv("OPENROUTER_ESTIMATED_OUTPUT_COST_PER_1K", "0.015"))


@dataclass
class OpenRouterResult:
    model: str
    content: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: int
    raw: dict[str, Any]


class OpenRouterClient:
    def __init__(self) -> None:
        self.api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        self.model = DEFAULT_OPENROUTER_MODEL
        self.base_url = DEFAULT_BASE_URL.rstrip("/")
        self.http_referer = DEFAULT_HTTP_REFERER
        self.app_title = DEFAULT_APP_TITLE
        self.timeout = float(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "60"))
        self._client = httpx.Client(timeout=self.timeout)

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def chat(
        self,
        *,
        customer_id: str,
        messages: list[dict[str, str]],
        model: str | None = None,
        call_type: str = "llm_call",
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> OpenRouterResult:
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not configured")

        payload = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.http_referer,
            "X-Title": self.app_title,
        }
        with TRACER.start_as_current_span("llm.openrouter.chat") as span:
            span.set_attribute("customer_id", customer_id)
            span.set_attribute("model", payload["model"])
            span.set_attribute("call_type", call_type)

            start = time.perf_counter()
            try:
                response = self._client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
                latency_ms = int((time.perf_counter() - start) * 1000)
                response.raise_for_status()
                data = response.json()
                choices = data.get("choices") or []
                if not choices:
                    raise RuntimeError("OpenRouter response did not include any choices")

                message = choices[0].get("message") or {}
                usage = data.get("usage") or {}
                content = message.get("content") or ""
                prompt_tokens = int(usage.get("prompt_tokens") or 0)
                completion_tokens = int(usage.get("completion_tokens") or 0)
                total_tokens = int(usage.get("total_tokens") or 0)
                resolved_model = data.get("model") or payload["model"]
                span.set_attribute("model", resolved_model)
                span.set_attribute("input_tokens", prompt_tokens)
                span.set_attribute("output_tokens", completion_tokens)
                span.set_attribute(
                    "cost_usd",
                    round((prompt_tokens * INPUT_COST_PER_1K_TOKENS + completion_tokens * OUTPUT_COST_PER_1K_TOKENS) / 1000.0, 6),
                )
                span.set_attribute("latency_ms", latency_ms)
                span.set_status(Status(StatusCode.OK))
                return OpenRouterResult(
                    model=resolved_model,
                    content=content,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    latency_ms=latency_ms,
                    raw=data,
                )
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise
