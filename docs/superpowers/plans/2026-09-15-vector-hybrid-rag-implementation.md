# Part 5 Vector Hybrid RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add optional local embedding retrieval and deterministic hybrid ranking to the existing OPC UA 10000-5 Part 5 RAG without breaking FTS-only operation.

**Architecture:** Keep exact matching and SQLite FTS5 as the reliable baseline. Add a lazy embedding provider and a JSONL vector index with metadata validation, then let `Part5Retriever` fuse exact, FTS, and vector candidates when both optional components are available. Base builds and queries remain dependency-free; vector behavior is opt-in and degrades to FTS5 when unavailable.

**Tech Stack:** Python standard library, optional `sentence-transformers`, NumPy when available, SQLite FTS5, `unittest`.

**Spec:** `docs/superpowers/specs/2026-09-15-vector-hybrid-rag-design.md`

## Global Constraints

- All indexed and retrieved content remains restricted to the verified `OPC-10000-5` source manifest.
- Base installation has no mandatory new dependency; `sentence-transformers` is optional and loaded lazily.
- No FAISS, Chroma, Qdrant, hosted vector service, automatic model download during ordinary queries, streaming, or conversation memory.
- Existing `KnowledgeBase`, `RAGPipeline`, and CLI behavior remain backward compatible.
- Vector artifacts must validate document ID, source hash, model name, and dimensions before use.
- Every behavior change starts with a failing unittest and ends with focused tests plus the full suite.

---

### Task 1: Embedding Provider Abstraction

**Files:**
- Create: `opcua_kb/embeddings.py`
- Create: `tests/test_embeddings.py`
- Create: `requirements-embeddings.txt`

**Interfaces:**
- Produces: `EmbeddingProvider`, `SentenceTransformerEmbeddingProvider`, `cosine_similarity`, and `rank_by_cosine`.
- Consumed later by `VectorIndex` and `Part5Retriever`.

- [ ] **Step 1: Write failing tests**

```python
def test_cosine_similarity_and_ranking_are_deterministic():
    self.assertAlmostEqual(cosine_similarity([1.0, 0.0], [0.8, 0.2]), 0.9701425, places=5)
    self.assertEqual(rank_by_cosine([1.0, 0.0], [[0.2, 0.9], [0.9, 0.1]]), [1, 0])


def test_sentence_transformer_import_is_lazy_and_missing_dependency_is_typed():
    with mock.patch.dict(sys.modules, {"sentence_transformers": None}):
        with self.assertRaises(EmbeddingError):
            SentenceTransformerEmbeddingProvider("missing-model")
```

- [ ] **Step 2: Run focused tests to verify failure**

Run: `python -m unittest tests.test_embeddings -v`

Expected: FAIL because `opcua_kb.embeddings` is missing.

- [ ] **Step 3: Implement minimal provider module**

Define:

```python
class EmbeddingError(RuntimeError): ...


class EmbeddingProvider(Protocol):
    model_name: str
    dimension: int
    def embed(self, texts: list[str]) -> list[list[float]]: ...
```

The sentence-transformers implementation must import the package inside `__init__`, construct the model with `local_files_only=True`, infer `dimension` from `get_sentence_embedding_dimension()`, convert outputs to plain float lists, and raise `EmbeddingError` for import, model, empty-input, or shape failures. `cosine_similarity` must reject mismatched dimensions and zero vectors; `rank_by_cosine` must sort by descending score and stable original index.

- [ ] **Step 4: Add optional dependency documentation and verify tests**

Put `sentence-transformers>=3,<6` in `requirements-embeddings.txt`. Run `python -m unittest tests.test_embeddings -v`; expected PASS without installing the optional package because tests use a fake provider or missing-dependency path.

- [ ] **Step 5: Commit**

```bash
git add opcua_kb/embeddings.py tests/test_embeddings.py requirements-embeddings.txt
git commit -m "feat: add optional Part 5 embedding provider"
```

### Task 2: Part 5 Vector Index

**Files:**
- Create: `opcua_kb/vector_index.py`
- Create: `tests/test_vector_index.py`

**Interfaces:**
- Consumes: `EmbeddingProvider`, Part 5 records, and the source SHA-256.
- Produces: `VectorIndex.build(records, provider, source_hash=...)` and `VectorIndex.search(query, provider, top_k=...)`.

- [ ] **Step 1: Write failing tests**

