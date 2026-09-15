"""Persistent JSONL vector index for verified OPC UA Part 5 records."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .embeddings import EmbeddingError, EmbeddingProvider, cosine_similarity
except ImportError:
    from embeddings import EmbeddingError, EmbeddingProvider, cosine_similarity


class VectorIndexError(RuntimeError):
    """Raised when vector artifacts are missing, stale, or malformed."""


class VectorIndex:
    def __init__(self, root: str | Path, *, source_hash: str | None = None) -> None:
        self.root = Path(root)
        self.index_dir = self.root / "indexes"
        self.vectors_path = self.index_dir / "embeddings.jsonl"
        self.meta_path = self.index_dir / "embeddings.meta.json"
        self.source_hash = source_hash

    def build(
        self, records: list[dict[str, Any]], provider: EmbeddingProvider, *, source_hash: str
    ) -> None:
        if not source_hash:
            raise ValueError("source_hash is required")
        selected: list[dict[str, Any]] = []
        for record in records:
            if record.get("doc") != "OPC-10000-5":
                continue
            record_id = record.get("id")
            text = record.get("text") or record.get("snippet") or record.get("summary_en")
            if not isinstance(record_id, str) or not record_id or not isinstance(text, str) or not text.strip():
                raise VectorIndexError("vector records require non-empty id and text")
            selected.append(
                {
                    "id": record_id,
                    "type": record.get("type", "chunk"),
                    "title": record.get("title", record_id),
                    "section": record.get("section"),
                    "table_number": record.get("table_number"),
                    "snippet": record.get("snippet") or text[:600],
                    "text": text,
                    "doc": "OPC-10000-5",
                }
            )
        try:
            vectors = provider.embed([record["text"] for record in selected]) if selected else []
        except Exception as exc:
            if isinstance(exc, EmbeddingError):
                raise
            raise VectorIndexError("embedding provider failed while building index") from exc
        if len(vectors) != len(selected) or any(len(vector) != provider.dimension for vector in vectors):
            raise VectorIndexError("embedding provider returned inconsistent dimensions")
        rows = []
        for record, vector in zip(selected, vectors):
            row = dict(record)
            row["vector"] = [float(value) for value in vector]
            rows.append(row)
        metadata = {
            "doc": "OPC-10000-5",
            "source_hash": source_hash,
            "model_name": provider.model_name,
            "dimension": provider.dimension,
            "built_at": datetime.now(timezone.utc).isoformat(),
        }
        self._publish(rows, metadata)

    def search(self, query: str, provider: EmbeddingProvider, *, top_k: int) -> list[dict[str, Any]]:
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        metadata = self._read_metadata()
        if metadata["doc"] != "OPC-10000-5":
            raise VectorIndexError("vector index is not an OPC UA 10000-5 index")
        if metadata["model_name"] != provider.model_name or metadata["dimension"] != provider.dimension:
            raise VectorIndexError("vector index metadata does not match embedding provider")
        if self.source_hash is not None and metadata["source_hash"] != self.source_hash:
            raise VectorIndexError("vector index source hash is stale")
        rows = self._read_rows()
        if not rows:
            return []
        try:
            query_vector = provider.embed([query])[0]
        except Exception as exc:
            if isinstance(exc, EmbeddingError):
                raise
            raise VectorIndexError("embedding provider failed while searching index") from exc
        if len(query_vector) != provider.dimension:
            raise VectorIndexError("query embedding dimension does not match index")
        scored = []
        for order, row in enumerate(rows):
            try:
                score = cosine_similarity(query_vector, row["vector"])
            except ValueError as exc:
                raise VectorIndexError("vector index contains an invalid vector") from exc
            scored.append((score, order, row))
        scored.sort(key=lambda item: (-item[0], item[1]))
        results = []
        for score, _, row in scored[:top_k]:
            result = dict(row)
            result.pop("vector", None)
            result["score"] = score
            results.append(result)
        return results

    def _publish(self, rows: list[dict[str, Any]], metadata: dict[str, Any]) -> None:
        self.index_dir.mkdir(parents=True, exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix=".embeddings-", dir=self.index_dir))
        temp_vectors = temp_dir / self.vectors_path.name
        temp_meta = temp_dir / self.meta_path.name
        try:
            with temp_vectors.open("w", encoding="utf-8", newline="\n") as handle:
                for row in rows:
                    handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            temp_meta.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temp_vectors, self.vectors_path)
            os.replace(temp_meta, self.meta_path)
        except OSError as exc:
            raise VectorIndexError(f"unable to publish vector index at {self.index_dir}") from exc
        finally:
            for path in temp_dir.iterdir():
                path.unlink(missing_ok=True)
            temp_dir.rmdir()

    def _read_metadata(self) -> dict[str, Any]:
        try:
            value = json.loads(self.meta_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise VectorIndexError(f"unable to read vector metadata: {self.meta_path}") from exc
        required = {"doc", "source_hash", "model_name", "dimension", "built_at"}
        if not isinstance(value, dict) or not required.issubset(value):
            raise VectorIndexError("vector metadata is invalid")
        return value

    def _read_rows(self) -> list[dict[str, Any]]:
        try:
            lines = self.vectors_path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as exc:
            raise VectorIndexError(f"unable to read vector index: {self.vectors_path}") from exc
        rows = []
        try:
            for line in lines:
                row = json.loads(line)
                if not isinstance(row, dict) or row.get("doc") != "OPC-10000-5":
                    raise ValueError
                rows.append(row)
        except (json.JSONDecodeError, ValueError) as exc:
            raise VectorIndexError(f"vector index is malformed: {self.vectors_path}") from exc
        return rows
