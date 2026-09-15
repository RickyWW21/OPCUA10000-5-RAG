"""Part 5 retrieval adapter for RAG consumers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .api import KnowledgeBase


@dataclass(frozen=True)
class RetrievedRecord:
    id: str
    type: str
    title: str
    snippet: str
    section: str | None = None
    table_number: str | None = None
    doc: str = "OPC-10000-5"


class Part5Retriever:
    """Normalize KnowledgeBase results while enforcing the Part 5 boundary."""

    def __init__(self, knowledge_base: KnowledgeBase):
        self.knowledge_base = knowledge_base

    def retrieve(
        self, question: str, *, top_k: int = 6, relationship_depth: int = 0
    ) -> list[RetrievedRecord]:
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        if relationship_depth < 0:
            raise ValueError("relationship_depth must be non-negative")

        results = self.knowledge_base.search(question, top_k=top_k)
        records: list[RetrievedRecord] = []
        seen: set[str] = set()

        def add(raw: dict[str, Any], *, fallback_type: str = "relationship") -> None:
            doc = raw.get("doc", "OPC-10000-5")
            if doc != "OPC-10000-5":
                return
            record_id = raw.get("id") or raw.get("target") or raw.get("source")
            if not isinstance(record_id, str) or record_id in seen:
                return
            seen.add(record_id)
            records.append(
                RetrievedRecord(
                    id=record_id,
                    type=str(raw.get("type") or fallback_type),
                    title=str(raw.get("title") or raw.get("relation") or record_id),
                    snippet=str(raw.get("snippet") or raw.get("description") or ""),
                    section=raw.get("section"),
                    table_number=raw.get("table_number"),
                    doc=doc,
                )
            )

        for result in results:
            add(dict(result), fallback_type="chunk")
            if relationship_depth and result.get("type") == "entity":
                entity = self.knowledge_base.get_entity(result.get("id", ""))
                if entity:
                    for edge in self.knowledge_base.relationships(
                        entity["id"], depth=relationship_depth
                    ):
                        add(
                            {
                                "id": edge.get("target"),
                                "type": "relationship",
                                "title": edge.get("relation", ""),
                                "snippet": f"{edge.get('source', entity['id'])} {edge.get('relation', '')} {edge.get('target', '')}",
                                "doc": edge.get("doc", "OPC-10000-5"),
                            }
                        )
            if len(records) >= top_k:
                break
        return records[:top_k]
