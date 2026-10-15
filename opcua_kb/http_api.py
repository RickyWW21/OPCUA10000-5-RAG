"""HTTP adapter for the existing Part 5 knowledge base and RAG pipeline."""

from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .api import KnowledgeBase
from .embeddings import EmbeddingError, SentenceTransformerEmbeddingProvider
from .llm import LLMError, OpenAICompatibleChatModel
from .rag import RAGPipeline
from .retrieval import Part5Retriever
from .session_store import SessionStore
from .vector_index import VectorIndex


class QueryRequest(BaseModel):
    question: str = Field(min_length=1)
    retrieval_mode: Literal["auto", "hybrid", "fts"] = "auto"
    top_k: int = Field(default=6, ge=1, le=20)
    relationship_depth: int = Field(default=0, ge=0, le=3)
    online: bool = False
    conversation_id: str | None = None


class ConversationCreateRequest(BaseModel):
    title: str = Field(default="New Part 5 conversation", max_length=120)


def create_app(root: str | Path | None = None) -> FastAPI:
    """Create an API that reuses the local read-only Part 5 artifacts."""

    root_path = Path(root or os.getenv("KB_ROOT") or Path(__file__).resolve().parents[1])
    app = FastAPI(title="OPC UA 10000-5 RAG API", version="1.0.0")
    app.state.knowledge_base = KnowledgeBase(root_path)
    app.state.root = root_path
    app.state.retrievers = {}
    app.state.sessions = SessionStore(
        os.getenv("SESSION_DB_PATH", str(root_path / "data" / "rag_sessions.sqlite3")),
        ttl_days=int(os.getenv("SESSION_TTL_DAYS", "30")),
    )
    app.state.session_cookie_samesite = _cookie_samesite()
    origins = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "doc": "OPC-10000-5"}

    @app.post("/api/v1/rag/query")
    def query(request: QueryRequest, http_request: Request, response: Response) -> dict[str, object]:
        session_id = _ensure_session(app, http_request, response)
        conversation_id = request.conversation_id
        if conversation_id is None:
            conversation_id = app.state.sessions.create_conversation(
                session_id, _conversation_title(request.question)
            )["id"]
        result = _execute_query(app, request)
        _persist_exchange(app, session_id, conversation_id, request, result)
        result["conversation_id"] = conversation_id
        return result

    @app.get("/api/v1/conversations")
    def conversations(http_request: Request, response: Response) -> dict[str, object]:
        session_id = _ensure_session(app, http_request, response)
        return {"conversations": app.state.sessions.list_conversations(session_id)}

    @app.post("/api/v1/conversations")
    def create_conversation(
        request: ConversationCreateRequest,
        http_request: Request,
        response: Response,
    ) -> dict[str, object]:
        session_id = _ensure_session(app, http_request, response)
        return app.state.sessions.create_conversation(session_id, request.title)

    @app.get("/api/v1/conversations/{conversation_id}")
    def get_conversation(
        conversation_id: str,
        http_request: Request,
        response: Response,
    ) -> dict[str, object]:
        session_id = _ensure_session(app, http_request, response)
        conversation = app.state.sessions.get_conversation(session_id, conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="conversation not found")
        return conversation

    @app.delete("/api/v1/conversations/{conversation_id}")
    def delete_conversation(
        conversation_id: str,
        http_request: Request,
        response: Response,
    ) -> dict[str, bool]:
        session_id = _ensure_session(app, http_request, response)
        archived = app.state.sessions.archive_conversation(session_id, conversation_id)
        if not archived:
            raise HTTPException(status_code=404, detail="conversation not found")
        return {"ok": True}

    @app.post("/api/v1/conversations/{conversation_id}/messages")
    def conversation_message(
        conversation_id: str,
        request: QueryRequest,
        http_request: Request,
        response: Response,
    ) -> dict[str, object]:
        session_id = _ensure_session(app, http_request, response)
        if app.state.sessions.get_conversation(session_id, conversation_id) is None:
            raise HTTPException(status_code=404, detail="conversation not found")
        result = _execute_query(app, request)
        user_message, assistant_message = _persist_exchange(
            app, session_id, conversation_id, request, result
        )
        result.update(
            {
                "conversation_id": conversation_id,
                "message_id": assistant_message["id"],
                "user_message_id": user_message["id"],
            }
        )
        return result

    @app.get("/api/v1/search")
    def search(q: str = Query(min_length=1), top_k: int = Query(default=6, ge=1, le=20)) -> dict[str, object]:
        return {"results": app.state.knowledge_base.search(q, top_k=top_k)}

    @app.get("/api/v1/entities/{entity_id}")
    def entity(entity_id: str) -> dict[str, object]:
        found = app.state.knowledge_base.get_entity(entity_id)
        if found is None:
            raise HTTPException(status_code=404, detail="entity not found")
        return found

    @app.get("/api/v1/graph")
    def graph(
        focus: str | None = None,
        relation: str | None = None,
        depth: int = Query(default=1, ge=1, le=3),
    ) -> dict[str, object]:
        return app.state.knowledge_base.graph(focus=focus, relation=relation, depth=depth)

    return app


