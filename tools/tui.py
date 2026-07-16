from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path
from typing import Any

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

from opcua_kb import KnowledgeBase, write_graph_html, write_graph_json


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

    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = root
        self.kb = KnowledgeBase(root)
        self.search_results: dict[str, dict[str, Any]] = {}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
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
                yield DataTable(id="relation-results", classes="full-detail", cursor_type="row")

            with TabPane("章节 / 表格", id="docs-tab"):
                with Horizontal(classes="toolbar"):
                    yield Input(placeholder="章节号，例如 8.3.1", id="chapter-number")
                    yield Button("查看章节", variant="primary", id="chapter-button")
                    yield Input(placeholder="表格号，例如 15 或 C.1", id="table-number")
                    yield Button("查看表格", variant="primary", id="table-button")
                yield Markdown(
                    "## 文档浏览\n\n输入章节号或表格号查看结构化内容。",
                    id="docs-detail",
                    classes="full-detail",
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
        search_table = self.query_one("#search-results", DataTable)
        search_table.add_columns("类型", "标题", "章节")
        relation_table = self.query_one("#relation-results", DataTable)
        relation_table.add_columns("源实体", "关系", "目标实体", "出处")
        self.query_one("#search-query", Input).focus()

    def action_focus_search(self) -> None:
        self.query_one(TabbedContent).active = "search-tab"
        self.query_one("#search-query", Input).focus()

    def action_show_help(self) -> None:
        self.notify("Ctrl+F 搜索，Tab 切换控件，Enter 执行，Ctrl+Q 退出", title="快捷键")

    def on_input_submitted(self, event: Input.Submitted) -> None:
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
        if event.data_table.id != "search-results":
            return
        item = self.search_results.get(str(event.row_key.value))
        if item:
            self.query_one("#search-detail", Markdown).update(self._format_search_result(item))

    def _search(self) -> None:
        query = self.query_one("#search-query", Input).value.strip()
        if not query:
            self.notify("请输入搜索内容。", severity="warning")
            return
        top_k = int(self.query_one("#search-limit", Select).value)
        results = self.kb.search(query, top_k=top_k)
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
            self.query_one("#search-detail", Markdown).update(self._format_search_result(results[0]))
        else:
            self.query_one("#search-detail", Markdown).update(f"## 未找到结果\n\n查询：`{query}`")
        self._set_status(f"搜索完成：{len(results)} 条结果")

    def _show_entity(self) -> None:
        name = self.query_one("#entity-name", Input).value.strip()
        if not name:
            self.notify("请输入实体名。", severity="warning")
            return
        entity = self.kb.get_entity(name)
        target = self.query_one("#entity-detail", Markdown)
        if not entity:
            target.update(f"## 未找到实体\n\n`{name}`")
            self._set_status("实体查询无结果")
            return
        target.update(format_entity(entity))
        self._set_status(f"已加载实体：{entity['name']}")

    def _show_relations(self) -> None:
        entity = self.query_one("#relation-entity", Input).value.strip()
        if not entity:
            self.notify("请输入实体名。", severity="warning")
            return
        relation = str(self.query_one("#relation-kind", Select).value or "") or None
        depth = int(self.query_one("#relation-depth", Select).value)
        edges = self.kb.relationships(entity, relation=relation, depth=depth)
        table = self.query_one("#relation-results", DataTable)
        table.clear()
        for edge in edges:
            source_ref = edge.get("source_ref") or {}
            source = " ".join(
                str(value) for value in (source_ref.get("section"), source_ref.get("table")) if value
            )
            table.add_row(
                str(edge.get("source", "")),
                str(edge.get("relation", "")),
                str(edge.get("target", "")),
                source or "-",
            )
        self._set_status(f"关系追踪完成：{len(edges)} 条边")
        if not edges:
            self.notify("未找到匹配关系。", severity="warning")

    def _show_chapter(self) -> None:
        section = self.query_one("#chapter-number", Input).value.strip()
        chapter = self.kb.chapter(section) if section else None
        target = self.query_one("#docs-detail", Markdown)
        if not chapter:
            target.update(f"## 未找到章节\n\n`{section or '（空）'}`")
            self._set_status("章节查询无结果")
            return
        target.update(format_chapter(chapter))
        self._set_status(f"已加载章节：{section}")

    def _show_table(self) -> None:
        number = self.query_one("#table-number", Input).value.strip()
        table = self.kb.table(number) if number else None
        target = self.query_one("#docs-detail", Markdown)
        if not table:
            target.update(f"## 未找到表格\n\n`{number or '（空）'}`")
            self._set_status("表格查询无结果")
            return
        target.update(format_table(table))
        self._set_status(f"已加载表格：{number}")

    def _generate_graph(self, open_after: bool) -> None:
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

    def _set_status(self, message: str) -> None:
        self.query_one("#status-line", Static).update(message)


def format_entity(entity: dict[str, Any]) -> str:
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


def format_chapter(chapter: dict[str, Any]) -> str:
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


def format_table(table: dict[str, Any]) -> str:
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
    summary_zh = str(entity.get("summary_zh") or "")
    mojibake_markers = ("鏄", "锛", "銆", "绗", "鐨", "€", "鍨", "瀹")
    if summary_zh and not any(marker in summary_zh for marker in mojibake_markers):
        return summary_zh
    return str(entity.get("summary_en") or summary_zh)


def main() -> None:
    parser = argparse.ArgumentParser(description="启动 OPC UA 10000-5 知识库 TUI。")
    parser.add_argument("--root", default=str(ROOT), help="知识库项目根目录。")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    required = [root / "kb" / "entities.jsonl", root / "indexes" / "fts.sqlite"]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        parser.error("知识库文件不存在：" + ", ".join(missing))
    KnowledgeBaseTUI(root).run()


if __name__ == "__main__":
    main()
