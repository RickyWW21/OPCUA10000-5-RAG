# OPC UA Parts 1-14 Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add reliable multi-Part ingestion, coverage reporting, validation, and cross-Part search for core OPC UA Parts 1-14 while preserving the current Part 5 API and CLI behavior.

**Architecture:** Keep the existing Markdown parser and FTS5 storage, but introduce a batch orchestration layer that parses each Part independently, annotates provenance, merges canonical records, adds Part catalog edges, validates the complete in-memory dataset, and publishes artifacts through the existing rollback transaction. Extend `KnowledgeBase` with coverage-aware, bounded relation expansion rather than replacing the current exact-plus-FTS search path.

**Tech Stack:** Python 3, `pathlib`, `json`, `sqlite3` FTS5, `argparse`, `unittest`/`pytest`, existing `opcua_kb.builder_parse` helpers.

**Spec:** `docs/superpowers/specs/2026-09-01-opcua-parts-1-14-coverage-design.md`

## Global Constraints

- Scope is core OPC UA Parts 1-14 only.
- Missing source documents must remain reported as missing; no normative content may be fabricated.
- Existing single-source build and `KnowledgeBase` methods remain compatible.
- No external runtime service or vector database may be added.
- Publication must remain rollback-safe: validation or publish failure leaves the previous artifacts untouched.
- Every generated record must carry `part`, `doc`, `version`, and `source_ref` provenance where applicable.

---

### Task 1: Define Part source resolution and provenance contracts

**Files:**
- Create: `opcua_kb/part_sources.py`
- Modify: `kb/part_catalog.jsonl`
- Modify: `tests/test_part_sources.py`

**Interfaces:**
- Produces `PartSource` dataclass with `part: int`, `doc: str`, `title: str`, `path: Path | None`, `status: str`, `depends_on: tuple[int, ...]`, and `links: tuple[str, ...]`.
- Produces `load_part_catalog(root: Path) -> list[PartSource]`.
- Produces `resolve_part_sources(root: Path, manifest: Path | None = None) -> list[PartSource]`.
- Produces `part_number_from_title(text: str) -> int | None`.

- [ ] **Step 1: Write failing tests for catalog loading and source resolution.**

```python
def test_resolve_default_layout_marks_only_existing_sources(tmp_path):
    (tmp_path / "kb").mkdir()
    (tmp_path / "source" / "parts").mkdir(parents=True)
    shutil.copy(ROOT / "kb" / "part_catalog.jsonl", tmp_path / "kb" / "part_catalog.jsonl")
    (tmp_path / "source" / "parts" / "part-05.md").write_text("OPC-10000-5\n", encoding="utf-8")
    sources = resolve_part_sources(tmp_path)
    assert sources[4].path.name == "part-05.md"
    assert sources[4].status == "present"
    assert sources[0].path is None
    assert sources[0].status == "missing"
```

- [ ] **Step 2: Run the focused test and verify it fails because the module is absent.**

Run: `python -m pytest tests/test_part_sources.py -q`

Expected: import failure for `opcua_kb.part_sources`.

- [ ] **Step 3: Implement catalog parsing and deterministic resolution.**

Use `json.loads` per JSONL line, require Part numbers 1 through 14, prefer an explicit manifest mapping, then `source/parts/part-NN.md`, then catalog `source_path`. Reject duplicate Part numbers and files whose title identifies a conflicting Part.

- [ ] **Step 4: Run the focused tests and add malformed-catalog cases.**

Run: `python -m pytest tests/test_part_sources.py -q`

Expected: all source-resolution tests pass, including duplicate and conflicting-title errors.

- [ ] **Step 5: Commit the source contract.**

```bash
git add opcua_kb/part_sources.py tests/test_part_sources.py kb/part_catalog.jsonl
git commit -m "feat: resolve OPC UA Part sources"
```

### Task 2: Add batch parsing, merge, and provenance-aware publication

**Files:**
- Create: `opcua_kb/multi_part.py`
- Modify: `opcua_kb/builder.py`
- Modify: `tests/test_multi_part_builder.py`

**Interfaces:**
- Produces `build_parts(root: Path, sources: Sequence[PartSource], rebuild: bool = False) -> dict[str, int]`.
- Produces `merge_part_records(parsed_parts: Sequence[ParsedPart]) -> MergedRecords`.
- `MergedRecords` exposes `chapters`, `tables`, `entities`, `relationships`, and `chunks` lists.
- Existing `build(root, source, rebuild=False)` delegates through the same publication path with one `PartSource`.

