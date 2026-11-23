"""Default-budget integration between original evidence and a long Wiki page."""

import unittest

from opcua_kb.rag import RAGPipeline
from opcua_kb.retrieval import RetrievedRecord
from tests.test_wiki_rag import (
    WIKI_PROVENANCE,
    FixtureRetriever,
    RecordingChatModel,
    source_chunk,
    wiki_record,
)


class WikiBudgetTests(unittest.TestCase):
    def test_relevant_wiki_source_precedes_other_pages_generic_source(self):
        primary = RetrievedRecord("primary", "entity", "Primary", "", evidence="x" * 100)
        generic = RetrievedRecord("generic", "chunk", "Generic", "", evidence="diagnostics " * 90)
        relevant = RetrievedRecord(
            "namespace-rule", "chunk", "Namespace rule", "",
            evidence="NamespaceArray cache index " + "x" * 750,
        )
        wiki = RetrievedRecord(
            "wiki:navigation", "wiki", "Navigation", "", evidence="draft body",
            source_records=(generic, relevant),
        )
        result = RAGPipeline(
            retriever=FixtureRetriever([primary, wiki]), max_context_chars=1600
        ).ask("缓存命名空间索引")
        ids = [item["id"] for item in result.retrieved]
        self.assertIn("namespace-rule", ids)
        self.assertNotIn("generic", ids)

    def test_fitting_complete_chapter_precedes_its_duplicate_prefix_chunk(self):
        prefix = "Start rule. " * 20
        chunk = RetrievedRecord("prefix", "chunk", "Prefix", "", section="6.3.2", evidence=prefix)
        chapter = RetrievedRecord(
            "whole", "chapter", "Whole", "", section="6.3.2",
            evidence=prefix + "More rules. " * 30 + "TAIL RULE",
        )
        result = RAGPipeline(
            retriever=FixtureRetriever([chunk, chapter]), max_context_chars=700
        ).ask("rules")
        self.assertEqual("whole", result.retrieved[0]["id"])
        self.assertIn("TAIL RULE", result.retrieved[0]["snippet"])

    def test_wiki_cannot_evict_fitting_chapter_after_oversized_entity(self):
        large = RetrievedRecord("large", "entity", "Large", "", evidence="x" * 2000)
        chapter = RetrievedRecord("chapter", "chunk", "Chapter", "", evidence="rule " * 130)
        wiki = wiki_record("# ServerType\n\n" + "ServerType explanation. " * 8)
        model = RecordingChatModel("Normative rule [C1].")
        result = RAGPipeline(
            retriever=FixtureRetriever([large, wiki, chapter]),
            chat_model=model,
            max_context_chars=1000,
        ).ask("ServerType")

        self.assertEqual("generated", result.mode)
        self.assertEqual(["chapter"], [item["id"] for item in result.retrieved])
        self.assertEqual(chapter.evidence, result.retrieved[0]["snippet"])
        self.assertNotIn("[W1]", model.system_prompt)
        self.assertIn("wiki:servertype", result.error)

    def test_later_original_keeps_budget_before_interleaved_wiki(self):
        first = RetrievedRecord("first", "entity", "First", "", evidence="x" * 100)
        later = RetrievedRecord("later", "chunk", "Later", "", evidence="rule " * 90)
        wiki = wiki_record("# ServerType\n\n" + "ServerType explanation. " * 8)
        model = RecordingChatModel("Rules [E1][C1].")
        result = RAGPipeline(
            retriever=FixtureRetriever([first, wiki, later]),
            chat_model=model,
            max_context_chars=1000,
        ).ask("ServerType")

        self.assertEqual("generated", result.mode)
        self.assertEqual(["first", "later"], [item["id"] for item in result.retrieved])
        self.assertEqual(["[E1]", "[C1]"], [item["label"] for item in result.citations])
        context = model.user_prompt.split("Part 5 evidence:\n", 1)[1]
        self.assertLessEqual(len(context), 1000)
        self.assertIn(later.evidence, context)

    def test_wiki_excerpt_exposes_original_hash_and_ranges_in_evidence(self):
        wiki = wiki_record(
            "# ServerType\n\n"
            "ServerType exposes capabilities, status, and diagnostics.\n\n"
            + "An indivisible long paragraph. " * 200
        )
        model = RecordingChatModel("Original [C1]; Wiki draft [W1].")
        records = [source_chunk(), wiki]

        generated = RAGPipeline(
            retriever=FixtureRetriever(records),
            chat_model=model,
            max_context_chars=1000,
        ).ask("What does ServerType expose?")
        offline = RAGPipeline(
            retriever=FixtureRetriever(records),
            max_context_chars=1000,
        ).ask("What does ServerType expose?")

        self.assertEqual("generated", generated.mode)
        for evidence in (model.user_prompt, offline.answer):
            self.assertIn(WIKI_PROVENANCE["source_sha256"], evidence)
            self.assertIn("6.3.1", evidence)
            self.assertIn("225-250", evidence)

    def test_default_budget_keeps_original_and_serializes_only_the_wiki_excerpt(self):
        original = RetrievedRecord(
            "ObjectType:ServerType",
            "entity",
            "ServerType",
            "",
            evidence="x" * 10646,
        )
        explanation = "ServerType exposes capabilities, status, and diagnostics."
        wiki = wiki_record(
            "# ServerType\n\n"
            + explanation
            + "\n\n"
            + "An indivisible long paragraph. " * 200
            + "\n\n[Source section](../../source/OPC-10000-5-v1.05.06.md#L225-L250)\n"
        )
        model = RecordingChatModel("Original evidence [E1]; Wiki explanation [W1].")

        result = RAGPipeline(
            retriever=FixtureRetriever([original, wiki]),
            chat_model=model,
        ).ask("What does ServerType expose?")

        self.assertEqual("generated", result.mode)
        self.assertEqual(["entity", "wiki"], [item["type"] for item in result.retrieved])
        self.assertEqual(["[E1]", "[W1]"], [item["label"] for item in result.citations])
        self.assertEqual(original.evidence, result.retrieved[0]["snippet"])
        self.assertIn(explanation, result.retrieved[1]["snippet"])
        self.assertNotIn("An indivisible long paragraph.", result.retrieved[1]["snippet"])
        self.assertEqual(wiki.provenance, result.citations[1]["provenance"])
        context = model.user_prompt.split("Part 5 evidence:\n", 1)[1]
        self.assertLessEqual(len(context), 12000)
        self.assertEqual(
            "\n\n".join(
                f"{item['label']} {item['title']}\n{item['snippet']}"
                for item in result.retrieved
            ),
            context,
        )


if __name__ == "__main__":
    unittest.main()
