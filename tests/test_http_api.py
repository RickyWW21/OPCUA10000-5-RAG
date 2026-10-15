import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from opcua_kb.http_api import create_app
from tests.helpers import write_knowledge_base


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
