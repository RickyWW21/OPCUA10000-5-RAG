"""CLI for traversing outgoing relationships from one entity."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from opcua_kb import KnowledgeBase


def main() -> None:
    """Trace optionally filtered relationships and print their source evidence."""

    parser = argparse.ArgumentParser(
        description="Trace OPC UA 10000-5 entity relationships. 追踪 OPC UA 10000-5 实体关系。",
        epilog=(
            "Examples:\n"
            "  python tools/trace_entity.py ServerType --relation HAS_COMPONENT --depth 1\n"
            "  python tools/trace_entity.py ObjectType:ServerType --relation HAS_PROPERTY\n"
            "  python tools/trace_entity.py BuildInfo --depth 1"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("entity", help="Entity name or entity id, e.g. ServerType or ObjectType:ServerType.")
    parser.add_argument("--relation", help="Optional relationship filter, e.g. HAS_COMPONENT or USES_DATATYPE.")
    parser.add_argument("--depth", type=int, default=1, help="Traversal depth. Default: 1.")
    parser.add_argument("--root", default=str(ROOT), help="Knowledge base project root. Default: repository root.")
    args = parser.parse_args()

    kb = KnowledgeBase(args.root)
    edges = kb.relationships(args.entity, relation=args.relation, depth=args.depth)
    if not edges:
        print("未找到关系。")
        return
    for edge in edges:
        ref = edge.get("source_ref", {})
        print(f"{edge['source']} --{edge['relation']}--> {edge['target']}  [{ref.get('section')} {ref.get('table')}]")


if __name__ == "__main__":
    main()
