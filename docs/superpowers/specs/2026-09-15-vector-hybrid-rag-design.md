# Part 5 Vector Hybrid RAG Design

**Date:** 2026-09-15  
**Status:** Approved in chat; written-spec review pending

## Goal

Upgrade the OPC UA 10000-5 Part 5 RAG from FTS-only retrieval to a hybrid retriever that combines exact identifiers, SQLite FTS5, optional local embeddings, and bounded relationship expansion.

## Scope

All indexed and retrieved content remains restricted to the verified `OPC-10000-5` source manifest. No other OPC UA Part, vendor document, web source, or conversation memory may enter the vector index or generated prompt.

## Architecture

```text
Part 5 Markdown
  -> structured JSONL/chunks + FTS5
  -> optional embedding provider
  -> indexes/embeddings.jsonl + metadata

question
  -> exact match + FTS5 + vector similarity
  -> score fusion and deduplication
  -> relationship expansion
  -> existing RAGPipeline
```

### Components

1. `opcua_kb/embeddings.py`
   - Defines `EmbeddingProvider`.
   - Provides an optional `SentenceTransformerEmbeddingProvider` that imports `sentence_transformers` lazily.
   - Exposes deterministic cosine similarity helpers using NumPy when available.

2. `opcua_kb/vector_index.py`
   - Persists vectors and metadata in `indexes/embeddings.jsonl` plus `indexes/embeddings.meta.json`.
   - Builds/rebuilds vectors only from Part 5 chunks/entities.
   - Validates source hash, model name, dimension, and document ID before querying.

3. `opcua_kb/retrieval.py`
   - Preserves the current public `Part5Retriever` constructor and retrieval contract.
   - Accepts optional vector index/provider injection.
   - Fuses exact, FTS, and vector candidates with deterministic weighted reciprocal-rank scoring.
   - Falls back to exact + FTS when vector dependencies, model files, or index metadata are unavailable.

4. `opcua_kb/builder.py` and `tools/build_kb.py`
   - Keep current JSONL/FTS build behavior.
   - Add an opt-in `--embeddings` build path and model selection flag.
   - Never make a successful base build depend on optional embedding packages.

5. `tools/ask_kb.py`
   - Adds optional hybrid/vector flags while preserving offline behavior.
   - Reports the retrieval mode (`exact`, `fts`, `hybrid`) in the trace.

## Interfaces

```python
class EmbeddingProvider(Protocol):
    model_name: str
    dimension: int
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class VectorIndex:
    def build(self, records: list[dict[str, Any]], provider: EmbeddingProvider, *, source_hash: str) -> None: ...
    def search(self, query: str, provider: EmbeddingProvider, *, top_k: int) -> list[dict[str, Any]]: ...


class Part5Retriever:
    def __init__(self, knowledge_base: KnowledgeBase, *, vector_index: VectorIndex | None = None, embedding_provider: EmbeddingProvider | None = None, vector_weight: float = 0.45, fts_weight: float = 0.55): ...
```

The existing `RAGPipeline` and `RAGAnswer` interfaces remain unchanged.

## Index Format and Invalidation

- `embeddings.jsonl` stores one vector record per searchable Part 5 chunk/entity: ID, type, title, section, snippet/text, document ID, and vector.
- `embeddings.meta.json` stores `doc`, source SHA-256, provider model name, vector dimension, and build timestamp.
- Querying rejects an index whose document ID, source hash, model name, or dimensions do not match the active provider/source.
- Rebuilding with `--embeddings` replaces vector artifacts atomically with the same publication discipline as existing generated artifacts.

## Score Fusion

- Exact matches receive the highest priority and remain first.
- FTS and vector candidates are ranked independently.
- Non-exact candidates use weighted reciprocal rank with configurable weights; ties resolve by original candidate order and ID.
- Duplicate IDs are emitted once.
- Relationship records remain bounded by `top_k` and are added after primary candidates.

## Optional Dependency and Fallback Rules

- Base installation has no mandatory new dependency.
- `sentence-transformers` is an optional extra documented in `requirements-embeddings.txt`.
- If the package/model/index is unavailable, the retriever operates in exact + FTS mode and reports that mode; it does not fail a normal query.
- Vector build requests fail clearly when the optional dependency is missing instead of producing fake vectors.

## Testing and Evaluation

- Unit tests cover provider loading, vector persistence, cosine ranking, metadata invalidation, score fusion, and FTS fallback.
- Existing tests must remain green.
- Add a small Part 5 evaluation fixture with paraphrase queries and expected entity/chunk IDs; report Recall@1 and Recall@3 for FTS and hybrid modes.
- No public network calls occur in tests.

## Non-Goals

- No FAISS, Chroma, Qdrant, or hosted vector service in this iteration.
- No automatic model download during ordinary query execution.
- No streaming, conversation memory, or multi-document retrieval.
