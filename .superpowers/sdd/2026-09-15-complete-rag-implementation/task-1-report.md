# Task 1 Report

## Files

- `opcua_kb/retrieval.py`
- `tests/test_retrieval.py`

## Verification

Command: `python -m unittest tests.test_retrieval -v`

Output: 3 tests ran; all passed (`OK`).

## Self-review

- Search result order is preserved, with first-seen IDs retained.
- Records declaring a document other than `OPC-10000-5` are rejected; missing `doc` defaults to Part 5.
- `top_k` and relationship depth are validated.
- Relationship records are added only after an entity resolves successfully.

## Concerns

Relationship records use the target ID as their record ID, so an entity and relationship targeting the same ID are intentionally deduplicated. The adapter assumes KnowledgeBase search results are ordered with exact matches first, as guaranteed by the existing API.
