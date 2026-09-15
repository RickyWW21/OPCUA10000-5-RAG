import sys
import unittest
from unittest import mock

from opcua_kb.embeddings import (
    EmbeddingError,
    SentenceTransformerEmbeddingProvider,
    cosine_similarity,
    rank_by_cosine,
)


class EmbeddingTests(unittest.TestCase):
    def test_cosine_similarity_and_ranking_are_deterministic(self):
        self.assertAlmostEqual(cosine_similarity([1.0, 0.0], [0.8, 0.2]), 0.9701425, places=5)
        self.assertEqual(rank_by_cosine([1.0, 0.0], [[0.2, 0.9], [0.9, 0.1]]), [1, 0])

    def test_sentence_transformer_import_is_lazy_and_missing_dependency_is_typed(self):
        with mock.patch.dict(sys.modules, {"sentence_transformers": None}):
            with self.assertRaises(EmbeddingError):
                SentenceTransformerEmbeddingProvider("missing-model")

    def test_zero_and_mismatched_vectors_are_rejected(self):
        with self.assertRaises(ValueError):
            cosine_similarity([0.0, 0.0], [1.0, 0.0])
        with self.assertRaises(ValueError):
            cosine_similarity([1.0], [1.0, 0.0])


if __name__ == "__main__":
    unittest.main()
