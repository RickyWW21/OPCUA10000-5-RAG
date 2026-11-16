# Part 5 retrieval baseline and evidence validation

This document covers the user-authorized Part 5 RAG improvements: an explicit
retrieval evaluation baseline and complete-evidence citation validation. The
CLI, TUI, Streamlit, FastAPI, and React surfaces keep their existing request and
response fields. No login, new dependency, paid model call, query rewriting, or
reranking was added.

## Evaluation commands

Run the versioned fixture with the default FTS-only behavior:

```powershell
python tools/evaluate_retrieval.py
python tools/evaluate_retrieval.py --retrieval-mode fts --top-k 3
```

Run the same fixture in strict hybrid mode against the local vector artifacts:

```powershell
python tools/evaluate_retrieval.py --retrieval-mode hybrid
# or make the local model path explicit; the model must already exist locally
python tools/evaluate_retrieval.py --retrieval-mode hybrid --embedding-model ".\models\all-MiniLM-L6-v2"
```

Hybrid evaluation never downloads a model. When `--embedding-model` is omitted,
the model name recorded in `indexes/embeddings.meta.json` is used. The command
validates the fixture, source manifest `sha256`, vector artifact presence,
metadata document/source-hash/model/dimension, and the local
`SentenceTransformerEmbeddingProvider` before querying. A missing or broken
artifact, model mismatch, or any per-query fallback raises a clear
`EvaluationError`; FTS results are never relabeled as hybrid. Empty vector
artifacts also fail strict hybrid evaluation. Malformed rows are rejected by
the shared vector reader so all consumers use the existing controlled fallback.

Run the focused tests or the complete Python suite:

```powershell
python -m unittest tests.test_retrieval_eval -v
python -m unittest discover -s tests -q
```

## Metric definitions

Positive cases are the only cases in aggregate retrieval metrics.

- **Hit@1 / Hit@3** — `1` when any expected ID appears in the first one or
  three retrieved IDs. This preserves the original "any expected ID" behavior.
- **Recall@1 / Recall@3** — unique expected IDs found in the first one or three
  retrieved IDs divided by the number of unique expected IDs. With multiple
  required evidence IDs this is lower than Hit.
- **MRR** — reciprocal rank (`1/rank`) of the first retrieved expected ID, or
  `0` when none is retrieved.
- **Latency** — measured per query around `Part5Retriever.retrieve` and reported
  in milliseconds; the aggregate is the mean over positive cases.

Each case reports its requested and actual retrieval modes, `top_k`,
`relationship_depth`, expected/retrieved IDs, the metrics above, and latency.
The report also records fixture path/hash/case-category counts, source manifest
metadata, embedding model, vector-index metadata, and aggregate parameters.

`out_of_scope` and `context_dependent` cases live under `diagnostics`, are
excluded from all positive aggregates, and have no success metric. A non-empty
nearest-neighbor result is reported only as `retrieved_nonempty`; it is never
treated as refusal success or answer correctness. Diagnostic cases must declare
an empty `expected_ids` array.

## Fixture schema

`tests/fixtures/part5_retrieval_eval.json` is a non-empty JSON array. Every case
requires a non-empty `question` and an `expected_ids` array of unique non-empty
strings. Optional fields are:

```json
{
  "question": "Section 6.3.1 ServerType",
  "expected_ids": ["sec-6.3.1", "ObjectType:ServerType"],
  "category": "positive",
  "top_k": 3,
  "relationship_depth": 0
}
```

`category` is one of `positive` (default), `out_of_scope`, or
`context_dependent`. Positive cases require at least one expected ID; diagnostic
cases must have none. `top_k` is a positive integer and `relationship_depth` is a
non-negative integer; booleans are rejected. All validation happens before an
embedding model is loaded. The fixture mixes Chinese/English questions,
paraphrases, entities, tables, chapters, and multiple-required-evidence cases
using canonical IDs verified against the generated artifacts.

## Evidence and citations

`KnowledgeBase.evidence(record_id, record_type)` returns original evidence:

- **chunk** — the original `kb/chunks.jsonl` text, not the highlighted FTS snippet;
- **chapter** — the full `kb/chapters.jsonl` text;
- **table** — every `raw_lines` entry including the header and final row;
- **entity** — English summary, structured kind/section/supertype/attributes/
  components/fields, and the defining related table(s), or the original chapter
  when no related table exists;
- **relationship** — no separate hydration; the Part 5 boundary snippet is kept.

