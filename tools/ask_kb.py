"""Ask grounded questions against the OPC UA 10000-5 Part 5 knowledge base."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from opcua_kb import KnowledgeBase, RAGPipeline
from opcua_kb.cli import run_cli
from opcua_kb.embeddings import EmbeddingError, SentenceTransformerEmbeddingProvider
from opcua_kb.llm import LLMError, OpenAICompatibleChatModel
from opcua_kb.retrieval import Part5Retriever
from opcua_kb.vector_index import VectorIndex


def _parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        description="Ask questions using OPC UA 10000-5 Part 5 evidence.",
        epilog=(
            "Examples:\n"
            '  $env:DEEPSEEK_API_KEY = "..."\n'
            '  python tools/ask_kb.py "ServerType 包含哪些组件？" --top-k 5\n'
            '  python tools/ask_kb.py "ServerType 包含哪些组件？" --offline'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )


def main() -> None:
    parser = _parser()
    parser.add_argument("question", help="Natural-language question about OPC UA Part 5.")
    parser.add_argument("--top-k", type=int, default=6, help="Maximum evidence records. Default: 6.")
    parser.add_argument("--relationship-depth", type=int, default=0, help="Relationship hops to include. Default: 0.")
    parser.add_argument("--offline", action="store_true", help="Use deterministic local retrieval output without an LLM.")
    parser.add_argument("--root", default=str(ROOT), help="Knowledge base project root. Default: repository root.")
    parser.add_argument("--no-embeddings", action="store_true", help="Disable optional vector retrieval and use FTS5 only.")
    parser.add_argument("--embedding-model", default=None, help="Local sentence-transformers model name.")
    args = parser.parse_args()
    run_cli(lambda: _run(args))


def _run(args: argparse.Namespace) -> None:
    if not args.question.strip():
        raise ValueError("question must not be blank")
    chat_model = None
    if not args.offline:
        try:
            chat_model = OpenAICompatibleChatModel(
                api_key=os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY"),
                model=os.getenv("DEEPSEEK_MODEL") or os.getenv("OPENAI_MODEL", "deepseek-chat"),
                base_url=os.getenv("DEEPSEEK_BASE_URL") or os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com"),
            )
        except LLMError as exc:
            raise ValueError(str(exc)) from exc
    retriever = _build_retriever(args)
    result = RAGPipeline(
        retriever=retriever,
        chat_model=chat_model,
    ).ask(args.question, top_k=args.top_k, relationship_depth=args.relationship_depth)
    print(f"模式 / Mode: {result.mode}")
    print(f"retrieval={retriever.last_mode}")
    print(result.answer)
    print("引用 / 寮曠敤:")
    for citation in result.citations:
        print(f"  {citation['label']} {citation['title']} ({citation['id']})")
    print("检索结果 / Retrieved:")
    for item in result.retrieved:
        print(f"  {item['label']} {item['id']} [{item['type']}]")
    if result.error:
        print(f"模型错误 / Model error: {result.error}", file=sys.stderr)


def _build_retriever(args: argparse.Namespace) -> Part5Retriever:
    """Create a Part 5 retriever with an optional, source-validated vector index."""

    root = Path(args.root)
    if args.no_embeddings:
        return Part5Retriever(KnowledgeBase(root))

    vector_path = root / "indexes" / "embeddings.jsonl"
    metadata_path = root / "indexes" / "embeddings.meta.json"
    manifest_path = root / "source" / "source_manifest.json"
    if not vector_path.exists() or not metadata_path.exists():
        return Part5Retriever(KnowledgeBase(root))

    source_hash = None
    try:
        import json

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if isinstance(manifest, dict) and isinstance(manifest.get("sha256"), str):
            source_hash = manifest["sha256"]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        source_hash = None

    if not source_hash:
        return Part5Retriever(KnowledgeBase(root))

    try:
        provider = SentenceTransformerEmbeddingProvider(
            args.embedding_model or "sentence-transformers/all-MiniLM-L6-v2"
        )
    except EmbeddingError:
        return Part5Retriever(KnowledgeBase(root))
    return Part5Retriever(
        KnowledgeBase(root),
        vector_index=VectorIndex(root, source_hash=source_hash),
        embedding_provider=provider,
    )


if __name__ == "__main__":
    main()
