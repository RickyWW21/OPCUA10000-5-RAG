"""Lazy, read-only access to the generated knowledge-base artifacts."""

from __future__ import annotations

import json
import re
import sqlite3
from collections import deque
from pathlib import Path
from typing import Any

from .graph import build_knowledge_graph


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
        self._tables: dict[str, dict[str, Any]] | None = None
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
        exact_results = self._exact_search(query)
        if len(exact_results) >= top_k:
            return exact_results[:top_k]

        rows = self._search_fts(query, top_k) if self.index_path.exists() else []
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

        section_match = re.search(r"(?<![A-Za-z.])(\d+(?:\.\d+){0,5})(?![A-Za-z.])", query)
        if section_match:
            chapter = self.chapter(section_match.group(1))
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

    def _load_tables(self) -> dict[str, dict[str, Any]]:
        """Load and cache tables using lowercase string identifiers."""

        if self._tables is None:
            self._tables = {str(item["number"]).lower(): item for item in _read_jsonl(self.kb_dir / "tables.jsonl")}
        return self._tables

    def _load_relationships(self) -> list[dict[str, Any]]:
        """Load and cache the ordered relationship records on first access."""

        if self._relationships is None:
            self._relationships = list(_read_jsonl(self.kb_dir / "relationships.jsonl"))
        return self._relationships

    def _load_relationships_by_source(self) -> dict[str, list[dict[str, Any]]]:
        """Load and cache outgoing relationship records keyed by source."""

        if self._relationships_by_source is None:
            self._relationships_by_source = {}
            for edge in self._load_relationships():
                source = edge.get("source")
                if source:
                    self._relationships_by_source.setdefault(source, []).append(edge)
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
    return " OR ".join(f'"{token}"' for token in tokens[:12])
