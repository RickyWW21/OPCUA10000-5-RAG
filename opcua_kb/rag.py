"""Part 5 retrieval-augmented generation pipeline."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from .llm import ChatModel, LLMError
from .retrieval import Part5Retriever, RetrievedRecord

_CANONICAL_CITATION = re.compile(r"\[([ETCR])([1-9][0-9]*)\]")
_CITATION_CANDIDATE = re.compile(
    r"\[(?:[ETCR][^\]\n]*|[A-Za-z][0-9][^\]\n]*)(?:\]|(?=\n|$))"
)
_CITATION_PREFIXES = {"entity": "E", "table": "T", "chunk": "C", "relationship": "R"}


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
        if not records:
            return RAGAnswer("未找到相关 Part 5 证据。", "offline", [], [])

        selected, omitted = self._select_units(records)
        if not selected:
            return RAGAnswer(
                "未找到能在上下文预算内完整容纳的 Part 5 证据。",
                "offline",
                [],
                [],
                self._no_fit_error(omitted),
            )

        retrieved, citations = self._serialize([record for record, _ in selected])
        context = self._context(selected, citations)
        omission_error = self._omission_error(omitted)
        system = (
            "You answer questions using only the supplied OPC UA 10000-5 Part 5 evidence. "
            "Cite claims only with the supplied labels: [E1] entity, [T1] table, "
            "[C1] chunk, [R1] relationship. Never invent labels, cite omitted "
            "evidence, or use a label that was not supplied. If the evidence is "
            "insufficient, say so; do not infer that the specification has no rule."
        )
        user = f"Question: {question.strip()}\n\nPart 5 evidence:\n{context}"
        if self.chat_model is not None:
            try:
                answer = self.chat_model.generate(system=system, user=user, temperature=0.0)
            except LLMError as exc:
                return RAGAnswer(
                    self._offline_answer(selected, citations),
                    "offline",
                    citations,
                    retrieved,
                    _join_errors(str(exc), omission_error),
                )
            citation_error = self._citation_error(
                answer, {citation["label"] for citation in citations}
            )
            if citation_error:
                return RAGAnswer(
                    self._offline_answer(selected, citations),
                    "offline",
                    citations,
                    retrieved,
                    _join_errors(citation_error, omission_error),
                )
            return RAGAnswer(answer, "generated", citations, retrieved, omission_error)
        return RAGAnswer(
            self._offline_answer(selected, citations),
            "offline",
            citations,
            retrieved,
            omission_error,
        )

    def _select_units(
        self, records: list[RetrievedRecord]
    ) -> tuple[list[tuple[RetrievedRecord, str]], list[RetrievedRecord]]:
        """Greedily select complete evidence units without cutting them.

        Include the prospective label and separator in each size check. Only
        accepted units advance numbering; oversized units leave room for later hits.
        """

        selected: list[tuple[RetrievedRecord, str]] = []
        omitted: list[RetrievedRecord] = []
        counters: dict[str, int] = {}
        used = 0
        for record in records:
            text = self._record_text(record)
            prefix = _CITATION_PREFIXES.get(record.type, "C")
            number = counters.get(prefix, 0) + 1
            unit = f"[{prefix}{number}] {record.title}\n{text}"
            addition = len(unit) + (2 if selected else 0)
            if used + addition <= self.max_context_chars:
                selected.append((record, text))
                counters[prefix] = number
                used += addition
            else:
                omitted.append(record)
        return selected, omitted

    @staticmethod
    def _record_text(record: RetrievedRecord) -> str:
        if isinstance(record.evidence, str) and record.evidence.strip():
            return record.evidence
        return record.snippet

    @staticmethod
    def _serialize(records: list[RetrievedRecord]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        counters: dict[str, int] = {}
        retrieved: list[dict[str, Any]] = []
        citations: list[dict[str, str]] = []
        for record in records:
            prefix = _CITATION_PREFIXES.get(record.type, "C")
            counters[prefix] = counters.get(prefix, 0) + 1
            label = f"[{prefix}{counters[prefix]}]"
            retrieved.append({"id": record.id, "type": record.type, "title": record.title, "snippet": RAGPipeline._record_text(record),
                              "section": record.section, "table_number": record.table_number, "doc": record.doc, "label": label})
            citations.append({"label": label, "title": record.title, "id": record.id})
        return retrieved, citations

    @staticmethod
    def _context(
        selected: list[tuple[RetrievedRecord, str]], citations: list[dict[str, str]]
    ) -> str:
        return "\n\n".join(
            f"{citation['label']} {record.title}\n{text}"
            for (record, text), citation in zip(selected, citations)
        )

    def _offline_answer(
        self,
        selected: list[tuple[RetrievedRecord, str]],
        citations: list[dict[str, str]],
    ) -> str:
        units = [
            f"{citation['label']} {record.title}\n{text}"
            for (record, text), citation in zip(selected, citations)
        ]
        return "\n".join(
            ["离线检索证据（非模型生成回答，来源：OPC UA 10000-5）：", *units]
        )

    def _omission_error(self, omitted: list[RetrievedRecord]) -> str | None:
        if not omitted:
            return None
        details = ", ".join(f"{record.id} ({record.title})" for record in omitted)
        return (
            f"上下文预算 {self.max_context_chars} 字符内省略了 {len(omitted)} 条证据；"
            f"这些证据未提供给模型，也未分配引用: {details}"
        )

    def _no_fit_error(self, omitted: list[RetrievedRecord]) -> str:
        details = ", ".join(f"{record.id} ({record.title})" for record in omitted)
        return (
            f"没有证据能在 {self.max_context_chars} 字符的上下文预算内完整容纳；"
            f"未调用语言模型。已省略: {details}"
        )

    @staticmethod
    def _citation_error(answer: str, supplied: set[str]) -> str | None:
        """Validate only canonical provenance labels, not semantic entailment."""

        if not isinstance(answer, str) or not answer.strip():
            return "模型返回了空回答，未能提供有效引用；已回退到离线证据。"
        invalid: list[str] = []
        valid = 0
        for match in _CITATION_CANDIDATE.finditer(answer):
            token = match.group(0)
            if _CANONICAL_CITATION.fullmatch(token) is None:
                invalid.append(token)
            elif token not in supplied:
                invalid.append(token)
            else:
                valid += 1
        if invalid:
            details = ", ".join(dict.fromkeys(invalid))
            return (
                f"模型回答包含格式错误或未提供的引用标签 {details}；"
                "已回退到离线证据。"
            )
        if valid == 0:
            return "模型回答没有使用任何已提供的引用标签；已回退到离线证据。"
        return None


def _join_errors(*errors: str | None) -> str | None:
    joined = "；".join(error for error in errors if error)
    return joined or None
