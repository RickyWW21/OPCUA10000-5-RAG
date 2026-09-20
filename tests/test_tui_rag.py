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

    def test_search_input_and_options_use_separate_rows(self) -> None:
        async def check_layout() -> None:
            root = make_root()
            app = tui.KnowledgeBaseTUI(root)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                input_row = app.query_one("#search-input-row")
                options_row = app.query_one("#search-options-row")
                search_input = app.query_one("#search-query")
                search_limit = app.query_one("#search-limit")
                self.assertIs(search_input.parent, input_row)
                self.assertIs(search_limit.parent, options_row)
                self.assertIsNot(input_row, options_row)
                self.assertLess(input_row.region.y, options_row.region.y)
                self.assertEqual(search_input.region.width, input_row.region.width)
                self.assertGreaterEqual(search_input.region.width, 100)

        import asyncio

        asyncio.run(check_layout())

    def test_online_checkbox_stays_visible_on_narrow_terminals(self) -> None:
        async def check_layout() -> None:
            for width in (80, 60):
                with self.subTest(width=width):
                    app = tui.KnowledgeBaseTUI(make_root())
                    async with app.run_test(size=(width, 30)) as pilot:
                        await pilot.pause()
                        options_row = app.query_one("#search-options-row")
                        checkbox = app.query_one("#rag-online")
                        self.assertLessEqual(checkbox.region.right, options_row.region.right)
                        self.assertGreaterEqual(checkbox.region.width, 17)

        import asyncio

        asyncio.run(check_layout())

    def test_online_checkbox_renders_distinct_checked_state(self) -> None:
        async def check_render() -> None:
            app = tui.KnowledgeBaseTUI(make_root())
            async with app.run_test(size=(80, 30)) as pilot:
                await pilot.pause()
                checkbox = app.query_one("#rag-online")
                self.assertEqual("在线生成：关闭", str(checkbox.render()))
                await pilot.click("#rag-online")
                await pilot.pause()
                self.assertEqual("在线生成：开启", str(checkbox.render()))

        import asyncio

        asyncio.run(check_render())


if __name__ == "__main__":
    unittest.main()
