"""Compare Part 5 RAG answers with and without Wiki evidence.
Only mechanical citation/source checks are performed, not semantic accuracy.
Offline is the default; ``--online`` is the only way to build a chat model.
This tool never retries API calls or stores credentials.
"""
from __future__ import annotations
import argparse, dataclasses, hashlib, json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from opcua_kb import KnowledgeBase
from opcua_kb.llm import LLMError, OpenAICompatibleChatModel
from opcua_kb.rag import RAGPipeline, _CANONICAL_CITATION, _CITATION_CANDIDATE
from opcua_kb.retrieval import Part5Retriever
from opcua_kb.source_view import SourceView, SourceViewError
TOP_K, DEPTH, CONTEXT_CHARS = 6, 0, 12000
ARMS = ("original", "mixed")
CATEGORIES = ("positive", "out_of_scope", "context_dependent")
PRODUCTION_FILES = (
    "opcua_kb/__init__.py", "opcua_kb/api.py", "opcua_kb/llm.py", "opcua_kb/rag.py",
    "opcua_kb/retrieval.py", "opcua_kb/source_view.py", "opcua_kb/wiki.py",
)
_EVIDENCE = "Part 5 evidence:\n"
class EvaluationError(RuntimeError):
    """Raised when a comparison cannot be run honestly."""
class RecordingRetriever(Part5Retriever):
    """Keep the records actually returned to the pipeline."""
    def __init__(self, knowledge_base: KnowledgeBase):
        super().__init__(knowledge_base)
        self.returned: list[Any] = []
    def retrieve(self, question: str, *, top_k: int = 6, relationship_depth: int = 0):
        records = super().retrieve(question, top_k=top_k, relationship_depth=relationship_depth)
        self.returned = list(records)
        return records
class NoWikiRetriever(RecordingRetriever):
    """Baseline that excludes Wiki before selection, not after mixed retrieval."""
    def _wiki_hits(self, question: str, top_k: int, *, has_specification: bool):
        return []
class CaptureChatModel:
    """Wrap the real client and keep the exact prompts and raw response."""
    def __init__(self, inner: OpenAICompatibleChatModel):
        self.inner = inner
        self.system = self.user = self.raw_answer = self.error = None
    def generate(self, *, system: str, user: str, temperature: float = 0.0) -> str:
        self.system, self.user = system, user
        try:
            self.raw_answer = self.inner.generate(system=system, user=user, temperature=temperature)
        except LLMError as exc:
            self.error = str(exc)
            raise
        return self.raw_answer
def _int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
def _range(record: Any) -> tuple[int, int] | None:
    if not isinstance(record, dict):
        return None
    start, end = record.get("start_line"), record.get("end_line")
    return (start, end) if _int(start) and _int(end) else None
def _load_source(root: Path) -> dict[str, Any]:
    manifest_path = root / "source" / "source_manifest.json"
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvaluationError(f"unable to read source manifest: {manifest_path}") from exc
    if not isinstance(data, dict) or data.get("doc") != "OPC-10000-5":
        raise EvaluationError("source manifest is not an OPC UA 10000-5 manifest")
    version, declared = str(data.get("version") or ""), str(data.get("sha256") or "").lower()
    if not version or re.fullmatch(r"[0-9a-f]{64}", declared) is None:
        raise EvaluationError("source manifest is missing a valid version or sha256")
    raw_name = data.get("local_source_path") or data.get("source_path") or ""
    name = str(raw_name).replace("\\", "/").rstrip("/").split("/")[-1]
    source_path = root / "source" / (name or f"OPC-10000-5-v{version}.md")
    try:
        resolved = source_path.resolve()
        resolved.relative_to(root.resolve())
        payload = resolved.read_bytes()
    except (OSError, ValueError) as exc:
        raise EvaluationError(f"unable to read source file: {source_path}") from exc
    actual = hashlib.sha256(payload).hexdigest()
    if actual != declared:
        raise EvaluationError("source hash does not match source_manifest.json")
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise EvaluationError("source file is not valid UTF-8") from exc
    return {"path": resolved.relative_to(root.resolve()).as_posix(), "doc": "OPC-10000-5",
            "version": version, "sha256": actual, "lines": lines}
def _wiki_hashes(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): _sha256(p) for p in sorted((root / "wiki").glob("**/*.md"))}
def _code_hashes() -> dict[str, str]:
    files = {name: ROOT / name for name in PRODUCTION_FILES}
    files["tools/evaluate_wiki_rag.py"] = Path(__file__).resolve()
    return {name: _sha256(path) for name, path in files.items()}
