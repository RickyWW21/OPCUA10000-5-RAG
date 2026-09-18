# OPC UA 10000-5 Part 5

## 结构化知识库与混合 RAG 使用说明手册

文档日期：2026-09-18
项目：`OPCUA10000-5`

本手册只针对 OPC UA 10000-5 Part 5（Information Model）。所有检索、向量索引和回答生成均受 Part 5 文档边界约束。

## 1. 项目概览

项目把 OPC UA 10000-5 Part 5 Markdown 解析为结构化知识库，提供：

- 精确实体、表格和章节匹配
- SQLite FTS5 全文检索
- 可选本地 embedding 向量检索
- FTS5 + 向量混合排序
- 关系扩展与知识图谱
- 离线 RAG 回答和引用
- 可选 OpenAI-compatible LLM 生成
- TUI 交互界面
- Recall@1、Recall@3 检索评测

### 1.1 处理流程

```text
Part 5 Markdown
    -> builder.py
    -> kb/*.jsonl + indexes/fts.sqlite
    -> optional sentence-transformers
    -> indexes/embeddings.jsonl + embeddings.meta.json
    -> exact + FTS5 + vector hybrid retrieval
    -> RAGPipeline
    -> offline answer / optional LLM answer
```

### 1.2 目录说明

| 目录/文件 | 用途 |
|---|---|
| `source/` | 原始 Part 5 Markdown 与 `source_manifest.json` |
| `kb/` | 章节、表格、实体、关系、文本块和别名 |
| `indexes/` | `fts.sqlite`，以及可选向量索引 |
| `tools/` | 命令行工具和 TUI |
| `opcua_kb/` | Python API、解析、检索、RAG、图谱和向量模块 |
| `tests/` | 单元测试、混合检索测试和评测 fixture |

## 2. 安装与环境准备

### 2.1 推荐使用项目虚拟环境

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-tui.txt
python -m pip install -r requirements-embeddings.txt
```

也可以使用系统 Python 安装同样依赖。TUI 需要 Textual，混合向量检索需要 `sentence-transformers`。

### 2.2 准备 embedding 模型

推荐模型：`sentence-transformers/all-MiniLM-L6-v2`。

```powershell
python -c "from sentence_transformers import SentenceTransformer; m=SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2'); m.save(r'.\models\all-MiniLM-L6-v2'); print(m.get_embedding_dimension())"
```

模型保存位置：

```text
models/all-MiniLM-L6-v2
```

当前项目已验证该模型的 embedding 维度为 `384`。模型目录已加入 `.gitignore`，不应提交到 Git。

### 2.3 验证离线加载

```powershell
python -c "from sentence_transformers import SentenceTransformer; m=SentenceTransformer(r'.\models\all-MiniLM-L6-v2', local_files_only=True); print(m.get_embedding_dimension())"
```

如果模型下载失败，可在可联网环境下载完整模型目录，再复制到 `models/all-MiniLM-L6-v2`。

### 2.4 当前已准备资产

- 系统 Python 与项目 `.venv` 均已安装 `sentence-transformers`。
- 模型已保存到 `models/all-MiniLM-L6-v2`。
- Part 5 向量索引已生成 886 条记录，维度为 384。

## 3. 构建知识库

### 3.1 基础构建（仅 FTS5）

```powershell
python tools/build_kb.py --source ".\source\OPC-10000-5-v1.05.06.md" --root . --rebuild
```

基础构建不依赖 embedding 模型，生成结构化 JSONL 和 SQLite FTS5 索引。

### 3.2 构建向量索引

```powershell
python tools/build_kb.py `
  --source ".\source\OPC-10000-5-v1.05.06.md" `
  --root . `
  --embeddings `
  --embedding-model ".\models\all-MiniLM-L6-v2"
