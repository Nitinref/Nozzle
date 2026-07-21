from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from pydantic import BaseModel, Field

from .models import TimeSeriesPoint


class TraceSpan(BaseModel):
    trace_id: str | None = None
    span_id: str | None = None
    parent_span_id: str | None = None
    name: str = ""
    customer_id: str = ""
    call_type: str = ""
    model: str = ""
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: float = 0.0
    timestamp_ms: int = 0


class CustomerSummaryItem(BaseModel):
    customer_id: str
    customer_label: str
    current_cost_usd: float
    current_call_count: int
    avg_cost_per_call_usd: float
    baseline_cost_usd: float
    baseline_call_count: int
    baseline_rate_per_minute: float
    current_rate_per_minute: float
    anomaly_ratio: float
    trend: str
    status: str
    retry_count: int
    tool_call_count: int
    llm_call_count: int
    cost_time_series: list[TimeSeriesPoint] = Field(default_factory=list)
    top_trace_id: str | None = None
    top_reason: str | None = None


class CustomerSummaryResponse(BaseModel):
    source: str
    generated_at: str
    current_window_minutes: int
    baseline_window_minutes: int
    anomaly_threshold: float
    customers: list[CustomerSummaryItem]


class CustomerAlert(BaseModel):
    customer_id: str
    customer_label: str
    generated_at: str
    current_window_minutes: int
    baseline_window_minutes: int
    current_cost_usd: float
    baseline_cost_usd: float
    current_call_count: int
    baseline_call_count: int
    current_rate_per_minute: float
    baseline_rate_per_minute: float
    anomaly_ratio: float
    threshold: float
    reason: str
    trend: str
    trace_ids: list[str]
    evidence: list[TraceSpan]


class CustomerAlertsResponse(BaseModel):
    source: str
    generated_at: str
    customer_id: str
    customer_label: str
    alerts: list[CustomerAlert]


@dataclass(frozen=True)
class SigNozConfig:
    base_url: str
    api_key: str | None
    service_name: str
    query_path: str = "/api/v5/query_range"
    timeout_seconds: float = 60.0


