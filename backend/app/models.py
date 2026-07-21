from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    customer_id: str = Field(..., min_length=1, max_length=128)
    message: str = Field(..., min_length=1, max_length=4000)


class SpikeRequest(BaseModel):
    customer_id: str = Field(..., min_length=1, max_length=128)
    multiplier: float = Field(default=4.0, ge=1.0, le=25.0)
    remaining_calls: int = Field(default=5, ge=1, le=100)


class CallRecord(BaseModel):
    call_id: str
    call_type: Literal["llm_call", "tool_call", "retry"]
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    tool_name: Optional[str] = None
    notes: Optional[str] = None


class TimeSeriesPoint(BaseModel):
    bucket_start_ms: int
    cost_usd: float
    call_count: int


class ChatResponse(BaseModel):
    customer_id: str
    message: str
    scenario: str
    assistant_message: str
    model_used: str
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float
    total_latency_ms: int
    calls: list[CallRecord]
    summary: str


class SpikeResponse(BaseModel):
    customer_id: str
    multiplier: float
    remaining_calls: int
    status: str
