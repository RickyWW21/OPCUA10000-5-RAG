"""Focused RAG tests for Wiki evidence, provenance, and W citation labels."""

import json
import re
import unittest

from opcua_kb.rag import RAGPipeline
from opcua_kb.retrieval import RetrievedRecord

WIKI_BODY = (
    "# ServerType\n\n"
    "LLM-written navigation draft for ServerType.\n\n"
    "[§6.3.1 Table 9 L225-L250](../../source/OPC-10000-5-v1.05.06.md#L225-L250)\n"
)

WIKI_PROVENANCE = {
    "page_id": "servertype",
    "path": "wiki/entities/servertype.md",
    "source_doc": "OPC-10000-5",
    "source_version": "1.05.06",
    "source_sha256": "a" * 64,
    "status": "draft",
    "sources": [{"section": "6.3.1", "table": "9", "lines": "225-250"}],
}

SOURCE_PROVENANCE = {
    "path": "source/OPC-10000-5-v1.05.06.md",
    "version": "1.05.06",
    "hash": "b" * 64,
    "lines": "225-250",
    "source": "wiki/entities/servertype.md",
    "source_doc": "OPC-10000-5",
    "section": "6.3.1",
    "table_number": "9",
}


LONG_SOURCE_BODY = (
    "ServerType 的规范原文规定了服务器对象的标准组件、成员和建模规则。" * 300
)[:10646]

BUDGET_WIKI_BODY = (
    "# ServerType\n\n"
    "ServerType 定义 OPC UA Server 对外声明其能力时使用的标准 ObjectType。"
    "标准 Server Object 以它为 TypeDefinition，因此客户端可以从 Server 浏览到"
    "服务器标识、状态、能力、诊断和冗余等标准入口。"
    "[§6.3.1 Table 9 L225-L250](../../source/OPC-10000-5-v1.05.06.md#L225-L250)\n\n"
    "## 重要成员\n\n"
    "Table 9 中的关键组件包括 ServerArray、NamespaceArray、ServerStatus、"
    "ServiceLevel、Auditing、ServerCapabilities、ServerDiagnostics、"
    "VendorServerInfo 和 ServerRedundancy。这些成员覆盖服务器标识、状态、"
    "能力与诊断等入口。"
    "[§6.3.1 Table 9 L225-L250](../../source/OPC-10000-5-v1.05.06.md#L225-L250)\n\n"
    "ServerArray 是 Server URI 表，索引 0 保留给本地 Server；NamespaceArray "
    "是命名空间 URI 表。客户端持有打开的 Session 时，Server 不得修改或删除"
    "这两张表的条目，但可以追加条目。"
    "[§6.3.1 L253-L260](../../source/OPC-10000-5-v1.05.06.md#L253-L260)\n\n"
    "## 大段未摘录正文\n\n"
    "OMITTED-TAIL-MARKER "
    + "这一段在默认预算内不会进入摘录。" * 400
    + "\n\n"
    "## 相关页面\n\n"
    "- [BaseObjectType](baseobjecttype.md)：父类型。\n"
    "- [返回目录](../index.md)\n"
)


def wiki_record(evidence=WIKI_BODY):
    return RetrievedRecord(
        "wiki:servertype",
        "wiki",
        "ServerType Wiki",
        WIKI_BODY,
        section="6.3.1",
        table_number="9",
        evidence=evidence,
        provenance=dict(WIKI_PROVENANCE),
    )


def source_chunk(with_provenance=False):
    return RetrievedRecord(
        "chunk-1",
        "chunk",
        "Original §6.3.1",
        "source snippet",
        section="6.3.1",
        table_number="9",
        evidence="Original specification text.",
        provenance=dict(SOURCE_PROVENANCE) if with_provenance else None,
    )


class FixtureRetriever:
    def __init__(self, records):
        self.records = records

    def retrieve(self, question, *, top_k=6, relationship_depth=0):
        return self.records[:top_k]


class RecordingChatModel:
    def __init__(self, answer):
        self.answer = answer
        self.system_prompt = ""
        self.user_prompt = ""
        self.calls = 0

    def generate(self, *, system, user, temperature=0.0):
        self.calls += 1
        self.system_prompt = system
        self.user_prompt = user
        return self.answer