```

元数据包含文档 ID、源文件 SHA-256、模型标识、维度和构建时间。

### 3.3 构建参数

| 参数 | 作用 |
|---|---|
| `--source` | 指定 Part 5 Markdown 源文件 |
| `--root` | 指定知识库根目录 |
| `--rebuild` | 强制重新复制源文件并重建产物 |
| `--embeddings` | 启用向量索引构建，默认关闭 |
| `--embedding-model` | 指定本地模型目录或模型标识 |

> 构建索引和查询必须使用相同的模型标识，否则向量索引会被判定为不匹配并回退 FTS5。

## 4. 命令行功能

### 4.1 帮助

```powershell
python help.py
python tools/help.py
```

### 4.2 普通检索：`query_kb.py`

```powershell
python tools/query_kb.py "ServerType 包含哪些组件？" --top-k 8
python tools/query_kb.py "BuildInfo 字段" --top-k 5
python tools/query_kb.py "12.10" --top-k 3
python tools/query_kb.py "Table C.1" --top-k 2
```

用于查看精确实体、章节、表格和文本块结果，不生成回答。

### 4.3 实体卡片：`inspect_entity.py`

```powershell
python tools/inspect_entity.py ServerType
python tools/inspect_entity.py ObjectType:ServerType
python tools/inspect_entity.py BuildInfo
```

输出类型、章节、表格、属性、组件、字段、枚举值和摘要。

### 4.4 关系追踪：`trace_entity.py`

```powershell
python tools/trace_entity.py ServerType --relation HAS_COMPONENT --depth 1
python tools/trace_entity.py BuildInfo --depth 2
```

支持 `HAS_COMPONENT`、`HAS_PROPERTY`、`USES_DATATYPE`、`DEFINED_BY_TABLE` 等关系。

### 4.5 Part 5 RAG：`ask_kb.py`

```powershell
python tools/ask_kb.py "ServerType 包含哪些组件？" --offline `
  --embedding-model ".\models\all-MiniLM-L6-v2"

python tools/ask_kb.py "ServerType 包含哪些组件？" --offline --no-embeddings

python tools/ask_kb.py "ServerType 包含哪些组件？" --top-k 5
```

| 参数 | 作用 |
|---|---|
| `question` | Part 5 自然语言问题 |
| `--top-k` | 证据数量，默认 6 |
| `--relationship-depth` | 关系扩展深度，默认 0 |
| `--offline` | 不调用 LLM，返回本地 RAG 回答 |
| `--no-embeddings` | 强制只使用精确匹配 + FTS5 |
| `--embedding-model` | 指定本地 embedding 模型 |
| `--root` | 指定知识库根目录 |

## 5. 混合 RAG

### 5.1 检索模式

| 模式 | 行为 |
|---|---|
| `exact` | 命中实体、表格或章节时优先返回精确结果 |
| `fts` | 使用 SQLite FTS5；没有可用向量索引时自动使用 |
| `hybrid` | 精确结果置顶，剩余候选由 FTS5 与向量结果加权融合 |

### 5.2 向量索引校验

- 只接受 `doc=OPC-10000-5` 的记录。
- 校验 `source_hash`，防止源文档变化后误用旧索引。
- 校验 `model_name` 和 `dimension`，防止模型不一致。
- 文件缺失、损坏或模型不可用时自动回退 FTS5。

### 5.3 回答与引用

`RAGPipeline` 将结果序列化为 `[E1]`、`[C1]`、`[T1]` 等标签，并限制上下文长度。离线模式返回本地证据；在线模式将证据发送给 OpenAI-compatible Chat Model。

### 5.4 在线模型配置

```powershell
$env:DEEPSEEK_API_KEY = "..."
$env:DEEPSEEK_MODEL = "deepseek-chat"
python tools/ask_kb.py "ServerType 是什么？"
```

API key 只放在环境变量中，不要写入 `config.toml`、README、源代码或 Git。

### 5.5 Python API

```python
from opcua_kb import KnowledgeBase, RAGPipeline
from opcua_kb.retrieval import Part5Retriever

answer = RAGPipeline(
    retriever=Part5Retriever(KnowledgeBase("."))
).ask("ServerType 包含哪些组件？", top_k=5)

print(answer.answer)
print(answer.citations)
```

## 6. TUI 交互界面

### 6.1 启动

```powershell
python tui.py --offline
python tui.py --retrieval-mode hybrid --embedding-model ".\models\all-MiniLM-L6-v2" --offline
```

TUI 包含搜索、实体、关系、章节/表格和知识图谱工作流。

### 6.2 搜索页

- 输入实体名称、自然语言问题、章节号或表格号。
- 选择返回数量、检索模式和关系扩展深度。
- 勾选在线生成后，在有 API key 时调用 LLM。
- 详情显示 RAG 回答、检索模式、生成模式和引用。

### 6.3 实体页

