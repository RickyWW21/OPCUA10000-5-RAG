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
        self.app = create_app(self.root)
        self.client = TestClient(self.app)

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
                "top_k": 2,
                "relationship_depth": 0,
                "online": False,
            },
        )

        body = response.json()
        self.assertEqual(200, response.status_code)
        self.assertEqual("offline", body["mode"])
        self.assertEqual("fts", body["retrieval_mode"])
        self.assertEqual("[E1]", body["citations"][0]["label"])
        self.assertIn("[E1]", body["answer"])

    def test_query_ignores_legacy_retrieval_mode_field(self) -> None:
        for legacy_mode in ("hybrid", "auto", "semantic"):
            with self.subTest(retrieval_mode=legacy_mode):
                response = self.client.post(
                    "/api/v1/rag/query",
                    json={
                        "question": "ServerType",
                        "retrieval_mode": legacy_mode,
                        "online": False,
                    },
                )
                self.assertEqual(200, response.status_code)
                self.assertEqual("fts", response.json()["retrieval_mode"])

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
        request = {"question": "ServerType", "top_k": 1, "online": True}

        with patch("opcua_kb.http_api.create_chat_model_from_env", return_value=(model, None)):
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

    def test_content_serves_spec_lines_and_rejects_wiki_path(self) -> None:
        lines = [f"Spec line {number}" for number in range(1, 261)]
        source_path = self.root / "source" / "OPC-10000-5-v1.05.06.md"
        source_path.write_text("\n".join(lines), encoding="utf-8")
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

        spec_response = self.client.get(
            "/api/v1/content",
            params={
                "path": "source/OPC-10000-5-v1.05.06.md",
                "start_line": 225,
                "end_line": 250,
            },
        )
        self.assertEqual(200, spec_response.status_code)
        body = spec_response.json()
        self.assertEqual("spec", body["kind"])
        self.assertEqual(225, body["start_line"])
        self.assertEqual(250, body["end_line"])
        self.assertEqual("\n".join(lines[224:250]), body["content"])

        missing_path = self.client.get("/api/v1/content")
        self.assertEqual(422, missing_path.status_code)

        wiki_response = self.client.get(
            "/api/v1/content",
            params={"path": "wiki/entities/servertype.md"},
        )
        self.assertEqual(404, wiki_response.status_code)

    def test_get_conversation_handles_legacy_wiki_messages(self) -> None:
        created = self.client.post("/api/v1/conversations", json={"title": "Legacy wiki"})
        self.assertEqual(201 if created.status_code == 201 else 200, created.status_code)
        conversation_id = created.json()["id"]
        session_id, _, _ = self.app.state.sessions.get_or_create_session(
            self.client.cookies["rag_session"]
        )
        self.app.state.sessions.append_message(
            session_id,
            conversation_id,
            role="assistant",
            content="Legacy answer with [W1] and [E1].",
            mode="offline",
            retrieval_mode="fts",
            citations=[
                {
                    "label": "[W1]",
                    "title": "ServerType Wiki",
                    "id": "wiki:servertype",
                    "source": {
                        "kind": "wiki",
                        "path": "wiki/entities/servertype.md",
                        "version": "1.05.06",
                        "status": "draft",
                        "locations": [],
                    },
                },
                {
                    "label": "[E1]",
                    "title": "ServerType",
                    "id": "ObjectType:ServerType",
                },
            ],
            retrieved=[
                {
                    "id": "wiki:servertype",
                    "type": "wiki",
                    "title": "ServerType Wiki",
                    "snippet": "Legacy wiki draft.",
                    "label": "[W1]",
                    "source": {
                        "kind": "wiki",
                        "path": "wiki/entities/servertype.md",
                        "version": "1.05.06",
                        "status": "draft",
                        "locations": [],
                    },
                }
            ],
        )

        loaded = self.client.get(f"/api/v1/conversations/{conversation_id}")
        self.assertEqual(200, loaded.status_code)
        message = loaded.json()["messages"][-1]
        for citation in message["citations"]:
            source = citation.get("source")
            if source is not None:
                self.assertNotEqual("wiki", source.get("kind"))
        for item in message["retrieved"]:
            source = item.get("source")
            if source is not None:
                self.assertNotEqual("wiki", source.get("kind"))
        wiki_citation = next(c for c in message["citations"] if c["label"] == "[W1]")
        self.assertEqual("legacy_wiki", wiki_citation["source"]["kind"])
        self.assertEqual("draft", wiki_citation["source"]["status"])
        self.assertEqual("wiki/entities/servertype.md", wiki_citation["source"]["path"])

    def test_fts_mode_is_available_without_loading_embedding_model(self) -> None:
        response = self.client.post(
            "/api/v1/rag/query",
            json={"question": "ServerType"},
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual("fts", response.json()["retrieval_mode"])

    def test_create_app_starts_without_manifest_and_returns_503_on_rag_query(self) -> None:
        with TemporaryDirectory() as tmp:
            missing_root = Path(tmp) / "missing_kb"
            session_db = Path(tmp) / "sessions.sqlite3"
            with patch.dict(os.environ, {"SESSION_DB_PATH": str(session_db)}, clear=False):
                app = create_app(missing_root)
            client = TestClient(app)

            health = client.get("/api/v1/health")
            self.assertEqual(200, health.status_code)
            conversations = client.get("/api/v1/conversations")
            self.assertEqual(200, conversations.status_code)

            rag_response = client.post(
                "/api/v1/rag/query",
                json={"question": "ServerType"},
            )
            self.assertEqual(503, rag_response.status_code)
            self.assertIn("source_manifest.json", rag_response.json()["detail"])
            conversations_after = client.get("/api/v1/conversations")
            self.assertEqual(200, conversations_after.status_code)
            self.assertEqual([], conversations_after.json()["conversations"])

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
                json={"question": "ServerType", "online": True},
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