- [ ] **Step 1: Write a failing two-Part merge test.**

```python
def test_build_parts_merges_sources_and_preserves_part_provenance(tmp_path):
    root = make_root_with_catalog(tmp_path)
    write_part(root, 1, "OPC-10000-1\n1 Concepts\nTable 1 - Base\n")
    write_part(root, 5, "OPC-10000-5\n1 Information Model\nTable 1 - Model\n")
    result = build_parts(root, resolve_part_sources(root))
    assert result["parts"] == 2
    entities = read_jsonl(root / "kb" / "entities.jsonl")
    assert {item["part"] for item in entities if item["kind"] != "Part"} == {1, 5}
```

- [ ] **Step 2: Run the test to verify the batch API is missing.**

Run: `python -m pytest tests/test_multi_part_builder.py::test_build_parts_merges_sources_and_preserves_part_provenance -q`

Expected: import or attribute failure for `build_parts`.

- [ ] **Step 3: Implement `ParsedPart`, `MergedRecords`, and per-Part parsing.**

Call the existing `parse_chapters`, `parse_tables`, and entity extraction helpers for each source. Add `part`, `doc`, and source references before merging. Keep document-scoped chapter/table/chunk IDs unique by prefixing the document key when two source documents reuse a section/table number.

- [ ] **Step 4: Implement deterministic entity and relationship de-duplication.**

Use canonical entity ID as the merge key. Combine provenance references in sorted order. Use `(source, relation, target, normalized properties)` as the relationship key and preserve all source references in a `source_refs` list.

- [ ] **Step 5: Reuse the existing rollback publication transaction.**

Refactor only the smallest shared portion of `builder.build` needed to publish merged lists, rebuild FTS, write the README, and restore previous artifacts on any parse, validation, or publish error.

- [ ] **Step 6: Run batch and regression tests.**

Run: `python -m pytest tests/test_multi_part_builder.py tests/test_builder.py -q`

Expected: new merge tests and all existing builder tests pass.

- [ ] **Step 7: Commit the batch pipeline.**

```bash
git add opcua_kb/multi_part.py opcua_kb/builder.py tests/test_multi_part_builder.py
git commit -m "feat: build a merged OPC UA Parts database"
```

### Task 3: Implement coverage and structural validation

**Files:**
- Create: `opcua_kb/validation.py`
- Modify: `opcua_kb/multi_part.py`
- Modify: `tests/test_validation.py`

**Interfaces:**
- Produces `coverage_report(root: Path) -> list[dict[str, Any]]`.
- Produces `validate_kb(root: Path, allow_missing_parts: bool = True) -> ValidationReport`.
- `ValidationReport` has `errors: list[str]`, `warnings: list[str]`, `counts: dict[str, int]`, and `ok: bool`.

- [ ] **Step 1: Write failing validation tests.**

```python
def test_coverage_reports_all_fourteen_parts(tmp_path):
    root = make_root_with_catalog(tmp_path)
    write_part(root, 5, "OPC-10000-5\n1 Information Model\n")
    build_parts(root, resolve_part_sources(root))
    rows = coverage_report(root)
    assert [row["part"] for row in rows] == list(range(1, 15))
    assert rows[4]["searchable"] is True
    assert rows[0]["present"] is False
```

```python
def test_validate_kb_rejects_unresolved_relationship_target(tmp_path):
    root = make_root_with_catalog(tmp_path)
    write_jsonl(root / "kb" / "relationships.jsonl", [{"source": "Part:Part 5", "relation": "DEPENDS_ON", "target": "Part:Part 99"}])
    report = validate_kb(root)
    assert report.ok is False
    assert any("Part 99" in error for error in report.errors)
```

- [ ] **Step 2: Run the tests and verify the validation API is absent.**

Run: `python -m pytest tests/test_validation.py -q`

Expected: import failure for `opcua_kb.validation`.

- [ ] **Step 3: Implement coverage calculation.**

Read the catalog, source resolution, generated records, and FTS rows. Compute `present`, `parsed`, `indexed`, and `searchable` independently, with counts for chapters, tables, entities, and chunks.

- [ ] **Step 4: Implement structural validation.**

