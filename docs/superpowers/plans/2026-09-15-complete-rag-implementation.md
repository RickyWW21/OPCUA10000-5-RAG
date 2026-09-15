# Complete RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a complete, Part 5-only RAG flow that retrieves evidence from the existing knowledge base, optionally calls an OpenAI-compatible DeepSeek endpoint, and returns cited answers with deterministic offline fallback.

**Architecture:** Keep `KnowledgeBase` as the source of truth for OPC UA 10000-5 artifacts. Add a focused retriever adapter, a standard-library OpenAI-compatible chat client, and a `RAGPipeline` that assembles bounded context and citations. Expose the pipeline through a new `ask_kb.py` CLI while preserving all existing APIs and commands.

**Tech Stack:** Python standard library, `sqlite3` FTS5, `urllib.request`, `unittest`, existing CLI error boundary.

**Spec:** `docs/superpowers/specs/2026-09-15-complete-rag-design.md`

## Global Constraints

- All retrieval and generation grounding must remain restricted to OPC UA 10000-5 Part 5 records.
- No vector database, embedding model, streaming response, conversation memory, or new runtime dependency.
- API keys come from explicit constructor arguments or `DEEPSEEK_API_KEY`/`OPENAI_API_KEY`; never add a real key to tracked files.
- Model failures degrade to a clearly labeled offline answer; retrieval failures remain visible to callers.
- Every behavior-changing implementation starts with a failing unittest and ends with a passing focused test plus the full suite.

---

### Task 1: Part 5 Retrieval Adapter

**Files:**
- Create: `opcua_kb/retrieval.py`
- Create: `tests/test_retrieval.py`

**Interfaces:**
- Consumes: `KnowledgeBase.search(query, top_k)`, `KnowledgeBase.get_entity(name)`, and `KnowledgeBase.relationships(entity, depth=...)`.
- Produces: `RetrievedRecord` and `Part5Retriever.retrieve(question, top_k=6, relationship_depth=0)` for `RAGPipeline`.

- [ ] **Step 1: Write the failing tests**

```python
def test_retriever_keeps_exact_results_before_fts_results():
    retriever = Part5Retriever(fake_kb)
    records = retriever.retrieve("ServerType components", top_k=2)
    assert [record.id for record in records] == ["ObjectType:ServerType", "sec-6.3.6"]


def test_retriever_deduplicates_and_rejects_non_part5_records():
    fake_kb.search.return_value = [
        {"type": "chunk", "id": "chunk-1", "title": "1 Scope", "snippet": "...", "doc": "OPC-10000-5"},
        {"type": "chunk", "id": "chunk-1", "title": "duplicate", "snippet": "...", "doc": "OPC-10000-5"},
        {"type": "chunk", "id": "foreign", "title": "Other Part", "snippet": "...", "doc": "OPC-10000-4"},
    ]
    assert [record.id for record in Part5Retriever(fake_kb).retrieve("x")] == ["chunk-1"]
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `python -m unittest tests.test_retrieval -v`

Expected: FAIL because `opcua_kb.retrieval` and `Part5Retriever` do not exist.

- [ ] **Step 3: Implement the minimal adapter**

Define:

```python
@dataclass(frozen=True)
class RetrievedRecord:
    id: str
    type: str
    title: str
    snippet: str
    section: str | None = None
    table_number: str | None = None
    doc: str = "OPC-10000-5"


class Part5Retriever:
    def __init__(self, knowledge_base: KnowledgeBase): ...
    def retrieve(self, question: str, *, top_k: int = 6, relationship_depth: int = 0) -> list[RetrievedRecord]: ...
```

Normalize search dictionaries into records, preserve first-seen IDs, enforce `doc == "OPC-10000-5"` when present, validate positive `top_k` and non-negative depth, and only add relationship records when a resolved entity exists.

- [ ] **Step 4: Run the focused tests and verify they pass**

Run: `python -m unittest tests.test_retrieval -v`

Expected: PASS with all retrieval tests green.

- [ ] **Step 5: Commit**

```bash
git add opcua_kb/retrieval.py tests/test_retrieval.py
git commit -m "feat: add Part 5 retrieval adapter"
```

### Task 2: OpenAI-Compatible Chat Client

**Files:**
- Create: `opcua_kb/llm.py`
- Create: `tests/test_llm.py`

**Interfaces:**
- Consumes: system/user prompt strings and optional environment configuration.
- Produces: `ChatModel.generate(system=..., user=..., temperature=...) -> str` and typed `LLMError` failures.

- [ ] **Step 1: Write the failing tests**

```python
def test_client_posts_openai_compatible_payload_and_returns_content():
    request = RecordingTransport({"choices": [{"message": {"content": "grounded answer"}}]})
    model = OpenAICompatibleChatModel(api_key="test-key", model="deepseek-chat", base_url="https://example.test", transport=request)
    assert model.generate(system="system", user="user") == "grounded answer"
    assert request.url == "https://example.test/chat/completions"
    assert request.headers["Authorization"] == "Bearer test-key"
    assert request.payload["messages"][1]["content"] == "user"


