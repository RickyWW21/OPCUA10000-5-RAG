from unittest.mock import Mock
import unittest

from opcua_kb.retrieval import Part5Retriever


class RetrievalTests(unittest.TestCase):
    def test_retriever_keeps_exact_results_before_fts_results(self):
        kb = Mock()
        kb.search.return_value = [
            {"type": "entity", "id": "ObjectType:ServerType", "title": "ServerType", "snippet": "exact"},
            {"type": "chunk", "id": "sec-6.3.6", "title": "6.3.6", "snippet": "fts"},
        ]
        records = Part5Retriever(kb).retrieve("ServerType components", top_k=2)
        self.assertEqual([record.id for record in records], ["ObjectType:ServerType", "sec-6.3.6"])

    def test_retriever_deduplicates_and_rejects_non_part5_records(self):
        kb = Mock()
        kb.search.return_value = [
            {"type": "chunk", "id": "chunk-1", "title": "1 Scope", "snippet": "...", "doc": "OPC-10000-5"},
            {"type": "chunk", "id": "chunk-1", "title": "duplicate", "snippet": "...", "doc": "OPC-10000-5"},
            {"type": "chunk", "id": "foreign", "title": "Other Part", "snippet": "...", "doc": "OPC-10000-4"},
        ]
        self.assertEqual([record.id for record in Part5Retriever(kb).retrieve("x")], ["chunk-1"])

    def test_validates_limits_and_adds_relationships_for_resolved_entities(self):
        kb = Mock()
        kb.search.return_value = [{"type": "entity", "id": "e1", "title": "E", "snippet": "s"}]
        kb.get_entity.return_value = {"id": "e1"}
        kb.relationships.return_value = [{"source": "e1", "target": "e2", "relation": "HAS_COMPONENT"}]
        with self.assertRaises(ValueError): Part5Retriever(kb).retrieve("x", top_k=0)
        with self.assertRaises(ValueError): Part5Retriever(kb).retrieve("x", relationship_depth=-1)
        self.assertEqual([r.id for r in Part5Retriever(kb).retrieve("x", relationship_depth=1)], ["e1", "e2"])


if __name__ == "__main__":
    unittest.main()
