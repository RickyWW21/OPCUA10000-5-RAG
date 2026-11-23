import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from opcua_kb.llm import LLMError
from opcua_kb.rag import RAGPipeline
from opcua_kb.retrieval import RetrievedRecord


class FixtureRetriever:
    def retrieve(self, question, *, top_k=6, relationship_depth=0):
        return [RetrievedRecord("server-type", "entity", "ServerType", "A ServerType defines server metadata.")][:top_k]


class EvidenceRetriever:
    def __init__(self, records):
        self.records = records

    def retrieve(self, question, *, top_k=6, relationship_depth=0):
        return self.records[:top_k]


class RecordingChatModel:
    def __init__(self, answer): self.answer, self.user_prompt, self.calls = answer, "", 0
    def generate(self, *, system, user, temperature=0.0):
        self.calls += 1
        self.user_prompt = user
        return self.answer


class FailingChatModel:
    def generate(self, *, system, user, temperature=0.0): raise LLMError("offline")


class RAGTests(unittest.TestCase):
    def test_flattened_table_9_footnotes_are_explained_without_rewriting_source(self):
        raw = (
            "HasComponent,Variable,ServerStatus1,ServerStatusDataType ServerStatusType,Mandatory\n"
            "HasComponent,Object,ServerCapabilities1,- ServerCapabilitiesType,Mandatory\n"
            "HasComponent,Object,ServerDiagnostics1,- ServerDiagnosticsType,Mandatory\n"
            "HasComponent,Object,ServerRedundancy1,- ServerRedundancyType,Mandatory\n"
            "HasComponent,Object,Channel1,- ChannelType,Optional"
        )
        for kind in ("entity", "table", "chunk", "chapter"):
            with self.subTest(kind=kind):
                record = RetrievedRecord(
                    "table-9", kind, "ServerType", "", section="6.3.1",
                    table_number="9", evidence=raw,
                )
                result = RAGPipeline(retriever=EvidenceRetriever([record])).ask("Members?")
                text = result.retrieved[0]["snippet"]
                self.assertTrue(text.startswith(raw))
                for clarification in (
                    "ServerStatus1 -> ServerStatus",
                    "ServerCapabilities1 -> ServerCapabilities",
                    "ServerDiagnostics1 -> ServerDiagnostics",
                    "ServerRedundancy1 -> ServerRedundancy",
                ):
                    self.assertIn(clarification, text)
                self.assertNotIn("Channel1 -> Channel", text)
                self.assertIn(raw, result.answer)
                self.assertEqual(raw, record.evidence)

    def test_table_9_name_notes_obey_evidence_budget_and_do_not_affect_other_tables(self):
        raw = "HasComponent,Object,ServerCapabilities1,- ServerCapabilitiesType,Mandatory"
        record = RetrievedRecord(
            "table-9", "table", "Definition", "", section="6.3.1",
            table_number="9", evidence=raw,
        )
        model = RecordingChatModel("ServerCapabilities [T1].")
        result = RAGPipeline(
            retriever=EvidenceRetriever([record]), chat_model=model,
            max_context_chars=len(f"[T1] Definition\n{raw}"),
        ).ask("Members?")
        self.assertEqual("offline", result.mode)
        self.assertEqual(0, model.calls)
        self.assertEqual([], result.citations)

        other = RetrievedRecord(
            "table-999", "table", "Other", "", section="8.1",
            table_number="999", evidence=raw,
        )
        result = RAGPipeline(retriever=EvidenceRetriever([other])).ask("Members?")
        self.assertEqual(raw, result.retrieved[0]["snippet"])

    def test_pipeline_offline_answer_contains_part5_citations(self):
        result = RAGPipeline(retriever=FixtureRetriever()).ask("What is ServerType?", top_k=2)
        self.assertEqual(result.mode, "offline")
        self.assertIn("OPC UA 10000-5", "OPC UA 10000-5 " + result.answer)
        self.assertEqual(result.citations[0]["label"], "[E1]")
        self.assertIn("[E1]", result.answer)

    def test_pipeline_sends_bounded_context_to_model_and_returns_generated_answer(self):
        model = RecordingChatModel("ServerType is defined in Part 5. [E1]")
        result = RAGPipeline(retriever=FixtureRetriever(), chat_model=model, max_context_chars=500).ask("What is ServerType?")
        self.assertEqual(result.mode, "generated")
        self.assertTrue(result.answer.startswith("ServerType"))
        self.assertIn("[E1]", model.user_prompt)
        self.assertLessEqual(len(model.user_prompt), 1000)

    def test_pipeline_converts_model_failure_to_offline_mode(self):
        result = RAGPipeline(retriever=FixtureRetriever(), chat_model=FailingChatModel()).ask("x")
        self.assertEqual(result.mode, "offline")
        self.assertTrue(result.error)

    def test_pipeline_sends_complete_evidence_beyond_the_search_snippet(self):
        retriever = EvidenceRetriever(
            [
                RetrievedRecord(
                    "chunk-sec-6.3.1-001",
                    "chunk",
                    "ServerType",
                    "search snippet",
                    evidence="Original chunk text. The table tail is only in the evidence body.",
                )
            ]
        )
        model = RecordingChatModel("The tail is present. [C1]")

        result = RAGPipeline(retriever=retriever, chat_model=model, max_context_chars=2000).ask(
            "What does the table tail say?"
        )

        self.assertEqual("generated", result.mode)
        self.assertIn("The table tail is only in the evidence body.", model.user_prompt)
        self.assertNotIn("search snippet", model.user_prompt)
        self.assertIn("[C1]", model.user_prompt)
        self.assertEqual("chunk-sec-6.3.1-001", result.retrieved[0]["id"])
        self.assertEqual(
            "Original chunk text. The table tail is only in the evidence body.",
            result.retrieved[0]["snippet"],
        )

    def test_pipeline_labels_only_selected_evidence_and_discloses_omissions(self):
        first = RetrievedRecord("e1", "entity", "First", "ignored", evidence="A" * 10)
        second = RetrievedRecord("e2", "chunk", "Second", "ignored", evidence="B" * 10)
        exact_unit = f"[E1] First\n{'A' * 10}"
        model = RecordingChatModel("[E1] ok")

        result = RAGPipeline(
            retriever=EvidenceRetriever([first, second]),
            chat_model=model,
            max_context_chars=len(exact_unit),
        ).ask("question")

        self.assertEqual("generated", result.mode)
        self.assertEqual(["e1"], [item["id"] for item in result.retrieved])
        self.assertEqual(["[E1]"], [item["label"] for item in result.citations])
        self.assertIn("A" * 10, model.user_prompt)
        self.assertNotIn("B" * 10, model.user_prompt)
        self.assertNotIn("[C1]", model.user_prompt)
        self.assertIn("e2", result.error)

    def test_pipeline_returns_offline_without_model_call_when_nothing_fits(self):
        model = RecordingChatModel("[E1] impossible")
        record = RetrievedRecord("e1", "entity", "First", "ignored", evidence="full evidence")

        result = RAGPipeline(
            retriever=EvidenceRetriever([record]),
            chat_model=model,
            max_context_chars=1,
        ).ask("question")

        self.assertEqual("offline", result.mode)
        self.assertEqual(0, model.calls)
        self.assertEqual([], result.citations)
        self.assertEqual([], result.retrieved)
        self.assertIn("e1", result.error)

    def test_pipeline_skips_oversized_unit_without_cutting_table_rows(self):
        table = RetrievedRecord(
            "table-9",
            "table",
            "ServerType definition",
            "ignored",
            evidence="Attribute,Value\nBrowseName,ServerType\nlast-row,kept-intact",
        )
        chunk = RetrievedRecord("chunk-1", "chunk", "Small", "ignored", evidence="small body")
        chunk_unit = "[C1] Small\nsmall body"
        model = RecordingChatModel("[C1] ok")

        result = RAGPipeline(
            retriever=EvidenceRetriever([table, chunk]),
            chat_model=model,
            max_context_chars=len(chunk_unit),
        ).ask("question")

        self.assertEqual(["chunk-1"], [item["id"] for item in result.retrieved])
        self.assertIn("small body", model.user_prompt)
        self.assertNotIn("last-row,kept-intact", model.user_prompt)
        self.assertIn("table-9", result.error)

    def test_label_overhead_does_not_discard_a_later_fitting_unit(self):
        records = [
            RetrievedRecord("large", "entity", "Large", "", evidence="x" * 17),
            RetrievedRecord("small", "chunk", "S", "", evidence="ok"),
        ]
        model = RecordingChatModel("Small evidence. [C1]")
        result = RAGPipeline(
            retriever=EvidenceRetriever(records), chat_model=model, max_context_chars=23
        ).ask("question")

        self.assertEqual("generated", result.mode)
        self.assertEqual(["small"], [item["id"] for item in result.retrieved])
        context = model.user_prompt.split("Part 5 evidence:\n", 1)[1]
        self.assertEqual("[C1] S\nok", context)
        self.assertLessEqual(len(context), 23)
        self.assertIn("large", result.error)

    def test_no_evidence_never_calls_the_model(self):
        model = RecordingChatModel("Unfounded answer. [E1]")
        result = RAGPipeline(
            retriever=EvidenceRetriever([]), chat_model=model
        ).ask("question")

        self.assertEqual("offline", result.mode)
        self.assertEqual(0, model.calls)
        self.assertEqual([], result.citations)
        self.assertEqual([], result.retrieved)

    def test_pipeline_keeps_whole_evidence_at_exact_budget_boundary(self):
        evidence = "row1\nrow2\nrow3"
        record = RetrievedRecord("table-9", "table", "Table", "ignored", evidence=evidence)
        exact_unit = f"[T1] Table\n{evidence}"
        model = RecordingChatModel("[T1] ok")

        result = RAGPipeline(
            retriever=EvidenceRetriever([record]),
            chat_model=model,
            max_context_chars=len(exact_unit),
        ).ask("question")

        self.assertEqual("generated", result.mode)
        self.assertIn(evidence, model.user_prompt)
        self.assertEqual(["[T1]"], [item["label"] for item in result.citations])

    def test_pipeline_rejects_missing_or_malformed_generated_citations(self):
        record = RetrievedRecord("e1", "entity", "First", "ignored", evidence="full evidence")
        for answer in (
            "", "An answer without sources.", "[E0]", "[Eabc]", "[E1, E99]",
            "[E2]", "[E1] and [E9]", "[E1] and [X99]", "[E1] and [e1]",
            "[E1] and [T99", "[E1] and [X99\nMore text.",
        ):
            with self.subTest(answer=answer):
                model = RecordingChatModel(answer)
                result = RAGPipeline(
                    retriever=EvidenceRetriever([record]),
                    chat_model=model,
                    max_context_chars=2000,
                ).ask("question")

                self.assertEqual("offline", result.mode)
                self.assertTrue(result.error)
                self.assertEqual(["[E1]"], [item["label"] for item in result.citations])
                self.assertIn("[E1]", result.answer)

    def test_pipeline_accepts_each_documented_canonical_label_prefix(self):
        records = [
            RetrievedRecord("e1", "entity", "Entity", "ignored", evidence="entity body"),
            RetrievedRecord("t1", "table", "Table", "ignored", evidence="table body"),
            RetrievedRecord("c1", "chunk", "Chunk", "ignored", evidence="chunk body"),
            RetrievedRecord(
                "r1", "relationship", "HAS_COMPONENT", "e1 HAS_COMPONENT e2"
            ),
        ]
        for answer, label in (
            ("[E1] ok", "[E1]"),
            ("[T1] ok", "[T1]"),
            ("[C1] ok", "[C1]"),
            ("[R1] ok", "[R1]"),
        ):
            with self.subTest(label=label):
                model = RecordingChatModel(answer)
                result = RAGPipeline(
                    retriever=EvidenceRetriever(records),
                    chat_model=model,
                    max_context_chars=2000,
                ).ask("question")

                self.assertEqual("generated", result.mode)
                self.assertIn(label, [item["label"] for item in result.citations])

    def test_pipeline_offline_fallback_uses_complete_selected_evidence(self):
        record = RetrievedRecord(
            "chunk-1",
            "chunk",
            "Scope",
            "short snippet",
            evidence="Full original chunk text, including rows beyond the snippet.",
        )

        result = RAGPipeline(
            retriever=EvidenceRetriever([record]), max_context_chars=2000
        ).ask("question")

        self.assertEqual("offline", result.mode)
        self.assertIn("Full original chunk text", result.answer)
        self.assertEqual(["[C1]"], [item["label"] for item in result.citations])

    def test_relationship_boundary_snippet_is_preserved(self):
        record = RetrievedRecord(
            "e2", "relationship", "HAS_COMPONENT", "e1 HAS_COMPONENT e2"
        )
        model = RecordingChatModel("[R1] ok")

        result = RAGPipeline(
            retriever=EvidenceRetriever([record]),
            chat_model=model,
            max_context_chars=2000,
        ).ask("question")

        self.assertIn("e1 HAS_COMPONENT e2", model.user_prompt)
        self.assertEqual("e2", result.retrieved[0]["id"])
        self.assertEqual("[R1]", result.citations[0]["label"])

    def test_create_retriever_accepts_path_or_kb(self):
        from opcua_kb import create_retriever
        from opcua_kb.api import KnowledgeBase
        from opcua_kb.retrieval import Part5Retriever

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            (source / "source_manifest.json").write_text(
                json.dumps({"doc": "OPC-10000-5"}), encoding="utf-8"
            )
            kb = KnowledgeBase(root)

            for arg in (root, str(root), kb):
                with self.subTest(arg=type(arg).__name__):
                    retriever = create_retriever(arg)
                    self.assertIsInstance(retriever, Part5Retriever)
                    self.assertEqual("fts", retriever.mode)

    def test_create_chat_model_from_env_handles_missing_key(self):
        from opcua_kb import create_chat_model_from_env

        with mock.patch.dict(os.environ, {}, clear=True):
            model, error = create_chat_model_from_env()
        self.assertIsNone(model)
        self.assertIsInstance(error, str)
        self.assertTrue(error)

    def test_create_chat_model_from_env_reads_deepseek_and_openai_env(self):
        from opcua_kb.llm import OpenAICompatibleChatModel
        from opcua_kb.rag import create_chat_model_from_env

        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "ds-key"}, clear=True):
            model, error = create_chat_model_from_env()
        self.assertIsNone(error)
        self.assertIsInstance(model, OpenAICompatibleChatModel)
        self.assertEqual("ds-key", model.api_key)
        self.assertEqual("deepseek-chat", model.model)
        self.assertEqual("https://api.deepseek.com/chat/completions", model.endpoint)

        with mock.patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "oa-key",
                "OPENAI_MODEL": "gpt-4o-mini",
                "OPENAI_BASE_URL": "https://api.openai.com/v1",
            },
            clear=True,
        ):
            model, error = create_chat_model_from_env()
        self.assertIsNone(error)
        self.assertIsInstance(model, OpenAICompatibleChatModel)
        self.assertEqual("oa-key", model.api_key)
        self.assertEqual("gpt-4o-mini", model.model)
        self.assertEqual("https://api.openai.com/v1/chat/completions", model.endpoint)

    def test_rag_pipeline_rejects_wiki_citation_labels(self):
        record = RetrievedRecord("e1", "entity", "First", "ignored", evidence="full evidence")
        for answer in ("[W1]", "[E1] and [W1]"):
            with self.subTest(answer=answer):
                model = RecordingChatModel(answer)
                result = RAGPipeline(
                    retriever=EvidenceRetriever([record]),
                    chat_model=model,
                    max_context_chars=2000,
                ).ask("question")

                self.assertEqual("offline", result.mode)
                self.assertTrue(result.error)
                self.assertEqual(["[E1]"], [item["label"] for item in result.citations])
                self.assertIn("[E1]", result.answer)


if __name__ == "__main__": unittest.main()