class SigNozTraceClient:
    def __init__(self, config: SigNozConfig | None = None) -> None:
        if config is None:
            config = SigNozConfig(
                base_url=os.getenv("SIGNOZ_BASE_URL", "http://localhost:8080"),
                api_key=os.getenv("SIGNOZ_API_KEY") or None,
                service_name=os.getenv("SIGNOZ_SERVICE_NAME", "per-customer-ai-cost-radar"),
                query_path=os.getenv("SIGNOZ_QUERY_PATH", "/api/v5/query_range"),
                timeout_seconds=float(os.getenv("SIGNOZ_TIMEOUT_SECONDS", "60")),
            )
        self.config = config
        self._client = httpx.Client(timeout=config.timeout_seconds)

    def query_spans(self, start_ms: int, end_ms: int, customer_id: str | None = None) -> list[TraceSpan]:
        query = self._build_clickhouse_query(start_ms, end_ms, customer_id=customer_id)
        payload: dict[str, Any] = {
            "start": start_ms,
            "end": end_ms,
            "requestType": "scalar",
            "variables": {},
            "compositeQuery": {
                "queries": [
                    {
                        "type": "clickhouse_sql",
                        "spec": {
                            "name": "A",
                            "query": query,
                            "disabled": False,
                        },
                    }
                ]
            },
        }
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["SIGNOZ-API-KEY"] = self.config.api_key

        response = self._client.post(f"{self.config.base_url.rstrip('/')}{self.config.query_path}", json=payload, headers=headers)
        response.raise_for_status()
        return self._extract_spans(response.json())

    def _build_clickhouse_query(self, start_ms: int, end_ms: int, customer_id: str | None = None) -> str:
        filters = [
            "timestamp BETWEEN $start_datetime AND $end_datetime",
            "ts_bucket_start BETWEEN $start_timestamp - 1800 AND $end_timestamp",
            f"`resource_string_service$$name` = '{self.config.service_name}'",
            "attributes_string['customer_id'] != ''",
        ]
        if customer_id:
            filters.append(f"attributes_string['customer_id'] = '{customer_id}'")
        where_clause = " AND ".join(filters)
        return f"""
SELECT
  toUnixTimestamp64Milli(timestamp) AS timestamp_ms,
  trace_id,
  span_id,
  parent_span_id,
  name,
  ifNull(attributes_string['customer_id'], '') AS customer_id,
  ifNull(attributes_string['call_type'], '') AS call_type,
  ifNull(attributes_string['model'], '') AS model,
  ifNull(attributes_number['cost_usd'], 0) AS cost_usd,
  ifNull(attributes_number['input_tokens'], 0) AS input_tokens,
  ifNull(attributes_number['output_tokens'], 0) AS output_tokens,
  toFloat64(duration_nano) / 1000000.0 AS duration_ms
FROM signoz_traces.distributed_signoz_index_v3
WHERE {where_clause}
ORDER BY timestamp ASC
LIMIT 10000
""".strip()

    def _extract_spans(self, payload: Any) -> list[TraceSpan]:
        rows = self._extract_rows(payload)
        spans: list[TraceSpan] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            spans.append(
                TraceSpan(
                    trace_id=self._string_value(row, "trace_id", "traceID", "traceId"),
                    span_id=self._string_value(row, "span_id", "spanID", "spanId"),
                    parent_span_id=self._string_value(row, "parent_span_id", "parentSpanId"),
                    name=self._string_value(row, "name"),
                    customer_id=self._string_value(row, "customer_id"),
                    call_type=self._string_value(row, "call_type"),
                    model=self._string_value(row, "model"),
                    cost_usd=self._float_value(row, "cost_usd"),
                    input_tokens=int(self._float_value(row, "input_tokens")),
                    output_tokens=int(self._float_value(row, "output_tokens")),
                    duration_ms=self._float_value(row, "duration_ms"),
                    timestamp_ms=int(self._float_value(row, "timestamp_ms")),
                )
            )
        return spans

    def _extract_rows(self, payload: Any) -> list[Any]:
        if isinstance(payload, list):
            return payload
        if not isinstance(payload, dict):
            return []
        data = payload.get("data")
        if isinstance(data, dict):
            for key in ("results", "result", "rows", "records"):
                value = data.get(key)
                if isinstance(value, list):
                    nested_rows = self._extract_rows(value)
                    if nested_rows:
                        return nested_rows
            if "data" in data and isinstance(data["data"], dict):
                nested_rows = self._extract_rows(data["data"])
                if nested_rows:
                    return nested_rows
        for key in ("data", "result", "results", "rows", "records"):
            value = payload.get(key)
            if isinstance(value, list):
                if value and all(isinstance(item, dict) and "data" in item for item in value):
                    flattened: list[dict[str, Any]] = []
                    for item in value:
                        if not isinstance(item, dict):
                            continue
                        rows = item.get("data")
                        columns = item.get("columns") or []
                        if not isinstance(rows, list):
                            continue
                        if rows and all(isinstance(row, list) for row in rows) and isinstance(columns, list) and all(isinstance(col, dict) for col in columns):
                            names = [str(col.get("name") or col.get("field") or col.get("column") or "") for col in columns]
                            for row_values in rows:
                                row: dict[str, Any] = {}
                                for idx, cell in enumerate(row_values):
                                    if idx < len(names) and names[idx]:
                                        row[names[idx]] = cell
                                flattened.append(row)
                        elif rows and all(isinstance(row, dict) for row in rows):
                            flattened.extend(rows)
                    if flattened:
                        return flattened
                if value and all(isinstance(item, dict) for item in value):
                    return value
                if value and all(isinstance(item, list) for item in value):
                    columns = payload.get("columns") or payload.get("schema") or []
                    if isinstance(columns, list) and all(isinstance(col, dict) for col in columns):
                        names = [str(col.get("name") or col.get("field") or col.get("column") or "") for col in columns]
                        mapped: list[dict[str, Any]] = []
                        for item in value:
                            row = {}
                            for idx, cell in enumerate(item):
                                if idx < len(names) and names[idx]:
                                    row[names[idx]] = cell
                            mapped.append(row)
                        return mapped
                    return value
            if isinstance(value, dict):
                nested = self._extract_rows(value)
                if nested:
                    return nested
        if isinstance(data, dict):
            results = data.get("results")
            if isinstance(results, list):
                mapped_rows: list[dict[str, Any]] = []
                for result in results:
                    if not isinstance(result, dict):
                        continue
                    rows = result.get("data")
                    columns = result.get("columns") or []
                    if isinstance(rows, list) and rows and all(isinstance(item, list) for item in rows):
                        if isinstance(columns, list) and all(isinstance(col, dict) for col in columns):
                            names = [str(col.get("name") or col.get("field") or col.get("column") or "") for col in columns]
                            for item in rows:
                                row: dict[str, Any] = {}
                                for idx, cell in enumerate(item):
                                    if idx < len(names) and names[idx]:
                                        row[names[idx]] = cell
                                mapped_rows.append(row)
                        elif rows and all(isinstance(item, dict) for item in rows):
                            mapped_rows.extend(rows)
                if mapped_rows:
                    return mapped_rows
        return []

    def _string_value(self, row: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = row.get(key)
            if value not in (None, ""):
                return str(value)
        return ""

    def _float_value(self, row: dict[str, Any], *keys: str) -> float:
        for key in keys:
            value = row.get(key)
            if value not in (None, ""):
                try:
                    return float(value)
                except (TypeError, ValueError):
                    continue
        return 0.0


class CustomerAnalyticsService:
    def __init__(self, client: SigNozTraceClient | None = None) -> None:
        self.client = client or SigNozTraceClient()
        self.current_window_minutes = int(os.getenv("ANOMALY_CURRENT_WINDOW_MINUTES", "15"))
        self.baseline_window_minutes = int(os.getenv("ANOMALY_BASELINE_WINDOW_MINUTES", "60"))
        self.bucket_minutes = int(os.getenv("ANOMALY_BUCKET_MINUTES", "5"))
        self.threshold = float(os.getenv("ANOMALY_THRESHOLD_MULTIPLIER", "3.0"))

    def _customer_label(self, customer_id: str) -> str:
        normalized = customer_id.replace("_", " ").replace("-", " ").strip()
        if not normalized:
            return customer_id
        return " ".join(part[:1].upper() + part[1:] for part in normalized.split())

    def summary(
        self,
        *,
        current_window_minutes: int | None = None,
        baseline_window_minutes: int | None = None,
    ) -> CustomerSummaryResponse:
        current_window_minutes = current_window_minutes or self.current_window_minutes
        baseline_window_minutes = baseline_window_minutes or self.baseline_window_minutes
        now = datetime.now(timezone.utc)
        start = now - timedelta(minutes=current_window_minutes + baseline_window_minutes)
        spans = self.client.query_spans(_to_ms(start), _to_ms(now))
        summaries = self._summarize_spans(
            spans,
            current_window_minutes=current_window_minutes,
            baseline_window_minutes=baseline_window_minutes,
        )
        return CustomerSummaryResponse(
            source="signoz_trace_api",
            generated_at=now.isoformat(),
            current_window_minutes=current_window_minutes,
            baseline_window_minutes=baseline_window_minutes,
            anomaly_threshold=self.threshold,
            customers=sorted(
                summaries.values(),
                key=lambda item: (item.status != "anomaly", -item.current_cost_usd, item.customer_id),
            ),
        )

    def alerts_for_customer(
        self,
        customer_id: str,
        *,
        current_window_minutes: int | None = None,
        baseline_window_minutes: int | None = None,
    ) -> CustomerAlertsResponse:
        current_window_minutes = current_window_minutes or self.current_window_minutes
        baseline_window_minutes = baseline_window_minutes or self.baseline_window_minutes
        now = datetime.now(timezone.utc)
        start = now - timedelta(minutes=current_window_minutes + baseline_window_minutes)
        spans = self.client.query_spans(_to_ms(start), _to_ms(now), customer_id=customer_id)
        summary = self._summarize_spans(
            spans,
            current_window_minutes=current_window_minutes,
            baseline_window_minutes=baseline_window_minutes,
        ).get(customer_id)
        if summary is None:
            return CustomerAlertsResponse(
                source="signoz_trace_api",
                generated_at=now.isoformat(),
                customer_id=customer_id,
                customer_label=customer_id,
                alerts=[],
            )

        alerts: list[CustomerAlert] = []
        if summary.status == "anomaly":
            customer_spans = [span for span in spans if span.customer_id == customer_id]
            evidence = self._top_evidence(customer_spans)
            alerts.append(
                CustomerAlert(
                    customer_id=customer_id,
                    customer_label=summary.customer_label,
                    generated_at=now.isoformat(),
                    current_window_minutes=current_window_minutes,
                    baseline_window_minutes=baseline_window_minutes,
                    current_cost_usd=summary.current_cost_usd,
                    baseline_cost_usd=summary.baseline_cost_usd,
                    current_call_count=summary.current_call_count,
                    baseline_call_count=summary.baseline_call_count,
                    current_rate_per_minute=summary.current_rate_per_minute,
                    baseline_rate_per_minute=summary.baseline_rate_per_minute,
                    anomaly_ratio=summary.anomaly_ratio,
                    threshold=self.threshold,
                    reason=summary.top_reason or "Spend exceeded baseline threshold",
                    trend=summary.trend,
                    trace_ids=[span.trace_id for span in evidence if span.trace_id],
                    evidence=evidence,
                )
            )

        return CustomerAlertsResponse(
            source="signoz_trace_api",
            generated_at=now.isoformat(),
            customer_id=customer_id,
            customer_label=summary.customer_label,
            alerts=alerts,
        )

    def _summarize_spans(
        self,
        spans: list[TraceSpan],
        *,
        current_window_minutes: int,
        baseline_window_minutes: int,
    ) -> dict[str, CustomerSummaryItem]:
        buckets: dict[str, dict[str, list[TraceSpan]]] = defaultdict(lambda: {"current": [], "baseline": []})
        series_buckets: dict[str, dict[int, list[TraceSpan]]] = defaultdict(lambda: defaultdict(list))
        now_ms = _to_ms(datetime.now(timezone.utc))
        current_start_ms = now_ms - current_window_minutes * 60 * 1000
        bucket_ms = max(60_000, self.bucket_minutes * 60 * 1000)

        for span in spans:
            if not span.customer_id:
                continue
            bucket_name = "current" if span.timestamp_ms >= current_start_ms else "baseline"
            buckets[span.customer_id][bucket_name].append(span)
            bucket_start_ms = (span.timestamp_ms // bucket_ms) * bucket_ms
            series_buckets[span.customer_id][bucket_start_ms].append(span)

        summaries: dict[str, CustomerSummaryItem] = {}
        for customer_id, groups in buckets.items():
            current_spans = groups["current"]
            baseline_spans = groups["baseline"]
            current_cost = round(sum(span.cost_usd for span in current_spans), 6)
            current_calls = len(current_spans)
            baseline_cost = round(sum(span.cost_usd for span in baseline_spans), 6)
            baseline_calls = len(baseline_spans)
            current_rate = current_cost / max(1, current_window_minutes)
            baseline_rate = baseline_cost / max(1, baseline_window_minutes)
            anomaly_ratio = round(current_rate / baseline_rate, 3) if baseline_rate > 0 else (float("inf") if current_cost > 0 else 0.0)
            trend = self._trend(current_rate, baseline_rate)
            retry_count = sum(1 for span in current_spans if span.call_type == "retry")
            tool_call_count = sum(1 for span in current_spans if span.call_type == "tool_call")
            llm_call_count = sum(1 for span in current_spans if span.call_type == "llm_call")
            avg_cost = round(current_cost / current_calls, 6) if current_calls else 0.0
            top_trace_id, top_reason = self._root_cause(current_spans)
            status = "anomaly" if anomaly_ratio >= self.threshold and current_cost > 0 else "normal"
            time_series = [
                TimeSeriesPoint(
                    bucket_start_ms=bucket_start_ms,
                    cost_usd=round(sum(span.cost_usd for span in bucket_spans), 6),
                    call_count=len(bucket_spans),
                )
                for bucket_start_ms, bucket_spans in sorted(series_buckets[customer_id].items())
            ]

            summaries[customer_id] = CustomerSummaryItem(
                customer_id=customer_id,
                customer_label=self._customer_label(customer_id),
                current_cost_usd=current_cost,
                current_call_count=current_calls,
                avg_cost_per_call_usd=avg_cost,
                baseline_cost_usd=baseline_cost,
                baseline_call_count=baseline_calls,
                baseline_rate_per_minute=round(baseline_rate, 6),
                current_rate_per_minute=round(current_rate, 6),
                anomaly_ratio=anomaly_ratio if anomaly_ratio != float("inf") else 9999.0,
                trend=trend,
                status=status,
                retry_count=retry_count,
                tool_call_count=tool_call_count,
                llm_call_count=llm_call_count,
                cost_time_series=time_series,
                top_trace_id=top_trace_id,
                top_reason=top_reason,
            )

        return summaries

    def _trend(self, current_rate: float, baseline_rate: float) -> str:
        if baseline_rate <= 0:
            return "up" if current_rate > 0 else "flat"
        ratio = current_rate / baseline_rate
        if ratio > 1.2:
            return "up"
        if ratio < 0.8:
            return "down"
        return "flat"

    def _root_cause(self, spans: list[TraceSpan]) -> tuple[str | None, str | None]:
        if not spans:
            return None, None

        trace_costs: dict[str, float] = defaultdict(float)
        trace_counts: dict[str, int] = defaultdict(int)
        retry_count = 0
        tool_count = 0
        for span in spans:
            if span.trace_id:
                trace_costs[span.trace_id] += span.cost_usd
                trace_counts[span.trace_id] += 1
            if span.call_type == "retry":
                retry_count += 1
            if span.call_type == "tool_call":
                tool_count += 1

        culprit_trace = max(trace_costs.items(), key=lambda item: item[1])[0] if trace_costs else None
        if retry_count >= 3:
            reason = f"{retry_count} retries in the current window"
        elif tool_count >= 3:
            reason = f"{tool_count} tool calls in the current window"
        elif culprit_trace:
            reason = f"largest trace accounted for {round(trace_costs[culprit_trace], 6)} USD across {trace_counts[culprit_trace]} spans"
        else:
            reason = "spend increased across live model calls"
        return culprit_trace, reason

    def _top_evidence(self, spans: list[TraceSpan], limit: int = 10) -> list[TraceSpan]:
        return sorted(spans, key=lambda span: (span.cost_usd, span.duration_ms), reverse=True)[:limit]


def _to_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)
