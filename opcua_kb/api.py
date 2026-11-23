"""Lazy, read-only access to the generated knowledge-base artifacts."""

from __future__ import annotations

import json
import re
import sqlite3
from collections import deque
from pathlib import Path
from typing import Any

from .graph import build_knowledge_graph

_QUERY_ALIASES = {
    "命名空间": "NamespaceArray namespace",
    "会话": "Session",
    "缓存": "cache",
    "索引": "index NamespaceIndex",
    "诊断": "diagnostics",
    "范围": "scope",
    "附录": "Annex",
}
_ANNEX_REFERENCE = re.compile(r"(?:\bAnnex|附录)\s*([A-Z])(?![A-Za-z])", re.IGNORECASE)


def expand_query(query: str) -> str:
    """Add a small Part 5 bilingual glossary; preserve the original question."""

    terms = [value for phrase, value in _QUERY_ALIASES.items() if phrase in query]
    return " ".join([*terms, query])


class KnowledgeBase:
    """Read-only facade over the generated JSONL records and SQLite FTS index."""

    def __init__(self, root: str | Path):
        """Point the API at a project root containing ``kb/`` and ``indexes/``."""

        self.root = Path(root)
        self.kb_dir = self.root / "kb"
        self.index_path = self.root / "indexes" / "fts.sqlite"
        self._entities: dict[str, dict[str, Any]] | None = None
        self._aliases: dict[str, str] | None = None
        self._chapters: dict[str, dict[str, Any]] | None = None
        self._chapters_by_id: dict[str, dict[str, Any]] | None = None
        self._tables: dict[str, dict[str, Any]] | None = None
        self._tables_by_id: dict[str, dict[str, Any]] | None = None
        self._chunks: dict[str, dict[str, Any]] | None = None
        self._relationships: list[dict[str, Any]] | None = None
        self._relationships_by_source: dict[str, list[dict[str, Any]]] | None = None

    def get_entity(self, name: str) -> dict[str, Any] | None:
        """Resolve an entity by ID, normalized alias, or case-insensitive name."""

        entities = self._load_entities()
        aliases = self._load_aliases()
        key = aliases.get(_norm(name), name)
        if key in entities:
            return entities[key]
        for entity in entities.values():
            if _norm(entity.get("name", "")) == _norm(name):
                return entity
        return None

    def search(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        """Return exact entity/document matches followed by full-text results."""

        query = query.strip()
        if not query:
            return []

        # Exact identifiers should remain ahead of less precise FTS matches.
        exact_results = [{**item, "match_kind": "exact"} for item in self._exact_search(query)]
        if len(exact_results) >= top_k:
            return exact_results[:top_k]

        rows = self._search_fts(expand_query(query), top_k) if self.index_path.exists() else []
        return _append_unique_search_results(exact_results, rows, top_k)

    def relationships(
        self, entity: str, relation: str | None = None, depth: int = 1
    ) -> list[dict[str, Any]]:
        """Traverse outgoing relationships breadth-first up to ``depth`` hops."""

        start = self._resolve_entity_id(entity)
        if not start:
            return []
        relationships_by_source = self._load_relationships_by_source()
        relation_norm = relation.upper() if relation else None
        results: list[dict[str, Any]] = []
        # A visited set prevents cycles while preserving breadth-first result order.
        visited = {start}
        queue: deque[tuple[str, int]] = deque([(start, 0)])
        while queue:
            current, current_depth = queue.popleft()
            if current_depth >= depth:
                continue
            for edge in relationships_by_source.get(current, []):
                if relation_norm and edge.get("relation") != relation_norm:
                    continue
                results.append(edge)
                target = edge.get("target")
                if target and target not in visited:
                    visited.add(target)
                    queue.append((target, current_depth + 1))
        return results

    def chapter(self, section: str) -> dict[str, Any] | None:
        """Return one chapter by its specification section number."""

        return self._load_chapters().get(section)

    def table(self, number: int | str) -> dict[str, Any] | None:
        """Return one table by numeric or annex-style identifier such as ``C.1``."""

        return self._load_tables().get(str(number).lower())

    def evidence(self, record_id: str, record_type: str) -> str | None:
        """Return the complete original evidence text for a search result.

        Chapters return their full text, tables every original raw line
        (including the header), chunks the original chunk text rather than the
        FTS snippet, and entities their English summary, structured definition,
        and defining table or original chapter. Relationships have no separate
        hydrated text and keep their boundary snippet in the retriever.
        """

        if not isinstance(record_id, str) or not record_id.strip():
            return None
        if not isinstance(record_type, str):
            return None
        if record_type == "entity":
            return self._entity_evidence(record_id)
        if record_type == "table":
            return self._table_evidence(record_id)
        if record_type == "chapter":
            return self._chapter_evidence(record_id)
        if record_type == "chunk":
            return self._chunk_evidence(record_id)
        return None

    def graph(
        self,
        focus: str | None = None,
        relation: str | None = None,
        depth: int = 1,
        min_weight: int = 1,
        include_defined: bool = False,
        limit: int = 12,
    ) -> dict[str, Any]:
        """Build a serializable graph view from the cached entity relationships."""

        return build_knowledge_graph(
            list(self._load_entities().values()),
            self._load_relationships(),
            focus=focus,
            relation=relation,
            depth=depth,
            min_weight=min_weight,
            include_defined=include_defined,
            limit=limit,
        )

    def _exact_search(self, query: str) -> list[dict[str, Any]]:
        """Extract deterministic entity, table, and chapter matches from a query."""

        results: list[dict[str, Any]] = []
        entity = self.get_entity(query)
        if entity:
            results.append(_entity_result(entity))

        for token in _candidate_tokens(query):
            entity = self.get_entity(token)
            if entity and all(r.get("id") != entity["id"] for r in results):
                results.append(_entity_result(entity))

        table_match = re.search(r"(?:Table|表)\s*(\d+|[A-Z]\.\d+)", query, re.IGNORECASE)
        if table_match:
            table = self.table(table_match.group(1))
            if table:
                results.append(
                    {
                        "type": "table",
                        "id": table["id"],
                        "title": table["caption"],
                        "section": table["section"],
                        "table_number": table["number"],
                        "snippet": "\n".join(table.get("raw_lines", [])[:8]),
                    }
                )

        reference_query = re.sub(r"\bPart\s+\d+\b|第\s*\d+\s*部分", "", query, flags=re.IGNORECASE)
        section_match = re.search(r"(?<![A-Za-z.])(\d+(?:\.\d+){0,5})(?![A-Za-z.])", reference_query)
        annex_match = _ANNEX_REFERENCE.search(query)
        if section_match or annex_match:
            section = f"Annex {annex_match.group(1).upper()}" if annex_match else section_match.group(1)
            chapter = self.chapter(section)
            if chapter:
                results.append(
                    {
                        "type": "chapter",
                        "id": chapter["id"],
                        "title": chapter["title"],
                        "section": chapter["section"],
                        "snippet": chapter.get("text", "")[:500],
                    }
                )
        return results

    def _resolve_entity_id(self, name: str) -> str | None:
        """Normalize a user-facing entity name to the canonical relationship ID."""

        entity = self.get_entity(name)
        if entity:
            return entity["id"]
        aliases = self._load_aliases()
        return aliases.get(_norm(name))

    def _search_fts(self, query: str, top_k: int) -> list[sqlite3.Row]:
        """Query FTS and preserve literal matching as a compatibility fallback."""

        try:
            conn = sqlite3.connect(self.index_path)
        except sqlite3.Error as exc:
            raise OSError(f"Unable to open search index: {self.index_path}") from exc
        conn.row_factory = sqlite3.Row
        try:
            try:
                return _fts_match_rows(conn, _fts_query(query), top_k)
            except sqlite3.OperationalError:
                # Malformed FTS syntax or an older index should still permit a
                # slower literal search instead of failing the entire query.
                return _literal_match_rows(conn, query, top_k)
        except sqlite3.Error as exc:
            raise OSError(f"Unable to query search index: {self.index_path}") from exc
        finally:
            conn.close()

    def _load_entities(self) -> dict[str, dict[str, Any]]:
        """Load and cache entities keyed by canonical ID on first access."""

        if self._entities is None:
            self._entities = {}
            for item in _read_jsonl(self.kb_dir / "entities.jsonl"):
                self._entities[item["id"]] = item
        return self._entities

    def _load_aliases(self) -> dict[str, str]:
        """Load and cache normalized aliases on first access."""

        if self._aliases is None:
            path = self.kb_dir / "aliases.json"
            try:
                contents = path.read_text(encoding="utf-8")
            except FileNotFoundError:
                self._aliases = {}
                return self._aliases
            except OSError as exc:
                raise OSError(f"Unable to read aliases artifact: {path}") from exc
            except UnicodeDecodeError as exc:
                raise ValueError(f"Invalid aliases artifact: {path}") from exc
            try:
                aliases = json.loads(contents)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid aliases JSON: {path}") from exc
            if not isinstance(aliases, dict):
                raise ValueError(f"Invalid aliases JSON object: {path}")
            if not all(
                isinstance(alias, str) and isinstance(entity_id, str)
                for alias, entity_id in aliases.items()
            ):
                raise ValueError(f"Invalid aliases JSON mapping: {path}")
            self._aliases = aliases
        return self._aliases

    def _load_chapters(self) -> dict[str, dict[str, Any]]:
        """Load and cache chapters keyed by section number on first access."""

        if self._chapters is None:
            self._chapters = {item["section"]: item for item in _read_jsonl(self.kb_dir / "chapters.jsonl")}
        return self._chapters

    def _load_chapters_by_id(self) -> dict[str, dict[str, Any]]:
        """Load and cache chapter records keyed by canonical chunk-facing ID."""

        if self._chapters_by_id is None:
            self._chapters_by_id = {
                item["id"]: item
                for item in self._load_chapters().values()
                if isinstance(item.get("id"), str)
            }
        return self._chapters_by_id

    def _load_tables(self) -> dict[str, dict[str, Any]]:
        """Load and cache tables using lowercase string identifiers."""

        if self._tables is None:
            self._tables = {str(item["number"]).lower(): item for item in _read_jsonl(self.kb_dir / "tables.jsonl")}
        return self._tables

    def _load_tables_by_id(self) -> dict[str, dict[str, Any]]:
        """Load and cache table records keyed by canonical ID such as ``table-9``."""

        if self._tables_by_id is None:
            self._tables_by_id = {
                item["id"]: item
                for item in self._load_tables().values()
                if isinstance(item.get("id"), str)
            }
        return self._tables_by_id

    def _load_chunks(self) -> dict[str, dict[str, Any]]:
        """Load and cache original chunk records keyed by canonical chunk ID."""

        if self._chunks is None:
            self._chunks = {
                item["id"]: item
                for item in _read_jsonl(self.kb_dir / "chunks.jsonl")
                if isinstance(item.get("id"), str)
            }
        return self._chunks

    def _entity_evidence(self, record_id: str) -> str | None:
        """Compose full entity evidence from summary, structure, and definition."""

        entity = self._load_entities().get(record_id) or self.get_entity(record_id)
        if not entity:
            return None
        name = entity.get("name") or record_id
        parts = [f"Entity: {name}"]
        if entity.get("kind"):
            parts.append(f"Kind: {entity['kind']}")
        if entity.get("section"):
            parts.append(f"Section: {entity['section']}")
        if entity.get("supertype"):
            parts.append(f"Supertype: {entity['supertype']}")
        if entity.get("summary_en"):
            parts.append(f"English summary: {entity['summary_en']}")
        elif entity.get("summary_zh"):
            parts.append(f"Summary: {entity['summary_zh']}")
        attributes = entity.get("attributes")
        if isinstance(attributes, dict) and attributes:
            parts.append(
                "Attributes: "
                + ", ".join(f"{key}={value}" for key, value in attributes.items())
            )
        components = entity.get("components")
        if isinstance(components, list) and components:
            lines = [
                _component_line(component)
                for component in components
                if isinstance(component, dict) and component.get("browse_name")
            ]
            if lines:
                parts.append("Components:\n" + "\n".join(lines))
        fields = entity.get("fields")
        if isinstance(fields, list) and fields:
            lines = [
                _field_line(field)
                for field in fields
                if isinstance(field, dict) and field.get("name")
            ]
            if lines:
                parts.append("Fields:\n" + "\n".join(lines))
        enum_values = entity.get("enum_values")
        if isinstance(enum_values, list) and enum_values:
            parts.append(
                "Enum values: "
                + ", ".join(
                    value.get("name", str(value))
                    if isinstance(value, dict)
                    else str(value)
                    for value in enum_values
                )
            )

        defining_tables = 0
        for table_ref in entity.get("related_tables") or []:
            table = self._table_by_reference(table_ref)
            if table is None:
                continue
            lines = _table_raw_lines(table)
            if not lines:
                continue
            defining_tables += 1
            parts.append(
                f"Defining Table {table.get('number', table.get('id', table_ref))}"
                f" - {table.get('caption', '')}:\n{lines}"
            )
        if not defining_tables:
            chapter = self.chapter(entity.get("section", "")) if entity.get("section") else None
            if chapter and isinstance(chapter.get("text"), str) and chapter["text"].strip():
                parts.append(f"Chapter {chapter.get('section', '')}:\n{chapter['text']}")
        return "\n\n".join(parts)

    def _table_by_reference(self, reference: Any) -> dict[str, Any] | None:
        if not isinstance(reference, str):
            return None
        return self._load_tables_by_id().get(reference) or self._load_tables().get(
            reference.lower()
        )

    def _table_evidence(self, record_id: str) -> str | None:
        """Return every original table raw line, including the header."""

        table = self._load_tables_by_id().get(record_id) or self._load_tables().get(
            record_id.lower()
        )
        if table is None:
            return None
        return _table_raw_lines(table) or None

    def _chapter_evidence(self, record_id: str) -> str | None:
        """Return one chapter's complete original text."""

        chapter = self._load_chapters_by_id().get(record_id) or self._load_chapters().get(
            record_id
        )
        if chapter is None:
            return None
        text = chapter.get("text")
        return text if isinstance(text, str) and text.strip() else None

    def _chunk_evidence(self, record_id: str) -> str | None:
        """Return the original chunk text rather than the FTS search snippet."""

        chunk = self._load_chunks().get(record_id)
        if chunk is None:
            return None
        text = chunk.get("text")
        return text if isinstance(text, str) and text.strip() else None

    def _load_relationships(self) -> list[dict[str, Any]]:
        """Load and cache the ordered relationship records on first access."""

        if self._relationships is None:
            self._relationships = list(_read_jsonl(self.kb_dir / "relationships.jsonl"))
        return self._relationships

    def _load_relationships_by_source(self) -> dict[str, list[dict[str, Any]]]:
        """Load and cache outgoing relationship records keyed by source."""

        if self._relationships_by_source is None:
            relationships_by_source: dict[str, list[dict[str, Any]]] = {}
            for edge in self._load_relationships():
                source = edge.get("source")
                if isinstance(source, str):
                    relationships_by_source.setdefault(source, []).append(edge)
            self._relationships_by_source = relationships_by_source
        return self._relationships_by_source


def _read_jsonl(path: Path):
    """Yield decoded JSONL records; a missing optional artifact is empty."""

    if not path.exists():
        return
    try:
        with path.open("r", encoding="utf-8") as f:
            for line_number, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Invalid JSONL record in {path} at line {line_number}"
                    ) from exc
    except OSError as exc:
        raise OSError(f"Unable to read knowledge-base artifact: {path}") from exc