def _build_chat_model(online: bool, model: str, base_url: str):
    if not online:
        return None, None
    key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not key:
        raise EvaluationError("--online requires DEEPSEEK_API_KEY or OPENAI_API_KEY")
    inner = OpenAICompatibleChatModel(api_key=key, model=model, base_url=base_url)
    return CaptureChatModel(inner), model
def _load_fixture(path: Path) -> tuple[list[dict[str, Any]], str]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise EvaluationError(f"unable to read fixture: {path}") from exc
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvaluationError(f"invalid fixture JSON: {path}") from exc
    return document, hashlib.sha256(raw).hexdigest()
def _validate_cases(cases: Any, knowledge_base: KnowledgeBase, source_lines: list[str]) -> None:
    if not isinstance(cases, list) or len(cases) != 16:
        raise EvaluationError("fixture must contain exactly 16 cases")
    case_ids: set[str] = set()
    fact_ids: set[str] = set()
    for case in cases:
        case_id = case.get("id") if isinstance(case, dict) else None
        if not isinstance(case_id, str) or not case_id.strip() or case_id in case_ids:
            raise EvaluationError("fixture case ids must be non-empty and unique")
        case_ids.add(case_id)
        if not isinstance(case.get("question"), str) or not case["question"].strip():
            raise EvaluationError(f"case {case_id} has no question")
        if case.get("category") not in CATEGORIES:
            raise EvaluationError(f"case {case_id} has an unknown category")
        expected = case.get("expected_ids")
        if (not isinstance(expected, list) or any(not isinstance(item, str) or not item for item in expected)
                or len(expected) != len(set(expected))):
            raise EvaluationError(f"case {case_id} has invalid expected_ids")
        if not isinstance(case.get("gold_facts"), list):
            raise EvaluationError(f"case {case_id} has invalid gold_facts")
        for fact in case["gold_facts"]:
            fact_id = fact.get("id") if isinstance(fact, dict) else None
            if not isinstance(fact_id, str) or not fact_id or fact_id in fact_ids:
                raise EvaluationError(f"case {case_id} has an invalid or duplicate gold fact id")
            fact_ids.add(fact_id)
            source = fact.get("source") if isinstance(fact, dict) else None
            section = source.get("section") if isinstance(source, dict) else None
            chapter = knowledge_base.chapter(section) if isinstance(section, str) else None
            if not isinstance(chapter, dict):
                raise EvaluationError(f"{fact_id} references an unknown section")
            start, end = source.get("start_line"), source.get("end_line")
            if not (_int(start) and _int(end) and 1 <= start <= end <= len(source_lines)):
                raise EvaluationError(f"{fact_id} has an invalid source line range")
            chapter_range = _range(chapter)
            if chapter_range and not (chapter_range[0] <= start and end <= chapter_range[1]):
                raise EvaluationError(f"{fact_id} source range is outside its chapter")
            table = source.get("table")
            if table is not None:
                key = table[6:] if isinstance(table, str) and table.lower().startswith("table-") else table
                if not isinstance(table, str) or not table or not isinstance(knowledge_base.table(key), dict):
                    raise EvaluationError(f"{fact_id} references an unknown table")
def _citation_metrics(text: Any, supplied: list[str]) -> dict[str, Any]:
    tokens = list(dict.fromkeys(
        match.group(0) for match in _CITATION_CANDIDATE.finditer(text if isinstance(text, str) else "")
    ))
    supplied_set = set(supplied)
    used = [token for token in tokens if _CANONICAL_CITATION.fullmatch(token) and token in supplied_set]
    invalid = [token for token in tokens if token not in used]
    return {"citation_labels_used": used, "invalid_labels": invalid,
            "unused_returned_labels": [label for label in supplied if label not in set(used)]}
def _check_item(citation: dict[str, Any], kind: Any, path: Any, location: Any, error: str | None) -> dict[str, Any]:
    return {"id": citation.get("id"), "label": citation.get("label"), "kind": kind,
            "path": path, "location": location, "ok": error is None, "error": error}
