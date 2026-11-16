# Part 5 Evidence Baseline Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement task by task with tests first.

**Goal:** Measure actual hybrid retrieval and supply verifiable, complete evidence.
**Architecture:** Extend the evaluator and shared KnowledgeBase, retriever and pipeline.
**Tech Stack:** Existing Python standard library, unittest, installed embeddings.
**Spec:** ../specs/2026-11-16-rag-evidence-baseline-design.md

## Global Constraints

Preserve CLI/TUI/Streamlit/FastAPI/React. No login, new dependencies or paid LLM calls.
Do not stage .agents, models, indexes, session databases, or unrelated changes.

## Review Focus

Hit versus recall with multiple expected IDs; silent hybrid fallback; table rows
beyond the original snippet; citations for omitted context; missing/malformed labels.

## Task 1: Retrieval baseline

Files: tools/evaluate_retrieval.py, tests/test_retrieval_eval.py,
tests/fixtures/part5_retrieval_eval.json, docs/rag-evaluation-baseline.md.

- [x] Write and run failing tests for true recall, explicit modes, strict hybrid,
      multiple evidence and separately reported unsupported/context cases.
- [x] Extend evaluate(root, fixture, *, top_k=3, ...) with explicit mode/model
      options, metrics, provenance, latency and grouped results. Preserve defaults.
- [x] Add bilingual fixtures with real verified IDs and explicit case semantics.
- [x] Run FTS and available local hybrid; record actual outcomes and limitations.

## Task 2: Evidence hydration and citation validation

Files: opcua_kb/api.py, opcua_kb/retrieval.py, opcua_kb/rag.py;
tests/test_api.py, tests/test_retrieval.py, tests/test_rag.py.

- [x] Write and run failing tests proving full chunk/table/chapter/entity evidence
      reaches generation and citation lists exclude omitted budget units.
- [x] Reuse existing JSONL loaders for evidence lookup and hydrate retrieved
      records without altering the search snippet schema.
- [x] Pack complete evidence units, label only selected records and fail offline
      if nothing fits. Include omission information in the context/response error.
- [x] Test then implement generated label validation with offline fallback.

## Task 3: Regression and documentation

- [x] Document evaluation commands, metric definitions and citation limitations.
- [x] Run python -m unittest discover -s tests -q.
- [x] Run npm.cmd run lint and npm.cmd run build in web.
- [x] Review git diff and report exact results without claiming semantic verification.

## Execution record

- DSH wrote the initial implementation but exceeded its 10-minute limit. The
  user explicitly authorized direct repair and final acceptance by the main agent.
- Before direct repairs: 129 tests ran, with one erroneous test expectation
  (asserting the canned model response contains its input evidence).
- Direct RED: tests reproduced budget-label overhead losing a fitting later
  record, acceptance of unknown/lowercase/unclosed labels, and short snippets
  returned instead of the full model evidence.
- Direct GREEN: 38 core tests passed; 21 RAG/HTTP tests passed, including full
  evidence in anonymous history and invalid-label fallback over HTTP.
- Ruling: Continue in the existing feature checkout and leave changes uncommitted;
  preserve the in-progress work rather than switching worktrees mid-task.
- Ruling: Keep the existing frontend schemas. RAG response snippets now expose
  complete selected evidence, while the standalone search API remains unchanged.
- Self-review by the main agent follows the user's approved direct acceptance;
  the interrupted DSH task was not automatically retried or reported as complete.
- Final boundary RED/GREEN: malformed vector rows now raise the shared
  VectorIndexError, and an empty vector artifact cannot report hybrid mode.
  All 13 vector-index/evaluation tests passed after these fixes.
- Final verification: 134 Python tests passed in 19.659 seconds; React lint and
  production build passed. git diff --check passed (line-ending warnings only).
  The existing Starlette/httpx deprecation warning remains non-failing.