def _entity_result(entity: dict[str, Any]) -> dict[str, Any]:
    """Project a full entity record into the common search-result schema."""

    return {
        "type": "entity",
        "id": entity["id"],
        "title": entity["name"],
        "kind": entity["kind"],
        "section": entity.get("section"),
        "table_number": ",".join(str(t).replace("table-", "") for t in entity.get("related_tables", [])),
        "snippet": entity.get("summary_zh") or entity.get("summary_en", ""),
    }


def _component_line(component: dict[str, Any]) -> str:
    """Render one structured instance declaration without losing its facts."""

    details = [
        f"{label}={component[key]}"
        for key, label in (
            ("node_class", "node_class"),
            ("data_type", "data_type"),
            ("reference_type", "reference_type"),
            ("type_definition", "type_definition"),
            ("modelling_rule", "modelling_rule"),
        )
        if component.get(key) not in (None, "")
    ]
    line = f"- {component['browse_name']}"
    return f"{line}: {', '.join(details)}" if details else line


def _field_line(field: dict[str, Any]) -> str:
    """Render one DataType field, including its description when present."""

    line = f"- {field['name']}"
    if field.get("type"):
        line += f" ({field['type']})"
    if field.get("description"):
        line += f": {field['description']}"
    return line


def _table_raw_lines(table: dict[str, Any]) -> str:
    """Join every original table line, preserving the header and row boundaries."""

    raw_lines = table.get("raw_lines")
    if not isinstance(raw_lines, list):
        return ""
    return "\n".join(line for line in raw_lines if isinstance(line, str))


