import json
import tempfile
import unittest
from pathlib import Path

from opcua_kb.vector_index import VectorIndex, VectorIndexError


class FakeProvider:
    model_name = "fake"
    dimension = 2

    def __init__(self, vectors):
        self.vectors = vectors

    def embed(self, texts):
        return [self.vectors[text] for text in texts]


class OtherProvider(FakeProvider):
    model_name = "other"


class VectorIndexTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.records = [
            {"id": "e1", "type": "entity", "title": "ServerType", "text": "server metadata", "doc": "OPC-10000-5"},
            {"id": "e2", "type": "entity", "title": "AlarmType", "text": "alarm metadata", "doc": "OPC-10000-5"},
            {"id": "foreign", "type": "chunk", "title": "Other", "text": "other", "doc": "OPC-10000-4"},
        ]
        self.provider = FakeProvider({"server metadata": [1.0, 0.0], "alarm metadata": [0.0, 1.0], "server": [0.9, 0.1]})

    def test_vector_index_builds_persists_and_searches_records(self):
        index = VectorIndex(self.root)
        index.build(self.records, self.provider, source_hash="abc")
        result = index.search("server", self.provider, top_k=1)
        self.assertEqual(result[0]["id"], "e1")
        self.assertTrue((self.root / "indexes" / "embeddings.jsonl").exists())
        self.assertTrue((self.root / "indexes" / "embeddings.meta.json").exists())

    def test_vector_index_rejects_stale_or_foreign_metadata(self):
        index = VectorIndex(self.root)
        index.build(self.records, self.provider, source_hash="abc")
        with self.assertRaises(VectorIndexError):
            index.search("server", OtherProvider(self.provider.vectors), top_k=1)

    def test_vector_index_rejects_invalid_top_k_and_missing_index(self):
        index = VectorIndex(self.root)
        with self.assertRaises(VectorIndexError):
            index.search("server", self.provider, top_k=1)
        with self.assertRaises(ValueError):
            index.build(self.records, self.provider, source_hash="")


if __name__ == "__main__":
    unittest.main()
