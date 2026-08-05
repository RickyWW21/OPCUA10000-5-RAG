# Module Split Design

## Scope

Split `opcua_kb/graph.py` and `opcua_kb/builder.py` by their existing
responsibilities. Preserve public imports, CLI/TUI behavior, generated
artifacts, exceptions, and output bytes where existing tests assert them.

## Graph Rendering

Move HTML/SVG generation, layout, HTML-safe JSON embedding, and renderer-only
constants from `graph.py` to `graph_render.py`.

`graph.py` remains the public facade for graph selection, aggregation, export
functions, and the existing `render_graph_html`, `write_graph_html`, and
`write_graph_json` APIs. It delegates HTML rendering to `graph_render.py`.

## Builder Parsing

Move `Chapter` and `Table` to `builder_models.py`. Move chapter parsing, table
parsing, CSV normalization, and table-row parsing to `builder_parse.py`.

`builder.py` remains the public facade for `build`, artifact publication, FTS,
entity enrichment, and CLI. It re-exports `Chapter` and `Table` to preserve
existing imports.

## Exclusions

Do not split entity extraction, FTS, publication, CLI, or TUI in this batch.
Those changes cross more behavior boundaries than the current refactor needs.

## Verification

Keep existing graph and builder tests green. Add focused import/behavior tests
only where a moved module boundary otherwise lacks coverage. Run the full
`unittest` suite after each subproject.
