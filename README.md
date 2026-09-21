# OPC UA 10000-5 结构化实体知识库

数据源：`C:\Users\admin\Downloads\OPC-10000-5-v1.05.06.md`

版本：1.05.06

发布时间：2025-10-22

## 统计

- Chapters: 301
- Tables: 323
- Entities: 262
- Relationships: 2537

## 常用命令

```powershell
python help.py
python tools/help.py
python tools/query_kb.py "ServerType 包含哪些组件？" --top-k 8
python tools/inspect_entity.py ServerType
python tools/trace_entity.py ServerType --relation HAS_COMPONENT --depth 1
python tools/demo_graph.py
python tools/graph_kb.py --format html --output exports/knowledge_graph.html
```

## Help / 帮助菜单

运行统一帮助菜单查看所有可用功能、示例命令、Python API 和关系过滤器：

```powershell
python help.py
python tools/help.py
python tools/ask_kb.py "ServerType" --offline
```

## Part 5 RAG 问答

```powershell
$env:DEEPSEEK_API_KEY = "..."
python tools/ask_kb.py "ServerType 包含哪些组件？" --top-k 5
python tools/ask_kb.py "ServerType 包含哪些组件？" --offline
```

命令会输出回答模式、Part 5 引用标签和检索记录 ID。请将 API 密钥保存在环境变量中。

每个 CLI 也支持 `--help`：

```powershell
python tools/build_kb.py --help
python tools/query_kb.py --help
python tools/inspect_entity.py --help
python tools/trace_entity.py --help
python tools/demo_graph.py --help
python tools/graph_kb.py --help
```

## 功能概览

- 构建知识库：从 OPC UA 10000-5 Markdown 源文件生成结构化 JSONL 和 FTS5 索引。
- 查询知识库：支持实体名、自然语言、章节号、表格号检索。
- 查看实体：输出实体卡片，包括章节、表格、属性、组件、字段、枚举值和中英摘要。
- 追踪关系：按 `HAS_COMPONENT`、`HAS_PROPERTY`、`USES_DATATYPE` 等关系过滤实体图。
- 设计知识图谱：生成 JSON 或离线 HTML，显示实体之间的关系类型和关联度权重。
- Python API：通过 `from opcua_kb import KnowledgeBase` 在本地脚本中调用。

## TUI 交互界面

首次使用时安装可选的 TUI 依赖：

```powershell
python -m pip install -r requirements-tui.txt
```

然后在项目根目录启动：

```powershell
python tui.py
```

TUI 提供搜索、实体详情、关系追踪、章节/表格浏览，以及交互式知识图谱导出。
使用 `Tab` 在控件间移动，`Enter` 执行操作，`Ctrl+F` 回到搜索，`Ctrl+Q` 退出。

## 知识图谱

生成全局知识图谱：

```powershell
python tools/demo_graph.py
python tools/graph_kb.py --format html --output exports/knowledge_graph.html
python tools/graph_kb.py --format json --output exports/knowledge_graph.json
```

围绕某个实体生成局部图谱：

```powershell
python tools/graph_kb.py --focus ServerType --depth 2 --format html --output exports/server_type_graph.html
```

只查看指定关系：

```powershell
python tools/graph_kb.py --relation HAS_COMPONENT,USES_DATATYPE --min-weight 3 --format json
```

图谱中的节点代表实体，边代表实体之间的关系。边的 `weight` 是聚合后的关联度，数值越大表示两个实体之间通过更多或更强的关系连接。
