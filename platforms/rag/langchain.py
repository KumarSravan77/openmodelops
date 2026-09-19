from __future__ import annotations

from collections.abc import Callable


def build_langchain_runnable(retrieve: Callable[[str], list[str]], generate: Callable[[dict], str]):
    """Build a real LangChain Runnable without coupling core services to LangChain."""
    try:
        from langchain_core.runnables import RunnableLambda, RunnableParallel, RunnablePassthrough
    except ImportError as exc:
        raise RuntimeError("install the 'rag' extra to enable LangChain") from exc

    return RunnableParallel(context=RunnableLambda(retrieve), question=RunnablePassthrough()) | RunnableLambda(generate)
