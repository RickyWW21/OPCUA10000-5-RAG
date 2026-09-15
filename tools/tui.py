"""Textual terminal interface for searching and exploring the knowledge base."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal
    from textual.widgets import (
        Button,
        Checkbox,
        DataTable,
        Footer,
        Header,
        Input,
        Label,
        Markdown,
        Select,
        Static,
        TabbedContent,
        TabPane,
    )
except ImportError as exc:
    print(
        "TUI 依赖尚未安装。请先运行：\n"
        "  python -m pip install -r requirements-tui.txt",
        file=sys.stderr,
    )
    raise SystemExit(2) from exc

from opcua_kb import KnowledgeBase, RAGPipeline, write_graph_html, write_graph_json
from opcua_kb.embeddings import EmbeddingError, SentenceTransformerEmbeddingProvider
from opcua_kb.errors import format_action_error
from opcua_kb.llm import LLMError, OpenAICompatibleChatModel
from opcua_kb.retrieval import Part5Retriever
from opcua_kb.rag import RAGAnswer
from opcua_kb.vector_index import VectorIndex


RAG_MODE_OPTIONS = [
    ("自动 / Auto", "auto"),
    ("混合 / Hybrid", "hybrid"),
    ("仅 FTS5 / FTS5", "fts"),
]


def build_rag_retriever(
    root: str | Path, *, mode: str = "auto", embedding_model: str | None = None
) -> Part5Retriever:
    """Build a verified Part 5 retriever for the TUI search workflow."""

    if mode not in {"auto", "hybrid", "fts"}:
        raise ValueError("retrieval mode must be auto, hybrid, or fts")
    root = Path(root)
    knowledge_base = KnowledgeBase(root)
    if mode == "fts":
        return Part5Retriever(knowledge_base)

    vector_path = root / "indexes" / "embeddings.jsonl"
    metadata_path = root / "indexes" / "embeddings.meta.json"
    manifest_path = root / "source" / "source_manifest.json"
    if not vector_path.exists() or not metadata_path.exists():
        return Part5Retriever(knowledge_base)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        source_hash = manifest.get("sha256") if isinstance(manifest, dict) else None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return Part5Retriever(knowledge_base)
    if not isinstance(source_hash, str) or not source_hash:
        return Part5Retriever(knowledge_base)
    try:
        provider = SentenceTransformerEmbeddingProvider(
            embedding_model or "sentence-transformers/all-MiniLM-L6-v2"
        )
    except EmbeddingError:
        return Part5Retriever(knowledge_base)
    return Part5Retriever(
        knowledge_base,
        vector_index=VectorIndex(root, source_hash=source_hash),
        embedding_provider=provider,
    )


def format_rag_answer(answer: RAGAnswer, *, retrieval_mode: str) -> str:
    """Render a RAG answer, its modes, citations, and retrieval error in Markdown."""

    lines = ["## RAG 回答", f"- 检索模式: `{retrieval_mode}`", f"- 生成模式: `{answer.mode}`", "", answer.answer]
    if answer.citations:
        lines.extend(["", "### 引用"])
        lines.extend(
            f"- {citation.get('label', '')} **{citation.get('title', citation.get('id', ''))}** `({citation.get('id', '')})`"
            for citation in answer.citations
        )
    if answer.error:
        lines.extend(["", f"> 模型回退: {answer.error}"])
    return "\n".join(lines)


RELATION_OPTIONS = [
    ("全部关系", ""),
    ("HAS_COMPONENT", "HAS_COMPONENT"),
    ("HAS_PROPERTY", "HAS_PROPERTY"),
    ("HAS_SUBTYPE", "HAS_SUBTYPE"),
    ("USES_DATATYPE", "USES_DATATYPE"),
    ("HAS_TYPE_DEFINITION", "HAS_TYPE_DEFINITION"),
    ("DEFINED_BY_TABLE", "DEFINED_BY_TABLE"),
    ("DEFINED_IN_SECTION", "DEFINED_IN_SECTION"),
]


class KnowledgeBaseTUI(App[None]):
    """Interactive terminal front end backed by the repository's Python API."""

    TITLE = "OPC UA 10000-5 知识库"
    SUB_TITLE = "交互式终端浏览器"

    CSS = """
    Screen {
        background: $surface;
    }

    Header {
        background: #005f73;
        color: white;
    }

    HeaderIcon {
        width: 10;
        content-align: center middle;
    }

    TabbedContent {
        height: 1fr;
    }

    TabPane {
        padding: 1 2;
    }

    .toolbar {
        height: auto;
        margin-bottom: 1;
    }

    .toolbar Input {
        width: 1fr;
        margin-right: 1;
    }

    .toolbar Select {
        width: 24;
        margin-right: 1;
    }

    .toolbar Button {
        min-width: 12;
        margin-right: 1;
    }

    .split {
        height: 1fr;
    }

    .results {
        width: 48%;
        min-width: 42;
        margin-right: 1;
        border: solid $primary;
    }

    .relation-results {
        width: 55%;
        min-width: 40;
        margin-right: 1;
        border: solid $primary;
    }

    .detail {
        width: 1fr;
        height: 1fr;
        padding: 1 2;
        border: solid $secondary;
        overflow-y: auto;
    }

    .full-detail {
        width: 1fr;
        height: 1fr;
        padding: 1 2;
        border: solid $secondary;
        overflow-y: auto;
    }

    .section-title {
        height: 1;
        margin: 0 0 1 0;
        color: $text-muted;
    }

    #graph-options {
        height: auto;
        margin-bottom: 1;
    }

    #graph-options Checkbox {
        margin-right: 3;
    }

    #graph-output-row {
        height: auto;
        margin-bottom: 1;
    }

    #graph-output-row Button {
        min-width: 12;
        margin-left: 1;
    }

    #graph-output {
        width: 1fr;
    }

    #status-line {
        dock: bottom;
        height: 1;
        padding: 0 2;
        background: #e9d8a6;
        color: #001219;
    }
    """

    BINDINGS = [
        ("ctrl+q", "quit", "退出"),
        ("ctrl+f", "focus_search", "搜索"),
        ("f1", "show_help", "帮助"),
    ]

    def __init__(
        self,
        root: Path,
        *,
        retrieval_mode: str = "auto",
        embedding_model: str | None = None,
        online: bool = False,
    ) -> None:
        """Initialize one API instance and row-key maps shared by TUI events."""

        super().__init__()
        self.root = root
        self.kb = KnowledgeBase(root)
        self.retrieval_mode = retrieval_mode
        self.embedding_model = embedding_model
        self.online = online
        self._retrievers: dict[str, Part5Retriever] = {}
        self.search_results: dict[str, dict[str, Any]] = {}
        self.relation_results: dict[str, dict[str, Any]] = {}

    def compose(self) -> ComposeResult:
        """Compose the five workflow tabs and their persistent result panels."""

        # A text label avoids the default palette glyph rendering as a missing
        # character in terminal fonts with limited Unicode coverage.
        yield Header(show_clock=True, icon="命令")
        with TabbedContent(initial="search-tab"):
            with TabPane("搜索", id="search-tab"):
                with Horizontal(classes="toolbar"):
                    yield Input(
                        placeholder="输入实体名、自然语言、章节号或表格号",
                        id="search-query",
                    )
                    yield Select(
                        [("5 条", 5), ("10 条", 10), ("20 条", 20), ("50 条", 50)],
                        value=10,
                        allow_blank=False,
                        id="search-limit",
                    )
                    yield Select(
                        RAG_MODE_OPTIONS,
                        value=self.retrieval_mode,
                        allow_blank=False,
                        id="rag-mode",
                    )
                    yield Select(
                        [("深度 0", 0), ("深度 1", 1), ("深度 2", 2)],
                        value=0,
                        allow_blank=False,
                        id="rag-depth",
                    )
                    yield Checkbox("在线生成", value=self.online, id="rag-online")
                    yield Button("搜索", variant="primary", id="search-button")
                with Horizontal(classes="split"):
                    yield DataTable(id="search-results", classes="results", cursor_type="row")
                    yield Markdown(
                        "## 开始搜索\n\n输入关键词后按 **Enter**，再选择左侧结果查看完整内容。",
                        id="search-detail",
                        classes="detail",
                    )

            with TabPane("实体", id="entity-tab"):
                with Horizontal(classes="toolbar"):
                    yield Input(placeholder="例如 ServerType 或 BuildInfo", id="entity-name")
                    yield Button("查看实体", variant="primary", id="entity-button")
                yield Markdown(
                    "## 实体详情\n\n可查看类型、定义章节、继承关系、属性、组件、字段和枚举值。",
                    id="entity-detail",
                    classes="full-detail",
                )

            with TabPane("关系", id="relations-tab"):
                with Horizontal(classes="toolbar"):
                    yield Input(placeholder="实体名，例如 ServerType", id="relation-entity")
                    yield Select(RELATION_OPTIONS, value="", allow_blank=False, id="relation-kind")
                    yield Select(
                        [("深度 1", 1), ("深度 2", 2), ("深度 3", 3)],
                        value=1,
                        allow_blank=False,
                        id="relation-depth",
                    )
                    yield Button("追踪关系", variant="primary", id="relation-button")
                with Horizontal(classes="split"):
                    yield DataTable(
                        id="relation-results",
                        classes="relation-results",
                        cursor_type="row",
                    )
                    yield Markdown(
                        "## 关系详情\n\n选择左侧关系后，可查看完整目标内容并跳转到相关实体、章节或表格。",
                        id="relation-detail",
                        classes="detail",
                        open_links=False,
                    )

            with TabPane("章节 / 表格", id="docs-tab"):
                with Horizontal(classes="toolbar"):
                    yield Input(placeholder="章节号，例如 8.3.1", id="chapter-number")
                    yield Button("查看章节", variant="primary", id="chapter-button")
                    yield Input(placeholder="表格号，例如 15 或 C.1", id="table-number")
                    yield Button("查看表格", variant="primary", id="table-button")
                with TabbedContent(initial="docs-structured-tab", id="table-view-tabs"):
                    with TabPane("结构化数据", id="docs-structured-tab"):
                        yield Markdown(
                            "## 文档浏览\n\n输入章节号或表格号查看结构化内容。",
                            id="docs-detail",
                            classes="full-detail",
                        )
                    with TabPane("常规表格", id="docs-grid-tab"):
                        yield DataTable(
                            id="table-grid",
                            classes="full-detail",
                            cursor_type="cell",
                            zebra_stripes=True,
                        )

            with TabPane("知识图谱", id="graph-tab"):
                yield Label("留空焦点可生成全局图谱；关系可使用逗号分隔。", classes="section-title")
                with Horizontal(classes="toolbar"):
                    yield Input(placeholder="焦点实体（可选）", id="graph-focus")
                    yield Input(placeholder="关系过滤（可选）", id="graph-relation")
                    yield Select(
                        [("深度 1", 1), ("深度 2", 2), ("深度 3", 3)],
                        value=1,
                        allow_blank=False,
                        id="graph-depth",
                    )
                    yield Select(
                        [("全部节点", 0), ("12 个节点", 12), ("30 个节点", 30), ("60 个节点", 60)],
                        value=0,
                        allow_blank=False,
                        id="graph-limit",
                    )
                with Horizontal(id="graph-options"):
                    yield Checkbox("包含定义关系", id="graph-defined")
                    yield Select(
                        [("交互式 HTML", "html"), ("JSON 数据", "json")],
                        value="html",
                        allow_blank=False,
                        id="graph-format",
                    )
                with Horizontal(id="graph-output-row"):
                    yield Input(value="exports/knowledge_graph.html", id="graph-output")
                    yield Button("生成", variant="primary", id="graph-button")
                    yield Button("生成并打开", id="graph-open-button")
                yield Markdown(
                    "## 图谱导出\n\nHTML 图谱支持拖动节点、平移、滚轮缩放和点击查看详情。",
                    id="graph-detail",
                    classes="full-detail",
                )
        yield Static(f"知识库：{self.root}", id="status-line")
        yield Footer()

    def on_mount(self) -> None:
        """Configure dynamic tables after widgets have entered the DOM."""

        search_table = self.query_one("#search-results", DataTable)
        search_table.add_columns("类型", "标题", "章节")
        relation_table = self.query_one("#relation-results", DataTable)
        relation_table.add_column("源实体", width=24)
        relation_table.add_column("关系", width=22)
        relation_table.add_column("目标摘要", width=42)
        self.query_one("#search-query", Input).focus()

    def action_focus_search(self) -> None:
        self.query_one(TabbedContent).active = "search-tab"
        self.query_one("#search-query", Input).focus()

    def action_show_help(self) -> None:
        self.notify("Ctrl+F 搜索，Tab 切换控件，Enter 执行，Ctrl+Q 退出", title="快捷键")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Dispatch Enter from each input to the matching workflow action."""

        actions = {
            "search-query": self._search,
            "entity-name": self._show_entity,
            "relation-entity": self._show_relations,
            "chapter-number": self._show_chapter,
            "table-number": self._show_table,
        }
        action = actions.get(event.input.id or "")
        if action:
            action()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Dispatch command buttons without duplicating workflow implementations."""

        actions = {
            "search-button": self._search,
            "entity-button": self._show_entity,
            "relation-button": self._show_relations,
            "chapter-button": self._show_chapter,
            "table-button": self._show_table,
            "graph-button": lambda: self._generate_graph(open_after=False),
            "graph-open-button": lambda: self._generate_graph(open_after=True),
        }
        action = actions.get(event.button.id or "")
        if action:
            action()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Resolve stable row keys back to the full search or relationship record."""

        key = str(event.row_key.value)
        if event.data_table.id == "search-results":
            item = self.search_results.get(key)
            if item:
                self.query_one("#search-detail", Markdown).update(self._format_search_result(item))
        elif event.data_table.id == "relation-results":
            edge = self.relation_results.get(key)
            if edge:
                self.query_one("#relation-detail", Markdown).update(self._format_relation(edge))

    def on_markdown_link_clicked(self, event: Markdown.LinkClicked) -> None:
        """Route custom relation-detail links without opening an external browser."""

        if event.markdown.id != "relation-detail":
            return
        event.stop()
        kind, separator, value = event.href.partition(":")
        if not separator or kind not in {"entity", "chapter", "table", "search"}:
            self.notify("无法识别该内部链接。", severity="warning")
            return
        if kind == "entity":
            self._open_linked_entity(value)
        elif kind == "chapter":
            self._open_linked_chapter(value)
        elif kind == "table":
            self._open_linked_table(value)
        else:
            self._open_linked_search(value)

    def _search(self) -> None:
        """Run a knowledge-base search and populate both result and detail panes."""

        query = self.query_one("#search-query", Input).value.strip()
        if not query:
            self.notify("请输入搜索内容。", severity="warning")
            return
        top_k = int(self.query_one("#search-limit", Select).value)
        retrieval_mode = str(self.query_one("#rag-mode", Select).value)
        relationship_depth = int(self.query_one("#rag-depth", Select).value)
        online = self.query_one("#rag-online", Checkbox).value
        try:
            self.kb.search(query, top_k=top_k)
        except (OSError, ValueError) as exc:
            message = format_action_error("搜索", exc)
            self.query_one("#search-detail", Markdown).update(f"## 搜索失败\n\n{message}")
            self._set_status(message)
            self.notify(message, severity="error")
            return
        try:
            retriever = self._get_rag_retriever(retrieval_mode)
            pipeline = RAGPipeline(
                retriever=retriever,
                chat_model=self._get_chat_model(online),
            )
            answer = pipeline.ask(
                query,
                top_k=top_k,
                relationship_depth=relationship_depth,
            )
            results = answer.retrieved
        except (OSError, ValueError) as exc:
            message = format_action_error("搜索", exc)
            self.query_one("#search-detail", Markdown).update(f"## 搜索失败\n\n{message}")
            self._set_status(message)
            self.notify(message, severity="error")
            return
        table = self.query_one("#search-results", DataTable)
        table.clear()
        self.search_results.clear()
        for index, item in enumerate(results):
            key = str(index)
            self.search_results[key] = item
            table.add_row(
                str(item.get("type", "")),
                str(item.get("title", "")),
                str(item.get("section") or "-"),
                key=key,
            )
        if results:
            table.move_cursor(row=0)
            self.query_one("#search-detail", Markdown).update(
                format_rag_answer(answer, retrieval_mode=retriever.last_mode)
            )
        else:
            self.query_one("#search-detail", Markdown).update(f"## 未找到结果\n\n查询：`{query}`")
        self._set_status(
            f"搜索完成：{len(results)} 条结果，检索模式：{retriever.last_mode}"
        )

    def _get_rag_retriever(self, mode: str) -> Part5Retriever:
        """Cache one retriever per selected mode so model loading is not repeated."""

        if mode not in self._retrievers:
            self._retrievers[mode] = build_rag_retriever(
                self.root, mode=mode, embedding_model=self.embedding_model
            )
        return self._retrievers[mode]

    @staticmethod
    def _get_chat_model(online: bool) -> OpenAICompatibleChatModel | None:
        if not online:
            return None
        try:
            return OpenAICompatibleChatModel(
                api_key=os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY"),
                model=os.getenv("DEEPSEEK_MODEL") or os.getenv("OPENAI_MODEL", "deepseek-chat"),
                base_url=os.getenv("DEEPSEEK_BASE_URL")
                or os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com"),
            )
        except LLMError:
            return None

    def _show_entity(self) -> None:
        """Resolve the entity input and render its complete structured card."""

        name = self.query_one("#entity-name", Input).value.strip()
        if not name:
            self.notify("请输入实体名。", severity="warning")
            return
        try:
            entity = self.kb.get_entity(name)
        except (OSError, ValueError) as exc:
            message = format_action_error("实体查询", exc)
            self.query_one("#entity-detail", Markdown).update(f"## 实体查询失败\n\n{message}")
            self._set_status(message)
            self.notify(message, severity="error")
            return
        target = self.query_one("#entity-detail", Markdown)
        if not entity:
            target.update(f"## 未找到实体\n\n`{name}`")
            self._set_status("实体查询无结果")
            return
        target.update(format_entity(entity))
        self._set_status(f"已加载实体：{entity['name']}")

    def _show_relations(self) -> None:
        """Trace filtered relationships and keep long targets out of table cells."""

        entity = self.query_one("#relation-entity", Input).value.strip()
        if not entity:
            self.notify("请输入实体名。", severity="warning")
            return
        relation = str(self.query_one("#relation-kind", Select).value or "") or None
        depth = int(self.query_one("#relation-depth", Select).value)
        try:
            edges = self.kb.relationships(entity, relation=relation, depth=depth)
        except (OSError, ValueError) as exc:
            message = format_action_error("关系追踪", exc)
            self.query_one("#relation-detail", Markdown).update(f"## 关系追踪失败\n\n{message}")
            self._set_status(message)
            self.notify(message, severity="error")
            return
        table = self.query_one("#relation-results", DataTable)
        table.clear()
        self.relation_results.clear()
        for index, edge in enumerate(edges):
            key = str(index)
            self.relation_results[key] = edge
            table.add_row(
                compact_entity_name(str(edge.get("source", ""))),
                str(edge.get("relation", "")),
                compact_relation_target(str(edge.get("target", ""))),
                key=key,
            )
        detail = self.query_one("#relation-detail", Markdown)
        if edges:
            table.move_cursor(row=0)
            detail.update(self._format_relation(edges[0]))
        else:
            detail.update(f"## 未找到关系\n\n实体：`{entity}`")
        self._set_status(f"关系追踪完成：{len(edges)} 条边")
        if not edges:
            self.notify("未找到匹配关系。", severity="warning")

    def _show_chapter(self) -> None:
        """Render a chapter and select the structured document view."""

        section = self.query_one("#chapter-number", Input).value.strip()
        if section:
            try:
                chapter = self.kb.chapter(section)
            except (OSError, ValueError) as exc:
                message = format_action_error("章节查询", exc)
                self.query_one("#docs-detail", Markdown).update(f"## 章节查询失败\n\n{message}")
                self._set_status(message)
                self.notify(message, severity="error")
                return
        else:
            chapter = None
        target = self.query_one("#docs-detail", Markdown)
        if not chapter:
            target.update(f"## 未找到章节\n\n`{section or '（空）'}`")
            self._set_status("章节查询无结果")
            return
        target.update(format_chapter(chapter))
        self.query_one("#table-view-tabs", TabbedContent).active = "docs-structured-tab"
        self._set_status(f"已加载章节：{section}")

    def _show_table(self) -> None:
        """Populate structured and conventional views for the requested table."""

        number = self.query_one("#table-number", Input).value.strip()
        if number:
            try:
                table = self.kb.table(number)
            except (OSError, ValueError) as exc:
                message = format_action_error("表格查询", exc)
                self.query_one("#docs-detail", Markdown).update(f"## 表格查询失败\n\n{message}")
                self._set_status(message)
                self.notify(message, severity="error")
                return
        else:
            table = None
        target = self.query_one("#docs-detail", Markdown)
        if not table:
            target.update(f"## 未找到表格\n\n`{number or '（空）'}`")
            self.query_one("#table-grid", DataTable).clear(columns=True)
            self._set_status("表格查询无结果")
            return
        target.update(format_table(table))
        self._populate_table_grid(table)
        self._set_status(f"已加载表格：{number}")

    def _populate_table_grid(self, table: dict[str, Any]) -> None:
        """Replace all dynamic columns and rows in the conventional table view."""

        columns, rows = table_grid_data(table)
        grid = self.query_one("#table-grid", DataTable)
        grid.clear(columns=True)
        for index, column in enumerate(columns):
            grid.add_column(column or f"列 {index + 1}", key=f"column-{index}")
        for row in rows:
            grid.add_row(*(format_table_cell(value) for value in row))

    def _generate_graph(self, open_after: bool) -> None:
        """Build the selected graph format and optionally open an HTML export."""

        focus = self.query_one("#graph-focus", Input).value.strip() or None
        relation = self.query_one("#graph-relation", Input).value.strip() or None
        depth = int(self.query_one("#graph-depth", Select).value)
        limit = int(self.query_one("#graph-limit", Select).value)
        include_defined = self.query_one("#graph-defined", Checkbox).value
        output_format = str(self.query_one("#graph-format", Select).value)
        output_text = self.query_one("#graph-output", Input).value.strip()
        if not output_text:
            output_text = f"exports/knowledge_graph.{output_format}"
        output = Path(output_text)
        if not output.is_absolute():
            output = self.root / output
        # Keep the selected format and filename extension consistent even when the
        # user edits a path left over from the other format.
        expected_suffix = f".{output_format}"
        if output.suffix.lower() != expected_suffix:
            output = output.with_suffix(expected_suffix)
            self.query_one("#graph-output", Input).value = str(output)

        try:
            graph = self.kb.graph(
                focus=focus,
                relation=relation,
                depth=depth,
                include_defined=include_defined,
                limit=limit,
            )
            if output_format == "html":
                write_graph_html(graph, output)
            else:
                write_graph_json(graph, output)
        except (OSError, ValueError) as exc:
            self.query_one("#graph-detail", Markdown).update(
                f"## 生成失败\n\n```text\n{exc}\n```"
            )
            self.notify(str(exc), title="图谱生成失败", severity="error")
            return

        metadata = graph["metadata"]
        self.query_one("#graph-detail", Markdown).update(
            "## 图谱已生成\n\n"
            f"- 文件：`{output}`\n"
            f"- 节点：**{metadata['node_count']}**\n"
            f"- 边：**{metadata['edge_count']}**\n"
            f"- 选择范围：`{metadata.get('selection', '-')}`"
        )
        self._set_status(f"图谱已写入：{output}")
        if open_after:
            if output_format == "html":
                webbrowser.open(output.resolve().as_uri())
            else:
                self.notify("只有 HTML 图谱可以直接在浏览器中打开。", severity="warning")

    def _format_search_result(self, item: dict[str, Any]) -> str:
        """Render an entity card when possible, otherwise a generic result summary."""

        if item.get("type") == "entity":
            entity = self.kb.get_entity(str(item.get("id", "")))
            if entity:
                return format_entity(entity)
        lines = [f"## {item.get('title') or item.get('id')}"]
        lines.append(f"\n- 类型：`{item.get('type', '-')}`")
        lines.append(f"- 标识：`{item.get('id', '-')}`")
        if item.get("section"):
            lines.append(f"- 章节：`{item['section']}`")
        if item.get("table_number"):
            lines.append(f"- 表格：`{item['table_number']}`")
        if item.get("snippet"):
            lines.append(f"\n{item['snippet']}")
        return "\n".join(lines)

    def _format_relation(self, edge: dict[str, Any]) -> str:
        """Build relation details with links to the best available TUI destination."""

        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        relation = str(edge.get("relation") or "-")
        source_ref = edge.get("source_ref") or {}
        lines = [f"## {relation}"]

        source_link = self._entity_or_search_link(source, "查看源实体")
        target_link = self._target_link(target)
        lines.extend(
            [
                f"\n- 源：{source_link}",
                f"- 目标：{target_link}",
                f"- 关系：`{relation}`",
            ]
        )

        section = str(source_ref.get("section") or "")
        table = str(source_ref.get("table") or "").removeprefix("table-")
        if section:
            lines.append(f"- 出处章节：{internal_link(section, 'chapter', section)}")
        if table:
            lines.append(f"- 出处表格：{internal_link('Table ' + table, 'table', table)}")

        lines.extend(["\n### 完整目标内容", "", escape_markdown(target) or "（无目标内容）"])

        component = self._find_component(source, target)
        if component:
            lines.extend(["\n### 组件信息", ""])
            for label, key in (
                ("BrowseName", "browse_name"),
                ("NodeClass", "node_class"),
                ("ReferenceType", "reference_type"),
                ("DataType", "data_type"),
                ("TypeDefinition", "type_definition"),
                ("ModellingRule", "modelling_rule"),
            ):
                if component.get(key):
                    lines.append(f"- **{label}**：`{component[key]}`")
        return "\n".join(lines)

    def _entity_or_search_link(self, entity_id: str, label: str) -> str:
        if self.kb.get_entity(entity_id):
            return internal_link(label, "entity", entity_id)
        return internal_link(label, "search", relation_search_term(entity_id))

    def _target_link(self, target: str) -> str:
        """Choose entity, chapter, table, or search navigation for a target ID."""

        entity = self.kb.get_entity(target)
        if entity:
            return internal_link(str(entity.get("name") or target), "entity", target)
        if target.startswith("sec-"):
            section = target.removeprefix("sec-")
            return internal_link(f"章节 {section}", "chapter", section)
        if target.startswith("table-"):
            number = target.removeprefix("table-")
            return internal_link(f"Table {number}", "table", number)
        label = compact_relation_target(target, limit=32)
        return internal_link(label, "search", relation_search_term(target))

    def _find_component(self, source: str, target: str) -> dict[str, Any] | None:
        entity = self.kb.get_entity(source)
        if not entity:
            return None
        # Builder-generated component targets may have a trailing ``1`` to make an
        # instance ID unique, while the source entity keeps the original BrowseName.
        target_name = target.split(":", 1)[-1].split(".")[-1]
        for component in entity.get("components") or []:
            browse_name = str(component.get("browse_name") or "")
            if browse_name == target_name or f"{browse_name}1" == target_name:
                return component
        return None

    def _open_linked_entity(self, entity_id: str) -> None:
        """Load an internal entity link and transfer focus to the entity tab."""

        entity = self.kb.get_entity(entity_id)
        if not entity:
            self.notify(f"未找到实体：{entity_id}", severity="warning")
            return
        self.query_one("#entity-name", Input).value = entity_id
        self.query_one("#entity-detail", Markdown).update(format_entity(entity))
        self.query_one(TabbedContent).active = "entity-tab"
        self.query_one("#entity-name", Input).focus()
        self._set_status(f"已从关系页打开实体：{entity['name']}")

    def _open_linked_chapter(self, section: str) -> None:
        self.query_one("#chapter-number", Input).value = section
        self._show_chapter()
        self.query_one(TabbedContent).active = "docs-tab"
        self.query_one("#chapter-number", Input).focus()

    def _open_linked_table(self, number: str) -> None:
        self.query_one("#table-number", Input).value = number
        self._show_table()
        self.query_one(TabbedContent).active = "docs-tab"
        self.query_one("#table-number", Input).focus()

    def _open_linked_search(self, query: str) -> None:
        self.query_one("#search-query", Input).value = query
        self._search()
        self.query_one(TabbedContent).active = "search-tab"
        self.query_one("#search-query", Input).focus()

    def _set_status(self, message: str) -> None:
        self.query_one("#status-line", Static).update(message)


def format_entity(entity: dict[str, Any]) -> str:
    """Render one entity record as a readable Markdown detail document."""

    lines = [f"## {entity.get('name', entity.get('id', '实体'))}"]
    lines.extend(
        [
            f"\n- ID：`{entity.get('id', '-')}`",
            f"- 类型：`{entity.get('kind', '-')}`",
            f"- 章节：`{entity.get('section') or '-'}`",
            f"- 相关表格：`{', '.join(entity.get('related_tables') or []) or '-'}`",
        ]
    )
    if entity.get("supertype"):
        lines.append(f"- 父类型：`{entity['supertype']}`")
    summary = _best_summary(entity)
    if summary:
        lines.extend(["\n### 摘要", "", str(summary)])
    attributes = entity.get("attributes") or {}
    if attributes:
        lines.extend(["\n### 属性", ""])
        lines.extend(f"- **{key}**：`{value}`" for key, value in attributes.items())
    components = entity.get("components") or []
    if components:
        lines.extend(["\n### 组件 / 引用", ""])
        lines.extend(
            f"- `{item.get('reference_type', '-')}` **{item.get('browse_name', '-')}** "
            f"({item.get('node_class', '-')}; {item.get('data_type') or item.get('type_definition') or '-'}) "
            f"{item.get('modelling_rule') or ''}"
            for item in components
        )
    fields = entity.get("fields") or []
    if fields:
        lines.extend(["\n### 字段", ""])
        lines.extend(
            f"- **{item.get('name', '-')}**：`{item.get('type', '-')}` — {item.get('description') or ''}"
            for item in fields
        )
    enum_values = entity.get("enum_values") or []
    if enum_values:
        lines.extend(["\n### 枚举值", ""])
        lines.extend(
            f"- `{item.get('value', '-')}` **{item.get('name', '-')}**：{item.get('description') or ''}"
            for item in enum_values
        )
    return "\n".join(lines)


def compact_entity_name(entity_id: str) -> str:
    return entity_id.split(":", 1)[-1]


def compact_relation_target(target: str, limit: int = 52) -> str:
    """Create a single-line target preview without losing the full stored value."""

    compact = " ".join(target.split())
    if ":" in compact:
        compact = compact.split(":", 1)[1]
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def relation_search_term(target: str) -> str:
    """Extract a bounded, useful fallback query from an unresolved target ID."""

    value = target.split(":", 1)[-1]
    if "." in value and len(value) < 160:
        value = value.rsplit(".", 1)[-1]
    return " ".join(value.split())[:120]


def internal_link(label: str, kind: str, value: str) -> str:
    """Build an encoded Markdown link handled by ``on_markdown_link_clicked``."""

    return f"[{escape_markdown(label)}]({kind}:{quote(value, safe='')})"


def escape_markdown(value: str) -> str:
    """Escape user/data-controlled text used inside generated Markdown."""

    escaped = value.replace("\\", "\\\\")
    for character in ("`", "*", "_", "[", "]", "<", ">"):
        escaped = escaped.replace(character, f"\\{character}")
    return escaped


def format_chapter(chapter: dict[str, Any]) -> str:
    """Render chapter metadata and source text as Markdown."""

    title = chapter.get("title") or chapter.get("section") or "章节"
    lines = [f"## {chapter.get('section', '')} {title}".strip()]
    path = chapter.get("path") or []
    if path:
        lines.append(f"\n**路径：** {' / '.join(path)}")
    if chapter.get("entities"):
        lines.append(f"\n**实体：** {', '.join(chapter['entities'])}")
    if chapter.get("tables"):
        lines.append(f"\n**表格：** {', '.join(map(str, chapter['tables']))}")
    lines.extend(["\n---\n", str(chapter.get("text") or "（无正文）")])
    return "\n".join(lines)


def table_grid_data(table: dict[str, Any]) -> tuple[list[str], list[list[Any]]]:
    """Convert structured rows or raw CSV lines into a rectangular TUI table."""

    columns = [str(column) for column in (table.get("columns") or table.get("headers") or [])]
    structured_rows = table.get("rows") or []
    if columns and structured_rows:
        rows: list[list[Any]] = []
        for row in structured_rows:
            if isinstance(row, dict):
                rows.append([row.get(column, "") for column in columns])
            elif isinstance(row, (list, tuple)):
                rows.append(list(row[: len(columns)]))
        if rows:
            return columns, rows

    raw_lines = [str(line) for line in (table.get("raw_lines") or []) if str(line).strip()]
    if not raw_lines:
        return ["内容"], [["（无表格数据）"]]

    # Some early specification tables only retain their source CSV lines.
    parsed = list(csv.reader(raw_lines))
    raw_columns = [cell.strip() for cell in parsed[0]]
    if len(raw_columns) <= 1:
        return ["内容"], [[line] for line in raw_lines]

    rows = []
    for parsed_row in parsed[1:]:
        if len(parsed_row) != len(raw_columns):
            if rows:
                # Explanatory prose often follows the CSV block in raw_lines.
                break
            continue
        rows.append([cell.strip() for cell in parsed_row])
    return raw_columns, rows or [[""] * len(raw_columns)]


def format_table_cell(value: Any) -> str:
    """Convert scalar or nested structured values to DataTable-safe text."""

    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def format_table(table: dict[str, Any]) -> str:
    """Render the source-preserving structured view of a table."""

    lines = [f"## 表 {table.get('number', '')}：{table.get('caption', '')}"]
    lines.append(f"\n- ID：`{table.get('id', '-')}`")
    lines.append(f"- 章节：`{table.get('section', '-')}`")
    headers = table.get("headers") or table.get("columns") or []
    rows = table.get("rows") or []
    if headers and rows:
        lines.extend(["\n### 结构化数据", "", "```json", json.dumps({"headers": headers, "rows": rows}, ensure_ascii=False, indent=2), "```"])
    elif table.get("raw_lines"):
        lines.extend(["\n### 原始内容", "", "```text", "\n".join(table["raw_lines"]), "```"])
    return "\n".join(lines)


def _best_summary(entity: dict[str, Any]) -> str:
    """Prefer Chinese unless known mojibake markers indicate damaged source text."""

    summary_zh = str(entity.get("summary_zh") or "")
    mojibake_markers = ("鏄", "锛", "銆", "绗", "鐨", "€", "鍨", "瀹")
    if summary_zh and not any(marker in summary_zh for marker in mojibake_markers):
        return summary_zh
    return str(entity.get("summary_en") or summary_zh)


def main() -> None:
    """Validate the project root and launch the terminal application."""

    parser = argparse.ArgumentParser(description="启动 OPC UA 10000-5 知识库 TUI。")
    parser.add_argument("--root", default=str(ROOT), help="知识库项目根目录。")
    parser.add_argument("--retrieval-mode", choices=("auto", "hybrid", "fts"), default="auto")
    parser.add_argument("--embedding-model", default=None, help="Local sentence-transformers model name.")
    parser.add_argument("--offline", action="store_true", help="Disable online LLM generation in the TUI.")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    required = [root / "kb" / "entities.jsonl", root / "indexes" / "fts.sqlite"]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        parser.error("知识库文件不存在：" + ", ".join(missing))
    KnowledgeBaseTUI(
        root,
        retrieval_mode=args.retrieval_mode,
        embedding_model=args.embedding_model,
        online=not args.offline,
    ).run()


if __name__ == "__main__":
    main()