查看实体类型、章节、表格、摘要、属性、组件、字段和枚举值。

### 6.4 关系页

按实体、关系类型和深度查看关系目标，并跳转到实体、章节或表格。

### 6.5 章节/表格页

按章节号或表格号查看原文、结构化数据和常规表格视图。

### 6.6 知识图谱页

按焦点实体、关系、深度和节点数生成 HTML 或 JSON 图谱。

### 6.7 快捷键

| 快捷键 | 功能 |
|---|---|
| `Ctrl+F` | 聚焦搜索输入框 |
| `F1` | 显示快捷提示 |
| `Ctrl+Q` | 退出 TUI |
| `Enter` | 执行当前输入框查询 |

## 7. 知识图谱与评测

### 7.1 图谱命令

```powershell
python tools/demo_graph.py
python tools/graph_kb.py --format html --output exports/knowledge_graph.html
python tools/graph_kb.py --format json --output exports/knowledge_graph.json
python tools/graph_kb.py --focus ServerType --depth 2 --format html
python tools/graph_kb.py --relation HAS_COMPONENT,USES_DATATYPE --min-weight 3 --format json
```

| 参数 | 作用 |
|---|---|
| `--focus` | 指定中心实体 |
| `--relation` | 关系过滤器 |
| `--depth` | 焦点图遍历深度 |
| `--min-weight` | 最小聚合边权重 |
| `--include-defined` | 包含章节/表格定义关系 |
| `--format` | `html` 或 `json` |
| `--output` | 输出文件路径 |

### 7.2 检索评测

```powershell
python tools/evaluate_retrieval.py
```

评测 fixture 位于 `tests/fixtures/part5_retrieval_eval.json`，输出 Recall@1 与 Recall@3。

### 7.3 测试

```powershell
python -m unittest discover -v
```

测试覆盖 API、构建器、错误边界、embedding provider、向量索引、混合检索、TUI RAG 装配和评测工具。

## 8. Python 模块与扩展点

| 模块 | 主要功能 |
|---|---|
| `opcua_kb.api` | `KnowledgeBase`：实体、章节、表格、FTS5 和关系访问 |
| `opcua_kb.builder` | 解析源文档并生成 JSONL、FTS5 和向量索引 |
| `opcua_kb.embeddings` | embedding provider、Sentence Transformer、余弦相似度 |
| `opcua_kb.vector_index` | JSONL 向量索引、元数据校验和搜索 |
| `opcua_kb.retrieval` | `Part5Retriever`、混合排序和关系扩展 |
| `opcua_kb.rag` | `RAGPipeline`、上下文限制、离线回答和引用 |
| `opcua_kb.graph` | 知识图谱模型、聚合边和 HTML/JSON 输出 |
| `tools/tui.py` | 完整 TUI 前端 |

## 9. 常见问题与排查

### 9.1 显示 `retrieval=fts`

检查模型依赖、模型目录、两个 embedding 文件和 `source_manifest.json`，并确认构建/查询使用同一模型标识。

### 9.2 向量索引过期

源 Markdown 变化后 `source_hash` 会变化，重新执行带 `--embeddings` 的构建即可。

### 9.3 在线回答失败

检查 API key、模型名和 base URL；`RAGPipeline` 会回退为离线回答。

### 9.4 找不到模型

使用完整本地模型目录，并先用 `local_files_only=True` 验证。

### 9.5 Python 环境不一致

```powershell
python -c "import sys; print(sys.executable)"
.\.venv\Scripts\python.exe -c "import sys; print(sys.executable)"
```

安装依赖和运行命令必须使用同一个 Python 环境。

## 10. 推荐工作流

1. 激活 `.venv` 并安装 TUI、embedding 依赖。
2. 下载并保存 `all-MiniLM-L6-v2`。
3. 执行带 `--embeddings` 的 Part 5 构建。
4. 运行 `evaluate_retrieval.py` 检查 Recall@1/Recall@3。
5. 使用 `ask_kb.py` 验证命令行 RAG。
6. 使用 `tui.py --retrieval-mode hybrid --offline` 进行交互查询。
7. 需要生成式回答时，再配置 API key 并开启在线生成。

> 默认原则：本地优先、Part 5 边界优先、向量可选、失败可回退。没有 embedding 模型时，精确匹配、FTS5、关系和知识图谱仍然可用。
