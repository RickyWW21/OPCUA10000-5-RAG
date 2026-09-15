"""Part 5 retrieval adapter for RAG consumers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .api import KnowledgeBase
from .embeddings import EmbeddingError, EmbeddingProvider
from .vector_index import VectorIndex, VectorIndexError


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

    def __init__(
        self,
        knowledge_base: KnowledgeBase,
        *,
        vector_index: VectorIndex | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        vector_weight: float = 0.45,
        fts_weight: float = 0.55,
    ):
        if vector_weight < 0 or fts_weight < 0 or vector_weight + fts_weight <= 0:
            raise ValueError("retrieval weights must be non-negative and not both zero")
        self.knowledge_base = knowledge_base
        self.vector_index = vector_index
        self.embedding_provider = embedding_provider
        self.vector_weight = vector_weight
        self.fts_weight = fts_weight
        self.last_mode = "fts"
        self._validate_part5_root()

    def _validate_part5_root(self) -> None:
        """Require a manifest identifying real knowledge-base roots as Part 5."""

        root = getattr(self.knowledge_base, "root", None)
        if not isinstance(root, (str, Path)):
            # Lightweight test doubles can provide explicit document metadata per row.
            return
        manifest_path = Path(root) / "source" / "source_manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Knowledge base is not a verified OPC UA 10000-5 source: {manifest_path}") from exc
        if not isinstance(manifest, dict) or manifest.get("doc") != "OPC-10000-5":
            raise ValueError(f"Knowledge base is not a verified OPC UA 10000-5 source: {manifest_path}")

    def retrieve(
        self, question: str, *, top_k: int = 6, relationship_depth: int = 0
    ) -> list[RetrievedRecord]:
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        if relationship_depth < 0:
            raise ValueError("relationship_depth must be non-negative")

        candidate_limit = max(top_k * 3, 20)
        results = self.knowledge_base.search(question, top_k=candidate_limit)
        exact_results = [
            result for result in results if result.get("type") in {"entity", "table", "chapter"}
        ]
        fts_results = [result for result in results if result not in exact_results]
        vector_results: list[dict[str, Any]] = []
        vector_available = self.vector_index is not None and self.embedding_provider is not None
        if vector_available:
            try:
                vector_results = self.vector_index.search(
                    question, self.embedding_provider, top_k=candidate_limit
                )
            except (EmbeddingError, VectorIndexError):
                vector_available = False
        if vector_available:
            self.last_mode = "hybrid"
        elif exact_results and not fts_results:
            self.last_mode = "exact"
        else:
            self.last_mode = "fts"
        primary_results = exact_results + self._fuse_candidates(fts_results, vector_results)
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
                                "snippet": f"{edge.get('source', entity['id'])} {edge.get('relation', '')} {edge.get('target', '')}",
                                "doc": edge.get("doc", "OPC-10000-5"),
                            }
                        )
            if len(records) >= top_k:
                break
        return records[:top_k]

    def _fuse_candidates(
        self, fts_results: list[dict[str, Any]], vector_results: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Fuse non-exact candidates with stable weighted reciprocal-rank scores."""

        if not vector_results:
            return fts_results
        candidates: dict[str, dict[str, Any]] = {}
        scores: dict[str, float] = {}
        for rank, result in enumerate(fts_results, start=1):
            record_id = result.get("id")
            if not isinstance(record_id, str):
                continue
            candidates.setdefault(record_id, result)
            scores[record_id] = scores.get(record_id, 0.0) + self.fts_weight / rank
        for rank, result in enumerate(vector_results, start=1):
            record_id = result.get("id")
            if not isinstance(record_id, str):
                continue
            candidates.setdefault(record_id, result)
            scores[record_id] = scores.get(record_id, 0.0) + self.vector_weight / rank
        order = {record_id: index for index, record_id in enumerate(candidates)}
        return [
            candidates[record_id]
            for record_id in sorted(candidates, key=lambda item: (-scores[item], order[item]))
        ]
