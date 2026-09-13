# TargetMind Deployment Guide

This guide covers how to deploy the TargetMind multi-agent orchestration system for production use.

## Prerequisites

1. **Docker & Docker Compose**: Ensure Docker is installed on your host machine.
2. **API Keys**: You must have a `.env` file in the root directory containing your LLM API keys.

```bash
# Example .env
GROQ_API_KEY=gsk_your_groq_api_key_here
```

## Running Locally via Docker Compose

For local testing or small-scale deployments, Docker Compose is the recommended approach. It automatically maps the `logs/` directory to your host machine so you can persist and inspect telemetry data.

```bash
# Build and start the container in detached mode
docker-compose up -d --build

# View real-time logs
docker-compose logs -f

# Stop the container
docker-compose down
```

The Chainlit UI will be accessible at `http://localhost:8000`.

## Production Considerations

### 1. Observability & Telemetry
TargetMind writes structured JSON logs to `logs/targetmind_telemetry.log`. In production, you should run an agent like **FluentBit**, **Logstash**, or **Promtail** to tail this file and forward it to a centralized logging system (e.g., Datadog, ELK stack, or Grafana Loki).

Telemetry captures:
- Trace IDs for end-to-end LLM requests.
- Latency (in milliseconds) for every agent hop.
- Errors, rate limits, and automated retry events.

### 2. Guardrails
The `orchestrator` implements deterministic guardrails:
- It halts empty responses.
- It detects and blocks hallucinated `ENTITY_ID` formats (e.g., `ENTITY_ID=UNKNOWN`).
- It hides internal tool execution stack traces from the end user.
If an agent hallucinates, the orchestrator transparently captures the failure in telemetry and triggers an automatic retry.

### 3. CI/CD & Benchmarking
Before deploying a new model version or modifying prompts, always run the evaluation harness:

```bash
# Inside the container or local env
python eval.py

# Expected Output:
# Entity Resolution Accuracy: [PASS] 18/18 correct
# OVERALL VERDICT: PASS
```

Never deploy if the entity resolution accuracy drops below the threshold (85%).

### 4. Scaling
For horizontal scaling (e.g., Kubernetes), configure the deployment to:
- Bind the Chainlit app to an ingress controller routing to port `8000`.
- Mount an ephemeral or persistent volume for `/app/logs` if running a sidecar logging agent.
- Set a higher `max_retries` configuration in `run_with_retry` if hitting aggressive API rate limits under high concurrency.
