# Task 4 Report

## Status

Complete. The Part 5 `ask_kb.py` CLI now supports offline retrieval, environment-configured OpenAI-compatible chat, concise validation errors, citations, and retrieved IDs. README and consolidated help include redacted Part 5 examples.

## Tests

Command:

```text
python -m unittest tests.test_ask_cli -v
```

Output:

```text
test_ask_cli_prints_answer_mode_and_citations (tests.test_ask_cli.AskCliTests.test_ask_cli_prints_answer_mode_and_citations) ... ok
test_ask_cli_rejects_empty_question_without_traceback (tests.test_ask_cli.AskCliTests.test_ask_cli_rejects_empty_question_without_traceback) ... ok
test_ask_cli_reports_missing_api_key_without_traceback (tests.test_ask_cli.AskCliTests.test_ask_cli_reports_missing_api_key_without_traceback) ... ok

----------------------------------------------------------------------
Ran 3 tests in 0.489s

OK
```

Additional checks passed:

- `python tools/ask_kb.py --help` displays the required question, top-k, relationship-depth, offline, and environment-backed usage.
- `python tools/help.py` includes the ask CLI examples.
- README contains redacted `DEEPSEEK_API_KEY` setup and online/offline Part 5 examples.

## Self-review

- Blank questions and missing API keys exit non-zero without a traceback.
- Offline mode performs no API-client construction or network call.
- API credentials and endpoint/model settings are read from environment variables; no secrets are stored in source or docs.
- Output includes mode, citation labels, and retrieved record IDs.
- Changes remain scoped to Task 4 files and Part 5 RAG usage.

## Concerns

- The repository's existing bilingual text is displayed with legacy mojibake in some terminals; this report preserves the project convention.
- Online mode requires a valid provider key and network access, so only offline behavior is deterministic in local tests.