```python
def test_vector_index_builds_persists_and_searches_records():
    index = VectorIndex(temp_root)
    provider = FakeProvider("fake", [[1.0, 0.0], [0.0, 1.0]])
    index.build([{"id": "e1", "type": "entity", "title": "ServerType", "text": "server metadata", "doc": "OPC-10000-5"}, {"id": "e2", "type": "entity", "title": "AlarmType", "text": "alarm metadata", "doc": "OPC-10000-5"}], provider, source_hash="abc")
    result = index.search("server", provider, top_k=1)
    self.assertEqual(result[0]["id"], "e1")


def test_vector_index_rejects_stale_or_foreign_metadata():
    index.build(records, FakeProvider("fake", vectors), source_hash="abc")
    with self.assertRaises(VectorIndexError):
        index.search("x", FakeProvider("other", vectors), top_k=1)
```

- [ ] **Step 2: Run focused tests to verify failure**

Run: `python -m unittest tests.test_vector_index -v`

Expected: FAIL because `opcua_kb.vector_index` is missing.

- [ ] **Step 3: Implement JSONL vector persistence and metadata validation**

Define:

```python
class VectorIndexError(RuntimeError): ...


class VectorIndex:
    def __init__(self, root: str | Path): ...
    def build(self, records: list[dict[str, Any]], provider: EmbeddingProvider, *, source_hash: str) -> None: ...
    def search(self, query: str, provider: EmbeddingProvider, *, top_k: int) -> list[dict[str, Any]]: ...
```

Store `indexes/embeddings.jsonl` and `indexes/embeddings.meta.json`. Build only records whose `doc` is `OPC-10000-5`; reject missing IDs, empty text, inconsistent vector dimensions, and provider failures. Metadata must include `doc`, `source_hash`, `model_name`, `dimension`, and UTC `built_at`. Search must validate all metadata against the active provider and query the provider once, then rank by cosine similarity. Use a temporary sibling directory and atomic replacement so interrupted builds do not leave a partial index.

- [ ] **Step 4: Run focused tests to verify pass**

Run: `python -m unittest tests.test_vector_index -v`

Expected: PASS for persistence, ranking, metadata mismatch, foreign-record filtering, and empty-index errors.

- [ ] **Step 5: Commit**

```bash
git add opcua_kb/vector_index.py tests/test_vector_index.py
git commit -m "feat: add Part 5 vector index"
```

### Task 3: Hybrid Part 5 Retriever

**Files:**
- Modify: `opcua_kb/retrieval.py`
- Create: `tests/test_hybrid_retrieval.py`

**Interfaces:**
- Consumes: existing `KnowledgeBase` search, optional `VectorIndex`, optional `EmbeddingProvider`.
- Produces: backward-compatible `Part5Retriever(...).retrieve(...)` with hybrid candidate fusion and a retrieval-mode indicator.

- [ ] **Step 1: Write failing tests**

```python
def test_hybrid_retriever_fuses_fts_and_vector_candidates_with_exact_first():
    retriever = Part5Retriever(kb, vector_index=vector_index, embedding_provider=provider)
    records = retriever.retrieve("server composition", top_k=3)
    self.assertEqual([r.id for r in records], ["ObjectType:ServerType", "chunk-vector", "chunk-fts"])
    self.assertEqual(retriever.last_mode, "hybrid")


def test_missing_vector_index_falls_back_to_fts():
    retriever = Part5Retriever(kb, vector_index=None, embedding_provider=provider)
    retriever.retrieve("server", top_k=2)
    self.assertEqual(retriever.last_mode, "fts")
```

- [ ] **Step 2: Run focused tests to verify failure**

Run: `python -m unittest tests.test_hybrid_retrieval -v`

Expected: FAIL because `Part5Retriever` has no vector options or `last_mode`.

- [ ] **Step 3: Implement deterministic hybrid fusion**

Extend the constructor with:

```python
def __init__(self, knowledge_base: KnowledgeBase, *, vector_index: VectorIndex | None = None, embedding_provider: EmbeddingProvider | None = None, vector_weight: float = 0.45, fts_weight: float = 0.55): ...
```

Keep manifest validation unchanged. Retrieve a larger candidate pool from FTS, query the vector index when both optional objects exist, preserve exact matches first, then combine non-exact candidates using weighted reciprocal-rank scoring. Deduplicate by `(type, id)`, cap at `top_k`, preserve relationship expansion semantics, and set `last_mode` to `exact`, `fts`, or `hybrid`. Catch only `EmbeddingError`/`VectorIndexError` for vector fallback; do not hide FTS or manifest errors. Validate weights are non-negative and not both zero.

- [ ] **Step 4: Run focused and existing retrieval tests**

Run: `python -m unittest tests.test_hybrid_retrieval tests.test_retrieval -v`

Expected: PASS with old Part 5 behavior unchanged and hybrid/fallback cases green.

- [ ] **Step 5: Commit**

```bash
git add opcua_kb/retrieval.py tests/test_hybrid_retrieval.py
git commit -m "feat: add hybrid Part 5 retrieval"
```