def _fts_match_rows(
    conn: sqlite3.Connection, query: str, top_k: int
) -> list[sqlite3.Row]:
    """Return ranked FTS rows using the established query and result schema."""

    return conn.execute(
        """
        SELECT item_type, item_id, title, section, table_number,
               snippet(search_fts, 5, '[', ']', ' ... ', 18) AS snippet,
               bm25(search_fts) AS score
        FROM search_fts
        WHERE search_fts MATCH ?
        ORDER BY rank
        LIMIT ?
        """,
        (query, max(top_k * 4, 20)),
    ).fetchall()


def _literal_match_rows(
    conn: sqlite3.Connection, query: str, top_k: int
) -> list[sqlite3.Row]:
    """Return literal matches when FTS syntax or index behavior is unavailable."""

    return conn.execute(
        """
        SELECT item_type, item_id, title, section, table_number,
               substr(body, 1, 320) AS snippet, 0 AS score
        FROM search_fts
        WHERE body LIKE ? OR title LIKE ?
        LIMIT ?
        """,
        (f"%{query}%", f"%{query}%", max(top_k * 4, 20)),
    ).fetchall()


def _append_unique_search_results(
    exact_results: list[dict[str, Any]], rows: list[sqlite3.Row], top_k: int
) -> list[dict[str, Any]]:
    """Append FTS rows after exact matches without duplicating result records."""

    results = exact_results[:]
    seen = {(result.get("type"), result.get("id")) for result in results}
    for row in rows:
        marker = (row["item_type"], row["item_id"])
        if marker in seen:
            continue
        seen.add(marker)
        results.append(
            {
                "type": row["item_type"],
                "id": row["item_id"],
                "title": row["title"],
                "section": row["section"],
                "table_number": row["table_number"],
                "snippet": row["snippet"],
                "match_kind": "fts",
            }
        )
        if len(results) >= top_k:
            break
    return results[:top_k]


def _norm(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def _candidate_tokens(query: str) -> list[str]:
    """Extract likely OPC UA identifiers for exact lookup before FTS."""

    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*(?:Type|DataType|ReferenceType)?", query)
    return sorted(set(tokens), key=len, reverse=True)


def _fts_query(query: str) -> str:
    """Convert free text into a bounded FTS5 OR expression."""

    tokens = re.findall(r"[\w\u4e00-\u9fff]+", query, flags=re.UNICODE)
    if not tokens:
        return query.replace('"', '""')
    expression = " OR ".join(f'"{token}"' for token in tokens[:12])
    annex = _ANNEX_REFERENCE.search(query)
    if annex:
        expression = f'({expression}) AND section : "Annex {annex.group(1).upper()}"'
    return expression
