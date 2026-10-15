import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from opcua_kb.http_api import create_app
from tests.helpers import write_knowledge_base


class SessionApiTests(unittest.TestCase):
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

    def test_new_browser_receives_anonymous_session_cookie(self) -> None:
        response = self.client.get("/api/v1/conversations")

        self.assertEqual(200, response.status_code)
        self.assertIn("rag_session", response.cookies)
        self.assertTrue(response.cookies["rag_session"])
        set_cookie = response.headers["set-cookie"].lower()
        self.assertIn("httponly", set_cookie)
        self.assertIn("samesite=lax", set_cookie)

    def test_conversation_and_message_survive_a_new_request(self) -> None:
        created = self.client.post("/api/v1/conversations", json={"title": "ServerType notes"})
        conversation_id = created.json()["id"]

        answered = self.client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            json={"question": "ServerType", "retrieval_mode": "fts", "online": False},
        )
        loaded = self.client.get(f"/api/v1/conversations/{conversation_id}")

        self.assertEqual(200, answered.status_code)
        self.assertEqual(conversation_id, answered.json()["conversation_id"])
        self.assertEqual(2, len(loaded.json()["messages"]))
        self.assertEqual("user", loaded.json()["messages"][0]["role"])
        self.assertEqual("assistant", loaded.json()["messages"][1]["role"])

    def test_second_anonymous_browser_cannot_read_first_browser_conversation(self) -> None:
        created = self.client.post("/api/v1/conversations", json={"title": "Private"})
        conversation_id = created.json()["id"]
        other_client = TestClient(self.client.app)

        response = other_client.get(f"/api/v1/conversations/{conversation_id}")

        self.assertEqual(404, response.status_code)

    def test_query_endpoint_can_create_and_persist_a_conversation(self) -> None:
        response = self.client.post(
            "/api/v1/rag/query",
            json={"question": "ServerType", "retrieval_mode": "fts", "online": False},
        )

        conversation_id = response.json()["conversation_id"]
        loaded = self.client.get(f"/api/v1/conversations/{conversation_id}")
        self.assertEqual(200, loaded.status_code)
        self.assertEqual(2, len(loaded.json()["messages"]))


if __name__ == "__main__":
    unittest.main()
