from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import sqlite3
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Any


DOC_NAME = "OPC-10000-5"
HEADING_RE = re.compile(r"^(\d+(?:\.\d+){0,5})\s+(.+?)\s*$")
ANNEX_RE = re.compile(r"^(Annex\s+[A-Z])\s+(.+?)\s*$")
TABLE_RE = re.compile(r"^Table\s+(\d+|[A-Z]\.\d+)\s+-\s+(.+?)\s*$")


@dataclass
class Chapter:
    id: str
    section: str
    title: str
    level: int
    parent: str | None
    path: list[str]
    start_line: int
    end_line: int = 0
    text: str = ""
    tables: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)


@dataclass
class Table:
    id: str
    number: str
    caption: str
    section: str | None
    table_kind: str
    target_entity: str | None
    start_line: int
    end_line: int
    raw_lines: list[str]
    columns: list[str] = field(default_factory=list)
    rows: list[dict[str, str]] = field(default_factory=list)
    attributes: dict[str, str] = field(default_factory=dict)
    conformance_units: list[str] = field(default_factory=list)


def build(root: Path, source: Path, rebuild: bool = False) -> dict[str, int]:
    root = root.resolve()
    source = source.resolve()
    source_dir = root / "source"
    kb_dir = root / "kb"
    indexes_dir = root / "indexes"
    tools_dir = root / "tools"
    exports_dir = root / "exports"
    for directory in (source_dir, kb_dir, indexes_dir, tools_dir, exports_dir):
        directory.mkdir(parents=True, exist_ok=True)

    target_source = source_dir / source.name
    if rebuild or not target_source.exists() or _sha256(source) != _sha256(target_source):
        shutil.copy2(source, target_source)

    text = source.read_text(encoding="utf-8")
    lines = text.splitlines()
    metadata = _metadata(text, source, target_source)
    (source_dir / "source_manifest.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    chapters = _parse_chapters(lines)
    tables = _parse_tables(lines, chapters)
    entities, relationships, aliases = _extract_entities_and_relationships(chapters, tables, target_source)
    chunks = _make_chunks(chapters, tables, entities)

    _write_jsonl(kb_dir / "chapters.jsonl", [c.__dict__ for c in chapters])
    _write_jsonl(kb_dir / "tables.jsonl", [t.__dict__ for t in tables])
    _write_jsonl(kb_dir / "entities.jsonl", entities)
    _write_jsonl(kb_dir / "relationships.jsonl", relationships)
    _write_jsonl(kb_dir / "chunks.jsonl", chunks)
    (kb_dir / "aliases.json").write_text(json.dumps(aliases, ensure_ascii=False, indent=2), encoding="utf-8")
    _build_fts(indexes_dir / "fts.sqlite", chapters, tables, entities, chunks)
    _write_readme(root, metadata, len(chapters), len(tables), len(entities), len(relationships))
    return {
        "chapters": len(chapters),
        "tables": len(tables),
        "entities": len(entities),
        "relationships": len(relationships),
        "chunks": len(chunks),
    }


def _metadata(text: str, source: Path, copied_source: Path) -> dict[str, Any]:
    version = _match_value(text, r"Version:\s*([^\n]+)") or ""
    published = _match_value(text, r"Published:\s*([^\n]+)") or ""
    return {
        "doc": DOC_NAME,
        "title": "OPC Unified Architecture - Part 5: Information Model",
        "version": version.strip(),
        "published": published.strip(),
        "source_path": str(source),
        "local_source_path": str(copied_source),
        "sha256": _sha256(source),
    }


def _parse_chapters(lines: list[str]) -> list[Chapter]:
    starts: list[tuple[int, str, str, int]] = []
    for i, line in enumerate(lines, start=1):
        heading = HEADING_RE.match(line)
        annex = ANNEX_RE.match(line)
        if heading:
            section, title = heading.groups()
            starts.append((i, section, title, section.count(".") + 1))
        elif annex:
            section, title = annex.groups()
            starts.append((i, section, title, 1))

    chapters: list[Chapter] = []
    section_to_chapter: dict[str, Chapter] = {}
    for idx, (start, section, title, level) in enumerate(starts):
        end = starts[idx + 1][0] - 1 if idx + 1 < len(starts) else len(lines)
        parent = _parent_section(section)
        path = []
        if parent and parent in section_to_chapter:
            path.extend(section_to_chapter[parent].path)
        path.append(f"{section} {title}")
        chapter = Chapter(
            id=f"sec-{section.replace(' ', '-')}",
            section=section,
            title=title,
            level=level,
            parent=f"sec-{parent.replace(' ', '-')}" if parent else None,
            path=path,
            start_line=start,
            end_line=end,
            text="\n".join(lines[start - 1 : end]),
        )
        chapters.append(chapter)
        section_to_chapter[section] = chapter
    return chapters


def _parse_tables(lines: list[str], chapters: list[Chapter]) -> list[Table]:
    starts = []
    for i, line in enumerate(lines, start=1):
        match = TABLE_RE.match(line)
        if match:
            starts.append((i, match.group(1), match.group(2).strip()))

    tables: list[Table] = []
    for idx, (start, number, caption) in enumerate(starts):
        next_table = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines) + 1
        next_heading = _next_heading_after(lines, start)
        end = min(next_table, next_heading) - 1
        raw_lines = [line for line in lines[start:end] if line.strip()]
        section = _chapter_for_line(chapters, start)
        table = Table(
            id=f"table-{number}",
            number=str(number),
            caption=caption,
            section=section.section if section else None,
            table_kind=_table_kind(caption, raw_lines),
            target_entity=None,
            start_line=start,
            end_line=end,
            raw_lines=raw_lines,
        )
        _parse_table_rows(table)
        tables.append(table)
        if section:
            section.tables.append(table.id)
    return tables


