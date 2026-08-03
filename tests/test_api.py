"""Public ``KnowledgeBase`` regression tests."""

from __future__ import annotations

from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from opcua_kb import KnowledgeBase
from tests.helpers import write_knowledge_base


class KnowledgeBaseTests(unittest.TestCase):
    """Exercise the public query facade against real temporary artifacts."""

    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        write_knowledge_base(self.root)
        self.kb = KnowledgeBase(self.root)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_search_keeps_exact_entity_before_fts_results(self) -> None:
        results = self.kb.search("ServerType build", top_k=5)

        self.assertEqual("ObjectType:ServerType", results[0]["id"])
        self.assertEqual("DataType:BuildInfo", results[1]["id"])

    def test_relationships_are_breadth_first_and_filterable(self) -> None:
        relationships = self.kb.relationships(
            "server", depth=2, relation="has_component"
        )

        self.assertEqual(["HAS_COMPONENT"], [edge["relation"] for edge in relationships])

    def test_relationships_cache_outgoing_edges_by_source_in_file_order(self) -> None:
        self.assertIsNone(self.kb._relationships_by_source)

        relationships = self.kb.relationships("server", depth=2)
        edges = self.kb._load_relationships()

        self.assertEqual(
            edges,
            [
                edge
                for outgoing_edges in self.kb._relationships_by_source.values()
                for edge in outgoing_edges
            ],
        )
        self.assertEqual(
            ["HAS_COMPONENT", "USES_DATATYPE"],
            [edge["relation"] for edge in relationships],
        )

    def test_invalid_jsonl_reports_the_artifact_path_and_line(self) -> None:
        (self.root / "kb" / "entities.jsonl").write_text("{not json}\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, r"entities\.jsonl.*line 1"):
            KnowledgeBase(self.root).get_entity("ServerType")

    def test_fts_operational_error_falls_back_to_literal_query(self) -> None:
        index = self.root / "indexes" / "fts.sqlite"
        index.unlink()
        conn = sqlite3.connect(index)
        try:
            conn.execute(
                "CREATE TABLE search_fts ("
                "item_type, item_id, title, section, table_number, body)"
            )
            conn.execute(
                "INSERT INTO search_fts VALUES (?, ?, ?, ?, ?, ?)",
                (
                    "entity",
                    "DataType:BuildInfo",
                    "BuildInfo",
                    "12.1",
                    "",
                    "build information",
                ),
            )
            conn.commit()
        finally:
            conn.close()

        self.assertEqual("DataType:BuildInfo", self.kb.search("build", top_k=1)[0]["id"])