def test_client_rejects_missing_key_and_malformed_response():
    with self.assertRaises(LLMError):
        OpenAICompatibleChatModel(api_key="", model="m", base_url="https://example.test")
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `python -m unittest tests.test_llm -v`

Expected: FAIL because `opcua_kb.llm` is missing.

- [ ] **Step 3: Implement the minimal standard-library client**

Define:

```python
class LLMError(RuntimeError): ...


class ChatModel(Protocol):
    def generate(self, *, system: str, user: str, temperature: float = 0.0) -> str: ...


class OpenAICompatibleChatModel:
    def __init__(self, *, api_key: str | None = None, model: str = "deepseek-chat", base_url: str = "https://api.deepseek.com", timeout: float = 60.0, transport: Callable[[Request, float], bytes] | None = None): ...
    def generate(self, *, system: str, user: str, temperature: float = 0.0) -> str: ...
```

Resolve key precedence as constructor, `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`; normalize the endpoint; send JSON with `model`, `messages`, and `temperature`; parse the first choice content; wrap URL, timeout, JSON, HTTP, and schema failures in `LLMError` without exposing secrets.

- [ ] **Step 4: Run the focused tests and verify they pass**

Run: `python -m unittest tests.test_llm -v`

Expected: PASS with request and error tests green.

- [ ] **Step 5: Commit**

```bash
git add opcua_kb/llm.py tests/test_llm.py
git commit -m "feat: add OpenAI-compatible chat client"
```

### Task 3: RAG Pipeline and Offline Fallback

**Files:**
- Create: `opcua_kb/rag.py`
- Create: `tests/test_rag.py`
- Modify: `opcua_kb/__init__.py`

**Interfaces:**
- Consumes: `Part5Retriever.retrieve(...)` and optional `ChatModel.generate(...)`.
- Produces: `RAGAnswer` and `RAGPipeline.ask(...)`, exported from `opcua_kb`.

- [ ] **Step 1: Write the failing tests**

```python
def test_pipeline_offline_answer_contains_part5_citations():
    pipeline = RAGPipeline(retriever=fixture_retriever, chat_model=None)
    result = pipeline.ask("What is ServerType?", top_k=2)
    assert result.mode == "offline"
    assert "OPC UA 10000-5" in result.answer
    assert result.citations[0]["label"] == "[E1]"
    assert "[E1]" in result.answer


def test_pipeline_sends_bounded_context_to_model_and_returns_generated_answer():
    model = RecordingChatModel("ServerType is defined in Part 5. [E1]")
    result = RAGPipeline(retriever=fixture_retriever, chat_model=model, max_context_chars=500).ask("What is ServerType?")
    assert result.mode == "generated"
    assert result.answer.startswith("ServerType")
    assert "[E1]" in model.user_prompt
    assert len(model.user_prompt) <= 500 + 500


def test_pipeline_converts_model_failure_to_offline_mode():
    result = RAGPipeline(retriever=fixture_retriever, chat_model=FailingChatModel()).ask("x")
    assert result.mode == "offline"
    assert result.error
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `python -m unittest tests.test_rag -v`

Expected: FAIL because `opcua_kb.rag` and `RAGPipeline` do not exist.

- [ ] **Step 3: Implement context assembly, prompt construction, and answer model**

Define:

```python
@dataclass(frozen=True)
class RAGAnswer:
    answer: str
    mode: Literal["generated", "offline"]
    citations: list[dict[str, str]]
    retrieved: list[dict[str, Any]]
    error: str | None = None


