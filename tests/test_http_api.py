import hashlib
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from opcua_kb.http_api import create_app
from tests.helpers import write_jsonl, write_knowledge_base


class HttpApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        write_knowledge_base(self.root)
        (self.root / "source").mkdir()
        (self.root / "source" / "source_manifest.json").write_text(
            json.dumps({"doc": "OPC-10000-5", "sha256": "fixture"}),
            encoding="utf-8",
        )
        self.client = TestClient(create_app(self.root))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_health_reports_part5_service(self) -> None:
        response = self.client.get("/api/v1/health")

        self.assertEqual(200, response.status_code)
        self.assertEqual({"status": "ok", "doc": "OPC-10000-5"}, response.json())

    def test_query_returns_offline_answer_with_citation(self) -> None:
        response = self.client.post(
            "/api/v1/rag/query",
            json={
                "question": "What is ServerType?",
                "retrieval_mode": "fts",
                "top_k": 2,
                "relationship_depth": 0,
                "online": False,
            },
        )

        body = response.json()
        self.assertEqual(200, response.status_code)
        self.assertEqual("offline", body["mode"])
        self.assertEqual("exact", body["retrieval_mode"])
        self.assertEqual("[E1]", body["citations"][0]["label"])
        self.assertIn("[E1]", body["answer"])

    def test_query_rejects_unknown_retrieval_mode(self) -> None:
        response = self.client.post(
            "/api/v1/rag/query",
            json={"question": "ServerType", "retrieval_mode": "semantic"},
        )

        self.assertEqual(422, response.status_code)

    def test_full_evidence_and_citation_fallback_survive_http_and_history(self) -> None:
        write_jsonl(
            self.root / "kb" / "chapters.jsonl",
            [{
                "id": "sec-6.3", "section": "6.3", "title": "Server",
                "text": "Original paragraph.\n" * 40 + "TAIL FACT",
            }],
        )
        model = Mock()
        model.generate.side_effect = ["Server evidence. [E1]", "Invented source. [X99]"]
        request = {"question": "ServerType", "retrieval_mode": "fts", "top_k": 1, "online": True}

        with patch("opcua_kb.http_api._chat_model", return_value=(model, None)):
            response = self.client.post("/api/v1/rag/query", json=request)
            body = response.json()
            self.assertEqual(200, response.status_code)
            self.assertEqual("generated", body["mode"])
            self.assertIn("TAIL FACT", body["retrieved"][0]["snippet"])
            self.assertIn("TAIL FACT", model.generate.call_args.kwargs["user"])

            conversation = self.client.get(f"/api/v1/conversations/{body['conversation_id']}")
            self.assertEqual(200, conversation.status_code)
            self.assertEqual(
                body["retrieved"], conversation.json()["messages"][-1]["retrieved"]
            )
            fallback = self.client.post(
                f"/api/v1/conversations/{body['conversation_id']}/messages", json=request
            )

        self.assertEqual(200, fallback.status_code)
        self.assertEqual("offline", fallback.json()["mode"])
        self.assertIn("X99", fallback.json()["error"])
        self.assertNotIn("X99", fallback.json()["answer"])
        self.assertIn("TAIL FACT", fallback.json()["answer"])

    def test_wiki_query_keeps_wiki_provenance_in_response_and_history(self) -> None:
        source_text = "\n".join(
            ["Source line 1", "Header row", "ServerType row", "Tail row"]
            + [f"line {number}" for number in range(5, 31)]
        )
        source_path = self.root / "source" / "OPC-10000-5-v1.05.06.md"
        source_path.write_text(source_text, encoding="utf-8")
        sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
        (self.root / "source" / "source_manifest.json").write_text(
            json.dumps(
                {
                    "doc": "OPC-10000-5",
                    "version": "1.05.06",
                    "sha256": sha256,
                    "local_source_path": "source/OPC-10000-5-v1.05.06.md",
                }
            ),
            encoding="utf-8",
        )
        write_jsonl(
            self.root / "kb" / "chapters.jsonl",
            [
                {
                    "id": "sec-6.3",
                    "section": "6.3",
                    "title": "Server",
                    "start_line": 1,
                    "end_line": 30,
                    "text": source_text,
                }
            ],
        )
        write_jsonl(
            self.root / "kb" / "tables.jsonl",
            [
                {
                    "id": "table-1",
                    "number": "1",
                    "caption": "Server table",
                    "section": "6.3",
                    "start_line": 2,
                    "end_line": 10,
                    "raw_lines": ["Header row", "ServerType row"],
                }
            ],
        )
        wiki_page = self.root / "wiki" / "entities" / "servertype.md"
        wiki_page.parent.mkdir(parents=True)
        wiki_page.write_text(
            "---\n"
            "page_id: servertype\n"
            "kind: entity\n"
            "source_doc: OPC-10000-5\n"
            "source_version: 1.05.06\n"
            f"source_sha256: {sha256}\n"
            "status: draft\n"
            "updated: 2026-11-18\n"
            'sources: [{"section": "6.3", "table": "1", "lines": "2-4"}]\n'
            "---\n"
            "# ServerType Wiki\n\n"
            "ServerType navigation draft.\n",
            encoding="utf-8",
        )

        response = self.client.post(
            "/api/v1/rag/query",
            json={
                "question": "ServerType",
                "retrieval_mode": "fts",
                "top_k": 2,
                "relationship_depth": 0,
                "online": False,
            },
        )

        body = response.json()
        self.assertEqual(200, response.status_code)
        self.assertEqual("offline", body["mode"])
        types = {item["type"] for item in body["retrieved"]}
        self.assertIn("wiki", types)
        self.assertTrue(types - {"wiki"})
        self.assertIn("[W1]", body["answer"])
        self.assertIn("Wiki 草稿", body["answer"])
        self.assertIn("wiki/entities/servertype.md", body["answer"])
        wiki_citation = next(
            citation for citation in body["citations"] if citation["id"] == "wiki:servertype"
        )
        provenance = wiki_citation["provenance"]
        self.assertEqual("wiki/entities/servertype.md", provenance["path"])
        self.assertEqual("1.05.06", provenance["source_version"])
        self.assertEqual("draft", provenance["status"])
        self.assertEqual(
            [{"section": "6.3", "table": "1", "lines": "2-4"}],
            provenance["sources"],
        )
        wiki_retrieved = next(
            item for item in body["retrieved"] if item["type"] == "wiki"
        )
        self.assertEqual(provenance, wiki_retrieved["provenance"])

        conversation = self.client.get(f"/api/v1/conversations/{body['conversation_id']}")
        self.assertEqual(200, conversation.status_code)
        history = conversation.json()["messages"][-1]
        self.assertEqual(body["citations"], history["citations"])
        self.assertEqual(body["retrieved"], history["retrieved"])
        history_citation = next(
            citation
            for citation in history["citations"]
            if citation["id"] == "wiki:servertype"
        )
        self.assertEqual(
            "wiki/entities/servertype.md",
            history_citation["provenance"]["path"],
        )
        self.assertEqual(
            [{"section": "6.3", "table": "1", "lines": "2-4"}],
            history_citation["provenance"]["sources"],
        )

    def test_fts_mode_is_available_without_loading_embedding_model(self) -> None:
        response = self.client.post(
            "/api/v1/rag/query",
            json={"question": "ServerType", "retrieval_mode": "fts"},
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual("exact", response.json()["retrieval_mode"])

    def test_online_query_exposes_missing_model_configuration(self) -> None:
        with patch.dict(
            os.environ,
            {
                "DEEPSEEK_API_KEY": "",
                "OPENAI_API_KEY": "",
            },
            clear=False,
        ):
            response = self.client.post(
                "/api/v1/rag/query",
                json={"question": "ServerType", "retrieval_mode": "fts", "online": True},
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual("offline", response.json()["mode"])
        self.assertIn("API key", response.json()["error"])

    def test_search_entity_and_graph_use_existing_knowledge_base(self) -> None:
        search = self.client.get("/api/v1/search", params={"q": "ServerType", "top_k": 1})
        entity = self.client.get("/api/v1/entities/ServerType")
        graph = self.client.get("/api/v1/graph", params={"focus": "ServerType", "depth": 1})

        self.assertEqual("ObjectType:ServerType", search.json()["results"][0]["id"])
        self.assertEqual("ServerType", entity.json()["name"])
        self.assertTrue(graph.json()["nodes"])


if __name__ == "__main__":
    unittest.main()