def _extract_entities_and_relationships(
    chapters: list[Chapter], tables: list[Table], source_file: Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, str]]:
    table_by_section: dict[str, list[Table]] = {}
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


def _parse_table_rows(table: Table) -> None:
    lines = table.raw_lines
    if not lines:
        return
    current_header: list[str] | None = None
    mode: str | None = None
    conformance = False
    for line in lines:
        if line.strip() == "Conformance Units":
            conformance = True
            mode = None
            current_header = None
            continue
        if conformance:
            if line.strip() and not TABLE_RE.match(line) and not HEADING_RE.match(line):
                table.conformance_units.append(line.strip())
            continue
        cells = _csv_cells(line)
        if _is_header(cells):
            current_header = _normalize_columns(cells)
            table.columns = current_header
            if len(current_header) == 2 and current_header[0].lower() in {"attribute", "attributes"}:
                mode = "attributes"
            else:
                mode = "rows"
            continue
        if mode == "attributes" and len(cells) >= 2:
            table.attributes[cells[0].strip()] = ",".join(cells[1:]).strip()
        elif mode == "rows" and current_header:
            row = _row_from_cells(current_header, cells)
            if any(v for v in row.values()):
                table.rows.append(row)
        elif line.startswith("Subtype of the "):
            table.rows.append({"References": line.strip()})


def _apply_table_to_entity(entity: dict[str, Any], table: Table, relationships: list[dict[str, Any]]) -> None:
    entity["attributes"].update(table.attributes)
    if "BrowseName" in table.attributes:
        entity["browse_name"] = table.attributes["BrowseName"]
    entity_id = entity["id"]
    for unit in table.conformance_units:
        relationships.append(_edge(entity_id, "HAS_CONFORMANCE_UNIT", f"ConformanceUnit:{unit}", table.section, table.id))

    for row in table.rows:
        first = row.get("References") or row.get("Name") or ""
        supertype = _supertype_from_text(first)
        if supertype:
            entity["supertype"] = supertype
            relationships.append(_edge(entity_id, "HAS_SUBTYPE", _typed_target(supertype, entity["kind"]), table.section, table.id))
            continue

        if "Reference" in table.table_kind or entity["kind"] == "ReferenceType":
            _apply_reference_type_row(entity, row, table, relationships)

        if _has_reference_row(row):
            item = {
                "reference_type": row.get("References", ""),
                "node_class": row.get("NodeClass", ""),
                "browse_name": row.get("BrowseName", ""),
                "data_type": row.get("DataType", ""),
                "type_definition": row.get("TypeDefinition", ""),
                "modelling_rule": row.get("ModellingRule", ""),
            }
            if item["browse_name"]:
                relation = _relation_for_ref(item["reference_type"])
                target_kind = item["node_class"] or "Node"
                target = f"{target_kind}:{entity['name']}.{item['browse_name']}"
                entity["components"].append(item)
                entity["references"].append(item)
                relationships.append(_edge(entity_id, relation, target, table.section, table.id, item))
                if item["data_type"] and item["data_type"] not in {"-", "--"}:
                    relationships.append(_edge(target, "USES_DATATYPE", f"DataType:{item['data_type']}", table.section, table.id))
                if item["type_definition"] and item["type_definition"] not in {"-", "--"}:
                    relationships.append(_edge(target, "HAS_TYPE_DEFINITION", _guess_type_definition(item["type_definition"]), table.section, table.id))
                if item["modelling_rule"]:
                    relationships.append(_edge(target, "HAS_MODELLING_RULE", f"ModellingRule:{item['modelling_rule']}", table.section, table.id))

        if _has_structure_field(row):
            field = {
                "name": row.get("Name", ""),
                "type": row.get("Type", ""),
                "description": row.get("Description", ""),
            }
            if field["name"] and field["name"] != entity["name"]:
                entity["fields"].append(field)
                relationships.append(_edge(entity_id, "HAS_FIELD", f"Field:{entity['name']}.{field['name']}", table.section, table.id, field))
                if field["type"]:
                    relationships.append(_edge(f"Field:{entity['name']}.{field['name']}", "USES_DATATYPE", f"DataType:{field['type']}", table.section, table.id))

        if _has_enum_value(row):
            value = {
                "name": row.get("Name", ""),
                "value": row.get("Value", ""),
                "description": row.get("Description", ""),
            }
            entity["enum_values"].append(value)


