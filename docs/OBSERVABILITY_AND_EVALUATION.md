# AI observability and evaluation

OpenModelOps uses OpenTelemetry as the stable instrumentation boundary. Agent, LLM, retrieval, reranking, tool, policy and factory operations use the same semantic operation model. Raw prompts, inputs, outputs, documents, retrieved context, credentials and authorization material are excluded unless an operator explicitly enables content capture.

## Support matrix

| Capability | Level | Production boundary |
|---|---|---|
| OpenTelemetry traces | Implemented | OTLP/HTTP exporter, parent trace propagation, privacy filtering and error recording |
| Prometheus metrics | Implemented | API request, latency and lifecycle metrics are scraped locally |
| Grafana | Implemented local deployment | Provisioned Prometheus source and factory dashboard; production alert routing remains environment-specific |
| Langfuse | Implemented OTLP adapter | Set provider `langfuse`, its OTLP endpoint and auth header; self-hosted Langfuse is deployed separately |
| Phoenix | Implemented OTLP adapter | Set provider `phoenix`, endpoint and project; Phoenix server is deployed separately |
| Opik | Implemented native SDK adapter | Uses the Opik span context manager with privacy-filtered metadata; install `.[observability]` and deploy/configure Opik separately |
| Ragas | Implemented optional runner | Install `.[evaluation]`; evaluator model and credentials are supplied by the deployment |
| DeepEval | Implemented optional runner | Install `.[evaluation]`; metrics are normalized into the same fail-closed quality gate |
| MLflow registry | Implemented REST synchronization | Registers versions, assigns aliases and records governance evidence as tags |
| LangChain | Implemented optional Runnable | Install `.[rag]`; retrieval and generation remain dependency-injected |
| LangGraph | Implemented optional graph | Bounded retrieve/grade/rewrite/generate/refuse workflow with maximum attempts |

The platform does not run every observability product simultaneously. That would duplicate sensitive telemetry and waste resources. Select one trace/evaluation backend per environment while retaining Prometheus and Grafana for service reliability.

## Local traces

Start the collector and point the agent API at it:

```bash
docker compose --profile telemetry up -d otel-collector
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://otel-collector:4318/v1/traces docker compose up --build agent-api
```

The local collector intentionally uses a debug exporter. For a shared environment, replace that exporter with the approved Langfuse, Phoenix, Opik or managed OTLP endpoint and store authentication in a secret manager.

## Quality gate

Ragas and DeepEval results are normalized to scores between zero and one. A release passes only when every configured engine reports all required metrics at or above threshold. Missing metrics, empty datasets and evaluator failures block promotion.

The default portfolio policy demonstrates:

- faithfulness at least 0.90;
- answer relevance at least 0.80;
- context precision at least 0.80;
- agent tool correctness at least 0.90.

These are starting policies, not universal business targets. Each production workload must establish its own risk-based thresholds, golden dataset and human review process.
