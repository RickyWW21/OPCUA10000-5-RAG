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
```

## Help / 帮助菜单

运行统一帮助菜单查看所有可用功能、示例命令、Python API 和关系过滤器：

```powershell
python help.py
python tools/help.py
```

每个 CLI 也支持 `--help`：

```powershell
python tools/build_kb.py --help
python tools/query_kb.py --help
python tools/inspect_entity.py --help
python tools/trace_entity.py --help
```

## 功能概览

- 构建知识库：从 OPC UA 10000-5 Markdown 源文件生成结构化 JSONL 和 FTS5 索引。
- 查询知识库：支持实体名、自然语言、章节号、表格号检索。
- 查看实体：输出实体卡片，包括章节、表格、属性、组件、字段、枚举值和中英摘要。
- 追踪关系：按 `HAS_COMPONENT`、`HAS_PROPERTY`、`USES_DATATYPE` 等关系过滤实体图。
- Python API：通过 `from opcua_kb import KnowledgeBase` 在本地脚本中调用。
