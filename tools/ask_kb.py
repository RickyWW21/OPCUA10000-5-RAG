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
from opcua_kb.llm import LLMError, OpenAICompatibleChatModel
from opcua_kb.retrieval import Part5Retriever


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
    result = RAGPipeline(
        retriever=Part5Retriever(KnowledgeBase(args.root)),
        chat_model=chat_model,
    ).ask(args.question, top_k=args.top_k, relationship_depth=args.relationship_depth)
    print(f"模式 / Mode: {result.mode}")
    print(result.answer)
    print("引用 / 寮曠敤:")
    for citation in result.citations:
        print(f"  {citation['label']} {citation['title']} ({citation['id']})")
    print("检索结果 / Retrieved:")
    for item in result.retrieved:
        print(f"  {item['label']} {item['id']} [{item['type']}]")
    if result.error:
        print(f"模型错误 / Model error: {result.error}", file=sys.stderr)


if __name__ == "__main__":
    main()
