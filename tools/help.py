from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


HELP_TEXT = f"""
OPC UA 10000-5 Structured Entity Knowledge Base Help
OPC UA 10000-5 结构化实体知识库帮助菜单

Project root / 项目目录
  {ROOT}

Available data / 可用数据
  source/                  Original OPC UA 10000-5 Markdown and source_manifest.json
  kb/chapters.jsonl        Parsed sections with source locations
  kb/tables.jsonl          Parsed specification tables
  kb/entities.jsonl        Structured ObjectType, EventType, VariableType, ReferenceType, DataType, Method, Object entities
  kb/relationships.jsonl   Entity relationship graph
  kb/chunks.jsonl          Text chunks for full-text retrieval
  kb/aliases.json          Entity aliases for case-insensitive lookup
  indexes/fts.sqlite       SQLite FTS5 full-text index

Main commands / 主要命令
  python tools/help.py
      Show this help menu.
      显示本帮助菜单。

  python tools/build_kb.py --source "C:\\Users\\admin\\Downloads\\OPC-10000-5-v1.05.06.md" --rebuild
      Rebuild the local knowledge base from the OPC UA 10000-5 Markdown source.
      从 OPC UA 10000-5 Markdown 源文件重建本地知识库。

  python tools/query_kb.py "ServerType 包含哪些组件？" --top-k 8
      Search entities, sections, tables and chunks. Exact entity/table/section matches are prioritized.
      检索实体、章节、表格和文本切片；精确实体、表格、章节会优先返回。

  python tools/inspect_entity.py ServerType
      Print one entity card with section, tables, attributes, components, fields, enum values and summaries.
      查看单个实体卡片，包括章节、表格、属性、组件、字段、枚举值和中英摘要。

  python tools/trace_entity.py ServerType --relation HAS_COMPONENT --depth 1
      Trace graph relationships from an entity. Omit --relation to show all outgoing relations.
      追踪实体关系图；省略 --relation 可显示全部出边关系。

Common query examples / 常用查询示例
  python tools/query_kb.py "ServerType components" --top-k 5
  python tools/query_kb.py "BuildInfo 字段" --top-k 5
  python tools/query_kb.py "HasComponent 和 HasProperty" --top-k 5
  python tools/query_kb.py "12.10" --top-k 3
  python tools/query_kb.py "Table C.1" --top-k 2

Entity examples / 实体查看示例
  python tools/inspect_entity.py ServerType
  python tools/inspect_entity.py BaseEventType
  python tools/inspect_entity.py PropertyType
  python tools/inspect_entity.py HasComponent
  python tools/inspect_entity.py BuildInfo

Relationship examples / 关系追踪示例
  python tools/trace_entity.py ServerType --relation HAS_COMPONENT --depth 1
  python tools/trace_entity.py ObjectType:ServerType --relation HAS_PROPERTY --depth 1
  python tools/trace_entity.py BuildInfo --depth 1

Python API / Python 调用
  from opcua_kb import KnowledgeBase

  kb = KnowledgeBase(r"{ROOT}")
  entity = kb.get_entity("ServerType")
  results = kb.search("SessionDiagnosticsDataType 字段", top_k=3)
  edges = kb.relationships("ObjectType:ServerType", "HAS_COMPONENT")
  chapter = kb.chapter("12.10")
  table = kb.table("C.1")

Supported entity kinds / 支持的实体类型
  ObjectType, EventType, VariableType, Object, ModellingRule, Method, ReferenceType, DataType

Supported relationship filters / 支持的关系过滤
  HAS_SUBTYPE
  HAS_COMPONENT
  HAS_PROPERTY
  HAS_TYPE_DEFINITION
  HAS_MODELLING_RULE
  USES_DATATYPE
  DEFINED_BY_TABLE
  DEFINED_IN_SECTION
  HAS_FIELD
  HAS_CONFORMANCE_UNIT

Notes / 注意事项
  - Entity names keep OPC UA English identifiers, e.g. ServerType, HasComponent, BuildInfo.
    实体名保留 OPC UA 英文标识符。
  - CLI output uses Chinese labels with English technical identifiers.
    CLI 输出使用中文标签并保留英文技术标识符。
  - Rebuilding rewrites README.md, kb/*.jsonl, indexes/fts.sqlite and source/source_manifest.json.
    重新构建会覆盖 README.md、kb/*.jsonl、indexes/fts.sqlite 和 source/source_manifest.json。
""".strip()


def main() -> None:
    print(HELP_TEXT)


if __name__ == "__main__":
    main()
