from __future__ import annotations

import json
import re
import sqlite3
from collections import deque
from pathlib import Path
from typing import Any

from .graph import build_knowledge_graph


class KnowledgeBase:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.kb_dir = self.root / "kb"
        self.index_path = self.root / "indexes" / "fts.sqlite"
        self._entities: dict[str, dict[str, Any]] | None = None
        self._aliases: dict[str, str] | None = None
        self._chapters: dict[str, dict[str, Any]] | None = None
        self._tables: dict[int, dict[str, Any]] | None = None
        self._relationships: list[dict[str, Any]] | None = None

    def get_entity(self, name: str) -> dict[str, Any] | None:
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
        query = query.strip()
        if not query:
            return []

        exact_results = self._exact_search(query)
        if len(exact_results) >= top_k:
            return exact_results[:top_k]

        results = exact_results[:]
        seen = {(r.get("type"), r.get("id")) for r in results}
        if self.index_path.exists():
            sql_query = _fts_query(query)
            conn = sqlite3.connect(self.index_path)
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    """
                    SELECT item_type, item_id, title, section, table_number, snippet(search_fts, 5, '[', ']', ' ... ', 18) AS snippet,
                           bm25(search_fts) AS score
                    FROM search_fts
                    WHERE search_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (sql_query, max(top_k * 4, 20)),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = conn.execute(
                    """
                    SELECT item_type, item_id, title, section, table_number, substr(body, 1, 320) AS snippet,
                           0 AS score
                    FROM search_fts
                    WHERE body LIKE ? OR title LIKE ?
                    LIMIT ?
                    """,
                    (f"%{query}%", f"%{query}%", max(top_k * 4, 20)),
                ).fetchall()
            finally:
                conn.close()

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

    def relationships(
        self, entity: str, relation: str | None = None, depth: int = 1
    ) -> list[dict[str, Any]]:
        start = self._resolve_entity_id(entity)
        if not start:
            return []
        relationships = self._load_relationships()
        relation_norm = relation.upper() if relation else None
        results: list[dict[str, Any]] = []
        visited = {start}
        queue: deque[tuple[str, int]] = deque([(start, 0)])
        while queue:
            current, current_depth = queue.popleft()
            if current_depth >= depth:
                continue
            for edge in relationships:
                if edge.get("source") != current:
                    continue
                if relation_norm and edge.get("relation") != relation_norm:
                    continue
                results.append(edge)
                target = edge.get("target")
                if target and target not in visited:
                    visited.add(target)
                    queue.append((target, current_depth + 1))
        return results

    def chapter(self, section: str) -> dict[str, Any] | None:
        return self._load_chapters().get(section)

    def table(self, number: int | str) -> dict[str, Any] | None:
        return self._load_tables().get(str(number).lower())

    def graph(
        self,
        focus: str | None = None,
        relation: str | None = None,
        depth: int = 1,
        min_weight: int = 1,
        include_defined: bool = False,
        limit: int = 160,
    ) -> dict[str, Any]:
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
        entity = self.get_entity(name)
        if entity:
            return entity["id"]
        aliases = self._load_aliases()
        return aliases.get(_norm(name))

    def _load_entities(self) -> dict[str, dict[str, Any]]:
        if self._entities is None:
            self._entities = {}
            for item in _read_jsonl(self.kb_dir / "entities.jsonl"):
                self._entities[item["id"]] = item
        return self._entities

    def _load_aliases(self) -> dict[str, str]:
        if self._aliases is None:
            path = self.kb_dir / "aliases.json"
            self._aliases = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        return self._aliases

    def _load_chapters(self) -> dict[str, dict[str, Any]]:
        if self._chapters is None:
            self._chapters = {item["section"]: item for item in _read_jsonl(self.kb_dir / "chapters.jsonl")}
        return self._chapters

    def _load_tables(self) -> dict[str, dict[str, Any]]:
        if self._tables is None:
            self._tables = {str(item["number"]).lower(): item for item in _read_jsonl(self.kb_dir / "tables.jsonl")}
        return self._tables

    def _load_relationships(self) -> list[dict[str, Any]]:
        if self._relationships is None:
            self._relationships = list(_read_jsonl(self.kb_dir / "relationships.jsonl"))
        return self._relationships


def _read_jsonl(path: Path):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def _entity_result(entity: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "entity",
        "id": entity["id"],
        "title": entity["name"],
        "kind": entity["kind"],
        "section": entity.get("section"),
        "table_number": ",".join(str(t).replace("table-", "") for t in entity.get("related_tables", [])),
        "snippet": entity.get("summary_zh") or entity.get("summary_en", ""),
    }


def _norm(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def _candidate_tokens(query: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*(?:Type|DataType|ReferenceType)?", query)
    return sorted(set(tokens), key=len, reverse=True)


def _fts_query(query: str) -> str:
    tokens = re.findall(r"[\w\u4e00-\u9fff]+", query, flags=re.UNICODE)
    if not tokens:
        return query.replace('"', '""')
    return " OR ".join(f'"{token}"' for token in tokens[:12])
