import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from opcua_kb.retrieval import Part5Retriever, RetrievalError, RetrievedRecord


class RetrievalTests(unittest.TestCase):
    def test_fts_chapter_intro_is_not_demoted_below_lower_ranked_tables(self):
        kb = Mock()
        kb.search.return_value = [
            {"type": "table", "id": "table-C.1", "title": "Dictionary",
             "snippet": "fields", "match_kind": "exact"},
            {"type": "chunk", "id": "annex-intro", "title": "Annex intro",
             "snippet": "Informative; deprecated.", "match_kind": "fts"},
            {"type": "table", "id": "table-C.2", "title": "Other table",
             "snippet": "other fields", "match_kind": "fts"},
        ]
        records = Part5Retriever(kb).retrieve("Annex C status", top_k=2)
        self.assertEqual(["table-C.1", "annex-intro"], [record.id for record in records])

    def _rooted_kb(self, manifest: object) -> Mock:
        root = Path(tempfile.mkdtemp())
        source = root / "source"
        source.mkdir()
        (source / "source_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        kb = Mock()
        kb.root = root
        return kb

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

    def test_rejects_unverified_or_foreign_knowledge_base_root(self):
        foreign = self._rooted_kb({"doc": "OPC-10000-4"})
        with self.assertRaises(ValueError):
            Part5Retriever(foreign)

        missing = Mock()
        missing.root = Path(tempfile.mkdtemp())
        with self.assertRaises(ValueError):
            Part5Retriever(missing)

    def test_accepts_verified_part5_knowledge_base_root(self):
        kb = self._rooted_kb({"doc": "OPC-10000-5"})
        kb.search.return_value = [{"type": "chunk", "id": "c1", "title": "Scope", "snippet": "Part 5"}]
        records = Part5Retriever(kb).retrieve("scope")
        self.assertEqual([record.id for record in records], ["c1"])

    def test_hydrates_full_evidence_from_a_real_public_knowledge_base_method(self):
        kb = Mock()
        kb.search.return_value = [
            {"type": "chunk", "id": "chunk-1", "title": "Scope", "snippet": "short"}
        ]
        kb.evidence.return_value = "complete original chunk text"

        records = Part5Retriever(kb).retrieve("scope")

        self.assertEqual("complete original chunk text", records[0].evidence)
        self.assertEqual("short", records[0].snippet)
        kb.evidence.assert_called_once_with("chunk-1", "chunk")

    def test_lightweight_doubles_fall_back_to_snippet_instead_of_mock_attributes(self):
        kb = Mock()
        kb.search.return_value = [
            {"type": "chunk", "id": "chunk-1", "title": "Scope", "snippet": "short"}
        ]

        records = Part5Retriever(kb).retrieve("scope")

        self.assertEqual("short", records[0].snippet)
        self.assertIsNone(records[0].evidence)

    def test_retrieved_record_evidence_default_keeps_positional_compatibility(self):
        record = RetrievedRecord("id", "chunk", "Title", "snippet")

        self.assertIsNone(record.evidence)
        self.assertEqual("OPC-10000-5", record.doc)

    def test_retriever_is_fts_only_and_stateless(self):
        kb = self._rooted_kb({"doc": "OPC-10000-5"})
        wiki_dir = kb.root / "wiki" / "entities"
        wiki_dir.mkdir(parents=True)
        (wiki_dir / "servertype.md").write_text("# ServerType\nWiki draft\n", encoding="utf-8")
        kb.search.return_value = [
            {"type": "chunk", "id": "chunk-1", "title": "6.3.1", "snippet": "ServerType spec"}
        ]

        retriever = Part5Retriever(kb)
        self.assertEqual("fts", retriever.mode)
        self.assertFalse(hasattr(retriever, "last_mode"))
        with self.assertRaises(AttributeError):
            retriever.mode = "hybrid"  # type: ignore[misc]
        with self.assertRaises(TypeError):
            Part5Retriever(kb, vector_index=object())  # type: ignore[call-arg]
        with self.assertRaises(TypeError):
            Part5Retriever(kb, embedding_provider=object())  # type: ignore[call-arg]

        records = retriever.retrieve("ServerType", top_k=4)
        self.assertEqual(["chunk-1"], [record.id for record in records])
        self.assertTrue(
            all(
                record.type != "wiki"
                and not hasattr(record, "companion_sources")
                and not record.source_records
                for record in records
            )
        )

    def test_retriever_manifest_guard_rejects_non_part5(self):
        foreign = self._rooted_kb({"doc": "OPC-10000-4"})
        with self.assertRaises(RetrievalError):
            Part5Retriever(foreign)

        with tempfile.TemporaryDirectory() as tmp:
            missing = Mock()
            missing.root = Path(tmp)
            with self.assertRaises(RetrievalError):
                Part5Retriever(missing)

            invalid = Mock()
            invalid.root = Path(tmp)
            (Path(tmp) / "source").mkdir()
            (Path(tmp) / "source" / "source_manifest.json").write_text("{bad json", encoding="utf-8")
            with self.assertRaises(RetrievalError):
                Part5Retriever(invalid)


if __name__ == "__main__":
    unittest.main()
