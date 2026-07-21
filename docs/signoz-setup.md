# SigNoz Local Setup

This project uses SigNoz self-hosted on Docker Compose, following the current Foundry-based install flow.

## Prerequisites

- Docker Engine 20.10+ with Docker Compose v2
- At least 4 GB RAM allocated to Docker
- Ports `8080`, `4317`, and `4318` available

If you are on Windows, run this inside WSL 2 with Docker Engine inside WSL.

## Install Foundry

```powershell
curl -fsSL https://signoz.io/foundry.sh | bash
```

## Create `casting.yaml`

```yaml
apiVersion: v1alpha1
kind: Installation
metadata:
  name: signoz
spec:
  deployment:
    flavor: compose
    mode: docker
```

## Generate and Start SigNoz

```powershell
foundryctl gauge -f casting.yaml
foundryctl forge -f casting.yaml
cd pours/deployment
docker compose up -d
```

If you want Foundry to do both generate and start in one step, use:

```powershell
foundryctl cast -f casting.yaml
```

## Verify It Is Up

```powershell
docker ps
```

You should see containers for ClickHouse, Postgres, ClickHouse Keeper, the SigNoz OTEL collector, and the SigNoz UI.

## Verify Traces Arrive

1. Open `http://localhost:8080`.
2. Go to `APM` or `Traces Explorer`.
3. Select the service `per-customer-ai-cost-radar`.
4. Search for spans with:
   - `name = 'llm.openrouter.chat'`
   - `customer_id = 'acme'`

Useful queries:

```text
service.name = 'per-customer-ai-cost-radar'
```

```text
service.name = 'per-customer-ai-cost-radar' AND customer_id = 'acme'
```

```text
name = 'tool.customer_context_lookup'
```

If you do not see data, check the SigNoz UI, confirm the app is exporting to `localhost:4317`, and make sure the app has received at least one `/chat` request.

