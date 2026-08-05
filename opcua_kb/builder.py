"""Build structured JSONL records and an FTS5 index from the OPC UA Markdown."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

try:
    from .builder_models import Chapter, Table
    from .builder_parse import parse_chapters, parse_tables
except ImportError:
    if __package__:
        raise
    from builder_models import Chapter, Table
    from builder_parse import parse_chapters, parse_tables

DOC_NAME = "OPC-10000-5"


class _PublicationRollbackError(OSError):
    """Signal that generated-artifact backups were retained for recovery."""


def build(root: Path, source: Path, rebuild: bool = False) -> dict[str, int]:
    """Run the complete source-copy, parse, export, and index pipeline."""

    root = root.resolve()
    source = source.resolve()
    if source.name.casefold() == "source_manifest.json":
        raise ValueError("Source filename source_manifest.json is reserved for the generated source manifest")
    target_source = root / "source" / source.name
    source_hash = _read_source_hash(source)
    text = _read_source_text(source)
    lines = text.splitlines()
    metadata = _metadata(text, source, target_source, source_hash)

    # Later stages enrich earlier records in place: tables attach to chapters and
    # entity extraction attaches entity IDs back to both chapters and tables.
    chapters = parse_chapters(lines)
    tables = parse_tables(lines, chapters)
    entities, relationships, aliases = _extract_entities_and_relationships(chapters, tables, target_source)
    chunks = _make_chunks(chapters, tables, entities)

    _preflight_generated_targets(root, source)
    source_needs_copy = rebuild or not target_source.exists() or source_hash != _read_source_hash(target_source)
    _make_directory(root.parent)
    for directory in (root / "tools", root / "exports"):
        _make_directory(directory)
    stage_root = Path(tempfile.mkdtemp(prefix=f".{root.name}.build-", dir=root.parent))
    retain_stage_root = False
    try:
        source_dir = stage_root / "source"
        kb_dir = stage_root / "kb"
        indexes_dir = stage_root / "indexes"
        for directory in (source_dir, kb_dir, indexes_dir):
            _make_directory(directory)

        _copy_source(source if source_needs_copy else target_source, source_dir / source.name)
        _write_text(source_dir / "source_manifest.json", json.dumps(metadata, ensure_ascii=False, indent=2), "write source manifest")
        _write_jsonl(kb_dir / "chapters.jsonl", [c.__dict__ for c in chapters])
        _write_jsonl(kb_dir / "tables.jsonl", [t.__dict__ for t in tables])
        _write_jsonl(kb_dir / "entities.jsonl", entities)
        _write_jsonl(kb_dir / "relationships.jsonl", relationships)
        _write_jsonl(kb_dir / "chunks.jsonl", chunks)
        _write_text(kb_dir / "aliases.json", json.dumps(aliases, ensure_ascii=False, indent=2), "write aliases artifact")
        _build_fts(indexes_dir / "fts.sqlite", chapters, tables, entities, chunks)
        _write_readme(stage_root, metadata, len(chapters), len(tables), len(entities), len(relationships))
        _publish_generated_artifacts(stage_root, root, source.name, include_source=source_needs_copy)
    except _PublicationRollbackError:
        retain_stage_root = True
        raise
    finally:
        if not retain_stage_root:
            shutil.rmtree(stage_root, ignore_errors=True)
    return {
        "chapters": len(chapters),
        "tables": len(tables),
        "entities": len(entities),
        "relationships": len(relationships),
        "chunks": len(chunks),
    }


def _generated_artifact_paths(source_name: str, include_source: bool = True) -> tuple[Path, ...]:
    """Return the artifact paths owned by the builder publication transaction."""

    artifacts = (
        Path("source") / "source_manifest.json",
        Path("kb") / "chapters.jsonl",
        Path("kb") / "tables.jsonl",
        Path("kb") / "entities.jsonl",
        Path("kb") / "relationships.jsonl",
        Path("kb") / "chunks.jsonl",
        Path("kb") / "aliases.json",
        Path("indexes") / "fts.sqlite",
        Path("README.md"),
    )
    return ((Path("source") / source_name,) if include_source else ()) + artifacts


def _preflight_generated_targets(root: Path, source: Path) -> None:
    """Preserve write error contracts for destinations that are directories."""

    actions = {
        Path("source") / source.name: "copy source",
        Path("source") / "source_manifest.json": "write source manifest",
        Path("kb") / "chapters.jsonl": "write JSONL",
        Path("kb") / "tables.jsonl": "write JSONL",
        Path("kb") / "entities.jsonl": "write JSONL",
        Path("kb") / "relationships.jsonl": "write JSONL",
        Path("kb") / "chunks.jsonl": "write JSONL",
        Path("kb") / "aliases.json": "write aliases artifact",
        Path("indexes") / "fts.sqlite": "prepare FTS index",
        Path("README.md"): "write README",
    }
    for relative_path, action in actions.items():
        target = root / relative_path
        if target.is_dir():
            error = IsADirectoryError(f"{target} is a directory")
            if relative_path == Path("source") / source.name:
                raise OSError(f"Unable to {action} from {source} to {target}") from error
            raise OSError(f"Unable to {action} at {target}") from error


def _publish_generated_artifacts(stage_root: Path, root: Path, source_name: str, include_source: bool = True) -> None:
    """Replace generated files with a rollback-capable same-filesystem transaction."""

    artifacts = _generated_artifact_paths(source_name, include_source)
    backup_root = stage_root / ".backup"
    published: list[Path] = []
    backed_up: list[Path] = []
    try:
        for relative_path in artifacts:
            destination = root / relative_path
            staged = stage_root / relative_path
            _make_directory(destination.parent)
            if destination.exists():
                backup = backup_root / relative_path
                _make_directory(backup.parent)
                destination.replace(backup)
                backed_up.append(relative_path)
            staged.replace(destination)
            published.append(relative_path)
    except OSError as publish_error:
        rollback_errors: list[str] = []
        for relative_path in reversed(published):
            destination = root / relative_path
            try:
                if destination.exists():
                    destination.unlink()
            except OSError as rollback_error:
                rollback_errors.append(f"unable to remove published target {destination}: {rollback_error}")
        for relative_path in reversed(backed_up):
            backup = backup_root / relative_path
            try:
                if backup.exists():
                    backup.replace(root / relative_path)
            except OSError as rollback_error:
                rollback_errors.append(f"unable to restore backup {backup} to {root / relative_path}: {rollback_error}")
        if rollback_errors:
            recovery_locations = [str(stage_root)]
            if backup_root.exists():
                recovery_locations.append(str(backup_root))
            detail = "; ".join(rollback_errors)
            raise _PublicationRollbackError(
                f"Unable to roll back generated artifacts; recoverable publication state remains at "
                f"{', '.join(recovery_locations)}: {detail}"
            ) from publish_error
        raise


def _metadata(text: str, source: Path, copied_source: Path, source_hash: str) -> dict[str, Any]:
    """Capture source provenance and version metadata for reproducible builds."""

    version = _match_value(text, r"Version:\s*([^\n]+)") or ""
    published = _match_value(text, r"Published:\s*([^\n]+)") or ""
    return {
        "doc": DOC_NAME,
        "title": "OPC Unified Architecture - Part 5: Information Model",
        "version": version.strip(),
        "published": published.strip(),
        "source_path": str(source),
        "local_source_path": str(copied_source),
        "sha256": source_hash,
    }


def _extract_entities_and_relationships(
    chapters: list[Chapter], tables: list[Table], source_file: Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, str]]:
    """Derive canonical entities, graph edges, and lookup aliases from sections."""

    table_by_section: dict[str, list[Table]] = {}
    # Table rows contain the detailed components, fields, and enum values that enrich
    # the top-level entities discovered from chapter headings.
    for table in tables:
        if table.section:
            table_by_section.setdefault(table.section, []).append(table)

    entities_by_id: dict[str, dict[str, Any]] = {}
    relationships: list[dict[str, Any]] = []

    for chapter in chapters:
        kind = _entity_kind(chapter.section, chapter.title)
        if not kind:
            continue
        name = _entity_name(chapter.title)
        if not _looks_like_entity_name(name, kind):
            continue
        entity_id = f"{kind}:{name}"
        related_tables = table_by_section.get(chapter.section, [])
        entity = {
            "id": entity_id,
            "name": name,
            "kind": kind,
            "section": chapter.section,
            "title": chapter.title,
            "browse_name": name,
            "node_id": None,
            "supertype": None,
            "attributes": {},
            "components": [],
            "fields": [],
            "enum_values": [],
            "references": [],
            "related_tables": [t.id for t in related_tables],
            "summary_zh": _summary_zh(name, kind, chapter.section, related_tables),
            "summary_en": _summary_en(chapter.text, name, kind),
            "source_ref": {
                "file": str(source_file),
                "section": chapter.section,
                "start_line": chapter.start_line,
                "end_line": chapter.end_line,
            },
        }
        entities_by_id[entity_id] = entity
        chapter.entities.append(entity_id)
        relationships.append(_edge(entity_id, "DEFINED_IN_SECTION", chapter.id, chapter.section, None))
        for table in related_tables:
            table.target_entity = entity_id
            relationships.append(_edge(entity_id, "DEFINED_BY_TABLE", table.id, chapter.section, table.id))

    for table in tables:
        if not table.target_entity or table.target_entity not in entities_by_id:
            continue
        entity = entities_by_id[table.target_entity]
        _apply_table_to_entity(entity, table, relationships)

    aliases: dict[str, str] = {}
    for entity in entities_by_id.values():
        for alias in _aliases_for(entity):
            aliases[_norm(alias)] = entity["id"]
    return list(entities_by_id.values()), relationships, aliases


def _apply_table_to_entity(entity: dict[str, Any], table: Table, relationships: list[dict[str, Any]]) -> None:
    """Merge one normalized table into an entity and emit its graph edges."""

    _apply_table_attributes(entity, table)
    _add_conformance_unit_edges(entity, table, relationships)

    for row in table.rows:
        if _apply_supertype_row(entity, row, table, relationships):
            continue
        if "Reference" in table.table_kind or entity["kind"] == "ReferenceType":
            _apply_reference_type_row(entity, row, table, relationships)
        _append_reference_component(entity, row, table, relationships)
        _append_structure_field(entity, row, table, relationships)
        _append_enum_value(entity, row)


def _apply_table_attributes(entity: dict[str, Any], table: Table) -> None:
    """Merge table attributes into an entity and promote its browse name."""

    entity["attributes"].update(table.attributes)
    if "BrowseName" in table.attributes:
        entity["browse_name"] = table.attributes["BrowseName"]


def _add_conformance_unit_edges(
    entity: dict[str, Any], table: Table, relationships: list[dict[str, Any]]
) -> None:
    """Attach the table's conformance-unit evidence to its owning entity."""

    for unit in table.conformance_units:
        relationships.append(
            _edge(
                entity["id"],
                "HAS_CONFORMANCE_UNIT",
                f"ConformanceUnit:{unit}",
                table.section,
                table.id,
            )
        )


