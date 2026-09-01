# OPC UA Parts 1-14 Coverage Design

**Date:** 2026-09-01
**Status:** Proposed
**Scope:** Core OPC UA Parts 1-14

## Goal

Turn the current Part 5-only knowledge base into a multi-document knowledge base that can ingest, validate, index, and cross-reference the core OPC UA Parts 1-14 without confusing catalog placeholders with ingested specification content.

## Current State

- `source/` contains only the Part 5 Markdown source.
- `kb/part_catalog.jsonl` lists Parts 1-14, with Part 5 marked `ingested` and the other parts marked `planned`.
- The builder accepts one source document per run and publishes one document's parsed artifacts.
- The current FTS index contains Part 5 records plus Part catalog entities and links.
- The existing test suite passes, but it does not prove multi-Part ingestion or cross-Part content retrieval.

## Success Criteria

1. A single command can build the shared database from any subset of local Part 1-14 source files.
2. A coverage command reports, for every Part 1-14, whether its source is present, parsed, indexed, and searchable.
3. A validation command detects malformed records, duplicate canonical IDs, unresolved relationship targets, stale index rows, and missing source references.
4. Searching an entity or concept returns its own result plus related results from other ingested Parts through explicit dependency and cross-Part links.
5. Missing source documents remain visible as missing; the system never reports them as fully covered.
6. Existing single-document commands and Python API behavior remain compatible.
7. Tests cover successful multi-Part builds, partial coverage, cross-Part retrieval, and failure recovery.

## Non-Goals

- Downloading or redistributing OPC Foundation specifications.
- Generating missing normative content from summaries or model output.
- Ingesting companion specifications outside Parts 1-14.
- Replacing the existing Markdown parser with a new document format.
- Introducing a vector database or external service dependency.

## Inputs and Layout

The canonical multi-Part input layout is:

```text
source/
  parts/
    part-01.md
    part-02.md
    ...
    part-14.md
  source_manifest.json
```

`kb/part_catalog.jsonl` remains the metadata source for the 14 core Parts. Each catalog record gains or derives:

- `part`, `number`, `title`
- `source_filename` or `source_path`
- `status`
- `depends_on`
- `links`
- optional source hash and version fields after a successful build

The builder also accepts an explicit manifest or repeated source arguments so repositories with different filenames can be used without copying files. A source file must identify its Part number from manifest metadata or a validated `OPC-10000-N` title; ambiguous files fail with a useful error.

## Data Model

Every generated record carries document provenance:

- `part`: integer 1-14
- `doc`: canonical document identifier such as `OPC-10000-5`
- `version`: source version when available
- `source_ref`: file, section, and line information

Canonical entity IDs remain `Kind:Name` for shared OPC UA entities. Part records use `Part:Part N`. Chapter, table, and chunk IDs are document-scoped and include the document key where needed to prevent collisions.

Relationship records use the existing schema and add these constraints:

- `DEPENDS_ON`: `Part:Part N` to another Part node.
- `CROSS_PART_LINK`: a Part or entity to a canonical entity, Part, chapter, or table.
- Existing entity relationships remain unchanged for compatibility.

The merge layer de-duplicates identical canonical entities and relationships while preserving all `source_ref` values in a deterministic order.

## Build Pipeline

The batch build pipeline is:

1. Load the Parts 1-14 catalog and resolve each source file.
2. Read and parse each source independently using the existing chapter/table/entity extraction helpers.
3. Attach `part`, `doc`, and source provenance to every record.
4. Merge records into one in-memory dataset, de-duplicating canonical entities and edges.
5. Add catalog Part nodes, dependency edges, and cross-Part anchors.
6. Generate chunks with Part-aware metadata.
7. Rebuild one FTS5 index containing entities, chapters, tables, chunks, and Part catalog records.
8. Run validation before publication.
9. Publish all generated artifacts through the existing rollback-capable transaction.

The existing single-source `build` path remains available and delegates to the same merge/publish machinery with one input.

## Search Behavior

The API gains a Part-aware search result contract while preserving existing keys. Each result may include `part`, `doc`, and `source_ref`.

Search order:

1. Exact canonical entity, Part, chapter, or table matches.
2. FTS matches across all ingested records.
3. Related cross-Part records reached from matched entities and Parts, bounded by a configurable hop and result limit.

Related results must be marked with a stable relation field so callers can distinguish direct matches from expanded context. A `part` filter limits direct and expanded results. Queries against a missing Part return the Part catalog record and coverage status, not fabricated content.

## Coverage and Validation

`coverage` reports one row per Part with:

- source path and source hash
- `present`, `parsed`, `indexed`, `searchable`
- chapter/table/entity/chunk counts
- validation errors and warnings

`validate_kb` checks:

- all JSONL records decode
- all IDs are unique within their namespace
- relationship sources and targets resolve, except explicitly external references
- every chapter/table/entity/chunk has a valid source reference
- every indexed row maps to a generated record
- every ingested Part has at least one searchable record
- Part dependency targets are within Parts 1-14

Validation returns a non-zero exit code on errors and a zero exit code with warnings for intentionally missing source Parts.

## Error Handling and Compatibility

- Missing files, invalid encoding, malformed manifests, and ambiguous Part identity fail before publication.
- Validation failures leave the previously published database untouched.
- Existing CLI error-boundary behavior remains concise and traceback-free.
- Existing `KnowledgeBase.search`, `get_entity`, `chapter`, `table`, `relationships`, and `graph` calls continue to work for the current Part 5 dataset.
- Existing generated artifacts are not deleted until a new validated build is ready to publish.

## Testing Strategy

Add focused tests for:

- two synthetic Part sources merged into one database
- all 14 catalog rows reported with correct missing/present states
- duplicate entity and edge de-duplication with preserved provenance
- cross-Part search expansion and Part filtering
- unresolved relationship and stale-index validation failures
- rollback after batch-build publication failure
- CLI help, normal output, and concise errors for new commands
- regression coverage for the existing 64 tests and subtests

Acceptance smoke tests will build a temporary Parts 1, 3, and 5 dataset, search `NodeId` and `ServerType`, verify results from more than one Part, then run `coverage` and `validate_kb`.

## Operational Notes

The repository will document that complete content coverage requires local source files for all Parts 1-14. The software can be fully capable before all sources are present, but the coverage report must remain the authoritative answer about which Parts are actually searchable.
