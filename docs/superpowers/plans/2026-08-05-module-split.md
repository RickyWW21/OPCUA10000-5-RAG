# Module Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split graph rendering and builder parsing into focused modules without changing public behavior or imports.

**Architecture:** `graph.py` remains the graph-model and export facade while `graph_render.py` owns HTML/SVG generation. `builder.py` remains the build/publish facade while `builder_models.py` owns the two mutable parse records and `builder_parse.py` owns Markdown/CSV parsing.

**Tech Stack:** Python standard library, `unittest`.

---

### Task 1: Extract Graph Rendering

**Files:**
- Create: `opcua_kb/graph_render.py`
- Modify: `opcua_kb/graph.py`
- Modify: `tests/test_graph.py`

- [ ] **Step 1: Add a boundary test**

```python
from opcua_kb.graph_render import render_interactive_graph_html

def test_public_renderer_delegates_to_render_module(self) -> None:
    graph = {"nodes": [], "edges": [], "metadata": {}}
    self.assertEqual(render_interactive_graph_html(graph), render_graph_html(graph))
```

- [ ] **Step 2: Verify RED**

Run: `python -m unittest tests.test_graph.GraphTests.test_public_renderer_delegates_to_render_module -v`

Expected: import failure because `opcua_kb.graph_render` does not exist.

- [ ] **Step 3: Move rendering-only symbols**

Create `opcua_kb/graph_render.py` with these moved symbols and only standard-library imports: `KIND_COLORS`, `render_interactive_graph_html`, `_render_static_graph_html`, `_layout`, `_json_for_html_script`, `_norm`.

Move the complete existing `_render_interactive_graph_html` definition unchanged,
renaming it to `render_interactive_graph_html`; move its renderer-only helpers
unchanged with it.

In `opcua_kb/graph.py`, import the renderer and retain the public facade:

```python
from .graph_render import render_interactive_graph_html

def render_graph_html(graph: dict[str, Any]) -> str:
    return render_interactive_graph_html(graph)
```

Remove moved imports and private symbols from `graph.py`. Keep `build_knowledge_graph`, graph filtering, aggregation, metadata, and write helpers there.

- [ ] **Step 4: Verify GREEN**

Run: `python -m unittest tests.test_graph -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add opcua_kb/graph.py opcua_kb/graph_render.py tests/test_graph.py
git commit -m "refactor: separate graph rendering"
```

### Task 2: Extract Builder Models

**Files:**
- Create: `opcua_kb/builder_models.py`
- Modify: `opcua_kb/builder.py`
- Modify: `tests/test_builder.py`

- [ ] **Step 1: Add an import-compatibility test**

```python
from opcua_kb.builder_models import Table as ModelTable

def test_builder_reexports_parse_models(self) -> None:
    self.assertIs(Table, ModelTable)
```

- [ ] **Step 2: Verify RED**

Run: `python -m unittest tests.test_builder.BuilderTests.test_builder_reexports_parse_models -v`

Expected: import failure because `opcua_kb.builder_models` does not exist.

- [ ] **Step 3: Move model declarations**

Create `opcua_kb/builder_models.py` containing the existing `Chapter` and `Table` dataclasses unchanged. Replace their definitions in `builder.py` with:

```python
from .builder_models import Chapter, Table
```

Do not change existing imports from `opcua_kb.builder`.

- [ ] **Step 4: Verify GREEN**

Run: `python -m unittest tests.test_builder -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add opcua_kb/builder.py opcua_kb/builder_models.py tests/test_builder.py
git commit -m "refactor: extract builder parse models"
```

### Task 3: Extract Builder Parsing

**Files:**
- Create: `opcua_kb/builder_parse.py`
- Modify: `opcua_kb/builder.py`
- Modify: `tests/test_builder.py`

- [ ] **Step 1: Add a parser boundary test**

```python
from opcua_kb.builder_parse import parse_chapters

def test_parser_module_preserves_chapter_shape(self) -> None:
    chapters = parse_chapters(["1 Introduction", "1.1 Scope"])
    self.assertEqual(["1", "1.1"], [chapter.section for chapter in chapters])
```

- [ ] **Step 2: Verify RED**

Run: `python -m unittest tests.test_builder.BuilderTests.test_parser_module_preserves_chapter_shape -v`

Expected: import failure because `opcua_kb.builder_parse` does not exist.

- [ ] **Step 3: Move parser-owned code**

Create `opcua_kb/builder_parse.py` with `parse_chapters`, `parse_tables`, and parser-private helpers moved from `builder.py`:

```text
_parent_section, _next_heading_after, _chapter_for_line, _table_kind,
_parse_table_rows, _csv_cells, _is_header, _normalize_columns, _row_from_cells
```

Keep regular expressions in the parser module. Update `builder.py` to import `parse_chapters` and `parse_tables`, then replace calls in `build`:

```python
chapters = parse_chapters(lines)
tables = parse_tables(lines, chapters)
```

Do not move entity enrichment, FTS, artifact I/O, publication, or CLI code.

- [ ] **Step 4: Verify GREEN**

Run: `python -m unittest tests.test_builder tests.test_error_boundaries -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add opcua_kb/builder.py opcua_kb/builder_parse.py tests/test_builder.py
git commit -m "refactor: separate builder markdown parsing"
```

### Task 4: Final Verification

**Files:**
- Modify: none

- [ ] **Step 1: Run full tests**

Run: `python -m unittest discover -s tests -v`

Expected: PASS with zero failures.

- [ ] **Step 2: Check public imports and diagnostics**

Run: `python -c "from opcua_kb import KnowledgeBase, render_graph_html; from opcua_kb.builder import Chapter, Table; print('ok')"`

Expected: `ok`.

Then use Serena `get_diagnostics_for_file` for `opcua_kb/graph.py`, `opcua_kb/graph_render.py`, `opcua_kb/builder.py`, and `opcua_kb/builder_parse.py` with `min_severity=4`.

Expected: no errors.

- [ ] **Step 3: Inspect final state**

Run: `git diff master...HEAD --check; git status --short`

Expected: no whitespace errors and no uncommitted tracked changes.