def _wiki_check(citation: dict[str, Any], source: dict[str, Any], view: SourceView, source_info: dict[str, Any]) -> dict[str, Any]:
    path, page, error = source.get("path"), None, None
    try:
        page = view.content(path)
    except (SourceViewError, OSError, ValueError, TypeError) as exc:
        error = f"wiki page not accessible: {exc}"
    if error is None:
        provenance = citation.get("provenance") if isinstance(citation.get("provenance"), dict) else {}
        if page.get("kind") != "wiki":
            error = "source did not open as a wiki page"
        elif page.get("version") != provenance.get("source_version"):
            error = "wiki version is missing or does not match provenance"
        elif not page.get("status"):
            error = "wiki status is not accessible"
        elif provenance.get("source_sha256") != source_info["sha256"]:
            error = "wiki source_sha256 is missing or does not match the manifest"
    return _check_item(citation, "wiki", path, None, error)
def _spec_check(citation: dict[str, Any], view: SourceView, source_lines: list[str], path: str, location: Any) -> dict[str, Any]:
    loc = dict(location) if isinstance(location, dict) else {}
    start, end = loc.get("start_line"), loc.get("end_line")
    error = None
    if not (_int(start) and _int(end) and 1 <= start <= end <= len(source_lines)):
        error = "invalid source line range"
    else:
        try:
            page = view.content(path, start_line=start, end_line=end)
        except (SourceViewError, OSError, ValueError, TypeError) as exc:
            error = f"source range not accessible: {exc}"
        else:
            if page.get("content") != "\n".join(source_lines[start - 1 : end]):
                error = f"content mismatch for {path}:{start}-{end}"
            elif page.get("start_line") != start or page.get("end_line") != end:
                error = f"served range differs for {path}:{start}-{end}"
    return _check_item(citation, "spec", path, loc or None, error)
def _source_checks(answer: dict[str, Any], view: SourceView, source_lines: list[str], source_info: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for citation in answer.get("citations") or []:
        if not isinstance(citation, dict):
            continue
        source = citation.get("source")
        if not isinstance(source, dict):
            checks.append(_check_item(citation, None, None, None, "citation has no enriched source"))
            continue
        kind, path = source.get("kind"), source.get("path")
        if kind == "wiki":
            checks.append(_wiki_check(citation, source, view, source_info))
            spec_path = source_info["path"]
        else:
            spec_path = path
        locations = source.get("locations") or []
        if not locations:
            checks.append(_check_item(citation, kind, path, None, "source has no locations"))
            continue
        checks.extend(_spec_check(citation, view, source_lines, spec_path, item) for item in locations)
    return checks
def _run_trial(root: Path, source_info: dict[str, Any], case: dict[str, Any], arm: str, online: bool, model: str, base_url: str) -> dict[str, Any]:
    knowledge_base = KnowledgeBase(root)
    retriever = (NoWikiRetriever if arm == "original" else RecordingRetriever)(knowledge_base)
    captured, requested_model = _build_chat_model(online, model, base_url)
    pipeline = RAGPipeline(retriever=retriever, chat_model=captured, max_context_chars=CONTEXT_CHARS)
    view = SourceView(root, knowledge_base)
    started = time.perf_counter()
    result = pipeline.ask(case["question"], top_k=TOP_K, relationship_depth=DEPTH)
    latency_ms = round((time.perf_counter() - started) * 1000.0, 3)
    answer = dataclasses.asdict(result)
    view.enrich_result(answer)
    if captured is not None and captured.user is not None and _EVIDENCE in captured.user:
        context = captured.user.split(_EVIDENCE, 1)[1]
    else:
        context = "\n\n".join(f"{item['label']} {item['title']}\n{item['snippet']}" for item in answer.get("retrieved") or [])
    supplied = [item["label"] for item in answer.get("citations") or []]
    inspected = captured.raw_answer if captured is not None and captured.raw_answer is not None else result.answer
    metrics = _citation_metrics(inspected, supplied)
    metrics["source_checks"] = _source_checks(answer, view, source_info["lines"], source_info)
    records = retriever.returned
    return {
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "id": case["id"], "arm": arm, "question": case["question"], "category": case["category"],
        "candidate_ids": [record.id for record in records],
        "candidate_types": [record.type for record in records],
        "candidate_sections": [record.section for record in records],
        "answer": answer,
        "model": {"requested_model": requested_model, "system": captured.system if captured else None,
                  "user": captured.user if captured else None, "raw_answer": captured.raw_answer if captured else None,
                  "error": captured.error if captured else None},
        "latency_ms": latency_ms, "retrieval_mode": getattr(retriever, "last_mode", None),
        "selected_context_chars": len(context),
        "wiki_selected": any(item.get("type") == "wiki" for item in answer.get("retrieved") or []),
        "metrics": metrics,
    }
def _iter_rows(pending: list[tuple[dict[str, Any], str]], root: Path, source_info: dict[str, Any], online: bool, model: str, base_url: str, workers: int):
    if workers == 1:
        for case, arm in pending:
            yield _run_trial(root, source_info, case, arm, online, model, base_url)
        return
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_run_trial, root, source_info, case, arm, online, model, base_url): (case, arm) for case, arm in pending}
        for future in as_completed(futures):
            yield future.result()
