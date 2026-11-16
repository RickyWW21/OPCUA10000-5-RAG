# Part 5 RAG evaluation and evidence design

The user authorized the first two recommended improvements: an honest retrieval
evaluation baseline, followed by complete evidence and citation validation.
Keep CLI, TUI, Streamlit, and FastAPI/React working; add no login or dependencies.

## Approach

Extend the existing evaluator and shared KnowledgeBase/RAGPipeline. A separate
evaluation service or frontend-specific pipelines would duplicate existing work.
Do not introduce reranking, query rewriting, a new vector database, or sessions work.

## Evaluation

- Run explicit FTS and hybrid modes on the same versioned query set. Hybrid must
  fail clearly if unavailable or if a query falls back; never label FTS as hybrid.
- Report Hit@1/3, true Recall@1/3, MRR, per-case results and latency, with model,
  source hash, requested/actual modes, fixture identity and parameters.
- Expand fixtures with Chinese/English, paraphrases, entity/table/section and
  multiple required evidence cases. Mark out-of-scope and context-dependent cases
  separately so an unconditional nearest-neighbor hit cannot count as success.
- Record a reproducible local baseline without calling a paid language model.

## Evidence and citations

- Resolve search hits to original chunk text, chapter text, full table raw lines
  (including header), or entity content and its defining tables. Preserve the
  existing search snippet contract; use additional evidence text in the shared
  retriever/pipeline, not frontend-specific code.
- Select complete evidence units within the existing character budget. Never
  silently cut a sentence/table row. Skip oversized units; disclose omissions.
- Assign citation labels after selection, and return only supplied evidence in
  citations/retrieved. If nothing fits, return offline without calling the model.
- Validate generated citation labels against supplied labels; missing, unknown,
  or malformed evidence labels trigger an explicit error and offline evidence.
- This validates provenance labels, not semantic entailment. Do not describe
  nonempty retrieval or valid labels as proof of answer correctness.

## Acceptance

Real artifact tests cover text beyond snippets, table tails and headers, entity
definition lookup, exact budget boundaries, invalid/missing citations, and no
evidence. Evaluator tests distinguish hit from recall, enforce strict hybrid,
and keep unanswerable/context-dependent cases outside positive retrieval scores.
Run the complete Python suite plus existing React lint/build. No external LLM is
required and no frontend/API field is removed.
