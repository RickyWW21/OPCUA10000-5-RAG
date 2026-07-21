"""Temporary artifact fixtures shared by knowledge-base tests."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    """Write JSONL records using the format consumed by ``KnowledgeBase``."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
    )


def write_knowledge_base(root: Path) -> None:
    """Create the smallest complete artifact set needed by API tests."""

    write_jsonl(
        root / "kb" / "entities.jsonl",
        [
            {
                "id": "ObjectType:ServerType",
                "name": "ServerType",
                "kind": "ObjectType",
                "section": "6.3",
                "related_tables": [],
                "summary_zh": "server",
            },
            {
                "id": "DataType:BuildInfo",
                "name": "BuildInfo",
                "kind": "DataType",
                "section": "12.1",
                "related_tables": [],
                "summary_en": "build information",
            },
        ],
    )
    write_jsonl(
        root / "kb" / "chapters.jsonl",
        [{"id": "sec-6.3", "section": "6.3", "title": "Server", "text": "Server chapter"}],
    )
    write_jsonl(
        root / "kb" / "tables.jsonl",
        [
            {
                "id": "table-1",
                "number": "1",
                "caption": "Server table",
                "section": "6.3",
                "raw_lines": ["header"],
            }
        ],
    )
    write_jsonl(
        root / "kb" / "relationships.jsonl",
        [
            {
                "source": "ObjectType:ServerType",
                "relation": "HAS_COMPONENT",
                "target": "DataType:BuildInfo",
            },
            {
                "source": "DataType:BuildInfo",
                "relation": "USES_DATATYPE",
                "target": "ObjectType:ServerType",
            },
        ],
    )
    aliases = root / "kb" / "aliases.json"
    aliases.write_text(
        json.dumps({"server": "ObjectType:ServerType"}), encoding="utf-8"
    )
    index = root / "indexes" / "fts.sqlite"
    index.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(index)
    try:
        conn.execute(
            "CREATE VIRTUAL TABLE search_fts USING fts5("
            "item_type, item_id, title, section, table_number, body)"
        )
        conn.execute(
            "INSERT INTO search_fts VALUES (?, ?, ?, ?, ?, ?)",
            ("entity", "DataType:BuildInfo", "BuildInfo", "12.1", "", "build information"),
        )
        conn.commit()
    finally:
        conn.close()
