import pytest


def test_rag_frameworks_import_and_langchain_pipeline_runs():
    pytest.importorskip("langgraph")
    pytest.importorskip("langchain_core")
    from platforms.rag.langchain import build_langchain_runnable

    pipeline = build_langchain_runnable(
        lambda question: [f"evidence:{question}"],
        lambda values: f"{values['question']}|{values['context'][0]}",
    )
    assert pipeline.invoke("question") == "question|evidence:question"


def test_evaluation_frameworks_import():
    assert pytest.importorskip("ragas")
    assert pytest.importorskip("deepeval")


def test_observability_frameworks_import():
    assert pytest.importorskip("opik")
    assert pytest.importorskip("langfuse")
    assert pytest.importorskip("phoenix.otel")
