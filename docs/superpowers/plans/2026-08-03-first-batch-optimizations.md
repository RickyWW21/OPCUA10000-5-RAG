# First-Batch Optimizations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make generated artifact publication recoverable, make relationship traversal scale with reachable edges, and remove the graph module's Pyright error.

**Architecture:** `builder.build` will write the complete generated artifact tree into a sibling staging directory and publish generated files through a backup/commit/rollback transaction only after every artifact is valid. `KnowledgeBase` will retain its ordered relationship cache while deriving a source-keyed adjacency cache for BFS. Graph aggregation will construct a fixed two-item tuple key explicitly.

**Tech Stack:** Python 3 standard library, SQLite FTS5, `unittest`, Serena LSP diagnostics.

---

## File Structure

- Modify: `opcua_kb/builder.py` - stage and publish generated artifacts with rollback.
- Modify: `opcua_kb/api.py` - cache ordered outgoing edges by source ID.
- Modify: `opcua_kb/graph.py` - build a statically typed pair key.
- Modify: `tests/test_error_boundaries.py` - prove a failed rebuild preserves the last publication.
- Modify: `tests/test_api.py` - prove BFS uses and preserves an ordered adjacency index.
- Modify: `tests/test_graph.py` - retain graph aggregation behavior after tuple typing change.

### Task 1: Transactional Artifact Publication

**Files:**
- Modify: `tests/test_error_boundaries.py`
- Modify: `opcua_kb/builder.py`

- [ ] **Step 1: Write the failing preservation test**

Add this test to `ErrorBoundaryTests`, importing `unittest.mock.patch` with the existing test imports:

```python
def test_failed_rebuild_preserves_previously_published_artifacts(self) -> None:
    with TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory) / "output"
        source = Path(temporary_directory) / "source.md"
        source.write_text("1 Introduction\n", encoding="utf-8")
        build(root, source)
        original_entities = (root / "kb" / "entities.jsonl").read_bytes()
        original_index = (root / "indexes" / "fts.sqlite").read_bytes()

        with patch("opcua_kb.builder._write_readme", side_effect=OSError("write failed")):
            with self.assertRaisesRegex(OSError, "write failed"):
                build(root, source, rebuild=True)

        self.assertEqual(original_entities, (root / "kb" / "entities.jsonl").read_bytes())
        self.assertEqual(original_index, (root / "indexes" / "fts.sqlite").read_bytes())
        self.assertEqual("Introduction", KnowledgeBase(root).chapter("1")["title"])
```

- [ ] **Step 2: Run the test and verify RED**

Run: `python -m unittest tests.test_error_boundaries.ErrorBoundaryTests.test_failed_rebuild_preserves_previously_published_artifacts -v`

Expected: FAIL because the current build writes artifacts into `root` before `_write_readme` raises.

- [ ] **Step 3: Implement staged generation and publication**

Refactor `build` so its generated output is a `TemporaryDirectory` sibling of `root`. Generate source copy, manifest, JSONL artifacts, aliases, FTS, and README beneath that staging root using existing writer helpers. Add a private `_publish_build(staging_root: Path, root: Path) -> None` that moves only generated targets (`source/<source-name>`, `source/source_manifest.json`, each `kb/*` artifact, `indexes/fts.sqlite`, and `README.md`) through a backup directory:

```python
def _publish_build(staging_root: Path, root: Path, targets: list[Path]) -> None:
    backup_root = Path(tempfile.mkdtemp(prefix=".opcua-kb-backup-", dir=root.parent))
    moved_backups: list[tuple[Path, Path]] = []
    published: list[Path] = []
    try:
        for relative_path in targets:
            target = root / relative_path
            staged = staging_root / relative_path
            if target.exists():
                backup = backup_root / relative_path
                backup.parent.mkdir(parents=True, exist_ok=True)
                target.replace(backup)
                moved_backups.append((target, backup))
            target.parent.mkdir(parents=True, exist_ok=True)
            staged.replace(target)
            published.append(target)
    except OSError:
        for target in reversed(published):
            if target.exists():
                target.unlink()
        for target, backup in reversed(moved_backups):
            if backup.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                backup.replace(target)
        raise
    finally:
        shutil.rmtree(backup_root, ignore_errors=True)
```

Use a staging parent next to `root` so each `Path.replace` is a same-filesystem atomic rename. Pass the staged root to `_write_readme`; do not touch generated targets until all generation calls succeed. Ensure staging cleanup occurs on every error and retain the current `OSError`/`ValueError` messages from lower-level helpers.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run: `python -m unittest tests.test_error_boundaries.ErrorBoundaryTests -v`

Expected: PASS, including the failed-rebuild preservation test and current write-failure diagnostics.

- [ ] **Step 5: Commit the transactional publication change**

```powershell
git add opcua_kb/builder.py tests/test_error_boundaries.py
git commit -m "fix: publish knowledge-base artifacts atomically"
```