def _ensure_session(app: FastAPI, request: Request, response: Response) -> str:
    token = request.cookies.get("rag_session")
    session_id, new_token, created = app.state.sessions.get_or_create_session(token)
    if created:
        response.set_cookie(
            "rag_session",
            new_token,
            max_age=app.state.sessions.ttl_seconds,
            httponly=True,
            samesite=app.state.session_cookie_samesite,
            secure=os.getenv("SESSION_COOKIE_SECURE", "").lower() in {"1", "true", "yes"},
            path="/",
        )
    return session_id


def _cookie_samesite() -> str:
    value = os.getenv("SESSION_COOKIE_SAMESITE", "lax").lower()
    return value if value in {"lax", "strict", "none"} else "lax"


def _execute_query(app: FastAPI, request: QueryRequest) -> dict[str, object]:
    retriever = _get_retriever(app, request.retrieval_mode)
    chat_model, model_error = _chat_model() if request.online else (None, None)
    answer = RAGPipeline(retriever=retriever, chat_model=chat_model).ask(
        request.question,
        top_k=request.top_k,
        relationship_depth=request.relationship_depth,
    )
    return {
        "answer": answer.answer,
        "mode": answer.mode,
        "retrieval_mode": retriever.last_mode,
        "citations": answer.citations,
        "retrieved": answer.retrieved,
        "error": answer.error or model_error,
    }


def _persist_exchange(
    app: FastAPI,
    session_id: str,
    conversation_id: str,
    request: QueryRequest,
    result: dict[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    user_message = app.state.sessions.append_message(
        session_id,
        conversation_id,
        role="user",
        content=request.question,
    )
    if user_message is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    assistant_message = app.state.sessions.append_message(
        session_id,
        conversation_id,
        role="assistant",
        content=str(result["answer"]),
        mode=str(result["mode"]),
        retrieval_mode=str(result["retrieval_mode"]),
        error=result["error"] if isinstance(result["error"], str) else None,
        citations=result["citations"] if isinstance(result["citations"], list) else [],
        retrieved=result["retrieved"] if isinstance(result["retrieved"], list) else [],
    )
    return user_message, assistant_message


def _conversation_title(question: str) -> str:
    normalized = " ".join(question.split())
    return normalized[:60] or "New Part 5 conversation"


def _get_retriever(app: FastAPI, mode: str) -> Part5Retriever:
    cached = app.state.retrievers.get(mode)
    if cached is not None:
        return cached
    knowledge_base = app.state.knowledge_base
    if mode == "fts":
        retriever = Part5Retriever(knowledge_base)
    else:
        retriever = _build_vector_retriever(app.state.root, knowledge_base)
    app.state.retrievers[mode] = retriever
    return retriever


def _build_vector_retriever(root: Path, knowledge_base: KnowledgeBase) -> Part5Retriever:
    vector_path = root / "indexes" / "embeddings.jsonl"
    metadata_path = root / "indexes" / "embeddings.meta.json"
    manifest_path = root / "source" / "source_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        source_hash = manifest.get("sha256") if isinstance(manifest, dict) else None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        source_hash = None
    if not vector_path.exists() or not metadata_path.exists() or not isinstance(source_hash, str):
        return Part5Retriever(knowledge_base)
    try:
        provider = SentenceTransformerEmbeddingProvider(
            os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
        )
    except EmbeddingError:
        return Part5Retriever(knowledge_base)
    return Part5Retriever(
        knowledge_base,
        vector_index=VectorIndex(root, source_hash=source_hash),
        embedding_provider=provider,
    )


def _chat_model() -> tuple[OpenAICompatibleChatModel | None, str | None]:
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


app = create_app()
