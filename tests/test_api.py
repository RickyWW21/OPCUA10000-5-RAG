"""Public ``KnowledgeBase`` regression tests."""

from __future__ import annotations

from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from opcua_kb import KnowledgeBase
from tests.helpers import write_jsonl, write_knowledge_base


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

    def test_chinese_namespace_paraphrases_recall_english_original(self) -> None:
        conn = sqlite3.connect(self.root / "indexes/fts.sqlite")
        try:
            conn.execute(
                "INSERT INTO search_fts VALUES (?, ?, ?, ?, ?, ?)",
                ("chunk", "namespace-rule", "NamespaceArray", "6.3.1", "",
                 "NamespaceArray entries may be cached by a Session client."),
            )
            conn.commit()
        finally:
            conn.close()
        for question in ("命名空间列表何时允许变化？", "缓存命名空间索引需要检查什么？"):
            with self.subTest(question=question):
                results = self.kb.search(question, top_k=1)
                self.assertTrue(results)
                self.assertEqual("namespace-rule", results[0]["id"])

    def test_part_number_is_not_mistaken_for_a_chapter_number(self) -> None:
        write_jsonl(self.root / "kb" / "chapters.jsonl", [{
            "id": "sec-5", "section": "5", "title": "Common Attributes", "text": "Attributes",
        }])
        conn = sqlite3.connect(self.root / "indexes/fts.sqlite")
        try:
            conn.execute(
                "INSERT INTO search_fts VALUES (?, ?, ?, ?, ?, ?)",
                ("chunk", "scope-rule", "Scope", "1", "", "Scope of this Part."),
            )
            conn.commit()
        finally:
            conn.close()
        self.assertEqual("scope-rule", self.kb.search("第5部分的范围是什么？", top_k=1)[0]["id"])

    def test_chinese_annex_reference_limits_results_to_that_annex(self) -> None:
        write_jsonl(self.root / "kb" / "chapters.jsonl", [{
            "id": "sec-Annex-C", "section": "Annex C", "title": "Binary", "text": "Informative",
        }])
        conn = sqlite3.connect(self.root / "indexes/fts.sqlite")
        try:
            conn.executemany(
                "INSERT INTO search_fts VALUES (?, ?, ?, ?, ?, ?)",
                [("chunk", "intro-c", "Annex", "Annex C", "", "Annex status informative"),
                 ("chunk", "intro-d", "Annex", "Annex D", "", "Annex status informative")],
            )
            conn.commit()
        finally:
            conn.close()
        self.assertEqual(
            ["sec-Annex-C", "intro-c"],
            [item["id"] for item in self.kb.search("附录C的状态", top_k=4)],
        )

    def test_relationships_are_breadth_first_and_filterable(self) -> None:
        relationships = self.kb.relationships(
            "server", depth=2, relation="has_component"
        )

        self.assertEqual(["HAS_COMPONENT"], [edge["relation"] for edge in relationships])

    def test_relationships_cache_outgoing_edges_by_source_in_file_order(self) -> None:
        write_jsonl(
            self.root / "kb" / "relationships.jsonl",
            [
                {
                    "source": "ObjectType:ServerType",
                    "relation": "FIRST",
                    "target": "DataType:BuildInfo",
                },
                {
                    "source": "DataType:BuildInfo",
                    "relation": "THIRD",
                    "target": "ObjectType:ServerType",
                },
                {
                    "source": "ObjectType:ServerType",
                    "relation": "SECOND",
                    "target": "ObjectType:ServerType",
                },
            ],
        )
        self.assertIsNone(self.kb._relationships_by_source)
        self.kb._load_relationships()
        self.assertIsNone(self.kb._relationships_by_source)
        self.kb.graph()
        self.assertIsNone(self.kb._relationships_by_source)

        relationships = self.kb.relationships("server", depth=2)

        self.assertEqual(
            ["FIRST", "SECOND"],
            [
                edge["relation"]
                for edge in self.kb._relationships_by_source["ObjectType:ServerType"]
            ],
        )
        self.assertEqual(
            ["THIRD"],
            [
                edge["relation"]
                for edge in self.kb._relationships_by_source["DataType:BuildInfo"]
            ],
        )
        self.assertEqual(
            ["FIRST", "SECOND", "THIRD"],
            [edge["relation"] for edge in relationships],
        )

    def test_relationships_skip_malformed_sources_and_keep_cache_usable(self) -> None:
        write_jsonl(
            self.root / "kb" / "relationships.jsonl",
            [
                {
                    "source": ["invalid"],
                    "relation": "INVALID",
                    "target": "DataType:BuildInfo",
                },
                {
                    "source": "ObjectType:ServerType",
                    "relation": "HAS_COMPONENT",
                    "target": "DataType:BuildInfo",
                },
            ],
        )

        first_results = self.kb.relationships("server")
        second_results = self.kb.relationships("server")

        self.assertEqual(["HAS_COMPONENT"], [edge["relation"] for edge in first_results])
        self.assertEqual(first_results, second_results)
        self.assertEqual(
            ["HAS_COMPONENT"],
            [
                edge["relation"]
                for edge in self.kb._relationships_by_source["ObjectType:ServerType"]
            ],
        )

    def test_invalid_jsonl_reports_the_artifact_path_and_line(self) -> None:
        (self.root / "kb" / "entities.jsonl").write_text("{not json}\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, r"entities\.jsonl.*line 1"):
            KnowledgeBase(self.root).get_entity("ServerType")

    def test_evidence_hydrates_full_entity_table_chapter_and_chunk_text(self) -> None:
        write_jsonl(
            self.root / "kb" / "entities.jsonl",
            [
                {
                    "id": "ObjectType:ServerType",
                    "name": "ServerType",
                    "kind": "ObjectType",
                    "section": "6.3.1",
                    "supertype": "BaseObjectType",
                    "attributes": {"IsAbstract": "False"},
                    "components": [
                        {
                            "browse_name": "ServerArray",
                            "data_type": "String[]",
                            "node_class": "Variable",
                            "reference_type": "HasProperty",
                            "type_definition": "PropertyType",
                            "modelling_rule": "Mandatory",
                        }
                    ],
                    "fields": [],
                    "enum_values": [],
                    "related_tables": ["table-9"],
                    "summary_en": "ServerType defines the capabilities of an OPC UA Server.",
                }
            ],
        )
        write_jsonl(
            self.root / "kb" / "tables.jsonl",
            [
                {
                    "id": "table-9",
                    "number": "9",
                    "caption": "ServerType definition",
                    "section": "6.3.1",
                    "raw_lines": [
                        "Attribute,Value",
                        "BrowseName,ServerType",
                        "HasProperty,Variable,ServerArray,String[]",
                        "HasComponent,Method,RequestServerStateChange,Defined in 9.4,Optional",
                    ],
                }
            ],
        )
        write_jsonl(
            self.root / "kb" / "chapters.jsonl",
            [
                {
                    "id": "sec-6.3.1",
                    "section": "6.3.1",
                    "title": "ServerType",
                    "text": "6.3.1 ServerType\n\nComplete chapter text beyond any search snippet.",
                }
            ],
        )
        write_jsonl(
            self.root / "kb" / "chunks.jsonl",
            [
                {
                    "id": "chunk-sec-6.3.1-001",
                    "type": "chunk",
                    "section": "6.3.1",
                    "text": "Original chunk text that is not the FTS highlighted snippet.",
                }
            ],
        )
        kb = KnowledgeBase(self.root)

        entity_evidence = kb.evidence("ObjectType:ServerType", "entity")
        self.assertIn("ServerType defines the capabilities", entity_evidence)
        self.assertIn("Table 9", entity_evidence)
        self.assertIn("Attribute,Value", entity_evidence)
        self.assertIn("RequestServerStateChange", entity_evidence)
        self.assertEqual(
            "\n".join(
                [
                    "Attribute,Value",
                    "BrowseName,ServerType",
                    "HasProperty,Variable,ServerArray,String[]",
                    "HasComponent,Method,RequestServerStateChange,Defined in 9.4,Optional",
                ]
            ),
            kb.evidence("table-9", "table"),
        )
        self.assertEqual(
            "6.3.1 ServerType\n\nComplete chapter text beyond any search snippet.",
            kb.evidence("sec-6.3.1", "chapter"),
        )
        self.assertEqual(
            "Original chunk text that is not the FTS highlighted snippet.",
            kb.evidence("chunk-sec-6.3.1-001", "chunk"),
        )
        self.assertIsNone(kb.evidence("missing-id", "entity"))

    def test_entity_evidence_falls_back_to_its_original_chapter(self) -> None:
        evidence = self.kb.evidence("ObjectType:ServerType", "entity")

        self.assertIn("server", evidence)
        self.assertIn("Server chapter", evidence)

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
