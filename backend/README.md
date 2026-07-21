# Per-Customer AI Cost Radar - Backend

Stage 1 demo service for the SigNoz hackathon.

## Environment

Set these before running the API:

- `OPENROUTER_API_KEY` - required
- `OPENROUTER_MODEL=openrouter/free` - default free router
- `OPENROUTER_HTTP_REFERER=http://localhost:8001` - optional but recommended
- `OPENROUTER_APP_TITLE=Per-Customer AI Cost Radar` - optional
- `OTEL_SERVICE_NAME=per-customer-ai-cost-radar`
- `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317`
- `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://localhost:4317`
- `OTEL_EXPORTER_OTLP_INSECURE=true`
- `OTEL_EXPORTER_OTLP_TRACES_INSECURE=true`
- `SIGNOZ_BASE_URL=http://localhost:8080`
- `SIGNOZ_API_KEY=` if your SigNoz instance requires API auth
- `SIGNOZ_SERVICE_NAME=per-customer-ai-cost-radar`
- `ANOMALY_CURRENT_WINDOW_MINUTES=15`
- `ANOMALY_BASELINE_WINDOW_MINUTES=60`
- `ANOMALY_BUCKET_MINUTES=5`
- `ANOMALY_THRESHOLD_MULTIPLIER=3.0`

The `cost_usd` fields are estimated from live token usage. If you use the free router, the real vendor bill is zero, so cost is best treated as a shadow estimate unless you switch to a paid model.

## Run

```powershell
cd backend
py -3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

## Endpoints

- `GET /health`
- `POST /chat`
- `POST /simulate_spike`
- `GET /simulate_spike`
- `GET /docs`

## Stage 2 tracing

- Every LLM call creates an `llm.openrouter.chat` span.
- Every tool lookup creates a `tool.customer_context_lookup` span.
- Each span carries `customer_id`, `model`, `input_tokens`, `output_tokens`, `cost_usd`, and `call_type`.

To verify locally, point the app at a collector or SigNoz instance on `localhost:4317`, call `/chat`, and confirm the traces show up in your backend.

## Stage 4 aggregation

- `GET /customers/summary`
- `GET /customers/{customer_id}/alerts`

These endpoints query SigNoz's Trace API and aggregate live span data by `customer_id`.
The default logic compares the last 15 minutes of spend to the previous 60 minutes of spend and flags an anomaly when the normalized spend rate is greater than `3x` baseline.
You can override the window sizes with query parameters like `?current_window_minutes=5&baseline_window_minutes=30`.
