"""Audit a saved Wiki comparison and its AI-assisted semantic review; no LLM calls."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient
from opcua_kb.http_api import create_app


def main() -> None:
    folder = ROOT / "reports/part5-wiki-evaluation"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default="run.jsonl")
    parser.add_argument("--review", default="review.json")
    parser.add_argument("--output", default="audit.json")
    args = parser.parse_args()
    run_path, review_path, output_path = (folder / name for name in (args.run, args.review, args.output))
    rows = [json.loads(line) for line in run_path.read_text(encoding="utf-8").splitlines()]
    meta = json.loads(run_path.with_suffix(".meta.json").read_text(encoding="utf-8"))
    fixture_path = ROOT / meta["fixture"]["path"]
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    review = json.loads(review_path.read_text(encoding="utf-8"))
    run_hash = hashlib.sha256(run_path.read_bytes()).hexdigest()
    if "run_sha256" in review:
        assert review["run_sha256"] == run_hash, "review belongs to a different run"
    indexed = {(row["id"], row["arm"]): row for row in rows}
    cases = {case["id"]: case for case in fixture}
    reviewed = {case["id"]: case for case in review["cases"]}
    assert len(rows) == len(indexed) == 32
    assert set(reviewed) == set(cases)
    assert set(indexed) == {(case, arm) for case in cases for arm in ("original", "mixed")}
    hashes = {**meta["code_sha256"], **meta["wiki_sha256"],
              meta["source"]["path"]: meta["source"]["sha256"],
              str(fixture_path): meta["fixture"]["sha256"],
              "indexes/fts.sqlite": meta["fts_sha256"]}
    archived_code = []
    for name, expected in hashes.items():
        actual = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        if actual != expected and name in meta["code_sha256"]:
            archive = run_path.parent / f"{run_path.stem}-code" / name
            if not archive.is_file():
                archive = run_path.parent / "baseline-code" / name
            assert archive.is_file(), f"changed code has no frozen snapshot: {name}"
            actual = hashlib.sha256(archive.read_bytes()).hexdigest()
            archived_code.append(name)
        assert actual == expected, name
    for row in rows:
        assert row["question"] == cases[row["id"]]["question"]
        assert row["selected_context_chars"] <= meta["safe_config"]["max_context_chars"]
        assert all(check["ok"] for check in row["metrics"]["source_checks"])
        if row["model"]["error"] is not None:
            assert row["answer"]["mode"] == "offline" and row["model"]["raw_answer"] is None
        assert "\ufffd" not in (row["model"]["raw_answer"] or "")
        if row["arm"] == "original":
            assert not row["wiki_selected"]
        if row["metrics"]["invalid_labels"]:
            assert row["answer"]["mode"] == "offline"

    summary = {}
    for arm in ("original", "mixed"):
        arm_rows = [row for row in rows if row["arm"] == arm]
        totals = {"gold_fact_units": 0, "raw_content_units": 0,
                  "final_content_units": 0, "final_cited_units": 0,
                  "final_spec_cited_units": 0, "complete_normative_answers": 0}
        for row in arm_rows:
            grading = reviewed[row["id"]][arm]
            scores, labels = grading["raw_facts"], grading["supporting_labels"]
            assert len(scores) == len(labels) == len(cases[row["id"]]["gold_facts"])
            sources = {item["label"]: item["source"]["kind"] for item in row["answer"]["citations"]}
            assert all(score in (0, 0.5, 1) for score in scores)
            assert all(label in sources for group in labels for label in group)
            totals["gold_fact_units"] += len(scores)
            totals["raw_content_units"] += sum(scores)
            if row["answer"]["mode"] != "generated" or not scores:
                continue
            totals["final_content_units"] += sum(scores)
            totals["final_cited_units"] += sum(score for score, group in zip(scores, labels) if group)
            spec_units = sum(score for score, group in zip(scores, labels)
                             if any(sources[label] == "spec" for label in group))
            totals["final_spec_cited_units"] += spec_units
            totals["complete_normative_answers"] += int(spec_units == len(scores))
        checks = [check for row in arm_rows for check in row["metrics"]["source_checks"]]
        diagnostics = [reviewed[row["id"]][arm] for row in arm_rows if row["category"] != "positive"]
        summary[arm] = {
            **totals, "positive_cases": sum(row["category"] == "positive" for row in arm_rows),
            "trials": len(arm_rows),
            "generated": sum(row["answer"]["mode"] == "generated" for row in arm_rows),
            "wiki_selected_trials": sum(row["wiki_selected"] for row in arm_rows),
            "no_evidence_trials": sum(not row["answer"]["retrieved"] for row in arm_rows),
            "model_responses": sum(row["model"]["raw_answer"] is not None for row in arm_rows),
            "model_error_trials": sum(row["model"]["error"] is not None for row in arm_rows),
            "invalid_citation_trials": sum(bool(row["metrics"]["invalid_labels"]) for row in arm_rows),
            "source_checks": len(checks), "source_checks_ok": sum(check["ok"] for check in checks),
            "mean_context_chars": round(statistics.mean(row["selected_context_chars"] for row in arm_rows), 2),
            "mean_latency_ms": round(statistics.mean(row["latency_ms"] for row in arm_rows), 2),
            "median_latency_ms": round(statistics.median(row["latency_ms"] for row in arm_rows), 2),
            "diagnostic_safe_abstentions": sum(item["safe_abstention"] for item in diagnostics),
            "strict_diagnostic_passes": sum(item["strict_diagnostic_pass"] for item in diagnostics),
        }

    source_lines = (ROOT / meta["source"]["path"]).read_text(encoding="utf-8").splitlines()
    pending = []
    for row in rows:
        pending.extend(item["source"]["url"] for item in row["answer"]["citations"])
        for check in row["metrics"]["source_checks"]:
            if check["kind"] == "spec":
                loc = check["location"]
                pending.append("/api/v1/content?" + urlencode({
                    "path": check["path"], "start_line": loc["start_line"], "end_line": loc["end_line"]}))
    seen, http = set(), []
    with TemporaryDirectory() as temporary:
        with patch.dict(os.environ, {"SESSION_DB_PATH": str(Path(temporary) / "sessions.sqlite3")}):
            with TestClient(create_app(ROOT)) as client:
                while pending:
                    url = pending.pop(0)
                    query = parse_qs(urlsplit(url).query)
                    marker = tuple(sorted((key, tuple(values)) for key, values in query.items()))
                    if marker in seen:
                        continue
                    seen.add(marker)
                    response = client.get(url)
                    assert response.status_code == 200, (url, response.status_code)
                    page = response.json()
                    assert page["version"] == meta["source"]["version"]
                    if page["kind"] == "spec":
                        start, end = page["start_line"], page["end_line"]
                        assert page["content"] == "\n".join(source_lines[start - 1:end])
                        assert start == int(query["start_line"][0]) and end == int(query["end_line"][0])
                    else:
                        assert page["status"] == "draft" and page["content"]
                        assert (ROOT / page["path"]).is_file()
                        for link in page["links"]:
                            pending.append("/api/v1/content?" + urlencode({
                                key: link[key] for key in ("path", "start_line", "end_line") if key in link}))
                    http.append({"url": url, "status": response.status_code, "kind": page["kind"],
                                 "version": page["version"], "start_line": page["start_line"],
                                 "end_line": page["end_line"], "ok": True})
    payloads = [path.read_bytes() for path in (run_path, run_path.with_suffix(".meta.json"), review_path)]
    for name in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY"):
        key = os.getenv(name)
        if key:
            assert all(key.encode() not in payload for payload in payloads), "credential found in artifact"
    audit = {"summary": summary, "hashes_match": True, "archived_code_used": archived_code,
             "credentials_absent": True,
             "run_sha256": hashlib.sha256(payloads[0]).hexdigest(),
             "review_sha256": hashlib.sha256(payloads[2]).hexdigest(),
             "http_note": "In-process HTTP through the existing FastAPI TestClient; not a browser click test.",
             "http_requests": http}
    output_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"summary": summary, "http_requests": len(http),
                      "wiki_pages": sum(item["kind"] == "wiki" for item in http)}, indent=2))


if __name__ == "__main__":
    main()
