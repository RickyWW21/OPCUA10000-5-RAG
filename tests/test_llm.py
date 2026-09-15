from __future__ import annotations

import json
import os
import unittest
from unittest import mock
from urllib.request import Request

from opcua_kb.llm import LLMError, OpenAICompatibleChatModel


class RecordingTransport:
    def __init__(self, response: object) -> None:
        self.response = json.dumps(response).encode("utf-8")
        self.url = ""
        self.headers: dict[str, str] = {}
        self.payload: dict[str, object] = {}

    def __call__(self, request: Request, timeout: float) -> bytes:
        self.url = request.full_url
        self.headers = dict(request.headers)
        self.payload = json.loads(request.data.decode("utf-8"))
        return self.response


class LLMTests(unittest.TestCase):
    def test_client_posts_openai_compatible_payload_and_returns_content(self) -> None:
        request = RecordingTransport({"choices": [{"message": {"content": "grounded answer"}}]})
        model = OpenAICompatibleChatModel(
            api_key="test-key", model="deepseek-chat", base_url="https://example.test/", transport=request
        )
        self.assertEqual("grounded answer", model.generate(system="system", user="user"))
        self.assertEqual("https://example.test/chat/completions", request.url)
        self.assertEqual("Bearer test-key", request.headers["Authorization"])
        self.assertEqual("user", request.payload["messages"][1]["content"])

    def test_client_rejects_missing_key_and_malformed_response(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(LLMError):
                OpenAICompatibleChatModel(api_key="", model="m", base_url="https://example.test")
        bad = RecordingTransport({"choices": []})
        model = OpenAICompatibleChatModel(api_key="k", base_url="https://example.test", transport=bad)
        with self.assertRaises(LLMError):
            model.generate(system="s", user="u")

    def test_constructor_key_precedence(self) -> None:
        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "deep", "OPENAI_API_KEY": "open"}):
            self.assertEqual("deep", OpenAICompatibleChatModel().api_key)
            self.assertEqual("explicit", OpenAICompatibleChatModel(api_key="explicit").api_key)


if __name__ == "__main__":
    unittest.main()
