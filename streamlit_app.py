"""Streamlit web front end for the OPC UA Part 5 RAG pipeline."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

try:
    import streamlit as st
except ImportError:  # pragma: no cover - exercised by the dependency guard in main
    st = None  # type: ignore[assignment]

from opcua_kb import KnowledgeBase, RAGPipeline
from opcua_kb.embeddings import EmbeddingError, SentenceTransformerEmbeddingProvider
from opcua_kb.llm import LLMError, OpenAICompatibleChatModel
from opcua_kb.rag import RAGAnswer
from opcua_kb.retrieval import Part5Retriever
from opcua_kb.vector_index import VectorIndex


ROOT = Path(__file__).resolve().parent
RAG_MODES = {"自动 / Auto": "auto", "混合 / Hybrid": "hybrid", "仅 FTS5 / FTS5": "fts"}


def format_answer_metadata(answer_mode: str, retrieval_mode: str) -> str:
    """Return a compact, user-facing status line for an answer."""

    return f"生成模式：{answer_mode} · 检索模式：{retrieval_mode}"


def format_citation_label(citation: dict[str, str]) -> str:
    """Render one citation without losing its stable record ID."""

    label = citation.get("label", "")
    title = citation.get("title") or citation.get("id", "")
    record_id = citation.get("id", "")
    return f"{label} {title} (`{record_id}`)".strip()


def format_retrieved_record(record: dict[str, Any]) -> str:
    """Render a retrieved record for the evidence panel."""

    record_type = record.get("type", "record")
    title = record.get("title", "")
    section = record.get("section") or "未标注章节"
    snippet = record.get("snippet", "")
    return f"{record_type} · {title} · {section}\n{snippet}".strip()


def _source_hash(root: Path) -> str | None:
    manifest_path = root / "source" / "source_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    source_hash = manifest.get("sha256") if isinstance(manifest, dict) else None
    return source_hash if isinstance(source_hash, str) and source_hash else None


def build_retriever(root: str | Path, mode: str, embedding_model: str) -> Part5Retriever:
    """Build a Part 5 retriever from the same validated local artifacts as the TUI."""

    if mode not in {"auto", "hybrid", "fts"}:
        raise ValueError("retrieval mode must be auto, hybrid, or fts")
    root_path = Path(root).resolve()
    knowledge_base = KnowledgeBase(root_path)
    if mode == "fts":
        return Part5Retriever(knowledge_base)

    vector_path = root_path / "indexes" / "embeddings.jsonl"
    metadata_path = root_path / "indexes" / "embeddings.meta.json"
    source_hash = _source_hash(root_path)
    if not vector_path.exists() or not metadata_path.exists() or not source_hash:
        return Part5Retriever(knowledge_base)
    try:
        provider = SentenceTransformerEmbeddingProvider(embedding_model)
    except EmbeddingError:
        return Part5Retriever(knowledge_base)
    return Part5Retriever(
        knowledge_base,
        vector_index=VectorIndex(root_path, source_hash=source_hash),
        embedding_provider=provider,
    )


if st is not None:
    _cached_build_retriever = st.cache_resource(show_spinner=False)(build_retriever)
else:  # pragma: no cover - only used to keep helper imports testable without Streamlit
    _cached_build_retriever = build_retriever


def _build_chat_model() -> tuple[OpenAICompatibleChatModel | None, str | None]:
    try:
        return (
            OpenAICompatibleChatModel(
                api_key=os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY"),
                model=os.getenv("DEEPSEEK_MODEL") or os.getenv("OPENAI_MODEL", "deepseek-chat"),
                base_url=os.getenv("DEEPSEEK_BASE_URL")
                or os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com"),
            ),
            None,
        )
    except LLMError as exc:
        return None, str(exc)


def _answer_to_state(answer: RAGAnswer, retrieval_mode: str) -> dict[str, Any]:
    return {
        "answer": answer.answer,
        "mode": answer.mode,
        "retrieval_mode": retrieval_mode,
        "citations": answer.citations,
        "retrieved": answer.retrieved,
        "error": answer.error,
    }


def _render_answer(state: dict[str, Any]) -> None:
    st.markdown(state["answer"])
    st.caption(format_answer_metadata(state["mode"], state["retrieval_mode"]))
    if state.get("error"):
        st.warning(f"模型请求失败，已回退到离线回答：{state['error']}")
    citations = state.get("citations", [])
    if citations:
        with st.expander(f"引用（{len(citations)}）", expanded=True):
            for citation in citations:
                st.markdown(f"- {format_citation_label(citation)}")
    records = state.get("retrieved", [])
    if records:
        with st.expander(f"检索证据（{len(records)}）"):
            for index, record in enumerate(records, start=1):
                st.markdown(f"**证据 {index}**")
                st.code(format_retrieved_record(record), language="text")


def _render_sidebar() -> dict[str, Any]:
    with st.sidebar:
        st.header("RAG 设置")
        root = Path(st.text_input("知识库根目录", value=str(ROOT))).expanduser()
        mode_label = st.selectbox("检索模式", list(RAG_MODES), index=0)
        top_k = st.slider("返回证据数", min_value=1, max_value=20, value=6)
        relationship_depth = st.slider("关系扩展深度", min_value=0, max_value=3, value=0)
        online = st.toggle("在线生成", value=False)
        embedding_model = st.text_input(
            "Embedding 模型",
            value="sentence-transformers/all-MiniLM-L6-v2",
            disabled=mode_label == "仅 FTS5 / FTS5",
        )
        if online:
            has_key = bool(os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY"))
            st.caption("语言模型 API Key：已配置" if has_key else "语言模型 API Key：未配置")
        if st.button("清空对话", use_container_width=True):
            st.session_state.messages = []
            st.rerun()
    return {
        "root": root,
        "mode": RAG_MODES[mode_label],
        "top_k": top_k,
        "relationship_depth": relationship_depth,
        "online": online,
        "embedding_model": embedding_model,
    }


def main() -> None:
    if st is None:
        raise SystemExit("Streamlit 未安装，请运行：python -m pip install -r requirements-streamlit.txt")

    st.set_page_config(page_title="OPC UA Part 5 RAG", page_icon="🔎", layout="wide")
    st.title("OPC UA 10000-5 Part 5 RAG")
    st.caption("结构化知识库、混合检索与可追溯引用工作台")
    settings = _render_sidebar()

    if "messages" not in st.session_state:
        st.session_state.messages = []
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if message["role"] == "assistant":
                _render_answer(message["state"])
            else:
                st.markdown(message["content"])

    prompt = st.chat_input("询问 OPC UA 10000-5 Part 5，例如：ServerType 包含哪些组件？")
    if not prompt:
        return

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        try:
            retriever = _cached_build_retriever(
                str(settings["root"]), settings["mode"], settings["embedding_model"]
            )
            chat_model = None
            if settings["online"]:
                chat_model, model_error = _build_chat_model()
                if model_error:
                    st.warning(f"在线生成不可用，将返回离线答案：{model_error}")
            answer = RAGPipeline(retriever=retriever, chat_model=chat_model).ask(
                prompt,
                top_k=settings["top_k"],
                relationship_depth=settings["relationship_depth"],
            )
            state = _answer_to_state(answer, retriever.last_mode)
            _render_answer(state)
            st.session_state.messages.append({"role": "assistant", "state": state})
        except (OSError, ValueError) as exc:
            st.error(f"检索失败：{exc}")


if __name__ == "__main__":
    main()
