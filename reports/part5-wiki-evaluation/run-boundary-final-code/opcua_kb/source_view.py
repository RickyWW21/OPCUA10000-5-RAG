"""Path-safe evidence metadata and content serving for the Part 5 API.

The helpers in this module are deliberately read-only.  They normalize the
source information already present in RAG records and expose the exact source
range that backs a citation without ever reading an arbitrary path.
"""

from __future__ import annotations

import json
import posixpath
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlsplit

_DOC = "OPC-10000-5"
_WIKI_PATH = re.compile(r"^wiki/(entities|topics)/[a-z0-9][a-z0-9-]*\.md$")
_SECTION = re.compile(r"^(?:\d+(?:\.\d+)*|Annex [A-Z]|[A-Z](?:\.\d+)+)$")
_TABLE = re.compile(r"^(?:\d+|[A-Z]\.\d+)$")
_LINES = re.compile(r"^(\d+)-(\d+)$")
_FRAGMENT = re.compile(r"^L(\d+)(?:-L?(\d+))?$", re.IGNORECASE)
_MARKDOWN_LINK = re.compile(r"(?<!!)\[([^\]\n]+)\]\(([^)\n]+)\)")
_SAFE_TARGET = re.compile(r"^[^\s]+$")


class SourceViewError(Exception):
    """A request that cannot be served from the allowlisted source files."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class SourceView:
    """Add normalized evidence sources and serve verified Wiki/spec content."""

    def __init__(self, root: str | Path, knowledge_base: Any) -> None:
        self.root = Path(root).resolve()
        self.knowledge_base = knowledge_base

    # ------------------------------------------------------------------
    # HTTP content endpoint
    # ------------------------------------------------------------------
    def content(
        self,
        path: str,
        *,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> dict[str, Any]:
        """Return a full Wiki page or an exact specification line range."""

        wiki_key = _wiki_key(path)
        if wiki_key is not None:
            return self._wiki_content(wiki_key)

        manifest = self._manifest()
        if manifest is None:
            raise SourceViewError(404, "source manifest not available")
        if not isinstance(path, str) or path != manifest["path"]:
            raise SourceViewError(404, "source path not allowed")
        if start_line is None or end_line is None:
            raise SourceViewError(422, "start_line and end_line are required for specification sources")
        if start_line < 1 or end_line < start_line:
            raise SourceViewError(422, "invalid line range")
        if end_line > len(manifest["lines"]):
            raise SourceViewError(422, "line range exceeds source length")

        location = self._find_location(start_line, end_line)
        content = "\n".join(manifest["lines"][start_line - 1 : end_line])
        return {
            "kind": "spec",
            "path": manifest["path"],
            "title": manifest["title"],
            "version": manifest["version"] or "unavailable",
            "start_line": start_line,
            "end_line": end_line,
            "content": content,
            "locations": [location],
            "links": [],
        }

    def _wiki_content(self, wiki_key: str) -> dict[str, Any]:
        page_path = self._wiki_pages().get(wiki_key)
        if page_path is None:
            raise SourceViewError(404, "wiki page not found")
        try:
            text = page_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise SourceViewError(404, "wiki page not readable") from exc
        page = _parse_wiki_page(text)
        if page is None:
            raise SourceViewError(422, "wiki page is not a valid content page")

        body = page["body"]
        content_lines = body.splitlines()
        end_line = len(content_lines) if content_lines else 0
        manifest = self._manifest()
        source_lines = manifest["lines"] if manifest is not None else None
        locations = (
            self._locations_from_entries(page["sources"], source_lines)
            if source_lines is not None
            else []
        )
        links = self._wiki_links(wiki_key, body, manifest, source_lines)
        return {
            "kind": "wiki",
            "path": wiki_key,
            "title": page["title"],
            "version": page["version"] or (manifest["version"] if manifest else "") or "unavailable",
            "status": page["status"] or "unavailable",
            "start_line": 1,
            "end_line": end_line,
            "content": body,
            "locations": locations,
            "links": links,
        }

    def _wiki_links(
        self,
        page_key: str,
        body: str,
        manifest: dict[str, Any] | None,
        source_lines: list[str] | None,
    ) -> list[dict[str, Any]]:
        """Parse Markdown links and keep only allowlisted Wiki/spec targets."""

        pages = self._wiki_pages()
        links: list[dict[str, Any]] = []
        seen: set[tuple[str, int | None, int | None]] = set()
        for match in _MARKDOWN_LINK.finditer(body):
            label = " ".join(match.group(1).split())
            target = _link_target(match.group(2))
            if not label or not target:
                continue
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            parts = urlsplit(target)
            if parts.scheme or parts.netloc:
                continue
            relative = unquote(parts.path)
            if not relative or relative.startswith("/"):
                continue
            normalized = posixpath.normpath(
                posixpath.join(posixpath.dirname(page_key), relative)
            )
            if normalized.startswith("../") or normalized == "..":
                continue
            if normalized in pages:
                marker = (normalized, None, None)
                if marker not in seen:
                    seen.add(marker)
                    links.append({"label": label, "path": normalized})
                continue
            if manifest is None or normalized != manifest["path"]:
                continue
            fragment = unquote(parts.fragment)
            fragment_match = _FRAGMENT.fullmatch(fragment)
            if fragment_match is None:
                continue
            start = int(fragment_match.group(1))
            end = int(fragment_match.group(2) or fragment_match.group(1))
            if (
                source_lines is None
                or start < 1
                or end < start
                or end > len(source_lines)
            ):
                continue
            marker = (manifest["path"], start, end)
            if marker in seen:
                continue
            seen.add(marker)
            links.append(
                {
                    "label": label,
                    "path": manifest["path"],
                    "start_line": start,
                    "end_line": end,
                }
            )
        return links

    # ------------------------------------------------------------------
    # Additive result enrichment
    # ------------------------------------------------------------------
    def enrich_result(self, result: dict[str, Any]) -> dict[str, Any]:
        """Attach a normalized ``source`` to retrieved items and citations."""

        sources_by_id: dict[str, dict[str, Any] | None] = {}
        retrieved = result.get("retrieved")
        if isinstance(retrieved, list):
            for item in retrieved:
                if not isinstance(item, dict):
                    continue
                try:
                    source = self.source_for_retrieved(item)
                except Exception:
                    source = None
                if source is not None:
                    item["source"] = source
                    sources_by_id[str(item.get("id") or "")] = source
                else:
                    sources_by_id.setdefault(str(item.get("id") or ""), None)

        citations = result.get("citations")
        if isinstance(citations, list):
            for citation in citations:
                if not isinstance(citation, dict):
                    continue
                try:
                    source = sources_by_id.get(str(citation.get("id") or ""))
                    if source is None:
                        source = self.source_for_citation(citation)
                except Exception:
                    source = None
                if source is not None:
                    citation["source"] = source
        return result

    def source_for_retrieved(self, item: dict[str, Any]) -> dict[str, Any] | None:
        provenance = item.get("provenance")
        record_id = str(item.get("id") or "")
        record_type = str(item.get("type") or "") or _infer_record_type(record_id)
        if (
            record_type == "wiki"
            or record_id.startswith("wiki:")
            or _is_wiki_provenance(provenance)
        ):
            if isinstance(provenance, dict):
                source = self._wiki_source(provenance)
                if source is not None:
                    return source
            return self._wiki_source_for_id(record_id)
        if isinstance(provenance, dict):
            return self._spec_source(provenance)
        relationship_source = None
        if record_type == "relationship":
            relationship_source = _relationship_source_id(
                item.get("snippet"),
                record_id,
                str(item.get("title") or ""),
            )
        return self._record_source(
            record_id,
            record_type,
            title=str(item.get("title") or ""),
            relationship_source=relationship_source,
        )

    def source_for_citation(self, citation: dict[str, Any]) -> dict[str, Any] | None:
        provenance = citation.get("provenance")
        record_id = str(citation.get("id") or "")
        if record_id.startswith("wiki:") or _is_wiki_provenance(provenance):
            if isinstance(provenance, dict):
                source = self._wiki_source(provenance)
                if source is not None:
                    return source
            return self._wiki_source_for_id(record_id)
        if isinstance(provenance, dict):
            return self._spec_source(provenance)
        return self._record_source(
            record_id,
            _infer_record_type(record_id),
            title=str(citation.get("title") or ""),
        )

    def _wiki_source_for_id(self, record_id: str) -> dict[str, Any] | None:
        if not record_id.startswith("wiki:"):
            return None
        page_id = record_id.split(":", 1)[1]
        key = None
        for candidate in self._wiki_pages():
            if candidate.rsplit("/", 1)[-1].removesuffix(".md") == page_id:
                key = candidate
                break
        if key is None:
            return None
        page_path = self._wiki_pages()[key]
        try:
            page = _parse_wiki_page(page_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            return None
        if page is None:
            return None
        provenance = {
            "path": key,
            "source_version": page["version"],
            "status": page["status"],
            "sources": page["sources"],
        }
        return self._wiki_source(provenance)

    def _wiki_source(self, provenance: dict[str, Any]) -> dict[str, Any] | None:
        path = provenance.get("path")
        key = _wiki_key(path)
        if key is None or key not in self._wiki_pages():
            return None
        manifest = self._manifest()
        source_lines = manifest["lines"] if manifest is not None else None
        raw_sources = provenance.get("sources")
        locations = (
            self._locations_from_entries(
                raw_sources if isinstance(raw_sources, list) else [], source_lines
            )
            if source_lines is not None
            else []
        )
        version = str(provenance.get("source_version") or "")
        if not version and manifest is not None:
            version = manifest["version"]
        status = provenance.get("status")
        source: dict[str, Any] = {
            "kind": "wiki",
            "path": key,
            "version": version or "unavailable",
            "locations": locations,
            "url": _content_url(key),
        }
        if isinstance(status, str) and status:
            source["status"] = status
        return source

    def _spec_source(self, provenance: dict[str, Any]) -> dict[str, Any] | None:
        manifest = self._manifest()
        if manifest is None:
            return None
        source_lines = manifest["lines"]
        locations: list[dict[str, Any]] = []
        line_value = provenance.get("lines")
        if isinstance(line_value, str):
            match = _LINES.fullmatch(line_value.strip())
            if match is not None:
                start, end = (int(part) for part in match.groups())
                location = self._validated_location(
                    {
                        "section": provenance.get("section"),
                        "table": provenance.get("table_number")
                        or provenance.get("table"),
                        "start_line": start,
                        "end_line": end,
                    },
                    source_lines,
                )
                if location is not None:
                    locations.append(location)
        version = str(provenance.get("version") or "")
        if not version:
            version = manifest["version"]
        return {
            "kind": "spec",
            "path": manifest["path"],
            "version": version or "unavailable",
            "locations": locations,
            "url": _content_url(manifest["path"], locations[0]) if locations else "",
        }

    def _record_source(
        self,
        record_id: str,
        record_type: str,
        *,
        title: str = "",
        relationship_source: str | None = None,
    ) -> dict[str, Any] | None:
        if not record_id:
            return None
        manifest = self._manifest()
        if manifest is None:
            return None
        locations = self._locations_for_record(
            record_id,
            record_type,
            title=title,
            relationship_source=relationship_source,
        )
        return {
            "kind": "spec",
            "path": manifest["path"],
            "version": manifest["version"] or "unavailable",
            "locations": locations,
            "url": _content_url(manifest["path"], locations[0]) if locations else "",
        }

    # ------------------------------------------------------------------
    # Knowledge-base lookups
    # ------------------------------------------------------------------
    def _locations_for_record(
        self,
        record_id: str,
        record_type: str,
        *,
        title: str = "",
        relationship_source: str | None = None,
    ) -> list[dict[str, Any]]:
        manifest = self._manifest()
        source_lines = manifest["lines"] if manifest is not None else None
        if record_type == "entity":
            entity = self._call_kb("get_entity", record_id)
            if not isinstance(entity, dict):
                return []
            direct = self._locations_from_ref(entity.get("source_ref"), source_lines)
            if direct:
                return direct
            chapter = self._chapter(entity.get("section"))
            return self._locations_from_range(
                chapter, section=entity.get("section"), source_lines=source_lines
            )

        if record_type == "table":
            table = self._table_by_reference(record_id)
            return self._locations_from_range(table, source_lines=source_lines, is_table=True)

        if record_type == "chapter":
            chapter = self._chapter_by_id(record_id) or self._chapter(record_id)
            return self._locations_from_range(chapter, source_lines=source_lines)

        if record_type == "chunk":
            chunk = self._chunk(record_id)
            if isinstance(chunk, dict):
                direct = self._locations_from_ref(chunk.get("source_ref"), source_lines)
                if direct:
                    return direct
                chapter = self._chapter(chunk.get("section"))
                if chunk.get("chunk_type") == "section_text":
                    chapter_range = _line_range(chapter)
                    text = chunk.get("text")
                    if chapter_range and source_lines is not None and isinstance(text, str) and text:
                        start, end = chapter_range
                        original = "\n".join(source_lines[start - 1:end])
                        offset = original.find(text)
                        if offset >= 0:
                            first_line = start + original[:offset].count("\n")
                            location = self._validated_location({
                                "section": chunk.get("section"), "start_line": first_line,
                                "end_line": first_line + text.count("\n"),
                            }, source_lines)
                            if location is not None:
                                return [location]
                    return self._locations_from_range(
                        chapter, section=chunk.get("section"), source_lines=source_lines
                    )
                for table_id in chunk.get("table_ids") or []:
                    table = self._table_by_reference(table_id)
                    locations = self._locations_from_range(
                        table, source_lines=source_lines, is_table=True
                    )
                    if locations:
                        return locations
                return self._locations_from_range(
                    chapter,
                    section=chunk.get("section"),
                    source_lines=source_lines,
                )
            if record_id.startswith("chunk-"):
                table = self._table_by_reference(record_id.removeprefix("chunk-"))
                return self._locations_from_range(
                    table, source_lines=source_lines, is_table=True
                )
            return []

        if record_type == "relationship":
            matches: list[list[dict[str, Any]]] = []
            for edge in self._relationships():
                if not isinstance(edge, dict):
                    continue
                if str(edge.get("target") or "") != record_id:
                    continue
                if title and str(edge.get("relation") or "") != title:
                    continue
                if (
                    relationship_source is not None
                    and str(edge.get("source") or "") != relationship_source
                ):
                    continue
                matches.append(
                    self._locations_from_ref(edge.get("source_ref"), source_lines)
                )
            distinct: list[list[dict[str, Any]]] = []
            for locations in matches:
                if locations not in distinct:
                    distinct.append(locations)
            # With no explicit origin, only an unambiguous legacy match is safe.
            return distinct[0] if len(distinct) == 1 else []

        return []

    def _locations_from_ref(
        self, ref: Any, source_lines: list[str] | None
    ) -> list[dict[str, Any]]:
        if not isinstance(ref, dict):
            return []
        table_ref = ref.get("table")
        table = self._table_by_reference(table_ref) if table_ref else None
        if isinstance(table, dict):
            return self._locations_from_range(
                table,
                section=ref.get("section") or table.get("section"),
                source_lines=source_lines,
                is_table=True,
            )
        start = ref.get("start_line")
        end = ref.get("end_line")
        if not _is_int(start) or not _is_int(end):
            chapter = self._chapter(ref.get("section"))
            return self._locations_from_range(
                chapter, section=ref.get("section"), source_lines=source_lines
            )
        location = self._validated_location(
            {
                "section": ref.get("section"),
                "table": table_ref,
                "start_line": start,
                "end_line": end,
            },
            source_lines,
        )
        return [location] if location is not None else []

    def _locations_from_range(
        self,
        record: Any,
        *,
        section: Any = None,
        source_lines: list[str] | None,
        is_table: bool = False,
    ) -> list[dict[str, Any]]:
        if not isinstance(record, dict):
            return []
        start = record.get("start_line")
        end = record.get("end_line")
        if not _is_int(start) or not _is_int(end):
            return []
        location = self._validated_location(
            {
                "section": section or record.get("section"),
                "table": record.get("number") if is_table else None,
                "start_line": start,
                "end_line": end,
            },
            source_lines,
        )
        return [location] if location is not None else []

    def _locations_from_entries(
        self, entries: Any, source_lines: list[str] | None
    ) -> list[dict[str, Any]]:
        if not isinstance(entries, list):
            return []
        locations: list[dict[str, Any]] = []
        seen: set[tuple[Any, Any, int, int]] = set()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            line_value = entry.get("lines")
            if not isinstance(line_value, str):
                continue
            match = _LINES.fullmatch(line_value.strip())
            if match is None:
                continue
            start, end = (int(part) for part in match.groups())
            location = self._validated_location(
                {
                    "section": entry.get("section"),
                    "table": entry.get("table"),
                    "start_line": start,
                    "end_line": end,
                },
                source_lines,
            )
            if location is None:
                continue
            marker = (
                location.get("section"),
                location.get("table"),
                location["start_line"],
                location["end_line"],
            )
            if marker in seen:
                continue
            seen.add(marker)
            locations.append(location)
        return locations

    def _validated_location(
        self, raw: dict[str, Any], source_lines: list[str] | None
    ) -> dict[str, Any] | None:
        start = raw.get("start_line")
        end = raw.get("end_line")
        if not _is_int(start) or not _is_int(end):
            return None
        if start < 1 or end < start:
            return None
        if source_lines is not None and end > len(source_lines):
            return None
        section = raw.get("section")
        section_text = str(section).strip() if section is not None else ""
        if section_text and not _SECTION.fullmatch(section_text):
            return None
        table = _clean_table(raw.get("table"))
        if table is not None and not _TABLE.fullmatch(table):
            return None

        if section_text:
            chapter = self._chapter(section_text)
            chapter_range = _line_range(chapter)
            if chapter_range is not None:
                chapter_start, chapter_end = chapter_range
                if start < chapter_start or end > chapter_end:
                    return None
        if table is not None:
            table_record = self._table_by_reference(table)
            table_range = _line_range(table_record)
            if table_range is not None:
                table_start, table_end = table_range
                if start < table_start or end > table_end:
                    return None

        location: dict[str, Any] = {}
        if section_text:
            location["section"] = section_text
        if table is not None:
            location["table"] = table
        location["start_line"] = start
        location["end_line"] = end
        return location

    def _find_location(self, start: int, end: int) -> dict[str, Any]:
        """Find the smallest chapter/table containing a requested range."""

        chapter = None
        chapter_size = None
        for record in self._chapters().values():
            if not isinstance(record, dict):
                continue
            line_range = _line_range(record)
            if line_range is None:
                continue
            chapter_start, chapter_end = line_range
            if chapter_start <= start and end <= chapter_end:
                size = chapter_end - chapter_start
                if chapter_size is None or size < chapter_size:
                    chapter = record
                    chapter_size = size

        table = None
        table_size = None
        for record in self._tables().values():
            if not isinstance(record, dict):
                continue
            line_range = _line_range(record)
            if line_range is None:
                continue
            table_start, table_end = line_range
            if table_start <= start and end <= table_end:
                size = table_end - table_start
                if table_size is None or size < table_size:
                    table = record
                    table_size = size

        location: dict[str, Any] = {}
        section = None
        if isinstance(table, dict):
            section = table.get("section")
            number = table.get("number")
            if number is not None:
                location["table"] = str(number)
        if section is None and isinstance(chapter, dict):
            section = chapter.get("section")
        if section is not None:
            location["section"] = str(section)
        location["start_line"] = start
        location["end_line"] = end
        return location

    def _manifest(self) -> dict[str, Any] | None:
        manifest_path = self.root / "source" / "source_manifest.json"
        source_dir = (self.root / "source").resolve()
        try:
            resolved_manifest = manifest_path.resolve()
            resolved_manifest.relative_to(source_dir)
            resolved_manifest.relative_to(self.root)
            data = json.loads(resolved_manifest.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            return None
        if not isinstance(data, dict) or data.get("doc") != _DOC:
            return None
        version = data.get("version")
        version = version.strip() if isinstance(version, str) else ""
        title = data.get("title")
        title = title.strip() if isinstance(title, str) else ""

        raw_path = data.get("local_source_path") or data.get("source_path") or ""
        filename = _basename(raw_path)
        if not filename.lower().endswith(".md"):
            filename = f"{_DOC}-v{version}.md" if version else ""
        if not filename or filename in {".", ".."}:
            return None

        source_path = self.root / "source" / filename
        try:
            if not source_path.is_file():
                return None
            resolved = source_path.resolve()
            resolved.relative_to(source_dir)
            resolved.relative_to(self.root)
            lines = resolved.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError, ValueError):
            return None
        return {
            "version": version,
            "title": title or filename,
            "path": resolved.relative_to(self.root).as_posix(),
            "lines": lines,
        }

    def _wiki_pages(self) -> dict[str, Path]:
        pages: dict[str, Path] = {}
        wiki_root = (self.root / "wiki").resolve()
        for folder in ("entities", "topics"):
            folder_path = self.root / "wiki" / folder
            if not folder_path.is_dir():
                continue
            try:
                candidates = sorted(folder_path.glob("*.md"))
            except OSError:
                continue
            for candidate in candidates:
                try:
                    resolved = candidate.resolve()
                    resolved.relative_to(wiki_root)
                    resolved.relative_to(self.root)
                except (OSError, ValueError):
                    continue
                if not resolved.is_file():
                    continue
                relative = resolved.relative_to(self.root).as_posix()
                if _WIKI_PATH.fullmatch(relative):
                    pages[relative] = resolved
        return pages

    def _call_kb(self, method_name: str, key: str) -> Any:
        method = getattr(self.knowledge_base, method_name, None)
        if not callable(method):
            return None
        try:
            return method(key)
        except Exception:
            return None

    def _artifact(self, loader_name: str, key: str) -> Any:
        loader = getattr(self.knowledge_base, loader_name, None)
        if not callable(loader):
            return None
        try:
            records = loader()
        except Exception:
            return None
        if not isinstance(records, dict):
            return None
        return records.get(key)

    def _chapter(self, section: Any) -> Any:
        if not isinstance(section, str) or not section:
            return None
        return self._call_kb("chapter", section)

    def _chapter_by_id(self, record_id: str) -> Any:
        record = self._artifact("_load_chapters_by_id", record_id)
        if record is not None:
            return record
        return self._chapters().get(record_id)

    def _chapters(self) -> dict[str, Any]:
        loader = getattr(self.knowledge_base, "_load_chapters", None)
        if not callable(loader):
            return {}
        try:
            records = loader()
        except Exception:
            return {}
        return records if isinstance(records, dict) else {}

    def _tables(self) -> dict[str, Any]:
        loader = getattr(self.knowledge_base, "_load_tables", None)
        if not callable(loader):
            return {}
        try:
            records = loader()
        except Exception:
            return {}
        return records if isinstance(records, dict) else {}

    def _table_by_reference(self, reference: Any) -> Any:
        if reference is None:
            return None
        key = _clean_table(reference)
        if key is None:
            return None
        by_id = self._artifact("_load_tables_by_id", f"table-{key}")
        if by_id is not None:
            return by_id
        by_number = self._tables().get(key.lower())
        if by_number is not None:
            return by_number
        return self._call_kb("table", key)

    def _chunk(self, record_id: str) -> Any:
        return self._artifact("_load_chunks", record_id)

    def _relationships(self) -> list[Any]:
        loader = getattr(self.knowledge_base, "_load_relationships", None)
        if not callable(loader):
            return []
        try:
            records = loader()
        except Exception:
            return []
        return records if isinstance(records, list) else []


def _parse_wiki_page(text: str) -> dict[str, Any] | None:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    closing = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            closing = index
            break
    if closing is None:
        return None

    data: dict[str, str] = {}
    for line in lines[1:closing]:
        key, separator, value = line.partition(":")
        if not separator or not key.strip():
            return None
        data[key.strip()] = value.strip()
    body = "\n".join(lines[closing + 1 :])
    title = _h1(body)
    if title is None:
        return None
    raw_sources: Any = []
    value = data.get("sources")
    if value:
        try:
            raw_sources = json.loads(value)
        except json.JSONDecodeError:
            raw_sources = []
    return {
        "title": title,
        "body": body,
        "version": data.get("source_version", ""),
        "status": data.get("status", ""),
        "sources": raw_sources if isinstance(raw_sources, list) else [],
    }


def _h1(body: str) -> str | None:
    for line in body.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            return title or None
    return None


def _wiki_key(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or "\\" in value or "\x00" in value:
        return None
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return None
    return value if _WIKI_PATH.fullmatch(value) else None


def _link_target(value: str) -> str | None:
    target = value.strip()
    if not target:
        return None
    first = target.split()[0]
    if first.startswith("<") and first.endswith(">"):
        first = first[1:-1]
    return first if _SAFE_TARGET.fullmatch(first) else None


def _is_wiki_provenance(provenance: Any) -> bool:
    return isinstance(provenance, dict) and _wiki_key(provenance.get("path")) is not None


def _relationship_source_id(
    snippet: Any, target_id: str, relation: str
) -> str | None:
    """Recover the origin ID from a retrieval snippet ``source RELATION target``."""

    if not isinstance(snippet, str) or not target_id:
        return None
    text = " ".join(snippet.split())
    suffix = f" {target_id}"
    if not text.endswith(suffix):
        return None
    prefix = text[: -len(suffix)].rstrip()
    source_id, separator, snippet_relation = prefix.rpartition(" ")
    if not separator:
        return None
    if relation and snippet_relation != relation:
        return None
    source_id = source_id.strip()
    return source_id or None


def _infer_record_type(record_id: str) -> str:
    if record_id.startswith("table-"):
        return "table"
    if record_id.startswith("sec-"):
        return "chapter"
    if record_id.startswith("chunk-") or record_id.startswith("source:"):
        return "chunk"
    if ":" in record_id:
        return "entity"
    return ""


def _basename(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.replace("\\", "/").rstrip("/").split("/")[-1]


def _clean_table(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.lower().startswith("table-"):
        text = text[6:]
    return text or None


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _line_range(record: Any) -> tuple[int, int] | None:
    if not isinstance(record, dict):
        return None
    start = record.get("start_line")
    end = record.get("end_line")
    if not _is_int(start) or not _is_int(end):
        return None
    if start < 1 or end < start:
        return None
    return start, end


def _content_url(path: str, location: dict[str, Any] | None = None) -> str:
    url = f"/api/v1/content?path={quote(path, safe='/')}"
    if location is not None:
        url += (
            f"&start_line={location['start_line']}"
            f"&end_line={location['end_line']}"
        )
    return url
