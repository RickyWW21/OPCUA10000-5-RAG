"""HTTP and security tests for normalized evidence sources and content serving."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from opcua_kb.http_api import create_app
from tests.helpers import write_jsonl


SOURCE_LINES = [f"source line {number}" for number in range(1, 31)]
SOURCE_TEXT = "\n".join(SOURCE_LINES) + "\n"


class SourceViewApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "source").mkdir()
        self.source_path = self.root / "source" / "OPC-10000-5-v1.05.06.md"
        self.source_path.write_text(SOURCE_TEXT, encoding="utf-8")
        self.sha256 = hashlib.sha256(self.source_path.read_bytes()).hexdigest()
        (self.root / "source" / "source_manifest.json").write_text(
            json.dumps(
                {
                    "doc": "OPC-10000-5",
                    "title": "OPC 10000-5 Information Model",
                    "version": "1.05.06",
                    "sha256": self.sha256,
                    # Deliberately stale absolute path; the portable basename
                    # under root/source must be used instead.
                    "local_source_path": "C:\\old\\OPC-10000-5-v1.05.06.md",
                }
            ),
            encoding="utf-8",
        )
        write_jsonl(
            self.root / "kb" / "chapters.jsonl",
            [
                {
                    "id": "sec-6.3.1",
                    "section": "6.3.1",
                    "title": "ServerType",
                    "start_line": 5,
                    "end_line": 20,
                    "text": "\n".join(SOURCE_LINES[4:20]),
                },
                {
                    "id": "sec-8.3.2",
                    "section": "8.3.2",
                    "title": "Server Object",
                    "start_line": 21,
                    "end_line": 30,
                    "text": "\n".join(SOURCE_LINES[20:30]),
                },
            ],
        )
        write_jsonl(
            self.root / "kb" / "tables.jsonl",
            [
                {
                    "id": "table-9",
                    "number": "9",
                    "caption": "ServerType components",
                    "section": "6.3.1",
                    "start_line": 6,
                    "end_line": 12,
                    "raw_lines": SOURCE_LINES[5:12],
                }
            ],
        )
        write_jsonl(
            self.root / "kb" / "entities.jsonl",
            [
                {
                    "id": "ObjectType:ServerType",
                    "name": "ServerType",
                    "kind": "ObjectType",
                    "section": "6.3.1",
                    "related_tables": ["table-9"],
                    "summary_en": "ServerType definition.",
                    "source_ref": {
                        "file": "C:\\old\\OPC-10000-5-v1.05.06.md",
                        "section": "6.3.1",
                        "start_line": 5,
                        "end_line": 20,
                    },
                },
                {
                    "id": "ObjectType:ServerDiagnosticsType",
                    "name": "ServerDiagnosticsType",
                    "kind": "ObjectType",
                    "section": "8.3.2",
                    "related_tables": [],
                    "summary_en": "Server diagnostics type.",
                },
            ],
        )
        write_jsonl(
            self.root / "kb" / "chunks.jsonl",
            [
                {
                    "id": "chunk-sec-6.3.1-001",
                    "doc": "OPC-10000-5",
                    "version": "1.05.06",
                    "section": "6.3.1",
                    "chunk_type": "section_text",
                    "text": "\n".join(SOURCE_LINES[4:20]),
                },
                {
                    "id": "chunk-table-9",
                    "doc": "OPC-10000-5",
                    "version": "1.05.06",
                    "section": "6.3.1",
                    "chunk_type": "table",
                    "table_ids": ["table-9"],
                    "text": "\n".join(SOURCE_LINES[5:12]),
                },
            ],
        )
        write_jsonl(
            self.root / "kb" / "relationships.jsonl",
            [
                {
                    "source": "ObjectType:ServerType",
                    "relation": "HAS_COMPONENT",
                    "target": "ObjectType:ServerDiagnosticsType",
                    "properties": {},
                    "source_ref": {"section": "6.3.1", "table": "table-9"},
                }
            ],
        )
        wiki_dir = self.root / "wiki" / "entities"
        wiki_dir.mkdir(parents=True)
        (wiki_dir / "servertype.md").write_text(
            "---\n"
            "page_id: servertype\n"
            "kind: entity\n"
            "entity_id: ObjectType:ServerType\n"
            "source_doc: OPC-10000-5\n"
            "source_version: 1.05.06\n"
            f"source_sha256: {self.sha256}\n"
            "status: draft\n"
            "updated: 2026-11-18\n"
            'sources: [{"section": "6.3.1", "table": "9", "lines": "6-12"}]\n'
            "---\n"
            "# ServerType\n\n"
            "Draft navigation text.\n\n"
            "[§6.3.1 Table 9 L6-L12](../../source/OPC-10000-5-v1.05.06.md#L6-L12)\n\n"
            "[ServerDiagnosticsType](serverdiagnosticstype.md)\n\n"
            "[Unsafe](https://example.com/unsafe)\n\n"
            "[Config](../../AGENTS.md)\n",
            encoding="utf-8",
        )
        (wiki_dir / "serverdiagnosticstype.md").write_text(
            "---\n"
            "page_id: serverdiagnosticstype\n"
            "kind: entity\n"
            "source_doc: OPC-10000-5\n"
            "source_version: 1.05.06\n"
            f"source_sha256: {self.sha256}\n"
            "status: draft\n"
            "sources: [{\"section\": \"8.3.2\", \"lines\": \"21-25\"}]\n"
            "---\n"
            "# ServerDiagnosticsType\n\n"
            "Another draft page.\n",
            encoding="utf-8",
        )
        (self.root / "AGENTS.md").write_text("not a knowledge page", encoding="utf-8")

        self.app = create_app(self.root)
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    # ------------------------------------------------------------------
    # Content endpoint
    # ------------------------------------------------------------------
    def test_content_returns_full_wiki_with_allowlisted_links(self) -> None:
        response = self.client.get(
            "/api/v1/content", params={"path": "wiki/entities/servertype.md"}
        )

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual("wiki", body["kind"])
        self.assertEqual("wiki/entities/servertype.md", body["path"])
        self.assertEqual("ServerType", body["title"])
        self.assertEqual("1.05.06", body["version"])
        self.assertEqual("draft", body["status"])
        self.assertIn("# ServerType", body["content"])
        self.assertEqual(
            [{"section": "6.3.1", "table": "9", "start_line": 6, "end_line": 12}],
            body["locations"],
        )
        links = {(link["path"], link.get("start_line"), link.get("end_line")): link for link in body["links"]}
        self.assertIn(("wiki/entities/serverdiagnosticstype.md", None, None), links)
        self.assertIn(("source/OPC-10000-5-v1.05.06.md", 6, 12), links)
        self.assertFalse(any("AGENTS" in link["path"] for link in body["links"]))
        self.assertFalse(any("example.com" in str(link) for link in body["links"]))

    def test_content_returns_exact_spec_range_without_truncation(self) -> None:
        response = self.client.get(
            "/api/v1/content",
            params={
                "path": "source/OPC-10000-5-v1.05.06.md",
                "start_line": 6,
                "end_line": 12,
            },
        )

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual("spec", body["kind"])
        self.assertEqual("source/OPC-10000-5-v1.05.06.md", body["path"])
        self.assertEqual(6, body["start_line"])
        self.assertEqual(12, body["end_line"])
        self.assertEqual("\n".join(SOURCE_LINES[5:12]), body["content"])
        self.assertEqual(
            [{"table": "9", "section": "6.3.1", "start_line": 6, "end_line": 12}],
            body["locations"],
        )
        self.assertNotIn("source line 5", body["content"])
        self.assertNotIn("source line 13", body["content"])

    def test_content_paths_are_restricted_to_manifest_and_wiki_pages(self) -> None:
        attempts = (
            "/api/v1/content?path=AGENTS.md",
            "/api/v1/content?path=../source/source_manifest.json",
            "/api/v1/content?path=wiki/../AGENTS.md",
            "/api/v1/content?path=wiki/index.md",
            "/api/v1/content?path=source/OPC-10000-5-v1.05.06.md/../../AGENTS.md",
            "/api/v1/content?path=C:%5CUsers%5Cadmin%5COPC-10000-5-v1.05.06.md",
        )
        for url in attempts:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(404, response.status_code)

        missing_path = self.client.get("/api/v1/content")
        self.assertEqual(422, missing_path.status_code)

    def test_content_rejects_invalid_ranges(self) -> None:
        path = "source/OPC-10000-5-v1.05.06.md"
        cases = (
            {"path": path},
            {"path": path, "start_line": 0, "end_line": 5},
            {"path": path, "start_line": 8, "end_line": 7},
            {"path": path, "start_line": 29, "end_line": 31},
            {"path": path, "start_line": -1, "end_line": 5},
        )
        for params in cases:
            with self.subTest(params=params):
                response = self.client.get("/api/v1/content", params=params)
                self.assertEqual(422, response.status_code)

    def test_symlink_escape_is_rejected(self) -> None:
        outside = self.root.parent / "outside-source.md"
        outside.write_text("SECRET OUTSIDE CONTENT\n", encoding="utf-8")
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        manifest = self.root / "source" / "source_manifest.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["local_source_path"] = "C:\\old\\escaped.md"
        manifest.write_text(json.dumps(data), encoding="utf-8")
        escaped = self.root / "source" / "escaped.md"
        wiki_escape = self.root / "wiki" / "entities" / "escaped.md"
        try:
            os.symlink(outside, escaped)
            os.symlink(outside, wiki_escape)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are not available on this host")

        response = self.client.get(
            "/api/v1/content",
            params={"path": "source/escaped.md", "start_line": 1, "end_line": 1},
        )
        wiki_response = self.client.get(
            "/api/v1/content", params={"path": "wiki/entities/escaped.md"}
        )

        self.assertEqual(404, response.status_code)
        self.assertEqual(404, wiki_response.status_code)
        self.assertNotIn("SECRET OUTSIDE", response.text)
        self.assertNotIn("SECRET OUTSIDE", wiki_response.text)

    def test_manifest_symlink_outside_root_is_rejected(self) -> None:
        outside = self.root.parent / "outside-manifest.json"
        outside.write_text(json.dumps({"doc": "OPC-10000-5"}), encoding="utf-8")
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        manifest = self.root / "source" / "source_manifest.json"
        manifest.unlink()
        try:
            os.symlink(outside, manifest)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are not available on this host")

        response = self.client.get(
            "/api/v1/content",
            params={
                "path": "source/OPC-10000-5-v1.05.06.md",
                "start_line": 1,
                "end_line": 1,
            },
        )

        self.assertEqual(404, response.status_code)

    # ------------------------------------------------------------------
    # Result enrichment
    # ------------------------------------------------------------------
    def test_query_enriches_citations_and_retrieved_with_normalized_sources(self) -> None:
        response = self.client.post(
            "/api/v1/rag/query",
            json={
                "question": "ServerType",
                "retrieval_mode": "fts",
                "top_k": 6,
                "online": False,
            },
        )

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertTrue(body["citations"])
        self.assertTrue(body["retrieved"])
        for citation in body["citations"]:
            self.assertIn("source", citation)
        for record in body["retrieved"]:
            self.assertIn("source", record)

        wiki_citation = next(
            citation for citation in body["citations"] if citation["id"] == "wiki:servertype"
        )
        wiki_source = wiki_citation["source"]
        self.assertEqual("wiki", wiki_source["kind"])
        self.assertEqual("wiki/entities/servertype.md", wiki_source["path"])
        self.assertEqual("1.05.06", wiki_source["version"])
        self.assertEqual("draft", wiki_source["status"])
        self.assertEqual(
            [{"section": "6.3.1", "table": "9", "start_line": 6, "end_line": 12}],
            wiki_source["locations"],
        )
        self.assertTrue(wiki_source["url"].startswith("/api/v1/content?path=wiki/"))

        spec_citation = next(
            citation
            for citation in body["citations"]
            if citation["id"] == "ObjectType:ServerType"
        )
        spec_source = spec_citation["source"]
        self.assertEqual("spec", spec_source["kind"])
        self.assertEqual("source/OPC-10000-5-v1.05.06.md", spec_source["path"])
        self.assertEqual("1.05.06", spec_source["version"])
        self.assertNotIn("status", spec_source)
        self.assertEqual(
            [{"section": "6.3.1", "start_line": 5, "end_line": 20}],
            spec_source["locations"],
        )
        self.assertIn("start_line=5", spec_source["url"])
        self.assertIn("end_line=20", spec_source["url"])

    def test_legacy_history_messages_are_enriched_at_read_time(self) -> None:
        response = self.client.post(
            "/api/v1/rag/query",
            json={"question": "ServerType", "retrieval_mode": "fts", "top_k": 6},
        )
        conversation_id = response.json()["conversation_id"]
        database = self.app.state.sessions.path
        conn = sqlite3.connect(database)
        try:
            rows = conn.execute(
                """
                SELECT id, citations_json, retrieved_json
                FROM messages
                WHERE conversation_id = ? AND role = 'assistant'
                """,
                (conversation_id,),
            ).fetchall()
            self.assertEqual(1, len(rows))
            citations = json.loads(rows[0][1])
            retrieved = json.loads(rows[0][2])
            for item in citations + retrieved:
                item.pop("source", None)
            conn.execute(
                "UPDATE messages SET citations_json = ?, retrieved_json = ? WHERE id = ?",
                (json.dumps(citations), json.dumps(retrieved), rows[0][0]),
            )
            conn.commit()
        finally:
            conn.close()

        loaded = self.client.get(f"/api/v1/conversations/{conversation_id}")

        self.assertEqual(200, loaded.status_code)
        message = loaded.json()["messages"][-1]
        self.assertTrue(all("source" in item for item in message["citations"]))
        self.assertTrue(all("source" in item for item in message["retrieved"]))
        spec = next(
            item
            for item in message["retrieved"]
            if item["id"] == "ObjectType:ServerType"
        )
        self.assertEqual("source/OPC-10000-5-v1.05.06.md", spec["source"]["path"])
        self.assertEqual(5, spec["source"]["locations"][0]["start_line"])
        self.assertEqual(20, spec["source"]["locations"][0]["end_line"])

    def test_enrichment_supports_entity_table_chapter_chunk_and_relationship(self) -> None:
        result = {
            "citations": [
                {"label": "[E1]", "title": "Entity", "id": "ObjectType:ServerType"},
                {"label": "[T1]", "title": "Table", "id": "table-9"},
                {"label": "[C1]", "title": "Chapter", "id": "sec-6.3.1"},
                {"label": "[C2]", "title": "Section chunk", "id": "chunk-sec-6.3.1-001"},
                {"label": "[C3]", "title": "Table chunk", "id": "chunk-table-9"},
                {
                    "label": "[R1]",
                    "title": "HAS_COMPONENT",
                    "id": "ObjectType:ServerDiagnosticsType",
                },
            ],
            "retrieved": [
                {
                    "label": "[E1]",
                    "id": "ObjectType:ServerType",
                    "type": "entity",
                    "title": "Entity",
                },
                {"label": "[T1]", "id": "table-9", "type": "table", "title": "Table"},
                {
                    "label": "[C1]",
                    "id": "sec-6.3.1",
                    "type": "chapter",
                    "title": "Chapter",
                },
                {
                    "label": "[C2]",
                    "id": "chunk-sec-6.3.1-001",
                    "type": "chunk",
                    "title": "Section chunk",
                },
                {
                    "label": "[C3]",
                    "id": "chunk-table-9",
                    "type": "chunk",
                    "title": "Table chunk",
                },
                {
                    "label": "[R1]",
                    "id": "ObjectType:ServerDiagnosticsType",
                    "type": "relationship",
                    "title": "HAS_COMPONENT",
                },
            ],
        }

        self.app.state.source_view.enrich_result(result)

        expected = {
            "ObjectType:ServerType": ("6.3.1", None, 5, 20),
            "table-9": ("6.3.1", "9", 6, 12),
            "sec-6.3.1": ("6.3.1", None, 5, 20),
            "chunk-sec-6.3.1-001": ("6.3.1", None, 5, 20),
            "chunk-table-9": ("6.3.1", "9", 6, 12),
            "ObjectType:ServerDiagnosticsType": ("6.3.1", "9", 6, 12),
        }
        for item in result["retrieved"]:
            source = item["source"]
            section, table, start, end = expected[item["id"]]
            self.assertEqual("spec", source["kind"])
            location = source["locations"][0]
            self.assertEqual(section, location["section"])
            self.assertEqual(table, location.get("table"))
            self.assertEqual(start, location["start_line"])
            self.assertEqual(end, location["end_line"])
        self.assertTrue(all("source" in citation for citation in result["citations"]))

    def test_relationship_snippet_selects_its_origin_entity(self) -> None:
        write_jsonl(
            self.root / "kb" / "relationships.jsonl",
            [
                {
                    "source": "ObjectType:ServerType",
                    "relation": "HAS_COMPONENT",
                    "target": "ObjectType:ServerDiagnosticsType",
                    "source_ref": {"section": "6.3.1"},
                },
                {
                    "source": "ObjectType:ServerDiagnosticsType",
                    "relation": "HAS_COMPONENT",
                    "target": "ObjectType:ServerDiagnosticsType",
                    "source_ref": {"section": "8.3.2"},
                },
            ],
        )
        view = self.app.state.source_view
        base = {
            "id": "ObjectType:ServerDiagnosticsType",
            "type": "relationship",
            "title": "HAS_COMPONENT",
        }

        first = view.source_for_retrieved(
            {
                **base,
                "snippet": (
                    "ObjectType:ServerType HAS_COMPONENT "
                    "ObjectType:ServerDiagnosticsType"
                ),
            }
        )
        second = view.source_for_retrieved(
            {
                **base,
                "snippet": (
                    "ObjectType:ServerDiagnosticsType HAS_COMPONENT "
                    "ObjectType:ServerDiagnosticsType"
                ),
            }
        )
        ambiguous = view.source_for_retrieved(base)

        self.assertEqual(
            [{"section": "6.3.1", "start_line": 5, "end_line": 20}],
            first["locations"],
        )
        self.assertEqual(
            [{"section": "8.3.2", "start_line": 21, "end_line": 30}],
            second["locations"],
        )
        self.assertEqual([], ambiguous["locations"])
        self.assertEqual("", ambiguous["url"])

    def test_unverifiable_record_does_not_fabricate_line_numbers(self) -> None:
        source = self.app.state.source_view.source_for_retrieved(
            {"id": "ObjectType:Missing", "type": "entity", "title": "Missing"}
        )

        self.assertIsNotNone(source)
        self.assertEqual("spec", source["kind"])
        self.assertEqual("source/OPC-10000-5-v1.05.06.md", source["path"])
        self.assertEqual([], source["locations"])
        self.assertEqual("", source["url"])

    def test_annex_chapter_keeps_its_source_location(self) -> None:
        write_jsonl(self.root / "kb" / "chapters.jsonl", [{
            "id": "sec-Annex-C", "section": "Annex C", "title": "Annex C",
            "start_line": 21, "end_line": 30, "text": "Annex text",
        }])
        source = self.app.state.source_view.source_for_retrieved(
            {"id": "sec-Annex-C", "type": "chapter"}
        )
        self.assertEqual([{
            "section": "Annex C", "start_line": 21, "end_line": 30,
        }], source["locations"])

    def test_section_intro_points_to_its_text_not_the_first_related_table(self) -> None:
        write_jsonl(self.root / "kb" / "chunks.jsonl", [{
            "id": "intro", "chunk_type": "section_text", "section": "6.3.1",
            "table_ids": ["table-9"], "text": "\n".join(SOURCE_LINES[4:6]),
        }])
        source = self.app.state.source_view.source_for_retrieved(
            {"id": "intro", "type": "chunk"}
        )
        self.assertEqual([{
            "section": "6.3.1", "start_line": 5, "end_line": 6,
        }], source["locations"])

    def test_missing_source_metadata_is_latently_unavailable(self) -> None:
        (self.root / "source" / "source_manifest.json").unlink()

        source = self.app.state.source_view.source_for_retrieved(
            {"id": "ObjectType:ServerType", "type": "entity", "title": "ServerType"}
        )

        self.assertIsNone(source)


if __name__ == "__main__":
    unittest.main()