### Task 2: Source-Keyed Relationship Index

**Files:**
- Modify: `tests/test_api.py`
- Modify: `opcua_kb/api.py`

- [ ] **Step 1: Write the failing adjacency-cache test**

Add this test to `KnowledgeBaseTests`:

```python
def test_relationships_cache_outgoing_edges_by_source_in_file_order(self) -> None:
    edges = self.kb._load_relationships()
    self.assertIsNone(getattr(self.kb, "_relationships_by_source", None))

    results = self.kb.relationships("server", depth=2)

    self.assertEqual(edges, [edge for group in self.kb._relationships_by_source.values() for edge in group])
    self.assertEqual(
        ["HAS_COMPONENT", "USES_DATATYPE"],
        [edge["relation"] for edge in results],
    )
```

- [ ] **Step 2: Run the test and verify RED**

Run: `python -m unittest tests.test_api.KnowledgeBaseTests.test_relationships_cache_outgoing_edges_by_source_in_file_order -v`

Expected: FAIL because `KnowledgeBase` has no `_relationships_by_source` cache.

- [ ] **Step 3: Implement the minimal adjacency index**

In `KnowledgeBase.__init__`, add:

```python
self._relationships_by_source: dict[str, list[dict[str, Any]]] | None = None
```

In `_load_relationships`, retain the existing ordered list load and derive the index once:

```python
if self._relationships is None:
    self._relationships = list(_read_jsonl(self.kb_dir / "relationships.jsonl"))
    self._relationships_by_source = {}
    for edge in self._relationships:
        source = edge.get("source")
        if source:
            self._relationships_by_source.setdefault(source, []).append(edge)
```

In `relationships`, replace the full scan with `for edge in self._relationships_by_source.get(current, []):`. Keep relation normalization, visited-set logic, queue behavior, and result order unchanged.

- [ ] **Step 4: Run the focused API tests and verify GREEN**

Run: `python -m unittest tests.test_api -v`

Expected: PASS, including exact search, malformed artifacts, FTS fallback, and BFS filtering.

- [ ] **Step 5: Commit the relationship index change**

```powershell
git add opcua_kb/api.py tests/test_api.py
git commit -m "perf: index relationships by source"
```

### Task 3: Fixed-Length Graph Edge Keys

**Files:**
- Modify: `tests/test_graph.py`
- Modify: `opcua_kb/graph.py`

- [ ] **Step 1: Write the regression test**

Add this test to `GraphTests`:

```python
def test_graph_aggregates_reversed_edge_endpoints_into_one_pair(self) -> None:
    graph = build_knowledge_graph(
        [
            {"id": "A", "name": "A", "kind": "ObjectType", "section": "1"},
            {"id": "B", "name": "B", "kind": "DataType", "section": "2"},
        ],
        [
            {"source": "A", "target": "B", "relation": "HAS_COMPONENT"},
            {"source": "B", "target": "A", "relation": "USES_DATATYPE"},
        ],
        include_defined=True,
        limit=0,
    )

    self.assertEqual(1, len(graph["edges"]))
    self.assertEqual({"HAS_COMPONENT": 5, "USES_DATATYPE": 3}, graph["edges"][0]["relations"])
```

- [ ] **Step 2: Run the test and record its baseline result**

Run: `python -m unittest tests.test_graph.GraphTests.test_graph_aggregates_reversed_edge_endpoints_into_one_pair -v`

Expected: PASS. This is a behavior-preservation regression test; the red signal for this task is Serena's existing Pyright diagnostic rather than a runtime failure.

- [ ] **Step 3: Fix the tuple key type without changing aggregation**

In `_aggregate_collapsed_edges`, replace `key = tuple(sorted((source, target)))` with:

```python
first, second = sorted((source, target))
key: tuple[str, str] = (first, second)
```

Keep all counter, evidence, filtering, sorting, and weight logic unchanged.

- [ ] **Step 4: Verify behavior and type diagnostics**

Run: `python -m unittest tests.test_graph -v`

Expected: PASS.

Then call Serena `get_diagnostics_for_file` for `opcua_kb/graph.py` with `min_severity=4`.

Expected: no diagnostics.

- [ ] **Step 5: Commit the graph typing change**

```powershell
git add opcua_kb/graph.py tests/test_graph.py
git commit -m "fix: type graph aggregation edge keys"
```

### Task 4: Full Verification

**Files:**
- Modify: none

- [ ] **Step 1: Run the complete suite**

Run: `python -m unittest discover -s tests -v`

Expected: PASS with 0 failures.

- [ ] **Step 2: Check the implementation diff**

Run: `git diff master...HEAD --check`

Expected: no whitespace errors and only the scoped source, test, and design-plan changes.

- [ ] **Step 3: Inspect repository state**

Run: `git status --short`

Expected: no uncommitted tracked changes.