class WikiRAGTests(unittest.TestCase):
    def test_instruction_allowlist_contains_only_supplied_citation_labels(self):
        model = RecordingChatModel("Rule [C1].")
        result = RAGPipeline(
            retriever=FixtureRetriever([source_chunk()]), chat_model=model
        ).ask("What does Table 9 say?")

        self.assertEqual("generated", result.mode)
        self.assertEqual(
            {"[C1]"}, set(re.findall(r"\[[ETCRW][1-9][0-9]*\]", model.system_prompt))
        )

    def test_registry_binds_labels_to_records_instead_of_embedded_table_numbers(self):
        entity = RetrievedRecord(
            "ObjectType:ServerType", "entity", "ServerType", "",
            section="6.3.1", evidence="Defining Table 9: the ServerType rules.",
        )
        table = RetrievedRecord(
            "table-119", "table", "Other definition", "",
            table_number="119", evidence="Unrelated table.",
        )
        model = RecordingChatModel("ServerType rules [E1].")
        result = RAGPipeline(
            retriever=FixtureRetriever([entity, table]), chat_model=model
        ).ask("What does Table 9 say?")

        self.assertEqual("generated", result.mode)
        self.assertIn("Citation registry:\n", model.user_prompt)
        registry = json.loads(
            model.user_prompt.split("Citation registry:\n", 1)[1].split(
                "\n\nPart 5 evidence:\n", 1
            )[0]
        )
        self.assertEqual(
            [("[E1]", "ObjectType:ServerType", None), ("[T1]", "table-119", "119")],
            [(item["label"], item["id"], item["table_number"]) for item in registry],
        )

    def test_mixed_context_cites_wiki_and_original_with_provenance(self):
        model = RecordingChatModel("[C1] Source says X. [W1] Wiki draft says X.")
        result = RAGPipeline(
            retriever=FixtureRetriever([source_chunk(with_provenance=True), wiki_record()]),
            chat_model=model,
            max_context_chars=4000,
        ).ask("What is ServerType?")

        self.assertEqual("generated", result.mode)
        self.assertEqual(["[C1]", "[W1]"], [item["label"] for item in result.citations])
        self.assertIn("[C1]", model.user_prompt)
        self.assertIn("[W1]", model.user_prompt)
        self.assertIn("Original specification text.", model.user_prompt)
        self.assertIn("LLM-written navigation draft", model.user_prompt)
        for value in (
            "wiki/entities/servertype.md",
            "1.05.06",
            "draft",
            "非规范原文",
        ):
            self.assertIn(value, model.user_prompt)
        self.assertIn("wiki", model.system_prompt.lower())
        self.assertIn("draft", model.system_prompt.lower())
        self.assertIn("canonical", model.system_prompt.lower())

        source_citation, wiki_citation = result.citations
        self.assertEqual(SOURCE_PROVENANCE, source_citation["provenance"])
        self.assertEqual(SOURCE_PROVENANCE, result.retrieved[0]["provenance"])
        self.assertEqual(WIKI_PROVENANCE, wiki_citation["provenance"])
        self.assertEqual(WIKI_PROVENANCE, result.retrieved[1]["provenance"])
        self.assertEqual("wiki:servertype", result.retrieved[1]["id"])
        self.assertIn(WIKI_BODY, result.retrieved[1]["snippet"])

    def test_invalid_or_unsupplied_wiki_citations_fall_back_offline(self):
        records = [source_chunk(), wiki_record()]
        for answer in ("[W0] invalid", "[Wabc] invalid", "[W99] unsupplied", "[W1] and [W2]"):
            with self.subTest(answer=answer):
                model = RecordingChatModel(answer)
                result = RAGPipeline(
                    retriever=FixtureRetriever(records),
                    chat_model=model,
                    max_context_chars=4000,
                ).ask("question")

                self.assertEqual("offline", result.mode)
                self.assertTrue(result.error)
                self.assertEqual(["[C1]", "[W1]"], [item["label"] for item in result.citations])
                self.assertIn("[W1]", result.answer)

    def test_wiki_omitted_by_budget_leaks_no_w_citation_or_provenance(self):
        small = RetrievedRecord("chunk-1", "chunk", "Small", "small snippet", evidence="small body")
        chunk_unit = "[C1] Small\nsmall body"
        model = RecordingChatModel("[C1] ok")
        result = RAGPipeline(
            retriever=FixtureRetriever([wiki_record(), small]),
            chat_model=model,
            max_context_chars=len(chunk_unit),
        ).ask("question")

        self.assertEqual("generated", result.mode)
        self.assertEqual(["chunk-1"], [item["id"] for item in result.retrieved])
        self.assertEqual(["[C1]"], [item["label"] for item in result.citations])
        self.assertNotIn("[W", model.user_prompt)
        self.assertNotIn("wiki/entities/servertype.md", model.user_prompt)
        self.assertNotIn("provenance", result.retrieved[0])
        self.assertIn("wiki:servertype", result.error)

    def test_default_budget_keeps_long_source_and_fitting_wiki_excerpt(self):
        source = RetrievedRecord(
            "entity:ObjectType:ServerType",
            "entity",
            "ObjectType:ServerType",
            "ignored",
            evidence=LONG_SOURCE_BODY,
        )
        model = RecordingChatModel("[E1] Source says X. [W1] Wiki draft says X.")
        result = RAGPipeline(
            retriever=FixtureRetriever([source, wiki_record(BUDGET_WIKI_BODY)]),
            chat_model=model,
        ).ask("ServerType 包含哪些组件？")

        self.assertEqual(10646, len(LONG_SOURCE_BODY))
        self.assertEqual(
            ["entity:ObjectType:ServerType", "wiki:servertype"],
            [item["id"] for item in result.retrieved],
        )
        self.assertEqual(["[E1]", "[W1]"], [item["label"] for item in result.citations])

        context = model.user_prompt.split("Part 5 evidence:\n", 1)[1]
        self.assertLessEqual(len(context), 12000)
        self.assertIn("[E1]", context)
        self.assertIn("[W1]", context)
        for value in ("Wiki 摘录", "excerpt", "非规范原文", "wiki/entities/servertype.md", "source_version=1.05.06", "status=draft"):
            self.assertIn(value, context)
        self.assertIn("ServerArray", context)
        self.assertNotIn("OMITTED-TAIL-MARKER", context)
        self.assertIn("摘录", result.error or "")

        wiki_snippet = result.retrieved[1]["snippet"]
        self.assertIn("Wiki 摘录", wiki_snippet)
        self.assertNotIn("OMITTED-TAIL-MARKER", wiki_snippet)
        self.assertEqual(WIKI_PROVENANCE, result.citations[1]["provenance"])
        self.assertEqual(WIKI_PROVENANCE, result.retrieved[1]["provenance"])

        # The API snippet is exactly the text the model saw, not the whole page.
        expected_context = "\n\n".join(
            f"{item['label']} {item['title']}\n{item['snippet']}"
            for item in result.retrieved
        )
        self.assertEqual(expected_context, context)

    def test_unsplittable_oversized_wiki_is_omitted_without_w_label(self):
        source = RetrievedRecord(
            "chunk-1", "chunk", "Small", "ignored", evidence="small body"
        )
        source_unit = "[C1] Small\nsmall body"
        huge = "# ServerType\n\n" + "不可分段正文" * 2000
        model = RecordingChatModel("[C1] ok")

        result = RAGPipeline(
            retriever=FixtureRetriever([source, wiki_record(huge)]),
            chat_model=model,
            max_context_chars=len(source_unit) + 300,
        ).ask("question")

        self.assertEqual("generated", result.mode)
        self.assertEqual(["chunk-1"], [item["id"] for item in result.retrieved])
        self.assertEqual(["[C1]"], [item["label"] for item in result.citations])
        self.assertNotIn("[W", model.user_prompt)
        self.assertNotIn("wiki/entities/servertype.md", model.user_prompt)
        self.assertIn("wiki:servertype", result.error)

    def test_complete_wiki_page_keeps_tail_without_excerpt(self):
        body = WIKI_BODY + "\n\n## 用途\n\nTAIL-KEPT 完整最后一段。\n"
        result = RAGPipeline(
            retriever=FixtureRetriever([wiki_record(body)])
        ).ask("question")

        self.assertEqual("offline", result.mode)
        self.assertIn("TAIL-KEPT 完整最后一段。", result.retrieved[0]["snippet"])
        self.assertIn("TAIL-KEPT 完整最后一段。", result.answer)
        self.assertIn("Wiki 草稿", result.retrieved[0]["snippet"])
        self.assertNotIn("Wiki 摘录", result.retrieved[0]["snippet"])
        self.assertIsNone(result.error)

    def test_legacy_records_without_provenance_keep_flat_shape(self):
        records = [
            RetrievedRecord("e1", "entity", "Entity", "entity snippet", evidence="entity body"),
            source_chunk(),
        ]
        result = RAGPipeline(retriever=FixtureRetriever(records)).ask("question")

        self.assertEqual("offline", result.mode)
        self.assertEqual(
            [
                {"label": "[E1]", "title": "Entity", "id": "e1"},
                {"label": "[C1]", "title": "Original §6.3.1", "id": "chunk-1"},
            ],
            result.citations,
        )
        for item in result.retrieved:
            self.assertNotIn("provenance", item)
            self.assertEqual({"id", "type", "title", "snippet", "section", "table_number", "doc", "label"}, set(item))
        self.assertIn("entity body", result.answer)
        self.assertNotIn("Wiki 草稿", result.answer)

    def test_offline_answer_marks_wiki_as_draft_next_to_original(self):
        result = RAGPipeline(
            retriever=FixtureRetriever([source_chunk(), wiki_record()])
        ).ask("question")

        self.assertEqual("offline", result.mode)
        self.assertIn("[C1]", result.answer)
        self.assertIn("Original specification text.", result.answer)
        self.assertIn("[W1]", result.answer)
        self.assertIn("Wiki 草稿", result.answer)
        self.assertIn("非规范原文", result.answer)
        self.assertIn("wiki/entities/servertype.md", result.answer)
        self.assertIn("status=draft", result.answer)
        self.assertIn("6.3.1", result.answer)

    def test_offline_answer_wiki_only_says_canonical_cannot_be_checked(self):
        result = RAGPipeline(retriever=FixtureRetriever([wiki_record()])).ask("question")

        self.assertEqual("offline", result.mode)
        self.assertIn("[W1]", result.answer)
        self.assertIn("Wiki 草稿", result.answer)
        self.assertIn("无法核对规范原文", result.answer)
        self.assertIn("不能作为规范确认", result.answer)


if __name__ == "__main__":
    unittest.main()
