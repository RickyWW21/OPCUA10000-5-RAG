"""Evaluate Part 5 FTS5 retrieval against a versioned JSON query set."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from opcua_kb.rag import create_retriever

POSITIVE = "positive"
DIAGNOSTIC_CATEGORIES = ("out_of_scope", "context_dependent")
CATEGORIES = (POSITIVE, *DIAGNOSTIC_CATEGORIES)


def evaluate(
    root: str | Path,
    fixture: str | Path,
    *,
    top_k: int = 3,
) -> dict[str, Any]:
    """Run a retrieval baseline and return per-case and aggregate metrics."""

    top_k = _positive_int(top_k, "top_k", allow_zero=False)
    cases, fixture_hash = _load_fixture(fixture, default_top_k=top_k)
    retriever = create_retriever(root)
    retrieval_mode = "fts"

    results: list[dict[str, Any]] = []
    for case in cases:
        started = time.perf_counter()
        records = retriever.retrieve(
            case["question"],
            top_k=case["top_k"],
            relationship_depth=case["relationship_depth"],
        )
        latency_ms = round((time.perf_counter() - started) * 1000.0, 3)
        actual_mode = _mode_name(getattr(retriever, "mode", None))

        retrieved_ids = [record.id for record in records]
        result = _case_result(case, retrieved_ids, latency_ms, retrieval_mode, actual_mode)
        results.append(result)

    positive = [result for result in results if result["category"] == POSITIVE]
    diagnostics = {
        category: {
            "queries": sum(1 for result in results if result["category"] == category),
            "retrieved_nonempty": sum(
                1
                for result in results
                if result["category"] == category and bool(result["retrieved_ids"])
            ),
            "results": [
                result for result in results if result["category"] == category
            ],
        }
        for category in DIAGNOSTIC_CATEGORIES
    }
    actual_modes = sorted({result["actual_mode"] for result in results})
    report: dict[str, Any] = {
        "doc": "OPC-10000-5",
        "queries": len(positive),
        "case_count": len(results),
        "hit_at_1": _mean([result["hit_at_1"] for result in positive]),
        "hit_at_3": _mean([result["hit_at_3"] for result in positive]),
        "recall_at_1": _mean([result["recall_at_1"] for result in positive]),
        "recall_at_3": _mean([result["recall_at_3"] for result in positive]),
        "mrr": _mean([result["mrr"] for result in positive]),
        "latency_ms": _mean([result["latency_ms"] for result in positive]),
        "requested_mode": retrieval_mode,
        "actual_modes": actual_modes,
        "results": positive,
        "diagnostics": diagnostics,
        "provenance": {
            "fixture": {
                "path": str(Path(fixture).resolve()),
                "sha256": fixture_hash,
                "case_count": len(cases),
                "case_categories": {
                    category: sum(1 for case in cases if case["category"] == category)
                    for category in CATEGORIES
                },
            },
            "source": _source_provenance(root),
            "retrieval": {
                "requested_mode": retrieval_mode,
                "parameters": {
                    "top_k": top_k,
                    "relationship_depth_default": 0,
                },
            },
            "metrics": {
                "hit_at_1": "any expected id in the first retrieved record",
                "hit_at_3": "any expected id in the first three retrieved records",
                "recall_at_1": "unique expected ids matched in first 1 / unique expected ids",
                "recall_at_3": "unique expected ids matched in first 3 / unique expected ids",
                "mrr": "reciprocal rank of the first matched expected id",
                "latency_ms": "mean retrieval latency over positive cases",
                "aggregates": "positive cases only; out_of_scope and context_dependent diagnostics are excluded",
            },
        },
    }
    return report


def _load_fixture(
    fixture: str | Path, *, default_top_k: int
) -> tuple[list[dict[str, Any]], str]:
    path = Path(fixture)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise OSError(f"unable to read evaluation fixture: {path}") from exc
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid evaluation fixture JSON: {path}") from exc
    if not isinstance(document, list) or not document:
        raise ValueError("evaluation fixture must be a non-empty JSON array")
    fixture_hash = hashlib.sha256(raw).hexdigest()
    return _validate_cases(document, default_top_k), fixture_hash


def _validate_cases(
    cases: list[Any], default_top_k: int
) -> list[dict[str, Any]]:
    """Validate every case before any expensive model or index work."""

    normalized: list[dict[str, Any]] = []
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"evaluation case {index} must be an object")
        question = case.get("question")
        if not isinstance(question, str) or not question.strip():
            raise ValueError("evaluation questions must be non-empty strings")
        category = case.get("category", POSITIVE)
        if category not in CATEGORIES:
            raise ValueError(
                f"evaluation case {question!r} has unknown category {category!r}"
            )
        expected = _validate_expected_ids(case.get("expected_ids"), question)
        if category == POSITIVE and not expected:
            raise ValueError(
                f"positive evaluation case {question!r} requires expected_ids"
            )
        if category != POSITIVE and expected:
            raise ValueError(
                f"{category} evaluation case {question!r} must not declare expected_ids"
            )
        normalized.append(
            {
                "question": question.strip(),
                "expected_ids": expected,
                "category": category,
                "top_k": _positive_int(
                    case.get("top_k", default_top_k), "top_k", allow_zero=False
                ),
                "relationship_depth": _positive_int(
                    case.get("relationship_depth", 0),
                    "relationship_depth",
                    allow_zero=True,
                ),
            }
        )
    return normalized


def _validate_expected_ids(value: Any, question: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"expected_ids for {question!r} must be a JSON array")
    expected: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(
                f"expected_ids for {question!r} must contain non-empty strings"
            )
        if item in seen:
            raise ValueError(f"expected_ids for {question!r} contains duplicates")
        seen.add(item)
        expected.append(item)
    return expected


def _positive_int(value: Any, name: str, *, allow_zero: bool) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    minimum = 0 if allow_zero else 1
    if value < minimum:
        qualifier = "non-negative" if allow_zero else "positive"
        raise ValueError(f"{name} must be {qualifier}")
    return value


def _source_provenance(root: str | Path) -> dict[str, Any]:
    manifest_path = Path(root) / "source" / "source_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {"manifest": str(manifest_path), "available": False}
    if not isinstance(manifest, dict):
        return {"manifest": str(manifest_path), "available": False}
    return {
        "manifest": str(manifest_path),
        "available": True,
        "doc": manifest.get("doc"),
        "version": manifest.get("version"),
        "sha256": manifest.get("sha256"),
    }


def _case_result(
    case: dict[str, Any],
    retrieved_ids: list[str],
    latency_ms: float,
    requested_mode: str,
    actual_mode: str,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "question": case["question"],
        "category": case["category"],
        "expected_ids": case["expected_ids"],
        "retrieved_ids": retrieved_ids,
        "latency_ms": latency_ms,
        "requested_mode": requested_mode,
        "actual_mode": actual_mode,
        "top_k": case["top_k"],
        "relationship_depth": case["relationship_depth"],
    }
    if case["category"] != POSITIVE:
        # A non-empty nearest-neighbour result is never scored as refusal success.
        result["retrieved_nonempty"] = bool(retrieved_ids)
        return result
    expected_unique = list(dict.fromkeys(case["expected_ids"]))
    expected_set = set(expected_unique)
    matched_at_1 = sum(1 for item in expected_unique if item in retrieved_ids[:1])
    matched_at_3 = sum(1 for item in expected_unique if item in retrieved_ids[:3])
    result.update(
        {
            "hit_at_1": int(any(item in retrieved_ids[:1] for item in expected_set)),
            "hit_at_3": int(any(item in retrieved_ids[:3] for item in expected_set)),
            "recall_at_1": matched_at_1 / len(expected_unique),
            "recall_at_3": matched_at_3 / len(expected_unique),
            "mrr": next(
                (
                    1.0 / rank
                    for rank, record_id in enumerate(retrieved_ids, start=1)
                    if record_id in expected_set
                ),
                0.0,
            ),
        }
    )
    return result


def _mode_name(value: Any) -> str:
    return value if isinstance(value, str) and value else "unknown"


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


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
    try:
        report = evaluate(
            args.root,
            args.fixture,
            top_k=args.top_k,
        )
    except (OSError, ValueError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