### Task 4: Embedding-Aware Build Pipeline and CLI

**Files:**
- Modify: `opcua_kb/builder.py`
- Modify: `tools/build_kb.py`
- Modify: `tools/ask_kb.py`
- Modify: `README.md`
- Modify: `tools/help.py`
- Create: `tests/test_embedding_build_cli.py`

**Interfaces:**
- Consumes: built Part 5 chunks/entities, `SentenceTransformerEmbeddingProvider`, and `VectorIndex`.
- Produces: `python tools/build_kb.py --embeddings --embedding-model MODEL` and optional hybrid flags on `ask_kb.py`.

- [ ] **Step 1: Write failing tests**

```python
def test_embedding_build_is_opt_in_and_base_build_still_works():
    self.assertNotIn("embeddings", build(root, source))
    result = run_builder("--embeddings", "--embedding-model", "fake-model")
    self.assertTrue((root / "indexes" / "embeddings.jsonl").exists())


def test_ask_cli_can_disable_vector_retrieval():
    result = run_cli_script("tools/ask_kb.py", "What is ServerType?", "--offline", "--no-embeddings")
    self.assertEqual(result.returncode, 0)
    self.assertIn("fts", result.stdout.lower())
```

- [ ] **Step 2: Run focused tests to verify failure**

Run: `python -m unittest tests.test_embedding_build_cli -v`

Expected: FAIL because build and ask CLI do not expose embedding options.

- [ ] **Step 3: Add opt-in build artifacts and query wiring**

Extend builder arguments with `--embeddings` and `--embedding-model`, but keep the default build dependency-free. When enabled, require the optional provider, collect Part 5 entity/chunk records, build the vector index using the source manifest hash, and publish vector artifacts atomically with the existing generated files. Extend `ask_kb.py` with `--no-embeddings` and `--embedding-model`; when enabled and valid artifacts exist, construct `VectorIndex` and provider, otherwise let `Part5Retriever` report FTS fallback. Print the selected retrieval mode. Update README/help with installation and environment-safe examples.

- [ ] **Step 4: Run focused tests to verify pass**

Run: `python -m unittest tests.test_embedding_build_cli -v`

Expected: PASS for opt-in behavior, missing optional dependency messaging, offline no-embedding mode, and generated artifact paths.

- [ ] **Step 5: Commit**

```bash
git add opcua_kb/builder.py tools/build_kb.py tools/ask_kb.py README.md tools/help.py tests/test_embedding_build_cli.py
git commit -m "feat: add opt-in Part 5 embedding build and query flags"
```

### Task 5: Evaluation and Full Verification

**Files:**
- Create: `tests/fixtures/part5_retrieval_eval.json`
- Create: `tools/evaluate_retrieval.py`
- Create: `tests/test_retrieval_eval.py`

- [ ] **Step 1: Write failing evaluation tests**

```python
def test_evaluation_fixture_has_part5_queries_and_expected_ids():
    cases = json.loads(Path("tests/fixtures/part5_retrieval_eval.json").read_text())
    self.assertGreaterEqual(len(cases), 5)
    self.assertTrue(all(case["doc"] == "OPC-10000-5" for case in cases))


def test_recall_at_k_is_computed_for_fts_and_hybrid_modes():
    report = evaluate_fixture(fixture_path, retriever_factory)
    self.assertIn("fts", report)
    self.assertIn("recall_at_1", report["fts"])
```

- [ ] **Step 2: Run focused tests to verify failure**

Run: `python -m unittest tests.test_retrieval_eval -v`

Expected: FAIL because the evaluation fixture and tool do not exist.

- [ ] **Step 3: Implement fixture and evaluator**

Use at least five Part 5 paraphrase cases covering an entity, a table, a chapter, a field, and a relationship. Implement `evaluate_fixture(path, retriever_factory) -> dict[str, dict[str, float]]` with Recall@1 and Recall@3 for FTS and hybrid modes. Never make evaluator success depend on a hosted model or public network.

- [ ] **Step 4: Run all verification commands**

Run:

```powershell
python -m unittest discover -v
python tools/ask_kb.py "ServerType 包含哪些组件？" --offline --top-k 3
python tools/evaluate_retrieval.py
git diff --check
rg -n "sk-[A-Za-z0-9]+" --glob '!*.pkl' --glob '!*.log' opcua_kb tools tests README.md docs
```

Expected: all tests pass; offline CLI returns Part 5 citations; evaluator prints Recall@1/Recall@3; diff check is clean; no secret pattern appears in implementation or docs.

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/part5_retrieval_eval.json tools/evaluate_retrieval.py tests/test_retrieval_eval.py
git commit -m "test: add Part 5 retrieval evaluation"
```

