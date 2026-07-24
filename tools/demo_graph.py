"""Generate a small focused HTML graph and print a terminal summary."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from opcua_kb import KnowledgeBase, write_graph_html
from opcua_kb.cli import run_cli


def main() -> None:
    """Parse demo options, export the graph, and optionally open it."""

    parser = argparse.ArgumentParser(
        description="Demo the OPC UA 10000-5 knowledge graph feature. 演示知识图谱功能。",
        epilog=(
            "Examples:\n"
            "  python tools/demo_graph.py\n"
            "  python tools/demo_graph.py --focus BuildInfo --depth 2 --open\n"
            "  python tools/demo_graph.py --focus ServerType --relation HAS_COMPONENT"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--root", default=str(ROOT), help="Knowledge base project root. Default: repository root.")
    parser.add_argument("--focus", default="ServerType", help="Central entity for the demo graph. Default: ServerType.")
    parser.add_argument("--relation", help="Optional relation filter, e.g. HAS_COMPONENT or USES_DATATYPE.")
    parser.add_argument("--depth", type=int, default=1, help="Graph traversal depth. Default: 1.")
    parser.add_argument("--limit", type=int, default=7, help="Maximum top related graph nodes. Default: 7.")
    parser.add_argument("--open", action="store_true", help="Open the generated HTML file with the default browser.")
    args = parser.parse_args()
    return run_cli(lambda: _run(args))

def _safe_name(value: str) -> str:
    """Convert an entity focus into a portable export filename segment."""

    return "".join(ch if ch.isalnum() else "_" for ch in value).strip("_") or "knowledge"


def _run(args: argparse.Namespace) -> None:
    root = Path(args.root)
    kb = KnowledgeBase(root)
    graph = kb.graph(focus=args.focus, relation=args.relation, depth=args.depth, limit=args.limit)
    output = root / "exports" / f"demo_{_safe_name(args.focus)}_graph.html"
    write_graph_html(graph, output)
    metadata = graph["metadata"]
    print("OPC UA 10000-5 Knowledge Graph Demo")
    print("=" * 42)
    print(f"Focus: {metadata['focus']}")
    print(f"Relation filter: {metadata['relation'] or 'ALL'}")
    print(f"Depth: {metadata['depth']}")
    print(f"Nodes: {metadata['node_count']}")
    print(f"Edges: {metadata['edge_count']}")
    print(f"HTML: {output}")
    print()
    print("Top related nodes:")
    for node in graph["nodes"][:8]:
        print(f"  - {node['label']} ({node['kind']}) score={node['score']} section={node.get('section', '-')}")
    print()
    print("Top relationship edges:")
    for edge in graph["edges"][:5]:
        relations = ", ".join(edge["relations"].keys())
        print(f"  - {edge['source']} <-> {edge['target']} weight={edge['weight']} relations={relations}")
    if args.open:
        os.startfile(output)  # type: ignore[attr-defined]


if __name__ == "__main__":
    main()
