"""Focused tests for the Wiki-vs-original RAG evaluation harness."""

import os
import unittest
from unittest.mock import patch

from opcua_kb.retrieval import Part5Retriever
from tools.evaluate_wiki_rag import (
    CaptureChatModel,
    EvaluationError,
    NoWikiRetriever,
    RecordingRetriever,
    _build_chat_model,
    _citation_metrics,
    _parser,
    _source_checks,
)

WIKI_HIT = {
    "id": "wiki:servertype",
    "type": "wiki",
    "title": "ServerType Wiki",
    "snippet": "draft body",
    "evidence": "draft body",
    "doc": "OPC-10000-5",
    "provenance": {"path": "wiki/entities/servertype.md"},
}


class _KB:
    root = None

    def search(self, query, top_k=10):
        return [{"id": "chunk-1", "type": "chunk", "title": "Original",
                 "snippet": "spec", "evidence": "spec", "doc": "OPC-10000-5"}]

    def evidence(self, record_id, record_type):
        return "spec"


class _View:
    def __init__(self, content):
        self.content_value = content

    def content(self, path, *, start_line=None, end_line=None):
        return {"kind": "spec", "path": path, "start_line": start_line,
                "end_line": end_line, "content": self.content_value}


def _original_answer():
    return {"citations": [{
        "id": "chunk-1", "label": "[C1]", "provenance": {},
        "source": {"kind": "spec", "path": "source/OPC-10000-5-v1.05.06.md",
                   "locations": [{"section": "1", "start_line": 2, "end_line": 2}]},
    }]}


class WikiEvaluationTests(unittest.TestCase):
    def test_baseline_excludes_wiki_before_selection_not_after_mix(self):
        def fake_hits(self, question, top_k, *, has_specification):
            return [dict(WIKI_HIT)]

        with patch.object(Part5Retriever, "_wiki_hits", fake_hits):
            mixed = RecordingRetriever(_KB())
            mixed_records = mixed.retrieve("question", top_k=6)
            baseline = NoWikiRetriever(_KB())
            baseline_records = baseline.retrieve("question", top_k=6)

        self.assertIn("wiki:servertype", [record.id for record in mixed_records])
        self.assertIn("wiki:servertype", [record.id for record in mixed.returned])
        self.assertEqual(["chunk-1"], [record.id for record in baseline_records])
        self.assertEqual(["chunk-1"], [record.id for record in baseline.returned])

    def test_metrics_flag_invalid_labels_and_bad_source_lines(self):
        metrics = _citation_metrics("[C1] ok [W9] [W0] [Q1]", ["[C1]", "[W1]"])
        self.assertEqual(["[C1]"], metrics["citation_labels_used"])
        self.assertEqual(["[W9]", "[W0]", "[Q1]"], metrics["invalid_labels"])
        self.assertEqual(["[W1]"], metrics["unused_returned_labels"])

        source_info = {"path": "source/OPC-10000-5-v1.05.06.md"}
        bad = _source_checks(_original_answer(), _View("wrong"), ["one", "two"], source_info)
        self.assertFalse(bad[0]["ok"])
        self.assertIn("mismatch", bad[0]["error"])
        good = _source_checks(_original_answer(), _View("two"), ["one", "two"], source_info)
        self.assertTrue(good[0]["ok"])
        self.assertIsNone(good[0]["error"])

    def test_offline_is_default_and_online_requires_explicit_key(self):
        self.assertFalse(_parser().parse_args([]).online)
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "secret"}, clear=False):
            self.assertEqual((None, None), _build_chat_model(False, "deepseek-chat", "https://api.deepseek.com"))
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(EvaluationError):
                _build_chat_model(True, "deepseek-chat", "https://api.deepseek.com")
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "secret"}, clear=True):
            model, requested = _build_chat_model(True, "deepseek-chat", "https://api.deepseek.com")
        self.assertIsInstance(model, CaptureChatModel)
        self.assertEqual("deepseek-chat", requested)


if __name__ == "__main__":
    unittest.main()
