#!/usr/bin/env python3
"""Structural and source checks for the checked-in LLM Wiki.

The checker intentionally validates form and provenance only.  A passing run
does not mean any statement was semantically reviewed by a human or by an
automated fact checker.

Contract used by the wiki pages
===============================

Frontmatter is a small YAML-compatible block.  ``sources`` is a JSON array of
objects with ``section``, optional ``table`` and ``lines``.  Body references
must use this exact Markdown shape::

    [§6.3.1 Table 9 L225-L250](../../source/OPC-10000-5-v1.05.06.md#L225-L250)

The section, optional table and line range must be listed verbatim in
``sources``.  The link must resolve to the manifest's source document.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = (
    "page_id",
    "kind",
    "source_doc",
    "source_version",
    "source_sha256",
    "status",
    "updated",
    "sources",
)
MIN_CONTENT_PAGES = 10
MAX_CONTENT_PAGES = 20
SECTION_RE = re.compile(r"^\d+(?:\.\d+)*$")
TABLE_RE = re.compile(r"^\d+$")
LINES_RE = re.compile(r"^(\d+)-(\d+)$")
PAGE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

CITATION_RE = re.compile(
    r"\[§(?P<section>\d+(?:\.\d+)*)"
    r"(?:\s+Table\s+(?P<table>\d+))?"
    r"\s+L(?P<start>\d+)-L(?P<end>\d+)\]"
    r"\((?P<target>[^)#]+)#L(?P<fragment_start>\d+)-L(?P<fragment_end>\d+)\)"
)
MD_LINK_RE = re.compile(r"\[[^\]]*\]\((?P<target>[^)\s]+)\)")
LOCAL_SOURCE_RE = re.compile(r"(?im)^Version:\s*(\S+)")


@dataclass(frozen=True)
class SourceRef:
    """One declared source range."""

    section: str
    table: str | None
    start: int
    end: int

    def label(self) -> str:
        table = f" Table {self.table}" if self.table else ""
        return f"§{self.section}{table} L{self.start}-L{self.end}"


@dataclass
class Page:
    """A parsed content page."""

    path: Path
    relative: str
    page_id: str
    kind: str
    entity_id: str | None
    source_doc: str
    source_version: str
    source_sha256: str
    status: str
    updated: str
    sources: list[SourceRef]
    body: str
    links: list[Path] = field(default_factory=list)


@dataclass
class Report:
    """Collect errors without aborting on the first malformed page."""

    errors: list[str] = field(default_factory=list)
    entity_count: int = 0
    topic_count: int = 0

    @property
    def content_count(self) -> int:
        return self.entity_count + self.topic_count


def _scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def _read_text(path: Path, errors: list[str], label: str) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"{label}: cannot read {path}: {exc}")
        return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_jsonl(path: Path, errors: list[str], label: str) -> list[dict[str, Any]]:
    text = _read_text(path, errors, label)
    if text is None:
        return []
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"{label}:{line_number}: invalid JSON: {exc}")
            continue
        if not isinstance(record, dict):
            errors.append(f"{label}:{line_number}: expected a JSON object")
            continue
        records.append(record)
    return records


def _line_range(record: dict[str, Any], label: str, errors: list[str]) -> tuple[int, int] | None:
    start = record.get("start_line")
    end = record.get("end_line")
    if not isinstance(start, int) or not isinstance(end, int):
        errors.append(f"{label}: start_line/end_line must be integers")
        return None
    if start < 1 or end < start:
        errors.append(f"{label}: invalid line range {start}-{end}")
        return None
    return start, end


def _load_manifest(root: Path, errors: list[str]) -> tuple[dict[str, Any], Path | None, str | None, int]:
    manifest_path = root / "source" / "source_manifest.json"
    text = _read_text(manifest_path, errors, "source/source_manifest.json")
    if text is None:
        return {}, None, None, 0
    try:
        manifest = json.loads(text)
    except json.JSONDecodeError as exc:
        errors.append(f"source/source_manifest.json: invalid JSON: {exc}")
        return {}, None, None, 0
    if not isinstance(manifest, dict):
        errors.append("source/source_manifest.json: expected a JSON object")
        return {}, None, None, 0

    for field_name in ("doc", "version", "sha256"):
        if not isinstance(manifest.get(field_name), str) or not manifest[field_name].strip():
            errors.append(f"source/source_manifest.json: missing {field_name}")

    raw_path = manifest.get("local_source_path") or manifest.get("source_path") or ""
    source_name = str(raw_path).replace("\\", "/").rstrip("/").split("/")[-1]
    if not source_name:
        source_name = f"{manifest.get('doc', 'OPC-10000-5')}-v{manifest.get('version', '')}.md"
    source_path = root / "source" / source_name
    if not source_path.is_file():
        errors.append(f"source/source_manifest.json: source file not found at source/{source_name}")
        return manifest, None, None, 0

    source_text = _read_text(source_path, errors, "source")
    if source_text is None:
        return manifest, None, None, 0
    line_count = len(source_text.splitlines())
    actual_hash = _sha256(source_path)
    declared_hash = str(manifest.get("sha256", ""))
    if actual_hash != declared_hash:
        errors.append(
            "source/source_manifest.json: sha256 does not match the source file "
            f"(manifest {declared_hash}, actual {actual_hash})"
        )

    header = source_text[:4096]
    doc = str(manifest.get("doc", ""))
    version = str(manifest.get("version", ""))
    if doc and doc not in header:
        errors.append(f"source/source_manifest.json: doc {doc!r} not found in source header")
    version_match = LOCAL_SOURCE_RE.search(header)
    if version_match and version_match.group(1) != version:
        errors.append(
            "source/source_manifest.json: version does not match source header "
            f"(manifest {version}, header {version_match.group(1)})"
        )
    return manifest, source_path, source_text, line_count


def _parse_sources(raw: Any, label: str, errors: list[str]) -> list[SourceRef]:
    if not isinstance(raw, list) or not raw:
        errors.append(f"{label}: sources must be a non-empty JSON array")
        return []
    parsed: list[SourceRef] = []
    for index, entry in enumerate(raw, 1):
        where = f"{label}: sources[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{where}: expected an object")
            continue
        section = str(entry.get("section", "")).strip()
        if not SECTION_RE.match(section):
            errors.append(f"{where}: invalid section {section!r}")
            continue
        table_value = entry.get("table")
        table = None if table_value is None else str(table_value).strip()
        if table is not None and not TABLE_RE.match(table):
            errors.append(f"{where}: invalid table {table!r}")
            continue
        lines_value = entry.get("lines")
        if not isinstance(lines_value, str):
            errors.append(f"{where}: lines must be a string such as 211-217")
            continue
        lines_match = LINES_RE.match(lines_value.strip())
        if not lines_match:
            errors.append(f"{where}: invalid lines {lines_value!r}")
            continue
        start, end = (int(part) for part in lines_match.groups())
        if start < 1 or end < start:
            errors.append(f"{where}: invalid line range {start}-{end}")
            continue
        parsed.append(SourceRef(section=section, table=table, start=start, end=end))
    return parsed


def _parse_page(path: Path, root: Path, errors: list[str]) -> Page | None:
    relative = path.relative_to(root).as_posix()
    text = _read_text(path, errors, relative)
    if text is None:
        return None
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        errors.append(f"{relative}: missing opening frontmatter delimiter")
        return None
    try:
        closing = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
    except StopIteration:
        errors.append(f"{relative}: missing closing frontmatter delimiter")
        return None

    data: dict[str, str] = {}
    for line_number, line in enumerate(lines[1:closing], 2):
        if not line.strip():
            continue
        key, separator, value = line.partition(":")
        if not separator or not key.strip():
            errors.append(f"{relative}:{line_number}: malformed frontmatter line")
            continue
        key = key.strip()
        if key in data:
            errors.append(f"{relative}:{line_number}: duplicate frontmatter key {key!r}")
            continue
        data[key] = _scalar(value)

    missing = [name for name in REQUIRED_FIELDS if not data.get(name)]
    if missing:
        errors.append(f"{relative}: missing frontmatter fields: {', '.join(missing)}")
        return None

    kind = data["kind"]
    if kind not in ("entity", "topic"):
        errors.append(f"{relative}: kind must be 'entity' or 'topic', got {kind!r}")
        return None
    entity_id = data.get("entity_id")
    if kind == "entity" and not entity_id:
        errors.append(f"{relative}: entity pages require entity_id")
    if kind == "topic" and entity_id:
        errors.append(f"{relative}: topic pages must not have entity_id")

    page_id = data["page_id"]
    if not PAGE_ID_RE.match(page_id):
        errors.append(f"{relative}: invalid page_id {page_id!r}")
    if not SHA256_RE.match(data["source_sha256"]):
        errors.append(f"{relative}: source_sha256 must be 64 lowercase hex characters")
    if not DATE_RE.match(data["updated"]):
        errors.append(f"{relative}: updated must use YYYY-MM-DD")
    if data["status"] != "draft":
        errors.append(f"{relative}: status must be 'draft' until a human review process exists")

    expected_folder = "entities" if kind == "entity" else "topics"
    if path.parent.name != expected_folder:
        errors.append(f"{relative}: {kind} page must live under wiki/{expected_folder}/")

    try:
        raw_sources = json.loads(data["sources"])
    except json.JSONDecodeError as exc:
        errors.append(f"{relative}: sources is not valid JSON: {exc}")
        return None

    sources = _parse_sources(raw_sources, relative, errors)
    if not sources:
        return None

    return Page(
        path=path,
        relative=relative,
        page_id=page_id,
        kind=kind,
        entity_id=entity_id,
        source_doc=data["source_doc"],
        source_version=data["source_version"],
        source_sha256=data["source_sha256"],
        status=data["status"],
        updated=data["updated"],
        sources=sources,
        body="\n".join(lines[closing + 1 :]),
    )


def _resolve_link(page: Page, target: str, root: Path, errors: list[str]) -> Path | None:
    clean = target.split("#", 1)[0]
    if not clean:
        return None
    if clean.startswith("/"):
        errors.append(f"{page.relative}: absolute link {target!r} is outside the relative wiki contract")
        return None
    candidate = (page.path.parent / clean).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        errors.append(f"{page.relative}: link target is outside project root: {target!r}")
        return None
    if not candidate.exists():
        errors.append(f"{page.relative}: link target does not exist: {target!r}")
        return None
    return candidate


def _check_source_range(
    source: SourceRef,
    page: Page,
    chapters: dict[str, dict[str, Any]],
    tables_by_number: dict[str, dict[str, Any]],
    line_count: int,
    errors: list[str],
) -> None:
    where = f"{page.relative}: {source.label()}"
    chapter = chapters.get(source.section)
    if chapter is None:
        errors.append(f"{where}: unknown section {source.section!r} in kb/chapters.jsonl")
        return
    chapter_range = _line_range(chapter, f"kb/chapters.jsonl section {source.section}", errors)
    if chapter_range is not None:
        chapter_start, chapter_end = chapter_range
        if source.start < chapter_start or source.end > chapter_end:
            errors.append(
                f"{where}: line range is outside section {source.section} "
                f"({chapter_start}-{chapter_end})"
            )
    if source.start > line_count or source.end > line_count:
        errors.append(f"{where}: line range is beyond end of source ({line_count} lines)")

    if source.table is not None:
        table = tables_by_number.get(source.table)
        if table is None:
            errors.append(f"{where}: unknown table {source.table!r} in kb/tables.jsonl")
            return
        table_section = str(table.get("section", ""))
        if table_section and table_section != source.section:
            errors.append(
                f"{where}: table {source.table} is defined in section {table_section}, "
                f"not {source.section}"
            )
        table_range = _line_range(table, f"kb/tables.jsonl table {source.table}", errors)
        if table_range is not None:
            table_start, table_end = table_range
            if source.start < table_start or source.end > table_end:
                errors.append(
                    f"{where}: line range is outside table {source.table} "
                    f"({table_start}-{table_end})"
                )


def _check_entity(
    page: Page,
    entities: dict[str, dict[str, Any]],
    tables_by_number: dict[str, dict[str, Any]],
    errors: list[str],
) -> None:
    assert page.entity_id is not None
    entity = entities.get(page.entity_id)
    if entity is None:
        errors.append(
            f"{page.relative}: entity_id {page.entity_id!r} not found in kb/entities.jsonl"
        )
        return
    entity_section = str(entity.get("section", ""))
    if not entity_section:
        errors.append(f"{page.relative}: entity {page.entity_id!r} has no section in kb/entities.jsonl")
    elif all(source.section != entity_section for source in page.sources):
        errors.append(
            f"{page.relative}: sources must include the entity section {entity_section}"
        )

    related = {str(item) for item in (entity.get("related_tables") or [])}
    if related:
        cited = {
            str(tables_by_number[source.table]["id"])
            for source in page.sources
            if source.table is not None and source.table in tables_by_number
        }
        if not related.intersection(cited):
            errors.append(
                f"{page.relative}: no cited table matches {page.entity_id} related_tables "
                f"({', '.join(sorted(related))})"
            )


def _check_body(
    page: Page,
    root: Path,
    source_path: Path,
    line_count: int,
    errors: list[str],
) -> None:
    used: set[int] = set()
    citation_count = 0
    for match in CITATION_RE.finditer(page.body):
        citation_count += 1
        section = match.group("section")
        table = match.group("table")
        start = int(match.group("start"))
        end = int(match.group("end"))
        fragment_start = int(match.group("fragment_start"))
        fragment_end = int(match.group("fragment_end"))
        target = match.group("target").strip()
        label = f"§{section}" + (f" Table {table}" if table else "") + f" L{start}-L{end}"

        if (fragment_start, fragment_end) != (start, end):
            errors.append(
                f"{page.relative}: citation {label} has mismatched fragment "
                f"#L{fragment_start}-L{fragment_end}"
            )
        if start < 1 or end < start or end > line_count:
            errors.append(f"{page.relative}: citation {label} has invalid line anchor")
            continue
        resolved = _resolve_link(page, target, root, errors)
        if resolved is None:
            continue
        if resolved != source_path.resolve():
            errors.append(
                f"{page.relative}: citation {label} must link to {source_path.name}"
            )
            continue

        matched = False
        for index, source in enumerate(page.sources):
            if (
                source.section == section
                and source.table == table
                and source.start == start
                and source.end == end
            ):
                used.add(index)
                matched = True
        if not matched:
            errors.append(
                f"{page.relative}: body citation {label} has no matching frontmatter source"
            )

    if citation_count == 0:
        errors.append(f"{page.relative}: body has no permanent source citation")
    for index, source in enumerate(page.sources):
        if index not in used:
            errors.append(
                f"{page.relative}: frontmatter source {source.label()} is not cited in the body"
            )


def _check_links(
    page: Page,
    root: Path,
    errors: list[str],
) -> None:
    for match in MD_LINK_RE.finditer(page.body):
        target = match.group("target").strip()
        if target.startswith(("#", "http://", "https://", "mailto:")):
            continue
        resolved = _resolve_link(page, target, root, errors)
        if resolved is not None and resolved.suffix.lower() == ".md":
            page.links.append(resolved)


def check_wiki(root: Path) -> Report:
    """Run all structural checks and return every discovered problem."""

    root = root.resolve()
    report = Report()
    errors = report.errors
    if not root.is_dir():
        errors.append(f"root is not a directory: {root}")
        return report

    manifest, source_path, _, line_count = _load_manifest(root, errors)
    if source_path is None:
        return report

    chapter_records = _load_jsonl(root / "kb" / "chapters.jsonl", errors, "kb/chapters.jsonl")
    table_records = _load_jsonl(root / "kb" / "tables.jsonl", errors, "kb/tables.jsonl")
    entity_records = _load_jsonl(root / "kb" / "entities.jsonl", errors, "kb/entities.jsonl")
    chapters = {
        str(record.get("section")): record
        for record in chapter_records
        if record.get("section")
    }
    tables_by_number = {
        str(record.get("number")): record
        for record in table_records
        if record.get("number")
    }
    entities = {
        str(record.get("id")): record
        for record in entity_records
        if record.get("id")
    }

    pages: list[Page] = []
    for folder, kind in (("entities", "entity"), ("topics", "topic")):
        for path in sorted((root / "wiki" / folder).glob("*.md")):
            page = _parse_page(path, root, errors)
            if page is None:
                continue
            if page.kind != kind:
                errors.append(f"{page.relative}: expected kind {kind!r}")
                continue
            pages.append(page)

    report.entity_count = sum(1 for page in pages if page.kind == "entity")
    report.topic_count = sum(1 for page in pages if page.kind == "topic")
    if not MIN_CONTENT_PAGES <= report.content_count <= MAX_CONTENT_PAGES:
        errors.append(
            f"wiki contains {report.content_count} content pages; expected "
            f"{MIN_CONTENT_PAGES}-{MAX_CONTENT_PAGES}"
        )

    seen_ids: dict[str, str] = {}
    for page in pages:
        if page.page_id in seen_ids:
            errors.append(
                f"{page.relative}: duplicate page_id {page.page_id!r} "
                f"(already used by {seen_ids[page.page_id]})"
            )
        else:
            seen_ids[page.page_id] = page.relative

        if page.source_doc != manifest.get("doc"):
            errors.append(
                f"{page.relative}: source_doc {page.source_doc!r} does not match manifest "
                f"{manifest.get('doc')!r}"
            )
        if page.source_version != manifest.get("version"):
            errors.append(
                f"{page.relative}: source_version {page.source_version!r} does not match manifest "
                f"{manifest.get('version')!r}"
            )
        if page.source_sha256 != manifest.get("sha256"):
            errors.append(
                f"{page.relative}: source_sha256 does not match manifest sha256"
            )

        for source in page.sources:
            _check_source_range(source, page, chapters, tables_by_number, line_count, errors)
        _check_body(page, root, source_path, line_count, errors)
        _check_links(page, root, errors)
        if page.kind == "entity":
            _check_entity(page, entities, tables_by_number, errors)

    content_paths = {page.path.resolve() for page in pages}
    for page in pages:
        outgoing = {
            target
            for target in page.links
            if target in content_paths and target != page.path.resolve()
        }
        if not outgoing:
            errors.append(f"{page.relative}: no link to another knowledge page")

    index_path = root / "wiki" / "index.md"
    index_text = _read_text(index_path, errors, "wiki/index.md")
    index_links: set[Path] = set()
    if index_text is not None:
        index_page = Page(
            path=index_path,
            relative="wiki/index.md",
            page_id="index",
            kind="topic",
            entity_id=None,
            source_doc="",
            source_version="",
            source_sha256="",
            status="",
            updated="",
            sources=[],
            body=index_text,
        )
        for match in MD_LINK_RE.finditer(index_text):
            target = match.group("target").strip()
            if target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            resolved = _resolve_link(index_page, target, root, errors)
            if resolved is not None and resolved.suffix.lower() == ".md":
                index_links.add(resolved)
        for page in pages:
            if page.path.resolve() not in index_links:
                errors.append(f"wiki/index.md: does not link {page.relative}")

    inbound: dict[Path, int] = {page.path.resolve(): 0 for page in pages}
    for target in index_links:
        if target in inbound:
            inbound[target] += 1
    for page in pages:
        for target in page.links:
            if target in inbound and target != page.path.resolve():
                inbound[target] += 1
    for page in pages:
        if inbound[page.path.resolve()] == 0:
            errors.append(f"{page.relative}: no inbound link from a knowledge page or index")

    for required in ("wiki/AGENTS.md", "wiki/log.md"):
        if not (root / required).is_file():
            errors.append(f"{required}: required workflow document is missing")

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="project root (default: repository containing this tool)",
    )
    args = parser.parse_args(argv)
    report = check_wiki(args.root)
    if report.errors:
        for error in report.errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(
            f"check_wiki: FAILED with {len(report.errors)} error(s); "
            "form/source checks only, no semantic review performed",
            file=sys.stderr,
        )
        return 1
    print(
        f"check_wiki: OK ({report.content_count} content pages: "
        f"{report.entity_count} entities, {report.topic_count} topics); "
        "form/source checks only, no semantic review performed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
