from dataclasses import dataclass

from platforms.rag import CorrectiveRAG, RetrievalDocument


@dataclass
class Retriever:
    responses: list[list[RetrievalDocument]]
    calls: int = 0

    def retrieve(self, query: str):
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return response


def workflow(retriever, maximum_attempts=3):
    return CorrectiveRAG(
        retriever,
        grader=lambda _query, doc: doc.score >= 0.8,
        rewriter=lambda question, attempt: f"{question} rewrite-{attempt}",
        generator=lambda _question, docs: f"Grounded in {docs[0].source}",
        maximum_attempts=maximum_attempts,
    )


def test_corrective_rag_rewrites_then_generates_from_relevant_evidence():
    document = RetrievalDocument("d1", "approved evidence", "runbook.md", 0.95)
    retriever = Retriever([[], [document]])
    result = workflow(retriever).invoke("How do I recover?")
    assert result.status == "grounded"
    assert result.attempts == 2
    assert result.documents == (document,)


def test_corrective_rag_stops_and_refuses_without_evidence():
    retriever = Retriever([[]])
    result = workflow(retriever, maximum_attempts=2).invoke("Unknown")
    assert result.status == "insufficient_evidence"
    assert result.attempts == 2
    assert retriever.calls == 2


def test_langgraph_dependency_boundary_is_explicit():
    retriever = Retriever([[]])
    try:
        graph = workflow(retriever, maximum_attempts=1).compile_langgraph()
    except RuntimeError as exc:
        assert "rag" in str(exc)
    else:
        result = graph.invoke({"question": "Unknown", "query": "", "attempts": 0, "documents": [], "answer": "", "status": ""})
        assert result["status"] == "insufficient_evidence"