class RAGPipeline:
    def __init__(self, *, retriever: Part5Retriever, chat_model: ChatModel | None = None, max_context_chars: int = 12000): ...
    def ask(self, question: str, *, top_k: int = 6, relationship_depth: int = 0) -> RAGAnswer: ...
```

Reject blank questions and invalid limits. Assign stable labels by record order (`[E1]`, `[T1]`, `[C1]`, `[R1]`), build a bounded Part 5 context, instruct the model to cite only supplied labels, and generate a deterministic fallback beginning with `离线检索结果（未调用语言模型）`. Empty retrieval must return `未找到相关 Part 5 证据。` with no citations. Catch only `LLMError` for fallback; allow retrieval/validation errors to propagate.

- [ ] **Step 4: Run the focused tests and verify they pass**

Run: `python -m unittest tests.test_rag -v`

Expected: PASS with generated, offline, citation, and validation cases green.

- [ ] **Step 5: Commit**

```bash
git add opcua_kb/rag.py opcua_kb/__init__.py tests/test_rag.py
git commit -m "feat: add Part 5 RAG pipeline"
```

### Task 4: Ask CLI and User Documentation

**Files:**
- Create: `tools/ask_kb.py`
- Modify: `README.md`
- Modify: `tools/help.py`
- Create: `tests/test_ask_cli.py`

**Interfaces:**
- Consumes: `KnowledgeBase`, `OpenAICompatibleChatModel`, and `RAGPipeline`.
- Produces: `python tools/ask_kb.py QUESTION [--top-k N] [--relationship-depth N] [--offline]`.

- [ ] **Step 1: Write the failing CLI tests**

```python
def test_ask_cli_prints_answer_mode_and_citations():
    result = run_cli_script("tools/ask_kb.py", "What is ServerType?", "--offline")
    self.assertEqual(result.returncode, 0)
    self.assertIn("离线检索结果", result.stdout)
    self.assertIn("引用", result.stdout)


def test_ask_cli_rejects_empty_question_without_traceback():
    result = run_cli_script("tools/ask_kb.py", "   ")
    self.assertNotEqual(result.returncode, 0)
    self.assertNotIn("Traceback", result.stderr)
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `python -m unittest tests.test_ask_cli -v`

Expected: FAIL because `tools/ask_kb.py` does not exist.

- [ ] **Step 3: Implement the CLI and documentation**

Construct `KnowledgeBase(ROOT)`, choose offline mode when `--offline` is set, otherwise build the chat client from environment variables, run `RAGPipeline.ask`, and print answer, mode, citations, and retrieved IDs. Use `run_cli` so errors remain concise. Update help and README with Part 5-only examples and redacted environment setup:

```powershell
$env:DEEPSEEK_API_KEY = "..."
python tools/ask_kb.py "ServerType 包含哪些组件？" --top-k 5
python tools/ask_kb.py "ServerType 包含哪些组件？" --offline
```

- [ ] **Step 4: Run CLI tests and verify they pass**

Run: `python -m unittest tests.test_ask_cli -v`

Expected: PASS with clean error output and cited answers.

- [ ] **Step 5: Commit**

```bash
git add tools/ask_kb.py tools/help.py README.md tests/test_ask_cli.py
git commit -m "feat: expose Part 5 RAG through ask CLI"
```

### Task 5: Full Verification and Security Review

**Files:**
- Modify: `config.toml` only if needed, without adding or retaining a real secret
- Modify: `.gitignore` only if needed to ignore local secret/config overrides

- [ ] **Step 1: Run the complete test suite**

Run: `python -m unittest discover -v`

Expected: zero failures and zero errors, including all existing tests.

- [ ] **Step 2: Run a live offline smoke test**

Run: `python tools/ask_kb.py "ServerType 包含哪些组件？" --offline --top-k 3`

Expected: a Part 5-only offline answer with stable citations and no traceback.

- [ ] **Step 3: Inspect the diff for scope and secret leakage**

Run: `git diff --check; git diff --stat; rg -n "sk-[A-Za-z0-9]|api_key\s*=\s*['\"]sk-" --glob '!*.pkl' --glob '!*.log' .`

Expected: no whitespace errors and no newly introduced tracked secret. Existing untracked `config.toml` must remain uncommitted.

- [ ] **Step 4: Commit final verification/documentation adjustments**

```bash
git add .gitignore config.toml
git commit -m "chore: document secure RAG configuration"
```

Only stage these files if the diff contains intentional secret-safe changes; never stage a real API key.

