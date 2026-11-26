import asyncio
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from opcua_kb.rag import RAGAnswer
from tools import tui


def make_root(case: unittest.TestCase | None = None) -> Path:
    root = Path(tempfile.mkdtemp())
    if case is not None:
        case.addCleanup(shutil.rmtree, root, ignore_errors=True)
    (root / "source").mkdir()
    (root / "source" / "source_manifest.json").write_text(
        json.dumps({"doc": "OPC-10000-5", "sha256": "abc"}), encoding="utf-8"
    )
    (root / "kb").mkdir()
    (root / "indexes").mkdir()
    return root


class TuiRagTests(unittest.TestCase):
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
        rendered = tui.format_rag_answer(answer, retrieval_mode="fts")
        self.assertIn("fts", rendered)
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

        asyncio.run(check_layout())

    def test_online_checkbox_stays_visible_on_narrow_terminals(self) -> None:
        async def check_layout() -> None:
            for width in (80, 60):
                with self.subTest(width=width):
                    app = tui.KnowledgeBaseTUI(make_root(self))
                    async with app.run_test(size=(width, 30)) as pilot:
                        await pilot.pause()
                        options_row = app.query_one("#search-options-row")
                        limit = app.query_one("#search-limit")
                        depth = app.query_one("#rag-depth")
                        checkbox = app.query_one("#rag-online")
                        button = app.query_one("#search-button")
                        self.assertEqual(0, len(app.query("#rag-mode")))
                        self.assertLessEqual(checkbox.region.right, options_row.region.right)
                        self.assertLessEqual(button.region.right, options_row.region.right)
                        self.assertGreater(limit.region.width, 0)
                        self.assertGreater(depth.region.width, 0)
                        self.assertGreaterEqual(checkbox.region.width, 21)

        asyncio.run(check_layout())

    def test_online_checkbox_renders_distinct_checked_state(self) -> None:
        async def check_render() -> None:
            app = tui.KnowledgeBaseTUI(make_root(self))
            async with app.run_test(size=(80, 30)) as pilot:
                await pilot.pause()
                checkbox = app.query_one("#rag-online")
                self.assertEqual("在线生成：关闭", str(checkbox.render()))
                await pilot.click("#rag-online")
                await pilot.pause()
                self.assertEqual("在线生成：开启", str(checkbox.render()))

        asyncio.run(check_render())

    def test_tui_search_does_not_double_query_kb(self) -> None:
        async def check_single_search() -> None:
            app = tui.KnowledgeBaseTUI(make_root(self))
            fake_answer = RAGAnswer(
                answer="[E1] ServerType",
                mode="offline",
                citations=[{"label": "[E1]", "title": "ServerType", "id": "ObjectType:ServerType"}],
                retrieved=[
                    {
                        "label": "[E1]",
                        "id": "ObjectType:ServerType",
                        "type": "entity",
                        "title": "ServerType",
                        "section": "6.3.1",
                    }
                ],
            )
            fake_pipeline = MagicMock()
            fake_pipeline.ask.return_value = fake_answer
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app.query_one("#search-query").value = "ServerType"
                with patch.object(app.kb, "search") as kb_search, patch.object(
                    tui, "RAGPipeline", return_value=fake_pipeline
                ):
                    app._search()
                kb_search.assert_not_called()
                fake_pipeline.ask.assert_called_once_with(
                    "ServerType", top_k=10, relationship_depth=0
                )

        asyncio.run(check_single_search())


if __name__ == "__main__":
    unittest.main()
