"""Parser helpers for OPC UA specification chapters and tables."""

from __future__ import annotations

import csv
import re
from io import StringIO

try:
    from .builder_models import Chapter, Table
except ImportError:
    if __package__:
        raise
    from builder_models import Chapter, Table

HEADING_RE = re.compile(r"^(\d+(?:\.\d+){0,5})\s+(.+?)\s*$")
ANNEX_RE = re.compile(r"^(Annex\s+[A-Z])\s+(.+?)\s*$")
TABLE_RE = re.compile(r"^Table\s+(\d+|[A-Z]\.\d+)\s+-\s+(.+?)\s*$")


def parse_chapters(lines: list[str]) -> list[Chapter]:
    """Parse numbered headings and annexes into a nested chapter sequence."""

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


def parse_tables(lines: list[str], chapters: list[Chapter]) -> list[Table]:
    """Parse table ranges, associate them with chapters, and normalize their rows."""

    starts = []
    for i, line in enumerate(lines, start=1):
        match = TABLE_RE.match(line)
        if match:
            starts.append((i, match.group(1), match.group(2).strip()))

    tables: list[Table] = []
    for idx, (start, number, caption) in enumerate(starts):
        next_table = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines) + 1
        next_heading = _next_heading_after(lines, start)
        # A table ends at whichever boundary appears first: another table or heading.
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


def _parse_table_rows(table: Table) -> None:
    """Interpret a table's raw lines with a small attributes/rows state machine."""

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
            # Everything after this marker is descriptive conformance-unit evidence,
            # not another CSV row in the table schema.
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
    """Classify a table using its caption first and header shape second."""

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
    """Parse one source CSV line with a conservative malformed-row fallback."""

    try:
        return [cell.strip() for cell in next(csv.reader(StringIO(line)))]
    except (csv.Error, StopIteration):
        # Preserve recoverability for malformed source rows without hiding code errors.
        return [cell.strip() for cell in line.split(",")]


def _is_header(cells: list[str]) -> bool:
    if not cells:
        return False
    first = cells[0].strip().lower()
    return first in {"attribute", "attributes", "references", "name"} and len(cells) >= 2


def _normalize_columns(cells: list[str]) -> list[str]:
    """Map source header spelling variants to stable knowledge-base field names."""

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
    """Align cells to a normalized header, merging overflow into the last column."""

    if "DataType" in header and "TypeDefinition" in header and len(cells) == len(header) - 1:
        idx = header.index("DataType")
        source = cells[idx] if idx < len(cells) else ""
        data_type, type_def = _split_datatype_type_definition(source)
        cells = cells[:idx] + [data_type, type_def] + cells[idx + 1 :]
    padded = cells + [""] * max(0, len(header) - len(cells))
    return {header[i]: padded[i].strip() for i in range(len(header))}


def _split_datatype_type_definition(value: str) -> tuple[str, str]:
    """Split the specification's combined DataType/TypeDefinition notation."""

    value = value.strip()
    if not value:
        return "", ""
    if value.startswith("Defined in"):
        return value, ""
    parts = value.rsplit(" ", 1)
    if len(parts) == 2 and (parts[1].endswith("Type") or parts[1] == "PropertyType"):
        return parts[0].strip(), parts[1].strip()
    return value, ""
