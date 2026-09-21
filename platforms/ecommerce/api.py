from __future__ import annotations

import os
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field

from packages.contracts import ModelEndpoint
from packages.observability.telemetry import telemetry_from_environment
from platforms.agents.providers import OllamaModel, OpenAICompatibleModel, UrllibTransport

from .catalog import ProductCatalog
from .domain import ChatRequest, ToolCallRequest
from .retrieval import HybridProductRetriever
from .tools import ProductToolRegistry
from .workflow import ProductAssistant

CATALOG_PATH = Path(os.getenv("ECOMMERCE_CATALOG", "examples/ecommerce-assistant/data/products.json"))
catalog = ProductCatalog.load(CATALOG_PATH)
retriever = HybridProductRetriever(catalog)


def _generator():
    provider = os.getenv("ECOMMERCE_MODEL_PROVIDER", "deterministic")
    if provider == "deterministic":
        return None
    model_id = os.getenv("ECOMMERCE_MODEL_ID", "qwen2.5:3b")
    endpoint = ModelEndpoint(
        "ecommerce-generator",
        model_id,
        os.getenv("ECOMMERCE_MODEL_BASE_URL", "http://127.0.0.1:11434"),
        timeout_seconds=int(os.getenv("ECOMMERCE_MODEL_TIMEOUT_SECONDS", "120")),
    )
    if provider == "ollama":
        model = OllamaModel(UrllibTransport())
    elif provider == "openai-compatible":
        model = OpenAICompatibleModel(UrllibTransport(), os.getenv("ECOMMERCE_MODEL_API_KEY", ""))
    else:
        raise RuntimeError("ECOMMERCE_MODEL_PROVIDER must be deterministic, ollama or openai-compatible")

    def generate(question, hits):
        evidence = "\n".join(
            f"[{hit.product.product_id}] {hit.product.name}; CAD {hit.product.price_cad:.2f}; "
            f"rating {hit.product.rating}/5; {hit.product.description}"
            for hit in hits
        )
        system = (
            "You are a product assistant. Use only the supplied catalog evidence. Cite every recommendation with its "
            "product ID in square brackets. If evidence is insufficient, say so. Never invent availability or prices."
        )
        return model.generate(endpoint, system, f"QUESTION:\n{question}\n\nCATALOG EVIDENCE:\n{evidence}")

    return generate


assistant = ProductAssistant(retriever, generator=_generator())
tools = ProductToolRegistry(catalog, retriever)
telemetry = telemetry_from_environment("openmodelops-ecommerce")

app = FastAPI(title="OpenModelOps Product Assistant", version="1.0.0")
REQUESTS = Counter("ecommerce_assistant_requests_total", "Product assistant requests", ["status"])
LATENCY = Histogram("ecommerce_assistant_duration_seconds", "Product assistant latency")
TOOL_CALLS = Counter("ecommerce_assistant_tool_calls_total", "Governed product tool calls", ["tool", "status"])


class MCPRequest(BaseModel):
    jsonrpc: str = Field(pattern=r"^2\.0$")
    id: str | int
    method: str
    params: dict = Field(default_factory=dict)


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "alive"}


@app.get("/health/ready")
def ready() -> dict:
    return {"status": "ready", "catalog_products": len(catalog.products), "external_web_search": False}


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/", response_class=HTMLResponse)
def chat_ui() -> str:
    return """<!doctype html><html><head><title>OpenModelOps Product Assistant</title>
    <meta name="viewport" content="width=device-width"><style>body{font:16px system-ui;max-width:850px;margin:3rem auto;padding:0 1rem}textarea{width:100%;min-height:90px}button{padding:.7rem 1.2rem}pre{white-space:pre-wrap;background:#f4f4f4;padding:1rem}</style></head>
    <body><h1>Product Assistant</h1><p>Synthetic catalog. Answers include product citations.</p>
    <textarea id="q" placeholder="Recommend noise-cancelling headphones under CAD 300"></textarea><br><button onclick="ask()">Ask</button><pre id="a"></pre>
    <script>async function ask(){let r=await fetch('/v1/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q.value})});a.textContent=JSON.stringify(await r.json(),null,2)}</script></body></html>"""


@app.post("/v1/chat")
def chat(request: ChatRequest) -> dict:
    started = time.perf_counter()
    attributes = {"rag.question.digest": __import__("hashlib").sha256(request.question.encode()).hexdigest()}
    try:
        if telemetry:
            with telemetry.operation("retrieval", attributes=attributes):
                result = assistant.ask(request.question, request.maximum_results)
        else:
            result = assistant.ask(request.question, request.maximum_results)
    except Exception:
        REQUESTS.labels("error").inc()
        raise
    REQUESTS.labels(result.status).inc()
    LATENCY.observe(time.perf_counter() - started)
    return {
        "answer": result.answer,
        "citations": result.citations,
        "attempts": result.attempts,
        "status": result.status,
        "web_search_used": False,
    }


@app.get("/v1/products")
def products() -> dict:
    return {"products": [product.model_dump() for product in catalog.products]}


@app.get("/v1/tools")
def tool_definitions() -> dict:
    return {"tools": tools.definitions()}


@app.post("/v1/tools/call")
def call_tool(request: ToolCallRequest) -> dict:
    try:
        result = tools.call(request.name, request.arguments)
    except PermissionError as exc:
        TOOL_CALLS.labels(request.name, "denied").inc()
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        TOOL_CALLS.labels(request.name, "invalid").inc()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    TOOL_CALLS.labels(request.name, "success").inc()
    return result


@app.post("/mcp")
def mcp(request: MCPRequest) -> dict:
    if request.method == "tools/list":
        result = {"tools": tools.definitions()}
    elif request.method == "tools/call":
        try:
            result = tools.call(str(request.params.get("name", "")), dict(request.params.get("arguments", {})))
        except (PermissionError, ValueError) as exc:
            return {"jsonrpc": "2.0", "id": request.id, "error": {"code": -32602, "message": str(exc)}}
    else:
        return {"jsonrpc": "2.0", "id": request.id, "error": {"code": -32601, "message": "method not found"}}
    return {"jsonrpc": "2.0", "id": request.id, "result": result}
