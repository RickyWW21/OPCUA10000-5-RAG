"""Small, dependency-free reader/search for the Part 5 Wiki.

Ponytail: this scans and parses the 15 content pages on every call.  That is
deliberate for the current Wiki size; if the Wiki grows significantly, replace
the directory scan with a maintained index.  Do not add embeddings, a database,
or a generic YAML/Markdown parser for this task.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any
from .api import expand_query

_ENTITY_DIRS = (("entities", "entity"), ("topics", "topic"))
_SECTION_RE = re.compile(r"^\d+(?:\.\d+)*$")
_TABLE_RE = re.compile(r"^\d+$")
_LINES_RE = re.compile(r"^(\d+)-(\d+)$")
_PAGE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_EN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_ZH_RE = re.compile(r"[\u4e00-\u9fff]+")

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "do", "does", "for",
    "from", "how", "in", "is", "it", "of", "on", "or", "should", "that",
    "the", "this", "to", "was", "were", "what", "when", "where", "which",
    "who", "why", "with",
}


def search_wiki(
    knowledge_base: Any, question: str, *, top_k: int
) -> list[dict[str, Any]]:
    """Return bounded local keyword matches from ``wiki/entities`` and ``wiki/topics``.

    Each result uses the existing search-result keys plus ``evidence`` and
    ``provenance``.  ``evidence`` is the complete Markdown body, never a
    truncation.  The returned dict also carries an internal ``companion_source``
    entry plus bounded question-related ``companion_sources``; the retriever
    keeps these internally before the context budget is applied. The helper does
    not import ``retrieval`` so either module can be used independently.
    """

    if not isinstance(question, str) or not question.strip() or top_k <= 0:
        return []
    root = getattr(knowledge_base, "root", None)
    if not isinstance(root, (str, Path)):
        return []

    root_path = Path(root)
    wiki_root = root_path / "wiki"
    if not wiki_root.is_dir():
        return []
    try:
        root_resolved = root_path.resolve()
        wiki_resolved = wiki_root.resolve()
        wiki_resolved.relative_to(root_resolved)
    except (OSError, ValueError):
        return []

    source_info = _load_source(root_path, root_resolved)
    if source_info is None:
        return []
    source_relative, source_doc, source_version, source_sha256, source_lines = source_info

    pages: list[dict[str, Any]] = []
    seen_page_ids: set[str] = set()
    for folder, expected_kind in _ENTITY_DIRS:
        folder_path = wiki_root / folder
        if not folder_path.is_dir():
            continue
        try:
            page_paths = sorted(folder_path.glob("*.md"))
        except OSError:
            continue
        for page_path in page_paths:
            try:
                resolved = page_path.resolve()
                resolved.relative_to(wiki_resolved)
            except (OSError, ValueError):
                # Reject symlinks that leave the Wiki tree.
                continue
            if not resolved.is_file():
                continue
            page = _load_page(
                page_path,
                folder=folder,
                expected_kind=expected_kind,
                knowledge_base=knowledge_base,
                source_relative=source_relative,
                source_doc=source_doc,
                source_version=source_version,
                source_sha256=source_sha256,
                source_lines=source_lines,
            )
            if page is None or page["page_id"] in seen_page_ids:
                continue
            seen_page_ids.add(page["page_id"])
            pages.append(page)

    frequency = Counter(term for page in pages for term in _terms(page["body"]))
    weights = {term: 1 + math.log((len(pages) + 1) / (count + 1))
               for term, count in frequency.items()}
    matches = [(_score(question, page["title"], page["body"], weights), page) for page in pages]
    matches = [item for item in matches if item[0] > 0]
    matches.sort(key=lambda item: (-item[0], item[1]["path"]))
    return [_as_search_result(page, source_lines, question) for _, page in matches[:top_k]]


def _load_source(
    root: Path, root_resolved: Path
) -> tuple[str, str, str, str, list[str]] | None:
    """Validate the manifest and source bytes before trusting any Wiki page."""

    manifest_path = root / "source" / "source_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(manifest, dict):
        return None
    doc = str(manifest.get("doc") or "")
    version = str(manifest.get("version") or "")
    declared_hash = str(manifest.get("sha256") or "").lower()
    if doc != "OPC-10000-5" or not version or not _SHA256_RE.fullmatch(declared_hash):
        return None

    raw_path = manifest.get("local_source_path") or manifest.get("source_path") or ""
    source_name = str(raw_path).replace("\\", "/").rstrip("/").split("/")[-1]
    if not source_name:
        source_name = f"{doc}-v{version}.md"
    source_path = root / "source" / source_name
    source_dir = (root / "source").resolve()
    try:
        if not source_path.is_file():
            return None
        resolved = source_path.resolve()
        resolved.relative_to(source_dir)
        resolved.relative_to(root_resolved)
        payload = resolved.read_bytes()
    except (OSError, ValueError):
        return None

    actual_hash = hashlib.sha256(payload).hexdigest()
    if actual_hash != declared_hash:
        return None
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return None
    source_relative = resolved.relative_to(root_resolved).as_posix()
    return source_relative, doc, version, actual_hash, text.splitlines()


def _load_page(
    path: Path,
    *,
    folder: str,
    expected_kind: str,
    knowledge_base: Any,
    source_relative: str,
    source_doc: str,
    source_version: str,
    source_sha256: str,
    source_lines: list[str],
) -> dict[str, Any] | None:
    """Parse and verify one page, returning ``None`` for any invalid evidence."""

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None
    try:
        closing = next(
            index for index in range(1, len(lines)) if lines[index].strip() == "---"
        )
    except StopIteration:
        return None

    data: dict[str, str] = {}
    for raw_line in lines[1:closing]:
        line = raw_line.rstrip("\r\n")
        if not line.strip():
            continue
        key, separator, value = line.partition(":")
        if not separator or not key.strip():
            return None
        key = key.strip()
        if key in data:
            return None
        data[key] = _scalar(value)

    required = (
        "page_id",
        "kind",
        "source_doc",
        "source_version",
        "source_sha256",
        "status",
        "sources",
    )
    if any(not data.get(name) for name in required):
        return None
    page_id = data["page_id"]
    if not _PAGE_ID_RE.fullmatch(page_id):
        return None
    if data["kind"] != expected_kind:
        return None
    if data["source_doc"] != source_doc:
        return None
    if data["source_version"] != source_version:
        return None
    if data["source_sha256"].lower() != source_sha256:
        return None
    if data["status"] != "draft":
        return None

    try:
        raw_sources = json.loads(data["sources"])
    except json.JSONDecodeError:
        return None
    if not isinstance(raw_sources, list) or not raw_sources:
        return None
    sources: list[dict[str, Any]] = []
    for entry in raw_sources:
        source = _validate_source(entry, knowledge_base, len(source_lines))
        if source is None:
            return None
        sources.append(source)

    body = "".join(lines[closing + 1 :])
    title = _h1(body)
    if not title or not body.strip():
        return None
    relative = f"wiki/{folder}/{path.name}"
    return {
        "page_id": page_id,
        "path": relative,
        "title": title,
        "body": body,
        "sources": sources,
        "raw_sources": raw_sources,
        "provenance": {
            "page_id": page_id,
            "path": relative,
            "source_doc": source_doc,
            "source_version": source_version,
            "source_sha256": source_sha256,
            "status": data["status"],
            "sources": raw_sources,
        },
        "source_relative": source_relative,
    }


def _validate_source(
    entry: Any, knowledge_base: Any, source_line_count: int
) -> dict[str, Any] | None:
    """Reject a page unless every declared source is inside Part 5 and the kb."""

    if not isinstance(entry, dict):
        return None
    section = str(entry.get("section") or "").strip()
    if not _SECTION_RE.fullmatch(section):
        return None
    table_value = entry.get("table")
    table = None if table_value is None else str(table_value).strip()
    if table is not None and not _TABLE_RE.fullmatch(table):
        return None
    lines_value = entry.get("lines")
    if not isinstance(lines_value, str):
        return None
    lines = lines_value.strip()
    match = _LINES_RE.fullmatch(lines)
    if match is None:
        return None
    start, end = (int(part) for part in match.groups())
    if start < 1 or end < start or end > source_line_count:
        return None

    chapter = _lookup(knowledge_base, "chapter", section)
    chapter_range = _line_range(chapter)
    if chapter_range is None:
        return None
    chapter_start, chapter_end = chapter_range
    if start < chapter_start or end > chapter_end:
        return None

    if table is not None:
        table_record = _lookup(knowledge_base, "table", table)
        table_range = _line_range(table_record)
        if table_range is None or not isinstance(table_record, dict):
            return None
        table_section = str(table_record.get("section") or "")
        if table_section and table_section != section:
            return None
        table_start, table_end = table_range
        if start < table_start or end > table_end:
            return None
    return {"section": section, "table": table, "lines": lines, "start": start, "end": end}


def _as_search_result(
    page: dict[str, Any], source_lines: list[str], question: str
) -> dict[str, Any]:
    """Project a verified page into the shared search-result schema."""

    def make_companion(source: dict[str, Any]) -> dict[str, Any]:
        start, end = source["start"], source["end"]
        companion_text = "\n".join(source_lines[start - 1:end])
        return {
            "id": f"source:{source['section']}:{start}-{end}",
            "type": "chunk",
            "title": _source_label(source),
            "snippet": companion_text,
            "evidence": companion_text,
            "section": source["section"],
            "table_number": source["table"],
            "doc": page["provenance"]["source_doc"],
            "provenance": {
                "path": page["source_relative"],
                "version": page["provenance"]["source_version"],
                "hash": page["provenance"]["source_sha256"],
                "lines": source["lines"],
                "source": page["path"],
                "source_doc": page["provenance"]["source_doc"],
                "section": source["section"],
                "table_number": source["table"],
            },
        }

    def source_score(source: dict[str, Any]) -> float:
        anchor = f"#L{source['start']}-L{source['end']})"
        paragraphs = "\n\n".join(
            block for block in page["body"].split("\n\n") if anchor in block
        )
        text = "\n".join(source_lines[source["start"] - 1:source["end"]])
        return _score(question, "", paragraphs + "\n" + text)

    ranked_sources = sorted(page["sources"], key=source_score, reverse=True)
    companions = [make_companion(source) for source in ranked_sources[:2]]
    first = page["sources"][0]
    return {
        "type": "wiki",
        "id": f"wiki:{page['page_id']}",
        "title": page["title"],
        "snippet": page["body"],
        "evidence": page["body"],
        "section": first["section"],
        "table_number": first["table"],
        "doc": page["provenance"]["source_doc"],
        "provenance": page["provenance"],
        # Internal key consumed and removed by Part5Retriever.
        "companion_source": companions[0],
        "companion_sources": companions,
    }


def _score(question: str, title: str, body: str, weights: dict[str, float] | None = None) -> float:
    """Weight rare query terms so common words cannot saturate all body scores."""

    query_terms = _terms(expand_query(question))
    if not query_terms:
        return 0.0
    title_terms = _terms(title)
    heading_terms: set[str] = set()
    for line in body.splitlines():
        if line.lstrip().startswith("#"):
            heading_terms.update(_terms(line))
    body_terms = _terms(body)

    return sum(
        (weights or {}).get(term, 1.0)
        * (8 * (term in title_terms) + 3 * (term in heading_terms) + (term in body_terms))
        for term in query_terms
    )


def _terms(text: str) -> set[str]:
    """Extract English identifiers and contiguous Chinese bigrams."""

    terms: set[str] = set()
    for token in _EN_RE.findall(text):
        token = token.lower()
        if token not in _STOPWORDS:
            terms.add(token)
    for sequence in _ZH_RE.findall(text):
        if len(sequence) == 1:
            terms.add(sequence)
        else:
            terms.update(sequence[index : index + 2] for index in range(len(sequence) - 1))
    return terms


def _h1(body: str) -> str | None:
    for line in body.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            return title or None
    return None


def _source_label(source: dict[str, Any]) -> str:
    table = f" Table {source['table']}" if source["table"] else ""
    return f"§{source['section']}{table} L{source['start']}-L{source['end']}"


def _lookup(knowledge_base: Any, method_name: str, key: str) -> Any:
    method = getattr(knowledge_base, method_name, None)
    if not callable(method):
        return None
    try:
        return method(key)
    except Exception:
        return None


def _line_range(record: Any) -> tuple[int, int] | None:
    if not isinstance(record, dict):
        return None
    start = record.get("start_line")
    end = record.get("end_line")
    if isinstance(start, bool) or isinstance(end, bool):
        return None
    if not isinstance(start, int) or not isinstance(end, int):
        return None
    if start < 1 or end < start:
        return None
    return start, end


def _scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value