def _apply_supertype_row(
    entity: dict[str, Any], row: dict[str, str], table: Table, relationships: list[dict[str, Any]]
) -> bool:
    """Apply a general supertype declaration and signal that the row is complete."""

    first = row.get("References") or row.get("Name") or ""
    supertype = _supertype_from_text(first)
    if not supertype:
        return False
    entity["supertype"] = supertype
    relationships.append(
        _edge(
            entity["id"],
            "HAS_SUBTYPE",
            _typed_target(supertype, entity["kind"]),
            table.section,
            table.id,
        )
    )
    return True


def _append_reference_component(
    entity: dict[str, Any], row: dict[str, str], table: Table, relationships: list[dict[str, Any]]
) -> None:
    """Add an instance declaration and all of its typed relationship evidence."""

    if not _has_reference_row(row):
        return
    item = {
        "reference_type": row.get("References", ""),
        "node_class": row.get("NodeClass", ""),
        "browse_name": row.get("BrowseName", ""),
        "data_type": row.get("DataType", ""),
        "type_definition": row.get("TypeDefinition", ""),
        "modelling_rule": row.get("ModellingRule", ""),
    }
    if not item["browse_name"]:
        return
    relation = _relation_for_ref(item["reference_type"])
    target_kind = item["node_class"] or "Node"
    target = f"{target_kind}:{entity['name']}.{item['browse_name']}"
    entity["components"].append(item)
    entity["references"].append(item)
    relationships.append(
        _edge(entity["id"], relation, target, table.section, table.id, item)
    )
    if item["data_type"] and item["data_type"] not in {"-", "--"}:
        relationships.append(
            _edge(
                target,
                "USES_DATATYPE",
                f"DataType:{item['data_type']}",
                table.section,
                table.id,
            )
        )
    if item["type_definition"] and item["type_definition"] not in {"-", "--"}:
        relationships.append(
            _edge(
                target,
                "HAS_TYPE_DEFINITION",
                _guess_type_definition(item["type_definition"]),
                table.section,
                table.id,
            )
        )
    if item["modelling_rule"]:
        relationships.append(
            _edge(
                target,
                "HAS_MODELLING_RULE",
                f"ModellingRule:{item['modelling_rule']}",
                table.section,
                table.id,
            )
        )


