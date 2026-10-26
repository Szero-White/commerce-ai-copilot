# Release v2.0 — 26 October 2026

## What was actually changed
- `app/support.py`: guarded support triage workflow, policy evidence, mandatory human review, read-only.
- `app/main.py`: `/api/support/triage`, Pydantic validation, updated health metadata.
- `app/storage.py`: migrations and `embedding_model` metadata for vector safety.
- `app/retrieval.py`: reindex when embedding model changes; avoid mixing model vectors.
- `app/services.py`: reject unsupported numeric claims from LLM before presenting as cited answer, with an extractive fallback.
- `scripts/verify_live_rag.py`: opt-in actual local Ollama check, writes observed metrics, cannot claim passed if LLM is off.
- `web/`: support workflow page, API wiring and responsive layout.
- `tests/test_v2.py`: regression and security contract tests.
- `docs/`: engineering handoff, honest JD coverage, Claude Code task briefs, CV text conditional on actual execution.

## Evidence
- `python -m pytest -q`: **25 passed** on the development environment; no paid API was used.
- Live FastAPI `/api/health`: HTTP 200, 15 demo documents.
- Screenshot UI checks: loaded the actual HTML/CSS/JS with **mocked API responses** sourced from the FastAPI TestClient, verified Support Triage interaction and Quality Lab 13/13 retrieval results with no browser JS errors. Screenshots MUST NOT be described as public deployment or real LLM inference.
- `python -m scripts.verify_live_rag` correctly exits with error when LLM+embedding are disabled.

## Explicitly not verified
Local Ollama generation and vector embeddings with an installed model; live-model answer factuality; user accounts and authentication; real Shopify/Meta/Google Ads integrations; revenue impact; scalability; external hosting.

## Blocker and next handoff
Claude Code Task 01 (`docs/tasks/01_CLAUDE_LIVE_RAG.md`) is the next highest ROI task to do on the user's machine. Only after genuine inference evidence, advance to the separate read-only code review task.
