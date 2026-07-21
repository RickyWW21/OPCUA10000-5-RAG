"""CLI for exporting filtered or global knowledge graphs as HTML or JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from opcua_kb import KnowledgeBase, write_graph_html, write_graph_json


def main() -> None:
    """Parse graph filters, build the graph payload, and write the export."""

    parser = argparse.ArgumentParser(
        description="Build an OPC UA 10000-5 knowledge graph. 生成 OPC UA 10000-5 知识图谱。",
        epilog=(
            "Examples:\n"
            "  python tools/graph_kb.py --format html --output exports/knowledge_graph.html\n"
            "  python tools/graph_kb.py --all --format html --output exports/knowledge_graph.html\n"
            "  python tools/graph_kb.py --focus ServerType --depth 2 --format json\n"
            "  python tools/graph_kb.py --relation HAS_COMPONENT,USES_DATATYPE --min-weight 3"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--root", default=str(ROOT), help="Knowledge base project root. Default: repository root.")
    parser.add_argument("--focus", help="Optional central entity, e.g. ServerType or DataType:BuildInfo.")
    parser.add_argument("--relation", help="Optional comma-separated relation filter, e.g. HAS_COMPONENT,USES_DATATYPE.")
    parser.add_argument("--depth", type=int, default=1, help="Traversal depth when --focus is set. Default: 1.")
    parser.add_argument("--min-weight", type=int, default=1, help="Minimum aggregated edge weight. Default: 1.")
    parser.add_argument("--include-defined", action="store_true", help="Include DEFINED_BY_TABLE and DEFINED_IN_SECTION edges.")
    parser.add_argument(
        "--limit",
        type=int,
        default=12,
        help="Maximum number of top related graph nodes. Use 0 for all nodes. Default: 12.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Include all selected nodes and edges. Equivalent to --limit 0.",
    )
    parser.add_argument("--format", choices=["json", "html"], default="html", help="Output format. Default: html.")
    parser.add_argument(
        "--output",
        help="Output path. Defaults to exports/knowledge_graph.html or exports/knowledge_graph.json.",
    )
    args = parser.parse_args()

    root = Path(args.root)
    kb = KnowledgeBase(root)
    limit = 0 if args.all else args.limit
    graph = kb.graph(
        focus=args.focus,
        relation=args.relation,
        depth=args.depth,
        min_weight=args.min_weight,
        include_defined=args.include_defined,
        limit=limit,
    )
    output = Path(args.output) if args.output else root / "exports" / f"knowledge_graph.{args.format}"
    if not output.is_absolute():
        output = root / output

    if args.format == "json":
        write_graph_json(graph, output)
    else:
        write_graph_html(graph, output)

    print(f"Graph written: {output}")
    print(f"Nodes: {graph['metadata']['node_count']}")
    print(f"Edges: {graph['metadata']['edge_count']}")

    if args.format == "json":
        preview = {
            "metadata": graph["metadata"],
            "top_nodes": graph["nodes"][:8],
            "top_edges": graph["edges"][:8],
        }
        print(json.dumps(preview, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
