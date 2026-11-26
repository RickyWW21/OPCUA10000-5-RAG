"""Part 5 retrieval adapter for RAG consumers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .api import KnowledgeBase
from .embeddings import EmbeddingError, EmbeddingProvider
from .vector_index import VectorIndex, VectorIndexError
from .wiki import search_wiki


@dataclass(frozen=True)
class RetrievedRecord:
    id: str
    type: str
    title: str
    snippet: str
    section: str | None = None
    table_number: str | None = None
    doc: str = "OPC-10000-5"
    evidence: str | None = None
    provenance: dict[str, Any] | None = None


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
        if vector_available and vector_results:
            self.last_mode = "hybrid"
        elif exact_results and not fts_results:
            self.last_mode = "exact"
        else:
            self.last_mode = "fts"
        primary_results = exact_results + self._fuse_candidates(fts_results, vector_results)
        records: list[RetrievedRecord] = []
        seen: set[str] = set()

        def make_record(raw: dict[str, Any], *, fallback_type: str) -> RetrievedRecord | None:
            doc = raw.get("doc", "OPC-10000-5")
            if doc != "OPC-10000-5":
                return None
            record_id = raw.get("id") or raw.get("target") or raw.get("source")
            if not isinstance(record_id, str):
                return None
            record_type = str(raw.get("type") or fallback_type)
            raw_evidence = raw.get("evidence")
            evidence = (
                raw_evidence
                if isinstance(raw_evidence, str) and raw_evidence.strip()
                else self._evidence_text(record_id, record_type)
            )
            provenance = raw.get("provenance")
            return RetrievedRecord(
                id=record_id,
                type=record_type,
                title=str(raw.get("title") or raw.get("relation") or record_id),
                snippet=str(raw.get("snippet") or raw.get("description") or ""),
                section=raw.get("section"),
                table_number=raw.get("table_number"),
                doc=doc,
                evidence=evidence,
                provenance=provenance if isinstance(provenance, dict) else None,
            )

        def add(raw: dict[str, Any], *, fallback_type: str = "relationship") -> None:
            record = make_record(raw, fallback_type=fallback_type)
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
                                "snippet": f"{edge.get('source', entity['id'])} {edge.get('relation', '')} {edge.get('target', '')}",
                                "doc": edge.get("doc", "OPC-10000-5"),
                            }
                        )
            if len(records) >= top_k:
                break

        wiki_hits = self._wiki_hits(question, top_k, has_specification=bool(records))
        if not wiki_hits:
            return records[:top_k]

        # Specification text stays authoritative.  Wiki records enter directly
        # after the first specification result, or (when there is no original
        # hit at all) only together with a real source chunk cited by the page.
        result: list[RetrievedRecord] = []
        result_ids: set[str] = set()
        if records:
            result.append(records[0])
            result_ids.add(records[0].id)
            for hit in wiki_hits:
                raw = dict(hit)
                raw.pop("companion_source", None)
                record = make_record(raw, fallback_type="wiki")
                if record is None or record.id in result_ids:
                    continue
                result_ids.add(record.id)
                result.append(record)
                if len(result) >= top_k:
                    break
            if len(result) < top_k:
                for record in records[1:]:
                    if record.id in result_ids:
                        continue
                    result_ids.add(record.id)
                    result.append(record)
                    if len(result) >= top_k:
                        break
            return result[:top_k]

        for hit in wiki_hits:
            raw = dict(hit)
            companion = raw.pop("companion_source", None)
            if isinstance(companion, dict):
                source_record = make_record(companion, fallback_type="chunk")
                if source_record is not None and source_record.id not in result_ids:
                    result_ids.add(source_record.id)
                    result.append(source_record)
                if len(result) >= top_k:
                    break
            record = make_record(raw, fallback_type="wiki")
            if record is None or record.id in result_ids:
                continue
            result_ids.add(record.id)
            result.append(record)
            if len(result) >= top_k:
                break
        return result[:top_k]

    def _wiki_hits(
        self, question: str, top_k: int, *, has_specification: bool
    ) -> list[dict[str, Any]]:
        """Read Wiki hits only for verified filesystem roots with a Wiki folder."""

        root = getattr(self.knowledge_base, "root", None)
        if not isinstance(root, (str, Path)):
            return []
        try:
            if not (Path(root) / "wiki").is_dir():
                return []
        except OSError:
            return []
        if top_k == 1 and has_specification:
            return []
        budget = max(1, top_k // 3) if top_k >= 2 else 1
        try:
            return search_wiki(self.knowledge_base, question, top_k=budget)
        except Exception:
            # A malformed Wiki must never break the specification path.
            return []

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