def _apply_reference_type_row(entity: dict[str, Any], row: dict[str, str], table: Table, relationships: list[dict[str, Any]]) -> None:
    text = row.get("References", "")
    supertype = _supertype_from_text(text)
    if supertype:
        entity["supertype"] = supertype
        relationships.append(_edge(entity["id"], "HAS_SUBTYPE", f"ReferenceType:{supertype}", table.section, table.id))


def _make_chunks(chapters: list[Chapter], tables: list[Table], entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    conn.execute(
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
    rows = []
    for entity in entities:
        rows.append(("entity", entity["id"], entity["name"], entity.get("section", ""), ",".join(entity.get("related_tables", [])), _entity_body(entity)))
    for chapter in chapters:
        rows.append(("chapter", chapter.id, chapter.title, chapter.section, ",".join(chapter.tables), chapter.text))
    for table in tables:
        rows.append(("table", table.id, table.caption, table.section or "", str(table.number), "\n".join(table.raw_lines)))
    for chunk in chunks:
        rows.append(("chunk", chunk["id"], " / ".join(chunk.get("heading_path", [])) or chunk["id"], chunk.get("section") or "", ",".join(chunk.get("table_ids", [])), chunk["text"]))
    conn.executemany("INSERT INTO search_fts(item_type,item_id,title,section,table_number,body) VALUES(?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()


def _write_readme(root: Path, metadata: dict[str, Any], chapters: int, tables: int, entities: int, relationships: int) -> None:
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
python tools/query_kb.py "ServerType 包含哪些组件？" --top-k 8
python tools/inspect_entity.py ServerType
python tools/trace_entity.py ServerType --relation HAS_COMPONENT --depth 1
```
"""
    (root / "README.md").write_text(readme, encoding="utf-8")


def _write_jsonl(path: Path, items: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _match_value(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text)
    return match.group(1) if match else None


def _parent_section(section: str) -> str | None:
    if section.startswith("Annex "):
        return None
    if "." not in section:
        return None
    return section.rsplit(".", 1)[0]


def _next_heading_after(lines: list[str], start: int) -> int:
    for i in range(start + 1, len(lines) + 1):
        line = lines[i - 1]
        if HEADING_RE.match(line) or ANNEX_RE.match(line):
            return i
    return len(lines) + 1


def _chapter_for_line(chapters: list[Chapter], line_no: int) -> Chapter | None:
    best = None
    for chapter in chapters:
        if chapter.start_line <= line_no <= chapter.end_line:
            if best is None or chapter.start_line > best.start_line:
                best = chapter
    return best


def _table_kind(caption: str, raw_lines: list[str]) -> str:
    low = caption.lower()
    if "referencetype" in low:
        return "reference_type"
    if "structure" in low:
        return "structure"
    if "values" in low:
        return "enum_values"
    if "definition" in low:
        return "definition"
    if "example" in low:
        return "example"
    first = raw_lines[1].lower() if len(raw_lines) > 1 else ""
    if first.startswith("name,type,description"):
        return "structure"
    if first.startswith("name,value,description"):
        return "enum_values"
    return "table"


def _csv_cells(line: str) -> list[str]:
    try:
        return [cell.strip() for cell in next(csv.reader(StringIO(line)))]
    except Exception:
        return [cell.strip() for cell in line.split(",")]


def _is_header(cells: list[str]) -> bool:
    if not cells:
        return False
    first = cells[0].strip().lower()
    return first in {"attribute", "attributes", "references", "name"} and len(cells) >= 2


def _normalize_columns(cells: list[str]) -> list[str]:
    normalized = []
    for cell in cells:
        value = re.sub(r"\s+", " ", cell).strip()
        value = value.replace("DataType / TypeDefinition", "DataTypeAndTypeDefinition")
        value = value.replace("DataType /", "DataType")
        value = value.replace("Modelling Rule", "ModellingRule")
        value = value.replace("Modelling                                           Rule", "ModellingRule")
        normalized.append(value)
    if "DataTypeAndTypeDefinition" in normalized:
        normalized = ["DataType" if c == "DataTypeAndTypeDefinition" else c for c in normalized]
        if "TypeDefinition" not in normalized:
            idx = normalized.index("DataType")
            normalized.insert(idx + 1, "TypeDefinition")
    return normalized


def _row_from_cells(header: list[str], cells: list[str]) -> dict[str, str]:
    if "DataType" in header and "TypeDefinition" in header and len(cells) == len(header) - 1:
        idx = header.index("DataType")
        source = cells[idx] if idx < len(cells) else ""
        data_type, type_def = _split_datatype_type_definition(source)
        cells = cells[:idx] + [data_type, type_def] + cells[idx + 1 :]
    padded = cells + [""] * max(0, len(header) - len(cells))
    return {header[i]: padded[i].strip() for i in range(len(header))}


def _split_datatype_type_definition(value: str) -> tuple[str, str]:
    value = value.strip()
    if not value:
        return "", ""
    if value.startswith("Defined in"):
        return value, ""
    parts = value.rsplit(" ", 1)
    if len(parts) == 2 and (parts[1].endswith("Type") or parts[1] == "PropertyType"):
        return parts[0].strip(), parts[1].strip()
    return value, ""


def _entity_kind(section: str, title: str) -> str | None:
    if section.startswith("6.4.") and section.count(".") >= 2 and title.endswith("Type"):
        return "EventType"
    if section.startswith("6.") and section.count(".") >= 1 and title.endswith(("Type", "definition", "Definition")):
        return "ObjectType"
    if section.startswith("7.") and section.count(".") >= 1 and title.endswith("Type"):
        return "VariableType"
    if section.startswith("8.4.") and section.count(".") >= 2:
        return "ModellingRule"
    if section.startswith("8.") and section.count(".") >= 1:
        return "Object"
    if section.startswith("9.") and section.count(".") >= 1:
        return "Method"
    if section.startswith("11.") and section.count(".") >= 1:
        return "ReferenceType"
    if section.startswith("12.") and section.count(".") >= 1:
        return "DataType"
    return None


def _entity_name(title: str) -> str:
    name = re.sub(r"\s+[Dd]efinition$", "", title.strip())
    name = re.sub(r"\s+[Rr]eferenceType$", "", name)
    return name.strip()


def _looks_like_entity_name(name: str, kind: str) -> bool:
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
    table_text = f"，关联表格 {', '.join(t.id.replace('table-', 'Table ') for t in tables)}" if tables else ""
    return f"{name} 是 OPC UA 10000-5 信息模型中的 {kind} 实体，定义位置为第 {section} 节{table_text}。"


def _summary_en(text: str, name: str, kind: str) -> str:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    for paragraph in paragraphs[1:]:
        if name in paragraph and not paragraph.startswith("Table "):
            return paragraph[:800]
    return f"{name} is a {kind} entity defined by OPC UA 10000-5."


def _supertype_from_text(text: str) -> str | None:
    match = re.search(r"Subtype of the\s+([A-Za-z0-9]+)\s+(?:defined|DataType|ReferenceType|ObjectType|VariableType)?", text)
    return match.group(1) if match else None


def _has_reference_row(row: dict[str, str]) -> bool:
    return bool(row.get("References") and row.get("NodeClass") and row.get("BrowseName"))


def _has_structure_field(row: dict[str, str]) -> bool:
    return bool(row.get("Name") and row.get("Type") and "Description" in row and not row.get("Value"))


def _has_enum_value(row: dict[str, str]) -> bool:
    return bool(row.get("Name") and row.get("Value") and "Description" in row)


def _relation_for_ref(ref: str) -> str:
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
    return {
        "source": source,
        "relation": relation,
        "target": target,
        "properties": properties or {},
        "source_ref": {"section": section, "table": table},
    }


def _aliases_for(entity: dict[str, Any]) -> list[str]:
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the OPC UA 10000-5 structured knowledge base.")
    parser.add_argument("--source", default=r"C:\Users\admin\Downloads\OPC-10000-5-v1.05.06.md")
    parser.add_argument("--root", default=".")
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()
    stats = build(Path(args.root), Path(args.source), rebuild=args.rebuild)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