def _append_structure_field(
    entity: dict[str, Any], row: dict[str, str], table: Table, relationships: list[dict[str, Any]]
) -> None:
    """Add a structured DataType field and its optional DataType edge."""

    if not _has_structure_field(row):
        return
    field = {
        "name": row.get("Name", ""),
        "type": row.get("Type", ""),
        "description": row.get("Description", ""),
    }
    if not field["name"] or field["name"] == entity["name"]:
        return
    field_id = f"Field:{entity['name']}.{field['name']}"
    entity["fields"].append(field)
    relationships.append(
        _edge(entity["id"], "HAS_FIELD", field_id, table.section, table.id, field)
    )
    if field["type"]:
        relationships.append(
            _edge(
                field_id,
                "USES_DATATYPE",
                f"DataType:{field['type']}",
                table.section,
                table.id,
            )
        )


def _append_enum_value(entity: dict[str, Any], row: dict[str, str]) -> None:
    """Add one enumeration value when a row matches the enum table shape."""

    if not _has_enum_value(row):
        return
    entity["enum_values"].append(
        {
            "name": row.get("Name", ""),
            "value": row.get("Value", ""),
            "description": row.get("Description", ""),
        }
    )


def _apply_reference_type_row(entity: dict[str, Any], row: dict[str, str], table: Table, relationships: list[dict[str, Any]]) -> None:
    """Extract ReferenceType inheritance expressed inside a reference table row."""

    text = row.get("References", "")
    supertype = _supertype_from_text(text)
    if supertype:
        entity["supertype"] = supertype
        relationships.append(_edge(entity["id"], "HAS_SUBTYPE", f"ReferenceType:{supertype}", table.section, table.id))


