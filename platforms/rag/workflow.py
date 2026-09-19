from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RetrievalDocument:
    document_id: str
    text: str
    source: str
    score: float


@dataclass(frozen=True)
class RAGResult:
    answer: str
    documents: tuple[RetrievalDocument, ...]
    attempts: int
    status: str


class Retriever(Protocol):
    def retrieve(self, query: str) -> list[RetrievalDocument]: ...


class CorrectiveRAG:
    """Bounded corrective-RAG workflow, usable directly or compiled with LangGraph."""

    def __init__(
        self,
        retriever: Retriever,
        grader: Callable[[str, RetrievalDocument], bool],
        rewriter: Callable[[str, int], str],
        generator: Callable[[str, list[RetrievalDocument]], str],
        maximum_attempts: int = 3,
    ) -> None:
        if not 1 <= maximum_attempts <= 5:
            raise ValueError("maximum_attempts must be between 1 and 5")
        self.retriever = retriever
        self.grader = grader
        self.rewriter = rewriter
        self.generator = generator
        self.maximum_attempts = maximum_attempts

    def invoke(self, question: str) -> RAGResult:
        query = question
        for attempt in range(1, self.maximum_attempts + 1):
            documents = [doc for doc in self.retriever.retrieve(query) if self.grader(query, doc)]
            if documents:
                return RAGResult(self.generator(question, documents), tuple(documents), attempt, "grounded")
            if attempt < self.maximum_attempts:
                query = self.rewriter(question, attempt)
        return RAGResult("Insufficient evidence to answer from the approved knowledge base.", (), self.maximum_attempts, "insufficient_evidence")

    def compile_langgraph(self):
        try:
            from langgraph.graph import END, START, StateGraph
        except ImportError as exc:
            raise RuntimeError("install the 'rag' extra to enable LangGraph") from exc

        from typing import TypedDict

        workflow = self

        class State(TypedDict):
            question: str
            query: str
            attempts: int
            documents: list[RetrievalDocument]
            answer: str
            status: str

        def retrieve(state: State):
            attempt = state.get("attempts", 0) + 1
            query = state.get("query") or state["question"]
            documents = [doc for doc in workflow.retriever.retrieve(query) if workflow.grader(query, doc)]
            return {"attempts": attempt, "query": query, "documents": documents}

        def route(state: State):
            if state["documents"]:
                return "generate"
            return "rewrite" if state["attempts"] < workflow.maximum_attempts else "refuse"

        def rewrite(state: State):
            return {"query": workflow.rewriter(state["question"], state["attempts"])}

        def generate(state: State):
            return {"answer": workflow.generator(state["question"], state["documents"]), "status": "grounded"}

        def refuse(_: State):
            return {"answer": "Insufficient evidence to answer from the approved knowledge base.", "status": "insufficient_evidence"}

        graph = StateGraph(State)
        graph.add_node("retrieve", retrieve)
        graph.add_node("rewrite", rewrite)
        graph.add_node("generate", generate)
        graph.add_node("refuse", refuse)
        graph.add_edge(START, "retrieve")
        graph.add_conditional_edges("retrieve", route)
        graph.add_edge("rewrite", "retrieve")
        graph.add_edge("generate", END)
        graph.add_edge("refuse", END)
        return graph.compile()
