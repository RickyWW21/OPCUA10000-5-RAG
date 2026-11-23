"""Path-safe spec-only evidence metadata and content serving for the Part 5 API.

The helpers in this module are deliberately read-only.  They normalize the
source information already present in RAG records and expose the exact source
range that backs a citation without ever reading an arbitrary path.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .api import load_source_manifest

_DOC = "OPC-10000-5"
_SECTION = re.compile(r"^(?:\d+(?:\.\d+)*|Annex [A-Z]|[A-Z](?:\.\d+)+)$")
_TABLE = re.compile(r"^(?:\d+|[A-Z]\.\d+)$")
_LINES = re.compile(r"^(\d+)-(\d+)$")
_WIKI_LABEL = re.compile(r"^\[W\d*\]$", re.IGNORECASE)


class SourceViewError(Exception):
    """A request that cannot be served from the allowlisted source files."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class SourceView:
    """Add normalized spec evidence sources and serve verified spec content."""

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
        """Return an exact specification line range."""

        if isinstance(path, str) and (path == "wiki" or path.startswith("wiki/")):
            raise SourceViewError(404, "source path not allowed")

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
                if _is_legacy_wiki_record(item):
                    legacy = self._legacy_wiki_source(item)
                    item["source"] = legacy
                    sources_by_id[str(item.get("id") or "")] = legacy
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
                if _is_legacy_wiki_record(citation):
                    existing = sources_by_id.get(str(citation.get("id") or ""))
                    if isinstance(existing, dict) and existing.get("kind") == "legacy_wiki":
                        citation["source"] = self._legacy_wiki_source(citation, fallback=existing)
                    else:
                        citation["source"] = self._legacy_wiki_source(citation)
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
        if _is_legacy_wiki_record(item):
            return self._legacy_wiki_source(item)
        provenance = item.get("provenance")
        record_id = str(item.get("id") or "")
        record_type = str(item.get("type") or "") or _infer_record_type(record_id)
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
        if _is_legacy_wiki_record(citation):
            return self._legacy_wiki_source(citation)
        provenance = citation.get("provenance")
        record_id = str(citation.get("id") or "")
        if isinstance(provenance, dict):
            return self._spec_source(provenance)
        return self._record_source(
            record_id,
            _infer_record_type(record_id),
            title=str(citation.get("title") or ""),
        )

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
                        original = "\n".join(source_lines[start - 1 : end])
                        offset = original.find(text)
                        if offset >= 0:
                            first_line = start + original[:offset].count("\n")
                            location = self._validated_location(
                                {
                                    "section": chunk.get("section"),
                                    "start_line": first_line,
                                    "end_line": first_line + text.count("\n"),
                                },
                                source_lines,
                            )
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
        for record in self._chapters():
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
        for record in self._tables():
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
            data = load_source_manifest(self.root)
        except (FileNotFoundError, ValueError, OSError):
            return None
        if data.get("doc") != _DOC:
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
        sha256 = data.get("sha256")
        sha256 = sha256.strip() if isinstance(sha256, str) else ""
        return {
            "version": version,
            "sha256": sha256,
            "title": title or filename,
            "path": resolved.relative_to(self.root).as_posix(),
            "lines": lines,
        }

    def _call_kb(self, method_name: str, *args: Any) -> Any:
        method = getattr(self.knowledge_base, method_name, None)
        if not callable(method):
            return None
        try:
            return method(*args)
        except Exception:
            return None

    def _chapter(self, section: Any) -> Any:
        if not isinstance(section, str) or not section:
            return None
        record = self._call_kb("chapter", section)
        return record if isinstance(record, dict) else None

    def _chapter_by_id(self, record_id: str) -> Any:
        record = self._call_kb("chapter_by_id", record_id)
        if isinstance(record, dict):
            return record
        for chapter in self._chapters():
            if isinstance(chapter, dict) and chapter.get("id") == record_id:
                return chapter
        return None

    def _chapters(self) -> list[dict[str, Any]]:
        records = self._call_kb("chapters")
        return records if isinstance(records, list) else []

    def _tables(self) -> list[dict[str, Any]]:
        records = self._call_kb("tables")
        return records if isinstance(records, list) else []

    def _table_by_reference(self, reference: Any) -> Any:
        if reference is None:
            return None
        key = _clean_table(reference)
        if key is None:
            return None
        by_id = self._call_kb("table_by_id", f"table-{key}")
        if isinstance(by_id, dict):
            return by_id
        by_number = self._call_kb("table", key)
        if isinstance(by_number, dict):
            return by_number
        key_lower = key.lower()
        for table in self._tables():
            if not isinstance(table, dict):
                continue
            if str(table.get("id") or "") == f"table-{key}":
                return table
            if str(table.get("number") or "").lower() == key_lower:
                return table
        return None

    def _chunk(self, record_id: str) -> Any:
        records = self._call_kb("chunks")
        if not isinstance(records, dict):
            return None
        record = records.get(record_id)
        return record if isinstance(record, dict) else None

    def _legacy_wiki_source(
        self,
        record: dict[str, Any],
        *,
        fallback: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build a read-only historical marker for retired Wiki citations."""

        source = record.get("source") if isinstance(record.get("source"), dict) else {}
        provenance = record.get("provenance") if isinstance(record.get("provenance"), dict) else {}
        wiki_path = ""
        for candidate in (
            source.get("path"),
            provenance.get("path"),
            fallback.get("path") if isinstance(fallback, dict) else None,
        ):
            if isinstance(candidate, str) and candidate.strip():
                wiki_path = candidate.strip().replace("\\", "/")
                break

        spec_path = ""
        manifest_version = ""
        manifest_sha256 = ""
        total_lines = 0
        manifest = self._manifest()
        if isinstance(manifest, dict):
            spec_path = str(manifest.get("path") or "")
            manifest_version = str(manifest.get("version") or "")
            manifest_sha256 = str(manifest.get("sha256") or "")
            lines = manifest.get("lines")
            if isinstance(lines, list):
                total_lines = len(lines)

        version = ""
        for candidate in (
            source.get("version"),
            provenance.get("source_version"),
            provenance.get("version"),
            fallback.get("version") if isinstance(fallback, dict) else None,
        ):
            if isinstance(candidate, str) and candidate.strip():
                version = candidate.strip()
                break

        legacy_sha256 = ""
        for candidate in (
            source.get("source_sha256"),
            source.get("sha256"),
            provenance.get("source_sha256"),
            provenance.get("sha256"),
            fallback.get("source_sha256") if isinstance(fallback, dict) else None,
        ):
            if isinstance(candidate, str) and candidate.strip():
                legacy_sha256 = candidate.strip()
                break

        has_version = bool(version)
        has_sha = bool(legacy_sha256)
        version_ok = (not has_version) or (bool(manifest_version) and version == manifest_version)
        sha_ok = (not has_sha) or (bool(manifest_sha256) and legacy_sha256.lower() == manifest_sha256.lower())
        source_matches = (has_version or has_sha) and version_ok and sha_ok

        raw_locations: list[Any] = []
        if isinstance(source.get("locations"), list):
            raw_locations.extend(source["locations"])
        if not raw_locations and isinstance(provenance.get("sources"), list):
            raw_locations.extend(provenance["sources"])
        if not raw_locations and isinstance(fallback, dict) and isinstance(fallback.get("locations"), list):
            raw_locations.extend(fallback["locations"])

        locations: list[dict[str, Any]] = []
        seen: set[tuple[str | None, str | None, int, int]] = set()
        if source_matches and total_lines > 0 and spec_path:
            for entry in raw_locations:
                if not isinstance(entry, dict):
                    continue
                bounds = _line_range(entry)
                if bounds is None and isinstance(entry.get("lines"), str):
                    parts = entry["lines"].strip().split("-", 1)
                    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                        s, e = int(parts[0]), int(parts[1])
                        if 1 <= s <= e:
                            bounds = (s, e)
                if bounds is None:
                    continue
                start_line, end_line = bounds
                if start_line < 1 or end_line > total_lines:
                    continue
                section = str(entry["section"]).strip() if entry.get("section") else None
                table = _clean_table(entry.get("table"))
                key = (section, table, start_line, end_line)
                if key in seen:
                    continue
                seen.add(key)
                loc: dict[str, Any] = {"start_line": start_line, "end_line": end_line}
                if section:
                    loc["section"] = section
                if table:
                    loc["table"] = table
                locations.append(loc)

        payload: dict[str, Any] = {
            "kind": "legacy_wiki",
            "path": wiki_path,
            "version": version,
            "status": "draft",
            "locations": locations,
        }
        if locations and spec_path:
            payload["spec_path"] = spec_path
        return payload

    def _relationships(self) -> list[Any]:
        records = self._call_kb("all_relationships")
        return records if isinstance(records, list) else []


def _is_legacy_wiki_record(record: dict[str, Any]) -> bool:
    record_type = str(record.get("type") or "")
    record_id = str(record.get("id") or "")
    label = record.get("label")
    source = record.get("source")
    provenance = record.get("provenance")
    if record_type == "wiki" or record_id.startswith("wiki:"):
        return True
    if isinstance(label, str) and _WIKI_LABEL.fullmatch(label.strip()):
        return True
    if isinstance(source, dict) and source.get("kind") in {"wiki", "legacy_wiki"}:
        return True
    if isinstance(provenance, dict):
        path = provenance.get("path")
        if isinstance(path, str) and path.strip().startswith("wiki/"):
            return True
    return False


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