`RetrievedRecord` has an optional `evidence` field appended after `doc`, so all
existing positional constructions and lightweight test doubles keep their search
snippet. The retriever hydrates through the real public method; a non-string
Mock attribute or a double without the method is ignored. The search snippet
contract itself is unchanged.

`RAGPipeline` packs complete evidence units within `max_context_chars`. It skips
a unit rather than cutting a sentence, line, or table row. Citation labels are
assigned only after selection, so `citations` and `retrieved` contain exactly the
evidence supplied to the model. Each size check includes the prospective label
and separators, so skipping an oversized hit leaves room for later smaller hits.
The RAG response's `retrieved[].snippet` contains the full selected evidence,
allowing existing frontend evidence panels and stored history to show what the
model received. `KnowledgeBase.search()` still returns the original short snippets.
Omitted records are named in the response
`error` field and receive no label. If no unit fits, the pipeline returns an
offline answer without calling the model.

Canonical labels are `[E1]` (entity), `[T1]` (table), `[C1]` (chunk), and `[R1]`
(relationship), numbered per prefix from 1. Generated answers are accepted only
when they contain at least one supplied canonical label and no malformed or
unknown labels. Missing labels, `[E0]`, `[Eabc]`, comma forms such as
`[E1, E99]`, unknown prefixes such as `[X99]`, lowercase numeric labels such as
`[e1]`, unclosed numeric labels, and labels not present in the supplied context fall back to the
existing offline evidence answer with a clear error. No retries or API loops are
performed.

## Recorded local baseline (2026-11-16)

The complete reports are `evaluations/2026-11-16-fts.json` and
`evaluations/2026-11-16-hybrid.json`. Both use the same 21-case fixture: 17
positive questions, 2 out-of-scope diagnostics and 2 context-dependent diagnostics.
Default `top_k` is 3; the fixture explicitly enables one relationship expansion.

| Metric | FTS | Hybrid |
| --- | ---: | ---: |
| Hit@1 | 64.71% | 64.71% |
| Hit@3 | 88.24% | 88.24% |
| Recall@1 | 49.02% | 49.02% |
| Recall@3 | 85.29% | 85.29% |
| MRR over retrieved candidates | 0.7451 | 0.7451 |
| Mean query latency | 7.28 ms | 340.68 ms |

Hybrid used the real local `.\models\all-MiniLM-L6-v2` model (384 dimensions)
and the existing source-matched vector index, with every query reporting
`actual_mode=hybrid`. Source version: 1.05.06. Source SHA-256:
`c8eca3199423cbe5746e6e0aa4782fb990494474668cc9f6b9000cb142aa42bf`.
Fixture SHA-256:
`f1bdecae118e20809ab709583774caba0d4cee4307566fc6f423bcb7f5999d46`.

These measurements do not show a metric gain from hybrid retrieval on this small
fixture. The pure-Chinese paraphrase for ServerStatusDataType misses its expected
ID in both modes; the currentTime/shutdownReason paraphrase retrieves table-242
but misses the required entity ID. Both modes return records for all four
diagnostic cases; that is not correct abstention and is not scored as success.
Metrics score record IDs before context packing, not the semantic contents of
hydrated evidence; an entity containing its defining table does not count as a
separate table-ID hit. Latency excludes model initialization and is one local
run, not a throughput benchmark. No online language model was called.

## Verification

Final local acceptance: 134 Python tests passed; React lint and production build
passed. HTTP integration tests cover complete evidence in responses and stored
anonymous history, plus offline fallback for unknown generated citation labels.
No online language model was called. An existing Starlette/httpx deprecation
warning does not fail the test suite.

## Limits

- Label validation proves only that the model used syntactically valid,
  supplied provenance labels. It does **not** prove semantic entailment or answer
  correctness; no similarity cutoff is used to reject answers.
- Out-of-scope and context-dependent diagnostics describe retrieval behavior,
  not refusal behavior. A non-empty result there is not a success.
- The fixture is a small, versioned regression baseline, not a statistical
  estimate of production quality.
- FTS5 tokenization is weak for long unspaced CJK runs, so pure-Chinese
  paraphrases may miss canonical English artifacts. Mixed Chinese/English
  queries with canonical identifiers are the reliable path; the fixture records
  this limitation instead of hiding it.
- Hybrid evaluation requires the local model and source-hash-matched vector
  artifacts already generated by the existing build command. It does not
  download or rebuild them.
- Offline mode remains a deterministic evidence listing; it is not a generated
  or semantically verified answer.
