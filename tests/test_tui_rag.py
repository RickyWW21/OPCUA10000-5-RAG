import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from opcua_kb.rag import RAGAnswer
from tools import tui


class FakeProvider:
    model_name = "fake-model"
    dimension = 2

    def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


def make_root() -> Path:
    root = Path(tempfile.mkdtemp())
    (root / "source").mkdir()
    (root / "source" / "source_manifest.json").write_text(
        json.dumps({"doc": "OPC-10000-5", "sha256": "abc"}), encoding="utf-8"
    )
    (root / "kb").mkdir()
    (root / "indexes").mkdir()
    return root


class TuiRagTests(unittest.TestCase):
    def test_build_rag_retriever_can_force_fts_mode(self):
        root = make_root()
        retriever = tui.build_rag_retriever(root, mode="fts")
        self.assertIsNone(retriever.vector_index)
        self.assertIsNone(retriever.embedding_provider)

    def test_build_rag_retriever_auto_uses_valid_local_vector_artifacts(self):
        root = make_root()
        (root / "indexes" / "embeddings.jsonl").write_text("{}\n", encoding="utf-8")
        (root / "indexes" / "embeddings.meta.json").write_text("{}", encoding="utf-8")
        with patch.object(tui, "SentenceTransformerEmbeddingProvider", return_value=FakeProvider()):
            retriever = tui.build_rag_retriever(root, mode="auto")
        self.assertIsNotNone(retriever.vector_index)
        self.assertIsNotNone(retriever.embedding_provider)

    def test_format_rag_answer_includes_retrieval_mode_and_citations(self):
        answer = RAGAnswer(
            answer="[E1] ServerType",
            mode="offline",
            citations=[{"label": "[E1]", "title": "ServerType", "id": "ObjectType:ServerType"}],
            retrieved=[
                {
                    "label": "[E1]",
                    "id": "ObjectType:ServerType",
                    "type": "entity",
                    "title": "ServerType",
                }
            ],
        )
        rendered = tui.format_rag_answer(answer, retrieval_mode="hybrid")
        self.assertIn("hybrid", rendered)
        self.assertIn("[E1]", rendered)
        self.assertIn("ServerType", rendered)


if __name__ == "__main__":
    unittest.main()
