"""Part 5 retrieval adapter for RAG consumers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .api import KnowledgeBase, load_source_manifest


class RetrievalError(ValueError):
    """Raised when the knowledge base fails Part 5 source validation."""


@dataclass(frozen=True)
class RetrievedRecord:
    """Normalized Part 5 search or relationship record for RAG consumers."""

    id: str
    type: str
    title: str
    snippet: str
    section: str | None = None
    table_number: str | None = None
    doc: str = "OPC-10000-5"
    evidence: str | None = None
    provenance: dict[str, Any] | None = None
    source_records: tuple[RetrievedRecord, ...] = ()


class Part5Retriever:
    """Stateless exact-match + SQLite FTS5 retriever enforcing the Part 5 boundary."""

    def __init__(self, knowledge_base: KnowledgeBase) -> None:
        self.knowledge_base = knowledge_base
        self._validate_part5_root()

    @property
    def mode(self) -> str:
        """Return the fixed retrieval mode identifier."""

        return "fts"

    def _validate_part5_root(self) -> None:
        """Require a manifest identifying real knowledge-base roots as Part 5."""

        root = getattr(self.knowledge_base, "root", None)
        if not isinstance(root, (str, Path)):
            # Lightweight test doubles can provide explicit document metadata per row.
            return
        manifest_path = Path(root) / "source" / "source_manifest.json"
        try:
            manifest = load_source_manifest(root)
        except (FileNotFoundError, ValueError, OSError) as exc:
            raise RetrievalError(
                f"Knowledge base is not a verified OPC UA 10000-5 source: {manifest_path}"
            ) from exc
        if manifest.get("doc") != "OPC-10000-5":
            raise RetrievalError(
                f"Knowledge base is not a verified OPC UA 10000-5 source: {manifest_path}"
            )

    def retrieve(
        self, question: str, *, top_k: int = 6, relationship_depth: int = 0
    ) -> list[RetrievedRecord]:
        """Return deduplicated Part 5 records ordered exact-match then FTS5."""

        if top_k <= 0:
            raise ValueError("top_k must be positive")
        if relationship_depth < 0:
            raise ValueError("relationship_depth must be non-negative")

        candidate_limit = max(top_k * 3, 20)
        results = self.knowledge_base.search(question, top_k=candidate_limit)
        exact_results = [
            result
            for result in results
            if result.get("match_kind") == "exact"
            or ("match_kind" not in result and result.get("type") in {"entity", "table", "chapter"})
        ]
        fts_results = [result for result in results if result not in exact_results]
        primary_results = exact_results + fts_results

        records: list[RetrievedRecord] = []
        seen: set[str] = set()

        def add(raw: dict[str, Any], *, fallback_type: str = "relationship") -> None:
            record = self._make_record(raw, fallback_type=fallback_type)
            if record is None or record.id in seen:
                return
            seen.add(record.id)
            records.append(record)

        for result in primary_results:
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
                                "snippet": (
                                    f"{edge.get('source', entity['id'])} "
                                    f"{edge.get('relation', '')} {edge.get('target', '')}"
                                ),
                                "doc": edge.get("doc", "OPC-10000-5"),
                            }
                        )
            if len(records) >= top_k:
                break

        return records[:top_k]

    def _make_record(
        self, raw: dict[str, Any], *, fallback_type: str
    ) -> RetrievedRecord | None:
        doc = raw.get("doc", "OPC-10000-5")
        if doc != "OPC-10000-5":
            return None
        record_id = raw.get("id") or raw.get("target") or raw.get("source")
        if not isinstance(record_id, str):
            return None
        record_type = str(raw.get("type") or fallback_type)
        if record_type == "wiki":
            return None
        raw_evidence = raw.get("evidence")
        evidence = (
            raw_evidence
            if isinstance(raw_evidence, str) and raw_evidence.strip()
            else self._evidence_text(record_id, record_type)
        )
        return RetrievedRecord(
            id=record_id,
            type=record_type,
            title=str(raw.get("title") or raw.get("relation") or record_id),
            snippet=str(raw.get("snippet") or raw.get("description") or ""),
            section=raw.get("section"),
            table_number=raw.get("table_number"),
            doc=doc,
            evidence=evidence,
        )

    def _evidence_text(self, record_id: str, record_type: str) -> str | None:
        """Hydrate original evidence through the public KnowledgeBase method.

        Lightweight doubles without a real ``evidence`` method keep the search
        snippet. A Mock attribute is not a string, so it is never mistaken for
        hydrated evidence.
        """

        method = getattr(self.knowledge_base, "evidence", None)
        if not callable(method):
            return None
        try:
            value = method(record_id, record_type)
        except TypeError:
            # A partial test double may expose an incompatible signature.
            return None
        if isinstance(value, str) and value.strip():
            return value
        return None
