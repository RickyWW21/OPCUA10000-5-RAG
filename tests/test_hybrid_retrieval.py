import unittest
from unittest.mock import Mock

from opcua_kb.retrieval import Part5Retriever


class FakeProvider:
    model_name = "fake"
    dimension = 2


class HybridRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.kb = Mock()
        self.kb.search.return_value = [
            {"type": "entity", "id": "ObjectType:ServerType", "title": "ServerType", "snippet": "exact"},
            {"type": "chunk", "id": "chunk-fts", "title": "FTS", "snippet": "fts"},
        ]
        self.vector_index = Mock()
        self.vector_index.search.return_value = [
            {"type": "chunk", "id": "chunk-vector", "title": "Vector", "snippet": "vector"},
            {"type": "chunk", "id": "chunk-fts", "title": "FTS", "snippet": "fts"},
        ]

    def test_hybrid_retriever_fuses_fts_and_vector_candidates_with_exact_first(self):
        retriever = Part5Retriever(
            self.kb, vector_index=self.vector_index, embedding_provider=FakeProvider()
        )
        records = retriever.retrieve("server composition", top_k=3)
        self.assertEqual([record.id for record in records], ["ObjectType:ServerType", "chunk-fts", "chunk-vector"])
        self.assertEqual(retriever.last_mode, "hybrid")

    def test_missing_vector_index_falls_back_to_fts(self):
        retriever = Part5Retriever(self.kb, vector_index=None, embedding_provider=FakeProvider())
        retriever.retrieve("server", top_k=2)
        self.assertEqual(retriever.last_mode, "fts")

    def test_invalid_weights_are_rejected(self):
        with self.assertRaises(ValueError):
            Part5Retriever(self.kb, fts_weight=0.0, vector_weight=0.0)
        with self.assertRaises(ValueError):
            Part5Retriever(self.kb, fts_weight=-1.0)


if __name__ == "__main__":
    unittest.main()
