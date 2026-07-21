"""CLI for exact and full-text knowledge-base searches."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from opcua_kb import KnowledgeBase


def main() -> None:
    """Run a query and print ranked results with optional structure details."""

    parser = argparse.ArgumentParser(
        description="Search the OPC UA 10000-5 knowledge base. 检索 OPC UA 10000-5 知识库。",
        epilog=(
            'Examples:\n'
            '  python tools/query_kb.py "ServerType 包含哪些组件？" --top-k 8\n'
            '  python tools/query_kb.py "BuildInfo 字段" --top-k 5\n'
            '  python tools/query_kb.py "Table C.1" --top-k 2'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("query", help="Natural-language query, entity name, section number, or table number.")
    parser.add_argument("--top-k", type=int, default=10, help="Maximum number of results to print. Default: 10.")
    parser.add_argument("--root", default=str(ROOT), help="Knowledge base project root. Default: repository root.")
    args = parser.parse_args()

    kb = KnowledgeBase(args.root)
    results = kb.search(args.query, top_k=args.top_k)
    for idx, item in enumerate(results, start=1):
        print(f"[{idx}] {item.get('type')} {item.get('title')} ({item.get('id')})")
        if item.get("section"):
            print(f"    章节: {item.get('section')}")
        if item.get("table_number"):
            print(f"    表格: {item.get('table_number')}")
        snippet = (item.get("snippet") or "").replace("\n", " ")
        if snippet:
            print(f"    摘要: {snippet[:600]}")
        if item.get("type") == "entity" and _wants_structure(args.query):
            entity = kb.get_entity(item["id"])
            if entity:
                _print_structure(entity)


def _wants_structure(query: str) -> bool:
    """Detect whether the query asks for components, fields, or containment."""

    markers = ["组件", "字段", "包含", "有哪些", "components", "fields", "contain"]
    return any(marker.lower() in query.lower() for marker in markers)


def _print_structure(entity: dict) -> None:
    """Print the bounded component, field, and enum sections of an entity."""

    components = entity.get("components") or []
    fields = entity.get("fields") or []
    enum_values = entity.get("enum_values") or []
    if components:
        print("    结构化组件:")
        for item in components[:20]:
            print(
                f"      - {item.get('reference_type')} {item.get('node_class')} "
                f"{item.get('browse_name')} [{item.get('data_type')} / {item.get('type_definition')}] "
                f"{item.get('modelling_rule')}"
            )
    if fields:
        print("    结构化字段:")
        for item in fields[:20]:
            print(f"      - {item.get('name')}: {item.get('type')} - {item.get('description')}")
    if enum_values:
        print("    枚举值:")
        for item in enum_values[:20]:
            print(f"      - {item.get('name')}={item.get('value')} - {item.get('description')}")


if __name__ == "__main__":
    main()