def _make_chunks(chapters: list[Chapter], tables: list[Table], entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Create bounded retrieval chunks while preserving entity and table links."""

    entity_by_section: dict[str, list[str]] = {}
    for entity in entities:
        entity_by_section.setdefault(entity["section"], []).append(entity["id"])
    chunks: list[dict[str, Any]] = []
    for chapter in chapters:
        text = chapter.text.strip()
        if text:
            chunks.append(
                {
                    "id": f"chunk-{chapter.id}-001",
                    "doc": DOC_NAME,
                    "version": "1.05.06",
                    "section": chapter.section,
                    "heading_path": chapter.path,
                    "chunk_type": "section_text",
                    "text": text[:6000],
                    "entity_ids": entity_by_section.get(chapter.section, []),
                    "table_ids": chapter.tables,
                    "keywords": _keywords(chapter.title, text),
                }
            )
    for table in tables:
        chunks.append(
            {
                "id": f"chunk-{table.id}",
                "doc": DOC_NAME,
                "version": "1.05.06",
                "section": table.section,
                "heading_path": [],
                "chunk_type": "table",
                "text": "\n".join(table.raw_lines),
                "entity_ids": [table.target_entity] if table.target_entity else [],
                "table_ids": [table.id],
                "keywords": _keywords(table.caption, "\n".join(table.raw_lines)),
            }
        )
    return chunks


def _build_fts(path: Path, chapters: list[Chapter], tables: list[Table], entities: list[dict[str, Any]], chunks: list[dict[str, Any]]) -> None:
    """Rebuild the SQLite FTS5 index from all searchable record types."""

    # The index is derived data; replacing it atomically at build granularity avoids
    # stale rows when source records disappear between builds.
    _prepare_fts_path(path)
    conn = _connect_fts(path)
    try:
        _create_fts_schema(conn, path)
        rows = []
        for entity in entities:
            rows.append(("entity", entity["id"], entity["name"], entity.get("section", ""), ",".join(entity.get("related_tables", [])), _entity_body(entity)))
        for chapter in chapters:
            rows.append(("chapter", chapter.id, chapter.title, chapter.section, ",".join(chapter.tables), chapter.text))
        for table in tables:
            rows.append(("table", table.id, table.caption, table.section or "", str(table.number), "\n".join(table.raw_lines)))
        for chunk in chunks:
            rows.append(("chunk", chunk["id"], " / ".join(chunk.get("heading_path", [])) or chunk["id"], chunk.get("section") or "", ",".join(chunk.get("table_ids", [])), chunk["text"]))
        _write_fts_rows(conn, path, rows)
    finally:
        conn.close()


def _prepare_fts_path(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except OSError as exc:
        raise OSError(f"Unable to prepare FTS index at {path}") from exc


def _connect_fts(path: Path) -> sqlite3.Connection:
    try:
        return sqlite3.connect(path)
    except (OSError, sqlite3.Error) as exc:
        raise OSError(f"Unable to open FTS index at {path}") from exc


def _create_fts_schema(connection: sqlite3.Connection, path: Path) -> None:
    try:
        connection.execute(
            """
            CREATE VIRTUAL TABLE search_fts USING fts5(
                item_type,
                item_id,
                title,
                section,
                table_number,
                body
            )
            """
        )
    except (OSError, sqlite3.Error) as exc:
        raise OSError(f"Unable to set up FTS index at {path}") from exc


def _write_fts_rows(connection: sqlite3.Connection, path: Path, rows: list[tuple[Any, ...]]) -> None:
    try:
        connection.executemany("INSERT INTO search_fts(item_type,item_id,title,section,table_number,body) VALUES(?,?,?,?,?,?)", rows)
        connection.commit()
    except (OSError, sqlite3.Error) as exc:
        raise OSError(f"Unable to write FTS index at {path}") from exc


def _write_readme(root: Path, metadata: dict[str, Any], chapters: int, tables: int, entities: int, relationships: int) -> None:
    """Regenerate the project README with source metadata and usage examples."""

    readme = f"""# OPC UA 10000-5 结构化实体知识库

数据源：`{metadata['source_path']}`

版本：{metadata['version']}

发布时间：{metadata['published']}

## 统计

- Chapters: {chapters}
- Tables: {tables}
- Entities: {entities}
- Relationships: {relationships}

## 常用命令

```powershell
python help.py
python tools/help.py
python tools/query_kb.py "ServerType 包含哪些组件？" --top-k 8
python tools/inspect_entity.py ServerType
python tools/trace_entity.py ServerType --relation HAS_COMPONENT --depth 1
python tools/demo_graph.py
python tools/graph_kb.py --format html --output exports/knowledge_graph.html
```

## Help / 帮助菜单

运行统一帮助菜单查看所有可用功能、示例命令、Python API 和关系过滤器：

```powershell
python help.py
python tools/help.py
```

每个 CLI 也支持 `--help`：

```powershell
python tools/build_kb.py --help
python tools/query_kb.py --help
python tools/inspect_entity.py --help
python tools/trace_entity.py --help
python tools/demo_graph.py --help
python tools/graph_kb.py --help
```

## 功能概览

- 构建知识库：从 OPC UA 10000-5 Markdown 源文件生成结构化 JSONL 和 FTS5 索引。
- 查询知识库：支持实体名、自然语言、章节号、表格号检索。
- 查看实体：输出实体卡片，包括章节、表格、属性、组件、字段、枚举值和中英摘要。
- 追踪关系：按 `HAS_COMPONENT`、`HAS_PROPERTY`、`USES_DATATYPE` 等关系过滤实体图。
- 设计知识图谱：生成 JSON 或离线 HTML，显示实体之间的关系类型和关联度权重。
- Python API：通过 `from opcua_kb import KnowledgeBase` 在本地脚本中调用。

## 知识图谱

生成全局知识图谱：

```powershell
python tools/demo_graph.py
python tools/graph_kb.py --format html --output exports/knowledge_graph.html
python tools/graph_kb.py --format json --output exports/knowledge_graph.json
```

围绕某个实体生成局部图谱：

```powershell
python tools/graph_kb.py --focus ServerType --depth 2 --format html --output exports/server_type_graph.html
```

只查看指定关系：

```powershell
python tools/graph_kb.py --relation HAS_COMPONENT,USES_DATATYPE --min-weight 3 --format json
```

图谱中的节点代表实体，边代表实体之间的关系。边的 `weight` 是聚合后的关联度，数值越大表示两个实体之间通过更多或更强的关系连接。
"""
    _write_text(root / "README.md", readme, "write README")


def _write_jsonl(path: Path, items: list[dict[str, Any]]) -> None:
    try:
        with path.open("w", encoding="utf-8", newline="\n") as f:
            for item in items:
                line = json.dumps(item, ensure_ascii=False, sort_keys=True)
                f.write(line + "\n")
    except OSError as exc:
        raise OSError(f"Unable to write JSONL artifact at {path}") from exc


def _make_directory(path: Path) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OSError(f"Unable to create build directory at {path}") from exc


def _read_source_hash(path: Path) -> str:
    try:
        return _sha256(path)
    except OSError as exc:
        raise OSError(f"Unable to read source file at {path}") from exc


def _read_source_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise OSError(f"Unable to read source file at {path}") from exc
    except UnicodeDecodeError as exc:
        raise ValueError(f"Unable to read source file at {path}") from exc


def _copy_source(source: Path, target: Path) -> None:
    try:
        shutil.copy2(source, target)
    except OSError as exc:
        raise OSError(f"Unable to copy source file from {source} to {target}") from exc


def _write_text(path: Path, content: str, operation: str) -> None:
    try:
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise OSError(f"Unable to {operation} at {path}") from exc


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _match_value(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text)
    return match.group(1) if match else None


def _entity_kind(section: str, title: str) -> str | None:
    """Infer an OPC UA entity kind from its section family and heading text."""

    section_depth = section.count(".")
    title_rules = (
        ("6.4.", 2, "EventType", title.endswith("Type")),
        ("6.", 1, "ObjectType", title.endswith(("Type", "definition", "Definition"))),
        ("7.", 1, "VariableType", title.endswith("Type")),
        ("8.4.", 2, "ModellingRule", True),
        ("8.", 1, "Object", True),
        ("9.", 1, "Method", True),
        ("11.", 1, "ReferenceType", True),
        ("12.", 1, "DataType", True),
    )
    for prefix, minimum_depth, kind, title_matches in title_rules:
        if section.startswith(prefix) and section_depth >= minimum_depth and title_matches:
            return kind
    return None


def _entity_name(title: str) -> str:
    name = re.sub(r"\s+[Dd]efinition$", "", title.strip())
    name = re.sub(r"\s+[Rr]eferenceType$", "", name)
    return name.strip()


def _looks_like_entity_name(name: str, kind: str) -> bool:
    """Reject generic headings that match a section family but are not entities."""

    if not name or name.lower() in {"general", "overview"}:
        return False
    if kind in {"ObjectType", "VariableType", "EventType"}:
        return name.endswith("Type")
    if kind == "ReferenceType":
        return bool(re.match(r"^[A-Z][A-Za-z0-9]+$", name))
    if kind == "DataType":
        return bool(re.match(r"^[A-Z0-9][A-Za-z0-9]*$", name))
    return True


def _summary_zh(name: str, kind: str, section: str, tables: list[Table]) -> str:
    """Generate the deterministic Chinese summary stored with each entity."""

    table_text = f"，关联表格 {', '.join(t.id.replace('table-', 'Table ') for t in tables)}" if tables else ""
    return f"{name} 是 OPC UA 10000-5 信息模型中的 {kind} 实体，定义位置为第 {section} 节{table_text}。"


def _summary_en(text: str, name: str, kind: str) -> str:
    """Choose the first useful source paragraph or a deterministic fallback."""

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    for paragraph in paragraphs[1:]:
        if name in paragraph and not paragraph.startswith("Table "):
            return paragraph[:800]
    return f"{name} is a {kind} entity defined by OPC UA 10000-5."


def _supertype_from_text(text: str) -> str | None:
    """Extract the common ``Subtype of`` notation used in definition tables."""

    match = re.search(r"Subtype of the\s+([A-Za-z0-9]+)\s+(?:defined|DataType|ReferenceType|ObjectType|VariableType)?", text)
    return match.group(1) if match else None


def _has_reference_row(row: dict[str, str]) -> bool:
    return bool(row.get("References") and row.get("NodeClass") and row.get("BrowseName"))


def _has_structure_field(row: dict[str, str]) -> bool:
    return bool(row.get("Name") and row.get("Type") and "Description" in row and not row.get("Value"))


def _has_enum_value(row: dict[str, str]) -> bool:
    return bool(row.get("Name") and row.get("Value") and "Description" in row)


def _relation_for_ref(ref: str) -> str:
    """Map OPC UA ReferenceType names to normalized relationship constants."""

    mapping = {
        "HasComponent": "HAS_COMPONENT",
        "HasProperty": "HAS_PROPERTY",
        "HasTypeDefinition": "HAS_TYPE_DEFINITION",
        "HasModellingRule": "HAS_MODELLING_RULE",
        "HasSubtype": "HAS_SUBTYPE",
    }
    return mapping.get(ref, ref.upper() if ref else "REFERENCES")


def _typed_target(name: str, source_kind: str) -> str:
    if source_kind == "EventType":
        return f"EventType:{name}"
    return f"{source_kind}:{name}"


def _guess_type_definition(value: str) -> str:
    """Attach the most likely entity-kind prefix to a type definition name."""

    if value.endswith("Type"):
        if value in {"PropertyType", "BaseDataVariableType", "BaseVariableType"}:
            return f"VariableType:{value}"
        return f"ObjectType:{value}"
    return value


def _edge(
    source: str,
    relation: str,
    target: str,
    section: str | None,
    table: str | None,
    properties: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create one relationship record with source evidence and optional properties."""

    return {
        "source": source,
        "relation": relation,
        "target": target,
        "properties": properties or {},
        "source_ref": {"section": section, "table": table},
    }


def _aliases_for(entity: dict[str, Any]) -> list[str]:
    """Return canonical and suffix-stripped names accepted by entity lookup."""

    name = entity["name"]
    aliases = [name, entity["id"], entity.get("browse_name", "")]
    if name.endswith("Type"):
        aliases.append(name[:-4])
    if name.endswith("DataType"):
        aliases.append(name[:-8])
    return [a for a in aliases if a]


def _norm(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def _keywords(title: str, text: str) -> list[str]:
    words = re.findall(r"[A-Z][A-Za-z0-9]{2,}", title + "\n" + text)
    return sorted(set(words), key=str.lower)[:30]


def _entity_body(entity: dict[str, Any]) -> str:
    """Flatten structured entity fields into text consumed by the FTS index."""

    parts = [
        entity.get("name", ""),
        entity.get("kind", ""),
        entity.get("summary_zh", ""),
        entity.get("summary_en", ""),
        json.dumps(entity.get("attributes", {}), ensure_ascii=False),
        json.dumps(entity.get("components", []), ensure_ascii=False),
        json.dumps(entity.get("fields", []), ensure_ascii=False),
    ]
    return "\n".join(parts)


def create_parser() -> argparse.ArgumentParser:
    """Create the shared argument parser for builder command entry points."""

    parser = argparse.ArgumentParser(description="Build the OPC UA 10000-5 structured knowledge base.")
    parser.add_argument("--source", default=r"C:\Users\admin\Downloads\OPC-10000-5-v1.05.06.md")
    parser.add_argument("--root", default=".")
    parser.add_argument("--rebuild", action="store_true")
    return parser


def run_build(args: argparse.Namespace) -> None:
    """Build from parsed CLI arguments and print generated artifact counts."""

    stats = build(Path(args.root), Path(args.source), rebuild=args.rebuild)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


def main() -> None:
    """Parse builder CLI arguments and print counts for the generated artifacts."""

    args = create_parser().parse_args()
    try:
        from .cli import run_cli
    except ImportError:
        if __package__:
            raise
        from cli import run_cli

    run_cli(lambda: run_build(args))


if __name__ == "__main__":
    main()
