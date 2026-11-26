# OPC UA 10000-5 结构化知识库与 RAG 系统

基于 **OPC Unified Architecture Part 5: Information Model**（`OPC-10000-5` v1.05.06，发布时间 `2025-10-22`）构建的本地结构化实体知识库、纯规范 FTS5 RAG 问答系统、知识图谱工具与多端交互平台。

- 规范源文件：`source/OPC-10000-5-v1.05.06.md`（附 `source/source_manifest.json` 校验清单）
- 结构化规模：**301 个章节 · 323 张表格 · 262 个实体 · 2,537 条关系**

---

## 核心架构

本仓库采用精简、可溯源的 **纯规范 FTS5（Spec-only FTS5）** 架构：

- **无状态检索主干**：结合精确实体/章节/表格匹配、SQLite FTS5 全文索引（`indexes/fts.sqlite`）与可选关系图谱扩展（`relationship_depth`），不依赖本地向量索引或外部 Wiki 混合检索。
- **规范原文行级溯源**：通过 `opcua_kb/source_view.py` 对齐磁盘实际规范文件字节 SHA-256，支持点击 `[E*]` / `[T*]` / `[C*]` / `[R*]` 引用直接查看精确行号范围；旧会话中残留的历史 Wiki 引用自动降级为只读草稿标识。
- **统一工厂与多端复用**：CLI、TUI、FastAPI Web 控制台与 MCP Server 共用 `create_retriever` / `create_chat_model_from_env` 工厂及核心 RAG 管线。
- **静态参考资产**：`wiki/` 目录（12 个实体页 + 3 个主题页）与 `reports/` 历史评测报告保留为静态参考文档，不参与运行时问答。

---

## 目录结构

```text
OPCUA10000-5/
├── source/              # OPC-10000-5 v1.05.06 Markdown 原文与 source_manifest.json
├── kb/                  # 结构化知识库产物（chapters/tables/entities/relationships/chunks/aliases）
├── indexes/             # SQLite FTS5 全文检索索引（fts.sqlite）
├── opcua_kb/            # 核心 Python 包（api, builder, retrieval, rag, llm, source_view, graph, http_api, session_store, mcp_server）
├── tools/               # Core CLI 工具集、TUI 实现、检索评测与静态 Wiki 校验脚本
├── web/                 # React 19 + TypeScript + Vite Web 控制台前端
├── wiki/                # 静态参考 Wiki 文档（不参与运行时 RAG）
├── reports/             # 历史 RAG / Wiki 评测报告与归档数据
├── tests/               # 单元测试与接口测试
├── api_server.py        # FastAPI 服务启动入口
├── tui.py               # Textual TUI 启动入口
└── help.py              # 统一帮助菜单入口
```

---

## 快速开始

### 1. Core CLI（`tools/`）

```powershell
# 查看完整帮助菜单
python help.py

# 检索实体、章节、表格与切片
python tools/query_kb.py "ServerType 包含哪些组件？" --top-k 8

# 查看实体卡片 / 追踪实体关系
python tools/inspect_entity.py ServerType
python tools/trace_entity.py ServerType --relation HAS_COMPONENT --depth 1

# Part 5 RAG 问答（支持离线检索或在线 LLM 生成）
python tools/ask_kb.py "ServerType 包含哪些组件？" --offline
$env:DEEPSEEK_API_KEY = "..."
python tools/ask_kb.py "ServerType 包含哪些组件？" --top-k 5

# 检索基线评测
python tools/evaluate_retrieval.py
```

每个 CLI 均支持 `--help`（`build_kb.py`、`query_kb.py`、`inspect_entity.py`、`trace_entity.py`、`demo_graph.py`、`graph_kb.py`、`ask_kb.py`、`evaluate_retrieval.py`）。

### 2. TUI 交互界面（`tui.py`）

安装可选依赖并启动终端工作台：

```powershell
python -m pip install -r requirements-tui.txt
python tui.py
```

提供搜索、实体详情、关系追踪、章节/表格浏览、Part 5 RAG 问答与离线知识图谱导出。快捷键：`Tab` 切换控件、`Enter` 执行、`Ctrl+F` 回到搜索、`Ctrl+Q` 退出。

### 3. Web 控制台（`api_server.py` + `web/`）

启动 FastAPI 后端（支持延迟初始化检索器，缺少清单时健康检查与会话接口仍可启动）：

```powershell
python -m pip install -r requirements-api.txt
python -m uvicorn api_server:app --reload --port 8000
```

启动 React 前端（默认将 `/api` 代理至 `http://127.0.0.1:8000`）：

```powershell
cd web
npm.cmd install
npm.cmd run dev
```

常用环境变量：

```powershell
$env:DEEPSEEK_API_KEY = "..."                         # 或 OPENAI_API_KEY
$env:CORS_ORIGINS = "http://localhost:5173,https://rag.example.com"
$env:SESSION_DB_PATH = "D:\rag-data\part5-sessions.sqlite3"
$env:SESSION_TTL_DAYS = "30"
$env:SESSION_COOKIE_SAMESITE = "lax"                  # 跨站 HTTPS 部署可用 none
$env:SESSION_COOKIE_SECURE = "true"                   # 仅 HTTPS 部署启用
```

Web 端使用匿名 `HttpOnly` Cookie 隔离浏览器会话，对话历史与引用证据默认持久化至 `data/rag_sessions.sqlite3`；API 文档位于 `/docs`、`/redoc` 与 `/openapi.json`。

### 4. MCP Server（`opcua_kb/mcp_server.py`）

安装 MCP 依赖后，可通过 stdio 协议接入支持 MCP / MCP App 的客户端：

```powershell
python -m pip install -r requirements-mcp.txt
python -m opcua_kb.mcp_server
# 如需启用环境变量配置的在线模型生成：
python -m opcua_kb.mcp_server --online
```

暴露只读工具 `ask_part5`（问答并返回带行号的引用）与 `open_part5_citation`（按引用句柄打开已校验的规范原文切片），以及交互式引用卡片资源 `ui://opcua/part5-citations.html`。

---

## 知识图谱与 Python API

生成全局或局部知识图谱（离线 HTML / JSON）：

```powershell
python tools/demo_graph.py
python tools/graph_kb.py --format html --output exports/knowledge_graph.html
python tools/graph_kb.py --focus ServerType --depth 2 --format html --output exports/server_type_graph.html
python tools/graph_kb.py --relation HAS_COMPONENT,USES_DATATYPE --min-weight 3 --format json
```

在 Python 脚本中直接调用：

```python
from opcua_kb import KnowledgeBase, RAGPipeline, create_retriever, create_chat_model_from_env

kb = KnowledgeBase(".")
entity = kb.get_entity("ServerType")
edges = kb.relationships("ObjectType:ServerType", "HAS_COMPONENT")

retriever = create_retriever(kb)
chat_model, _ = create_chat_model_from_env()
answer = RAGPipeline(retriever=retriever, chat_model=chat_model).ask("ServerType", top_k=5)
```

---

## 开发验证与测试

```powershell
# Python 单元测试
python -m unittest discover -s tests -t .

# 静态 Wiki 结构与引用校验
python tools/check_wiki.py

# Web 前端构建与代码检查
npm --prefix web run build
npm --prefix web run lint
```