def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare Part 5 Wiki and original-evidence RAG.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--fixture", default=str(ROOT / "tests" / "fixtures" / "part5_wiki_comparison.json"))
    parser.add_argument("--output", default=str(ROOT / "reports" / "part5-wiki-evaluation" / "run.jsonl"))
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--online", action="store_true", help="Explicitly use the API; offline is the default.")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--model", default=None)
    parser.add_argument("--base-url", default=None)
    return parser
def _meta_matches(old: Any, new: dict[str, Any]) -> bool:
    keys = ("format", "safe_config", "source", "fixture", "wiki_sha256", "code_sha256", "fts_sha256")
    return isinstance(old, dict) and all(old.get(key) == new.get(key) for key in keys)
def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    try:
        if args.workers <= 0:
            raise EvaluationError("--workers must be positive")
        root, fixture_path = Path(args.root).resolve(), Path(args.fixture).resolve()
        output = Path(args.output)
        if not output.is_absolute():
            output = Path.cwd() / output
        meta_path = output.with_suffix(".meta.json")
        if output.exists() and not args.resume:
            raise EvaluationError("output already exists; choose another --output or use --resume")
        cases, fixture_hash = _load_fixture(fixture_path)
        source_info = _load_source(root)
        _validate_cases(cases, KnowledgeBase(root), source_info["lines"])
        model = args.model or os.getenv("DEEPSEEK_MODEL") or os.getenv("OPENAI_MODEL") or "deepseek-chat"
        base_url = args.base_url or os.getenv("DEEPSEEK_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://api.deepseek.com"
        _build_chat_model(args.online, model, base_url)
        meta = {
            "format": 1,
            "started_at_utc": datetime.now(timezone.utc).isoformat(),
            "safe_config": {"online": bool(args.online), "model": model if args.online else None,
                            "base_url": base_url if args.online else None, "top_k": TOP_K, "relationship_depth": DEPTH,
                            "max_context_chars": CONTEXT_CHARS, "arms": list(ARMS), "temperature": 0.0},
            "source": {key: source_info[key] for key in ("path", "doc", "version", "sha256")},
            "fixture": {"path": str(fixture_path), "sha256": fixture_hash, "cases": len(cases)},
            "wiki_sha256": _wiki_hashes(root), "code_sha256": _code_hashes(),
            "fts_sha256": _sha256(root / "indexes" / "fts.sqlite"),
            "metrics_note": "mechanical citation/source checks only; not semantic accuracy",
        }
        completed: set[tuple[str, str]] = set()
        if args.resume and output.exists():
            try:
                old = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise EvaluationError("--resume requires matching metadata") from exc
            if not _meta_matches(old, meta):
                raise EvaluationError("--resume metadata differs from source/fixture/config/code; refusing to mix runs")
            for line in output.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise EvaluationError("existing output contains a partial or invalid row; inspect it before resuming") from exc
                if isinstance(row, dict) and row.get("arm") in ARMS and isinstance(row.get("id"), str):
                    completed.add((row["id"], row["arm"]))
        pending = [(case, arm) for case in cases for arm in ARMS if (case["id"], arm) not in completed]
        output.parent.mkdir(parents=True, exist_ok=True)
        if not (args.resume and output.exists()):
            meta_path.parent.mkdir(parents=True, exist_ok=True)
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[wiki-eval] online={bool(args.online)} model={meta['safe_config']['model'] or 'none'} "
              f"workers={args.workers} pending={len(pending)}", flush=True)
        if args.resume and output.exists() and output.read_bytes()[-1:] not in (b"", b"\n"):
            with output.open("a", encoding="utf-8") as tail:
                tail.write("\n")
        done = 0
        with output.open("a" if args.resume and output.exists() else "w", encoding="utf-8") as handle:
            for row in _iter_rows(pending, root, source_info, args.online, model, base_url, args.workers):
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                handle.flush()
                done += 1
                print(f"[wiki-eval] {done}/{len(pending)} {row['id']} {row['arm']}", flush=True)
    except (EvaluationError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
if __name__ == "__main__":
    main()
