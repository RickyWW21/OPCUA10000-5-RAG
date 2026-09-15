"""Part 5 retrieval-augmented generation pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .llm import ChatModel, LLMError
from .retrieval import Part5Retriever, RetrievedRecord


@dataclass(frozen=True)
class RAGAnswer:
    answer: str
    mode: Literal["generated", "offline"]
    citations: list[dict[str, str]]
    retrieved: list[dict[str, Any]]
    error: str | None = None


class RAGPipeline:
    def __init__(self, *, retriever: Part5Retriever, chat_model: ChatModel | None = None, max_context_chars: int = 12000) -> None:
        if max_context_chars <= 0:
            raise ValueError("max_context_chars must be positive")
        self.retriever = retriever
        self.chat_model = chat_model
        self.max_context_chars = max_context_chars

    def ask(self, question: str, *, top_k: int = 6, relationship_depth: int = 0) -> RAGAnswer:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("question must not be blank")
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        if relationship_depth < 0:
            raise ValueError("relationship_depth must be non-negative")
        records = self.retriever.retrieve(question, top_k=top_k, relationship_depth=relationship_depth)
        retrieved, citations = self._serialize(records)
        if not records:
            return RAGAnswer("未找到相关 Part 5 证据。", "offline", [], [])
        context = self._context(records, citations)
        system = ("You answer questions using only the supplied OPC UA 10000-5 Part 5 evidence. "
                  "Cite claims with supplied labels (for example [E1]); never invent labels or sources.")
        user = f"Question: {question.strip()}\n\nPart 5 evidence:\n{context}"
        if self.chat_model is not None:
            try:
                answer = self.chat_model.generate(system=system, user=user, temperature=0.0)
                return RAGAnswer(answer, "generated", citations, retrieved)
            except LLMError as exc:
                return RAGAnswer(self._offline_answer(records, citations), "offline", citations, retrieved, str(exc))
        return RAGAnswer(self._offline_answer(records, citations), "offline", citations, retrieved)

    @staticmethod
    def _serialize(records: list[RetrievedRecord]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        counters: dict[str, int] = {}
        retrieved: list[dict[str, Any]] = []
        citations: list[dict[str, str]] = []
        prefixes = {"entity": "E", "table": "T", "chunk": "C", "relationship": "R"}
        for record in records:
            prefix = prefixes.get(record.type, "C")
            counters[prefix] = counters.get(prefix, 0) + 1
            label = f"[{prefix}{counters[prefix]}]"
            retrieved.append({"id": record.id, "type": record.type, "title": record.title, "snippet": record.snippet,
                              "section": record.section, "table_number": record.table_number, "doc": record.doc, "label": label})
            citations.append({"label": label, "title": record.title, "id": record.id})
        return retrieved, citations

    def _context(self, records: list[RetrievedRecord], citations: list[dict[str, str]]) -> str:
        chunks: list[str] = []
        used = 0
        for record, citation in zip(records, citations):
            line = f"{citation['label']} {record.title}: {record.snippet}"
            remaining = self.max_context_chars - used
            if remaining <= 0:
                break
            chunks.append(line[:remaining])
            used += len(chunks[-1]) + 1
        return "\n".join(chunks)

    @staticmethod
    def _offline_answer(records: list[RetrievedRecord], citations: list[dict[str, str]]) -> str:
        return "\n".join(["离线检索结果（未调用语言模型，来源：OPC UA 10000-5）："] + [f"{c['label']} {r.title}: {r.snippet}" for r, c in zip(records, citations)])