Decode every JSONL file, detect duplicate IDs, resolve relationship endpoints except explicitly external references, verify source references, verify FTS row IDs, and enforce Part dependency targets in 1-14. Missing source Parts produce warnings when `allow_missing_parts=True` and errors otherwise.

- [ ] **Step 5: Integrate validation before publication.**

Have `build_parts` validate staged artifacts before replacing published artifacts. On failure, raise `ValueError` with the report summary and keep the old database intact.

- [ ] **Step 6: Run focused and full tests.**

Run: `python -m pytest tests/test_validation.py tests/test_multi_part_builder.py tests/test_error_boundaries.py -q`

Expected: validation, rollback, and existing error-boundary tests pass.

- [ ] **Step 7: Commit coverage and validation.**

```bash
git add opcua_kb/validation.py opcua_kb/multi_part.py tests/test_validation.py
git commit -m "feat: report and validate Part coverage"
```

### Task 4: Extend the API with cross-Part search expansion

**Files:**
- Modify: `opcua_kb/api.py`
- Modify: `opcua_kb/__init__.py`
- Modify: `tests/test_api.py`

**Interfaces:**
- Extend `KnowledgeBase.search(query, top_k=10, part: int | None = None, expand: bool = True, depth: int = 1)` without breaking existing positional calls.
- Add `KnowledgeBase.coverage() -> list[dict[str, Any]]`.
- Add `KnowledgeBase.validate(allow_missing_parts: bool = True) -> dict[str, Any]`.

- [ ] **Step 1: Write failing cross-Part search tests.**

```python
def test_search_expands_to_related_ingested_parts(tmp_path):
    root = build_fixture_with_parts(tmp_path, parts=(1, 3, 5))
    results = KnowledgeBase(root).search("NodeId", top_k=12)
    assert any(item.get("part") == 5 and item["type"] == "entity" for item in results)
    assert any(item.get("part") == 3 for item in results)
    assert any(item.get("relation") for item in results if item.get("part") == 3)
```

```python
def test_search_part_filter_excludes_other_parts(tmp_path):
    root = build_fixture_with_parts(tmp_path, parts=(1, 3, 5))
    results = KnowledgeBase(root).search("NodeId", part=3)
    assert all(item.get("part") in (3, None) for item in results)
```

- [ ] **Step 2: Run the focused tests and verify the new arguments are unsupported.**

Run: `python -m pytest tests/test_api.py -q`

Expected: failure at the new keyword arguments or missing methods.

- [ ] **Step 3: Add provenance-aware result projection.**

Include `part`, `doc`, and `source_ref` in exact and FTS result dictionaries when present. Keep the existing `type`, `id`, `title`, `section`, `table_number`, and `snippet` keys.

- [ ] **Step 4: Implement bounded cross-Part expansion.**

Resolve matched entity/Part IDs, traverse `CROSS_PART_LINK` and `DEPENDS_ON` edges breadth-first, skip direct duplicates, respect `depth`, `top_k`, and `part`, and mark expanded records with `relation="cross_part"` or the originating edge relation.

- [ ] **Step 5: Add API wrappers for coverage and validation.**

Delegate to `opcua_kb.validation` and return JSON-serializable dictionaries.

- [ ] **Step 6: Run API regression tests.**

Run: `python -m pytest tests/test_api.py tests/test_graph.py -q`

Expected: all old API tests plus new cross-Part tests pass.

- [ ] **Step 7: Commit the search API.**

```bash
git add opcua_kb/api.py opcua_kb/__init__.py tests/test_api.py
git commit -m "feat: add cross-Part search expansion"
```

### Task 5: Add batch, coverage, and validation CLI commands

**Files:**
- Create: `tools/build_parts.py`
- Create: `tools/coverage_kb.py`
- Create: `tools/validate_kb.py`
- Modify: `opcua_kb/__main__.py`
- Modify: `tools/query_kb.py`
- Modify: `tools/help.py`
- Modify: `README.md`
- Modify: `tests/test_cli.py`

**Interfaces:**
- `python tools/build_parts.py --root . [--manifest PATH] [--rebuild]` builds all resolvable Parts.
- `python tools/coverage_kb.py --root . [--json]` prints one row per Part and exits 0 when only intentional missing sources exist.
- `python tools/validate_kb.py --root . [--strict-missing]` prints errors/warnings and exits 1 on validation errors.
- `python -m opcua_kb parts`, `coverage`, and `validate` dispatch to these tools.
- `query_kb.py` accepts `--part N`, `--no-expand`, and `--depth N`.

