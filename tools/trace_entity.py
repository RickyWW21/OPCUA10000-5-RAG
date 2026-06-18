from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from opcua_kb import KnowledgeBase


def main() -> None:
    parser = argparse.ArgumentParser(description="Trace OPC UA 10000-5 entity relationships.")
    parser.add_argument("entity")
    parser.add_argument("--relation")
    parser.add_argument("--depth", type=int, default=1)
    parser.add_argument("--root", default=str(ROOT))
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
