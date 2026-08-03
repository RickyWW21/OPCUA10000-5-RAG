# First-Batch Optimization Design

## Scope

Implement the first approved optimization batch without changing the public CLI,
TUI, JSONL artifact schema, or `KnowledgeBase` API signatures:

- publish generated knowledge-base artifacts atomically;
- index relationships by source for breadth-first traversal;
- resolve the graph module's Pyright tuple-key diagnostic;
- add regression tests for each behavior.

## Atomic Build Publication

`build()` will stage all generated artifacts in a sibling temporary directory. The
staging tree contains `kb/`, `indexes/`, `source/`, generated `README.md`, and
the exported source copy. Generation errors clean up staging and leave the current
published artifacts untouched.

The project root also contains source code, so it cannot be replaced as a whole.
After successful generation, publication is a backup/commit/rollback transaction
over only the generated files: the previous targets are moved to a backup area,
staged files are moved into place, and backups are removed. If any publish move
fails, all moved targets are restored before reporting the error. The source
Markdown input and project source files are never moved or altered.

## Relationship Traversal

`KnowledgeBase` retains the existing cached ordered relationship list and builds
an additional cached mapping from source entity ID to its ordered outgoing edges.
`relationships()` continues breadth-first traversal and relation filtering, but
reads only each visited node's outgoing edges. Public result order remains
unchanged.

## Graph Typing

Graph edge aggregation will explicitly construct a `tuple[str, str]` key after
ordering source and target IDs. This preserves runtime behavior and satisfies
Pyright's fixed-length tuple requirement.

## Tests And Acceptance

- A failed rebuild preserves a queryable previously published knowledge base.
- Relationship traversal returns the same breadth-first, filtered result order and
  demonstrates use of the cached adjacency index.
- Graph aggregation remains behaviorally identical and has no Pyright diagnostics.
- The complete `python -m unittest discover -s tests -v` suite passes.
