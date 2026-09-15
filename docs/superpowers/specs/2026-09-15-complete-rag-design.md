# Complete RAG Design

**Date:** 2026-09-15  
**Status:** Approved design

## Goal

Turn the existing offline OPC UA knowledge base into an end-to-end RAG system that retrieves grounded evidence, optionally enriches it with graph relationships, and generates a cited answer through a configurable OpenAI-compatible chat model.

## Scope

The first implementation will use the existing SQLite FTS5 index as the retrieval engine. It will not add an embedding model, vector database, or external framework. The design keeps those capabilities replaceable through small interfaces, so semantic retrieval can be added later without changing the public RAG API.

The system will support two modes:

- **Generated mode:** retrieve evidence and call a configured OpenAI-compatible chat endpoint, defaulting to the existing DeepSeek settings.
- **Offline mode:** retrieve evidence and return a deterministic evidence-based response when no API key is configured or the model request fails. The response must state that it is an offline fallback and must not pretend to be an LLM answer.

## Architecture

```text
question
  -> KnowledgeBase.search()
  -> optional relationship expansion
  -> context assembly with stable source labels
  -> prompt construction
  -> ChatModel.generate()
  -> RAGAnswer(answer, citations, retrieval metadata)
```

### Components

1. `opcua_kb/retrieval.py`
   - Defines a small retriever protocol and an FTS-backed implementation around `KnowledgeBase`.
   - Performs exact/FTS retrieval, deduplication, top-k limiting, and optional relationship expansion.

2. `opcua_kb/rag.py`
   - Owns the end-to-end `RAGPipeline`.
   - Builds bounded context and prompts.
   - Calls the chat model when configured.
   - Produces a serializable `RAGAnswer` with answer text, citations, retrieved records, and mode/error metadata.

3. `opcua_kb/llm.py`
   - Defines a `ChatModel` protocol.
   - Implements an OpenAI-compatible JSON-over-HTTP client using the Python standard library.
   - Reads API credentials from an explicit argument or environment variable; configuration files may provide endpoint/model defaults but must not require a committed secret.

4. `tools/ask_kb.py`
   - Provides the user-facing CLI for asking questions.
   - Prints the answer, mode, citations, and a compact retrieval trace.

5. `tests/test_rag.py` and `tests/test_llm.py`
   - Cover context construction, offline fallback, citation stability, prompt payloads, successful model responses, and model/network failures.

## Public Interfaces

```python
class ChatModel(Protocol):
    def generate(self, *, system: str, user: str, temperature: float = 0.0) -> str: ...


@dataclass(frozen=True)
class RAGAnswer:
    answer: str
    mode: Literal["generated", "offline"]
    citations: list[dict[str, str]]
    retrieved: list[dict[str, Any]]
    error: str | None = None


class RAGPipeline:
    def ask(self, question: str, *, top_k: int = 6, relationship_depth: int = 0) -> RAGAnswer: ...
```

The existing `KnowledgeBase` API remains backward compatible. The pipeline accepts it through constructor injection, which keeps tests deterministic and allows alternate retrievers later.

## Retrieval and Context Rules

- Exact entity, table, and chapter matches retain their existing priority.
- FTS results fill the remaining slots.
- Duplicate IDs are removed while preserving first-seen order.
- Relationship expansion is opt-in and bounded by depth and the same context limit.
- Each context item gets a stable citation label such as `[E1]`, `[T2]`, or `[C3]`.
- Context includes title, section/table identifier, snippet, and source record ID; it is truncated to a fixed character budget before model invocation.
- The prompt instructs the model to answer only from supplied context, cite claims with labels, and say when evidence is insufficient.

## LLM Client Rules

- Use `urllib.request` and `json` from the standard library; no runtime dependency is required.
- Endpoint is normalized to `<base_url>/chat/completions` unless the caller supplies a full endpoint.
- API key precedence: constructor argument, `DEEPSEEK_API_KEY`, then `OPENAI_API_KEY`.
- Model and endpoint defaults may come from environment variables or a non-secret TOML file.
- Timeouts and malformed responses raise a typed `LLMError` with safe messages that do not include credentials or full response bodies.
- The pipeline catches `LLMError` and returns offline fallback output with `error` metadata.

## Offline Fallback

The fallback is deterministic and grounded. It summarizes the top retrieved records as a short evidence list, includes citations, and begins with an explicit marker such as `离线检索结果（未调用语言模型）`. An empty retrieval result returns a clear “未找到相关证据” response and an empty citation list.

## Configuration and Security

- Never commit a real API key.
- Support environment variables for secrets.
- Keep `config.toml` compatible with the existing project, but treat its `api_key` value as optional and prefer environment variables.
- Document setup with a redacted example in README/help output.

## Error Handling

- Empty questions are rejected before retrieval.
- Invalid `top_k` or negative relationship depth raises `ValueError`.
- Retrieval errors remain visible to callers; model errors degrade to offline mode.
- CLI errors use the existing `run_cli` boundary and return a non-zero exit code without a traceback.

## Testing Strategy

- Unit tests use a temporary knowledge base fixture and a deterministic fake chat model.
- HTTP tests use a local in-process HTTP server or a transport seam; they must verify request headers, endpoint, payload, and response parsing without reaching the public network.
- Every new behavior follows a red-green-refactor cycle.
- The full existing unittest suite must remain green.

## Non-Goals

- No vector database or embedding model in this iteration.
- No streaming responses.
- No conversation memory or multi-turn session state.
- No frontend application.
