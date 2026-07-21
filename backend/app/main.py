from __future__ import annotations

from fastapi import FastAPI, HTTPException

from .aggregator import CustomerAnalyticsService, CustomerAlertsResponse, CustomerSummaryResponse
from .models import ChatRequest, ChatResponse, SpikeRequest, SpikeResponse
from .simulation import SPIKES, simulate_agent_run
from .telemetry import init_telemetry

app = FastAPI(
    title="Per-Customer AI Cost Radar",
    version="0.1.0",
    description="Stage 1 demo app for live multi-tenant AI usage and customer spikes.",
)

init_telemetry(app)
analytics = CustomerAnalyticsService()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    try:
        (
            scenario,
            calls,
            summary,
            assistant_message,
            model_used,
            total_input,
            total_output,
            total_cost,
            total_latency,
        ) = simulate_agent_run(
            request.customer_id,
            request.message,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return ChatResponse(
        customer_id=request.customer_id,
        message=request.message,
        scenario=scenario,
        assistant_message=assistant_message,
        model_used=model_used,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        total_cost_usd=total_cost,
        total_latency_ms=total_latency,
        calls=calls,
        summary=summary,
    )


@app.post("/simulate_spike", response_model=SpikeResponse)
def simulate_spike(request: SpikeRequest) -> SpikeResponse:
    state = SPIKES.trigger(request.customer_id, request.multiplier, request.remaining_calls)
    return SpikeResponse(
        customer_id=request.customer_id,
        multiplier=state.multiplier,
        remaining_calls=state.remaining_calls,
        status="spike_armed",
    )


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "Per-Customer AI Cost Radar",
        "stage": "1",
        "docs": "/docs",
    }


@app.get("/simulate_spike")
def simulate_spike_via_query(
    customer_id: str,
    multiplier: float = 4.0,
    remaining_calls: int = 5,
) -> SpikeResponse:
    if not customer_id.strip():
        raise HTTPException(status_code=400, detail="customer_id is required")
    state = SPIKES.trigger(customer_id, multiplier, remaining_calls)
    return SpikeResponse(
        customer_id=customer_id,
        multiplier=state.multiplier,
        remaining_calls=state.remaining_calls,
        status="spike_armed",
    )


@app.get("/customers/summary", response_model=CustomerSummaryResponse)
def customers_summary(
    current_window_minutes: int | None = None,
    baseline_window_minutes: int | None = None,
) -> CustomerSummaryResponse:
    try:
        return analytics.summary(
            current_window_minutes=current_window_minutes,
            baseline_window_minutes=baseline_window_minutes,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Unable to query SigNoz traces: {exc}") from exc


@app.get("/customers/{customer_id}/alerts", response_model=CustomerAlertsResponse)
def customer_alerts(
    customer_id: str,
    current_window_minutes: int | None = None,
    baseline_window_minutes: int | None = None,
) -> CustomerAlertsResponse:
    try:
        return analytics.alerts_for_customer(
            customer_id,
            current_window_minutes=current_window_minutes,
            baseline_window_minutes=baseline_window_minutes,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Unable to query SigNoz traces: {exc}") from exc
