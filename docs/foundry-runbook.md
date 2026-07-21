# Foundry Runbook

Use this when you need to generate and commit `casting.yaml.lock` for a reproducible SigNoz deployment.

## Prerequisites

- Linux or macOS
- On Windows, use WSL 2 with native Docker Engine inside WSL
- Docker Engine 20.10+ with Compose v2
- At least 4 GB RAM allocated to Docker
- Open ports `8080`, `4317`, `4318`, and `8000` if you enable the MCP server

## 1. Install Foundry

```bash
curl -fsSL https://signoz.io/foundry.sh | bash
```

## 2. Create `casting.yaml`

Use the repo-root file already included in this project:

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

To enable the MCP server, uncomment or add:

```yaml
  mcp:
    spec:
      enabled: true
```

For the hackathon demo, you can also use the prebuilt MCP-enabled file at [casting.mcp.yaml](/D:/nozzle/casting.mcp.yaml).

## 3. Generate the lockfile

Run Foundry in sequence so the generated files and lockfile are reproducible:

```bash
foundryctl gauge -f casting.yaml
foundryctl forge -f casting.yaml
```

At this point Foundry writes `casting.yaml.lock`.

## 4. Start SigNoz

Use the one-step command if you want Foundry to validate, render, and start the stack:

```bash
foundryctl cast -f casting.yaml
```

If you prefer to inspect the generated Compose files before starting:

```bash
cd pours/deployment
docker compose up -d
```

## 5. Verify the stack

```bash
docker ps
```

Open:

```text
http://localhost:8080
```

If MCP is enabled, verify it too:

```bash
curl -fsS localhost:8000/livez && echo " OK"
```

## 6. Commit the reproducibility files

Commit these files at repo root:

- `casting.yaml`
- `casting.yaml.lock`

## 7. Re-run after edits

Whenever `casting.yaml` changes, rerun:

```bash
foundryctl cast -f casting.yaml
```

That updates the generated files and refreshes the lockfile.
