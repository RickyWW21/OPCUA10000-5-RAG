"""Evaluate Part 5 retrieval against a small JSON query set."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from opcua_kb import KnowledgeBase
from opcua_kb.retrieval import Part5Retriever


def evaluate(root: str | Path, fixture: str | Path, *, top_k: int = 3) -> dict[str, Any]:
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    cases = json.loads(Path(fixture).read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not cases:
        raise ValueError("evaluation fixture must be a non-empty JSON array")
    retriever = Part5Retriever(KnowledgeBase(root))
    results: list[dict[str, Any]] = []
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("each evaluation case must be an object")
        question = case.get("question")
        expected = case.get("expected_ids")
        if not isinstance(question, str) or not question.strip():
            raise ValueError("evaluation questions must be non-empty strings")
        if not isinstance(expected, list) or not expected or not all(isinstance(item, str) for item in expected):
            raise ValueError("expected_ids must be a non-empty string array")
        k = int(case.get("top_k", top_k))
        depth = int(case.get("relationship_depth", 0))
        records = retriever.retrieve(question, top_k=k, relationship_depth=depth)
        retrieved_ids = [record.id for record in records]
        results.append(
            {
                "question": question,
                "expected_ids": expected,
                "retrieved_ids": retrieved_ids,
                "recall_at_1": int(any(item in retrieved_ids[:1] for item in expected)),
                "recall_at_3": int(any(item in retrieved_ids[:3] for item in expected)),
                "mode": retriever.last_mode,
            }
        )
    total = len(results)
    return {
        "doc": "OPC-10000-5",
        "queries": total,
        "recall_at_1": sum(item["recall_at_1"] for item in results) / total,
        "recall_at_3": sum(item["recall_at_3"] for item in results) / total,
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate OPC UA 10000-5 Part 5 retrieval.")
    parser.add_argument("--root", default=str(ROOT), help="Knowledge base project root.")
    parser.add_argument(
        "--fixture",
        default=str(ROOT / "tests" / "fixtures" / "part5_retrieval_eval.json"),
        help="JSON evaluation fixture.",
    )
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.root, args.fixture, top_k=args.top_k), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
