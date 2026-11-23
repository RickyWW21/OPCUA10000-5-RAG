"""Security and provenance tests for normalized spec-only evidence sources."""

from __future__ import annotations

import hashlib
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from opcua_kb.api import KnowledgeBase
from opcua_kb.rag import RAGPipeline
from opcua_kb.retrieval import Part5Retriever
from opcua_kb.session_store import SessionStore
from opcua_kb.source_view import SourceView, SourceViewError
from tests.helpers import write_jsonl


SOURCE_LINES = [f"source line {number}" for number in range(1, 31)]
SOURCE_TEXT = "\n".join(SOURCE_LINES) + "\n"


class SourceViewTests(unittest.TestCase):
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
            "Draft navigation text.\n",
            encoding="utf-8",
        )
        (self.root / "AGENTS.md").write_text("not a knowledge page", encoding="utf-8")

        self.kb = KnowledgeBase(self.root)
        self.sv = SourceView(self.root, self.kb)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    # ------------------------------------------------------------------
    # Content serving
    # ------------------------------------------------------------------
    def test_content_rejects_wiki_path(self) -> None:
        with self.assertRaises(SourceViewError) as ctx:
            self.sv.content("wiki/entities/servertype.md")
        self.assertIn(ctx.exception.status_code, (400, 404))

    def test_content_returns_exact_spec_range_without_truncation(self) -> None:
        body = self.sv.content(
            "source/OPC-10000-5-v1.05.06.md",
            start_line=6,
            end_line=12,
        )

        self.assertEqual("spec", body["kind"])
        self.assertEqual("source/OPC-10000-5-v1.05.06.md", body["path"])
        self.assertEqual(6, body["start_line"])
        self.assertEqual(12, body["end_line"])
        self.assertEqual("\n".join(SOURCE_LINES[5:12]), body["content"])
        self.assertEqual(
            [{"table": "9", "section": "6.3.1", "start_line": 6, "end_line": 12}],
            body["locations"],
        )
        self.assertEqual([], body["links"])
        self.assertNotIn("source line 5", body["content"])
        self.assertNotIn("source line 13", body["content"])

    def test_content_paths_are_restricted_to_manifest_only(self) -> None:
        attempts = (
            "AGENTS.md",
            "../source/source_manifest.json",
            "wiki/../AGENTS.md",
            "wiki/index.md",
            "wiki/entities/servertype.md",
            "source/OPC-10000-5-v1.05.06.md/../../AGENTS.md",
            "C:\\Users\\admin\\OPC-10000-5-v1.05.06.md",
            "",
        )
        for path in attempts:
            with self.subTest(path=path):
                with self.assertRaises(SourceViewError) as ctx:
                    self.sv.content(path, start_line=1, end_line=1)
                self.assertEqual(404, ctx.exception.status_code)

    def test_content_rejects_invalid_ranges(self) -> None:
        path = "source/OPC-10000-5-v1.05.06.md"
        cases = (
            {},
            {"start_line": 0, "end_line": 5},
            {"start_line": 8, "end_line": 7},
            {"start_line": 29, "end_line": 31},
            {"start_line": -1, "end_line": 5},
        )
        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(SourceViewError) as ctx:
                    self.sv.content(path, **kwargs)
                self.assertEqual(422, ctx.exception.status_code)

    def test_symlink_escape_is_rejected(self) -> None:
        outside = self.root.parent / "outside-source.md"
        outside.write_text("SECRET OUTSIDE CONTENT\n", encoding="utf-8")
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        manifest = self.root / "source" / "source_manifest.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["local_source_path"] = "C:\\old\\escaped.md"
        manifest.write_text(json.dumps(data), encoding="utf-8")
        escaped = self.root / "source" / "escaped.md"
        try:
            os.symlink(outside, escaped)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are not available on this host")

        with self.assertRaises(SourceViewError) as ctx:
            self.sv.content("source/escaped.md", start_line=1, end_line=1)
        self.assertEqual(404, ctx.exception.status_code)
        self.assertNotIn("SECRET OUTSIDE", ctx.exception.detail)

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

        with self.assertRaises(SourceViewError) as ctx:
            self.sv.content(
                "source/OPC-10000-5-v1.05.06.md",
                start_line=1,
                end_line=1,
            )
        self.assertEqual(404, ctx.exception.status_code)

    # ------------------------------------------------------------------
    # Result enrichment & legacy SQLite safety
    # ------------------------------------------------------------------
    def test_query_enriches_citations_and_retrieved_with_normalized_sources(self) -> None:
        answer = RAGPipeline(retriever=Part5Retriever(self.kb)).ask("ServerType", top_k=6)
        body = self.sv.enrich_result(
            {
                "answer": answer.answer,
                "mode": answer.mode,
                "citations": answer.citations,
                "retrieved": answer.retrieved,
            }
        )

        self.assertTrue(body["citations"])
        self.assertTrue(body["retrieved"])
        for citation in body["citations"]:
            self.assertIn("source", citation)
            self.assertEqual("spec", citation["source"]["kind"])
        for record in body["retrieved"]:
            self.assertIn("source", record)
            self.assertEqual("spec", record["source"]["kind"])

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
        store = SessionStore(self.root / "data" / "rag_sessions.sqlite3")
        session_id, _, _ = store.get_or_create_session(None)
        conversation = store.create_conversation(session_id, "ServerType history")
        conversation_id = conversation["id"]
        store.append_message(session_id, conversation_id, role="user", content="ServerType")
        store.append_message(
            session_id,
            conversation_id,
            role="assistant",
            content="ServerType [E1] [W1]",
            mode="generated",
            retrieval_mode="fts",
            citations=[
                {"label": "[E1]", "title": "ServerType", "id": "ObjectType:ServerType"},
                {
                    "label": "[W1]",
                    "title": "ServerType",
                    "id": "wiki:servertype",
                    "source": {
                        "kind": "wiki",
                        "path": "wiki/entities/servertype.md",
                        "url": "/api/v1/content?path=wiki/entities/servertype.md",
                    },
                },
            ],
            retrieved=[
                {
                    "label": "[E1]",
                    "id": "ObjectType:ServerType",
                    "type": "entity",
                    "title": "ServerType",
                },
                {
                    "label": "[W1]",
                    "id": "wiki:servertype",
                    "type": "wiki",
                    "title": "ServerType",
                    "source": {
                        "kind": "wiki",
                        "path": "wiki/entities/servertype.md",
                    },
                },
            ],
        )

        loaded = store.get_conversation(session_id, conversation_id)
        self.assertIsNotNone(loaded)
        message = loaded["messages"][-1]
        self.sv.enrich_result(message)

        spec_citation = next(c for c in message["citations"] if c["id"] == "ObjectType:ServerType")
        wiki_citation = next(c for c in message["citations"] if c["label"] == "[W1]")
        spec_retrieved = next(r for r in message["retrieved"] if r["id"] == "ObjectType:ServerType")
        wiki_retrieved = next(r for r in message["retrieved"] if r["label"] == "[W1]")

        self.assertEqual("source/OPC-10000-5-v1.05.06.md", spec_citation["source"]["path"])
        self.assertEqual("source/OPC-10000-5-v1.05.06.md", spec_retrieved["source"]["path"])
        self.assertEqual(5, spec_retrieved["source"]["locations"][0]["start_line"])
        self.assertEqual(20, spec_retrieved["source"]["locations"][0]["end_line"])
        self.assertEqual("legacy_wiki", wiki_citation["source"]["kind"])
        self.assertEqual("draft", wiki_citation["source"]["status"])
        self.assertEqual("legacy_wiki", wiki_retrieved["source"]["kind"])
        self.assertEqual("draft", wiki_retrieved["source"]["status"])

    def test_enrich_result_normalizes_legacy_wiki_source_and_preserves_verified_spec_locations(self) -> None:
        legacy_wiki_citation = {
            "label": "[W1]",
            "title": "ServerType",
            "id": "wiki:servertype",
            "source": {
                "kind": "wiki",
                "path": "wiki/entities/servertype.md",
                "version": "1.05.06",
                "url": "/api/v1/content?path=wiki/entities/servertype.md",
                "locations": [
                    {"section": "6.3.1", "table": "9", "start_line": 5, "end_line": 12},
                    {"section": "99.9", "start_line": 9999, "end_line": 10010},
                ],
            },
        }
        legacy_w_only_citation = {
            "label": "[W2]",
            "title": "Legacy page without prefix",
            "id": "servertype",
        }
        legacy_wiki_retrieved = {
            "label": "[W1]",
            "id": "wiki:servertype",
            "title": "ServerType",
            "source": {
                "kind": "wiki",
                "path": "wiki/entities/servertype.md",
                "locations": [{"section": "6.3.1", "table": "9", "start_line": 5, "end_line": 12}],
            },
        }
        spec_citation = {
            "label": "[E1]",
            "title": "ServerType",
            "id": "ObjectType:ServerType",
        }
        spec_retrieved = {
            "label": "[E1]",
            "id": "ObjectType:ServerType",
            "type": "entity",
            "title": "ServerType",
        }

        cit_source = self.sv.source_for_citation(legacy_wiki_citation)
        self.assertIsNotNone(cit_source)
        self.assertEqual("legacy_wiki", cit_source["kind"])
        self.assertEqual("draft", cit_source["status"])
        self.assertEqual("wiki/entities/servertype.md", cit_source["path"])
        self.assertEqual("source/OPC-10000-5-v1.05.06.md", cit_source["spec_path"])
        self.assertEqual(
            [{"section": "6.3.1", "table": "9", "start_line": 5, "end_line": 12}],
            cit_source["locations"],
        )
        self.assertNotIn("url", cit_source)

        w_only_source = self.sv.source_for_citation(legacy_w_only_citation)
        self.assertIsNotNone(w_only_source)
        self.assertEqual("legacy_wiki", w_only_source["kind"])
        self.assertEqual("", w_only_source["version"])
        self.assertEqual([], w_only_source["locations"])
        self.assertNotIn("spec_path", w_only_source)

        mismatched_version_citation = {
            "label": "[W3]",
            "title": "Old ServerType",
            "id": "wiki:servertype",
            "provenance": {
                "path": "wiki/entities/servertype.md",
                "source_version": "1.05.05",
                "sources": [{"section": "6.3.1", "lines": "5-12"}],
            },
        }
        mismatched_source = self.sv.source_for_citation(mismatched_version_citation)
        self.assertIsNotNone(mismatched_source)
        self.assertEqual("legacy_wiki", mismatched_source["kind"])
        self.assertEqual("1.05.05", mismatched_source["version"])
        self.assertEqual([], mismatched_source["locations"])
        self.assertNotIn("spec_path", mismatched_source)

        mismatched_sha_citation = {
            "label": "[W4]",
            "title": "Stale Hash ServerType",
            "id": "wiki:servertype",
            "source": {
                "kind": "wiki",
                "path": "wiki/entities/servertype.md",
                "version": "1.05.06",
                "source_sha256": "0" * 64,
                "locations": [{"section": "6.3.1", "start_line": 5, "end_line": 12}],
            },
        }
        mismatched_sha = self.sv.source_for_citation(mismatched_sha_citation)
        self.assertIsNotNone(mismatched_sha)
        self.assertEqual("legacy_wiki", mismatched_sha["kind"])
        self.assertEqual([], mismatched_sha["locations"])
        self.assertNotIn("spec_path", mismatched_sha)

        result = {
            "answer": "ServerType [E1] [W1] [W2]",
            "citations": [legacy_wiki_citation, legacy_w_only_citation, spec_citation],
            "retrieved": [legacy_wiki_retrieved, spec_retrieved],
        }

        enriched = self.sv.enrich_result(result)

        self.assertEqual("legacy_wiki", enriched["citations"][0]["source"]["kind"])
        self.assertEqual("source/OPC-10000-5-v1.05.06.md", enriched["citations"][0]["source"]["spec_path"])
        self.assertEqual("legacy_wiki", enriched["citations"][1]["source"]["kind"])
        self.assertEqual("legacy_wiki", enriched["retrieved"][0]["source"]["kind"])
        self.assertEqual("spec", enriched["citations"][2]["source"]["kind"])
        self.assertEqual(
            [{"section": "6.3.1", "start_line": 5, "end_line": 20}],
            enriched["citations"][2]["source"]["locations"],
        )
        self.assertEqual("spec", enriched["retrieved"][1]["source"]["kind"])

    def test_legacy_wiki_hash_checks_actual_file_bytes_and_shares_rejection_across_retrieved_and_citations(
        self,
    ) -> None:
        # Case 1: retrieved has mismatched hash, citation with same id only has matching version.
        # Both must share the rejected verdict (no spec_path, empty locations).
        shared_result = {
            "answer": "ServerType [W1]",
            "retrieved": [
                {
                    "label": "[W1]",
                    "id": "wiki:servertype",
                    "type": "wiki",
                    "title": "ServerType",
                    "source": {
                        "kind": "wiki",
                        "path": "wiki/entities/servertype.md",
                        "version": "1.05.06",
                        "source_sha256": "0" * 64,
                        "locations": [{"section": "6.3.1", "start_line": 5, "end_line": 12}],
                    },
                }
            ],
            "citations": [
                {
                    "label": "[W1]",
                    "id": "wiki:servertype",
                    "title": "ServerType",
                    "source": {
                        "kind": "wiki",
                        "path": "wiki/entities/servertype.md",
                        "version": "1.05.06",
                        "locations": [{"section": "6.3.1", "start_line": 5, "end_line": 12}],
                    },
                }
            ],
        }
        enriched = self.sv.enrich_result(shared_result)
        self.assertEqual([], enriched["retrieved"][0]["source"]["locations"])
        self.assertNotIn("spec_path", enriched["retrieved"][0]["source"])
        self.assertEqual([], enriched["citations"][0]["source"]["locations"])
        self.assertNotIn("spec_path", enriched["citations"][0]["source"])

        # Case 2: replace the Markdown file on disk while keeping the old manifest intact.
        # Even a citation matching the old manifest's version & hash must be rejected.
        self.source_path.write_text("tampered line 1\n" * 30, encoding="utf-8")
        stale_manifest_citation = {
            "label": "[W1]",
            "id": "wiki:servertype",
            "title": "ServerType",
            "source": {
                "kind": "wiki",
                "path": "wiki/entities/servertype.md",
                "version": "1.05.06",
                "source_sha256": self.sha256,
                "locations": [{"section": "6.3.1", "start_line": 5, "end_line": 12}],
            },
        }
        tampered_source = self.sv.source_for_citation(stale_manifest_citation)
        self.assertIsNotNone(tampered_source)
        self.assertEqual("legacy_wiki", tampered_source["kind"])
        self.assertEqual([], tampered_source["locations"])
        self.assertNotIn("spec_path", tampered_source)

    def test_source_view_uses_no_private_kb_loaders(self) -> None:
        source_view_path = Path(__file__).resolve().parents[1] / "opcua_kb" / "source_view.py"
        source_text = source_view_path.read_text(encoding="utf-8")
        for private_name in (
            "_load_chapters",
            "_load_tables",
            "_load_chunks",
            "_load_relationships",
        ):
            self.assertNotIn(private_name, source_text)

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

        self.sv.enrich_result(result)

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
        # Re-instantiate KB so cached relationships reflect the updated fixture.
        view = SourceView(self.root, KnowledgeBase(self.root))
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
        source = self.sv.source_for_retrieved(
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
        view = SourceView(self.root, KnowledgeBase(self.root))
        source = view.source_for_retrieved(
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
        view = SourceView(self.root, KnowledgeBase(self.root))
        source = view.source_for_retrieved(
            {"id": "intro", "type": "chunk"}
        )
        self.assertEqual([{
            "section": "6.3.1", "start_line": 5, "end_line": 6,
        }], source["locations"])

    def test_missing_source_metadata_is_latently_unavailable(self) -> None:
        (self.root / "source" / "source_manifest.json").unlink()

        source = self.sv.source_for_retrieved(
            {"id": "ObjectType:ServerType", "type": "entity", "title": "ServerType"}
        )

        self.assertIsNone(source)


if __name__ == "__main__":
    unittest.main()