- [ ] **Step 1: Write failing CLI tests for help and normal output.**

```python
def test_coverage_cli_lists_all_parts(tmp_path):
    root = build_fixture_with_parts(tmp_path, parts=(5,))
    result = run_tool("coverage_kb.py", "--root", str(root))
    assert result.returncode == 0
    assert "Part 1" in result.stdout
    assert "Part 5" in result.stdout
```

- [ ] **Step 2: Run the tests and verify the command files are absent.**

Run: `python -m pytest tests/test_cli.py -q`

Expected: command invocation failure for the new scripts.

- [ ] **Step 3: Implement the three CLI wrappers using existing `run_cli`.**

Keep expected failures concise, prefix errors with `错误:`, and avoid tracebacks. JSON output must be valid JSON and include the same report data returned by the API.

- [ ] **Step 4: Add dispatcher entries and query flags.**

Map `parts`, `coverage`, and `validate` in `opcua_kb.__main__.COMMANDS`; pass the new search options through `tools/query_kb.py`.

- [ ] **Step 5: Update help and README examples.**

Document the `source/parts/` layout, the distinction between capability and actual source coverage, and the acceptance commands.

- [ ] **Step 6: Run CLI and full regression tests.**

Run: `python -m pytest tests/test_cli.py tests/test_error_boundaries.py -q`

Expected: all CLI tests pass without stderr on successful runs and without tracebacks on expected failures.

- [ ] **Step 7: Commit the command surface.**

```bash
git add tools/build_parts.py tools/coverage_kb.py tools/validate_kb.py opcua_kb/__main__.py tools/query_kb.py tools/help.py README.md tests/test_cli.py
git commit -m "feat: expose multi-Part build and validation commands"
```

### Task 6: Add end-to-end acceptance fixtures and finalize verification

**Files:**
- Modify: `tests/helpers.py`
- Create: `tests/test_parts_acceptance.py`
- Modify: `README.md`

**Interfaces:**
- Fixture helper `build_fixture_with_parts(tmp_path, parts: tuple[int, ...]) -> Path` creates deterministic synthetic Part sources with shared `NodeId` and `ServerType` references.

- [ ] **Step 1: Write the end-to-end acceptance test.**

```python
def test_parts_1_3_5_acceptance_flow(tmp_path):
    root = build_fixture_with_parts(tmp_path, parts=(1, 3, 5))
    assert run_tool("build_parts.py", "--root", str(root)).returncode == 0
    search = KnowledgeBase(root).search("NodeId", top_k=20)
    assert {item.get("part") for item in search} >= {1, 3, 5}
    assert KnowledgeBase(root).validate()["ok"] is True
```

- [ ] **Step 2: Run the acceptance test before final changes.**

Run: `python -m pytest tests/test_parts_acceptance.py -q`

Expected: failure until all preceding tasks are integrated.

- [ ] **Step 3: Implement deterministic fixtures and adjust only integration defects.**

Use small Markdown documents that exercise chapters, tables, entities, relationships, and shared catalog links; do not embed real OPC Foundation source text in tests.

- [ ] **Step 4: Run the complete verification suite.**

Run: `python -m pytest -q`

Expected: all existing and new tests pass.

- [ ] **Step 5: Run the repository smoke commands.**

```powershell
python tools/build_parts.py --root .
python tools/coverage_kb.py --root .
python tools/validate_kb.py --root .
python tools/query_kb.py "NodeId" --part 3 --depth 2 --top-k 10
```

Expected: commands complete without tracebacks; coverage explicitly reports missing local Parts until their source files are supplied.

- [ ] **Step 6: Commit final acceptance coverage.**

```bash
git add tests/helpers.py tests/test_parts_acceptance.py README.md
git commit -m "test: verify OPC UA Parts coverage workflow"
```

## Self-Review Checklist

- Spec input layout and source resolution: Task 1.
- Provenance, merge, de-duplication, and rollback publication: Task 2.
- Coverage states and structural validation: Task 3.
- Cross-Part search, filtering, and compatibility: Task 4.
- CLI operation and documentation: Task 5.
- End-to-end acceptance and regression verification: Task 6.
- No task relies on external downloads or fabricated specification content.
- All interfaces used by later tasks are defined by earlier tasks.
- Missing source Parts are warnings by default and errors only in strict mode.
