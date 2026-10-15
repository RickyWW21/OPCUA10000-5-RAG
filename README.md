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

## Streamlit RAG Web 前端

安装 Web 前端依赖：

```powershell
python -m pip install -r requirements-streamlit.txt
```

启动浏览器前端：

```powershell
python -m streamlit run streamlit_app.py
```

Web 前端支持多轮问答、`auto / hybrid / fts` 检索模式、证据数量、关系扩展深度、在线生成开关，以及回答引用和检索证据展开查看。语言模型仍通过 `DEEPSEEK_API_KEY` 或 `OPENAI_API_KEY` 环境变量配置。

## FastAPI + React 前端

安装后端依赖：

```powershell
python -m pip install -r requirements-api.txt
```

启动 FastAPI：

```powershell
python -m uvicorn api_server:app --reload --port 8000
```

启动 React 开发前端：

```powershell
cd web
npm.cmd install
npm.cmd run dev
```

React 开发服务器默认通过 `/api` 代理到 `http://127.0.0.1:8000`。部署到不同域名时，用 `CORS_ORIGINS` 配置允许的前端来源，例如：

```powershell
$env:CORS_ORIGINS = "http://localhost:5173,https://rag.example.com"
```

FastAPI 提供 `/docs`、`/redoc` 和 `/openapi.json`，React 前端保留现有 Streamlit 前端不受影响。

React 端使用匿名 `HttpOnly` Cookie 识别浏览器会话，不需要用户登录。会话、对话、消息、引用和检索证据默认保存在项目根目录的 `data/rag_sessions.sqlite3`。可通过环境变量调整：

```powershell
$env:SESSION_DB_PATH = "D:\rag-data\part5-sessions.sqlite3"
$env:SESSION_TTL_DAYS = "30"
$env:SESSION_COOKIE_SAMESITE = "lax"  # 跨站 HTTPS 部署可使用 none
$env:SESSION_COOKIE_SECURE = "true"  # 仅 HTTPS 部署时启用
```

清除浏览器 Cookie 会创建新的匿名会话；不同浏览器默认互相隔离。建议仅在可信局域网使用匿名模式，并通过防火墙限制服务端口。

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
