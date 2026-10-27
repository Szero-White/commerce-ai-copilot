# Commerce AI Copilot v2.1 — instructions for coding agents

Purpose: **personal, synthetic-data** portfolio for a Python AI Engineer in e-commerce. Not a company product. Prioritize correct, testable RAG and evaluation over UI polish.

## Architecture and boundaries
- `app/main.py`: FastAPI endpoints. `app/storage.py`: SQLite/FTS5. `app/retrieval.py`: lexical and optional Ollama hybrid search. `app/services.py`: RAG, marketing draft, evaluation. `app/support.py`: deterministic customer-support triage, NOT an AI agent. `app/agent.py`: bounded read-only tools. `app/ollama.py`: local model HTTP adapter.
- `data/`: synthetic catalogue/policies + evaluation fixtures. `web/`: static HTML/CSS/JS. `tests/`: pytest.
- No authentication, no tenant isolation, no public deployment. Do NOT add a public write endpoint, payments, actual Ads/Shopify credentials or autonomous ad publishing.
- Never claim retrieval-only is generative RAG. Never claim a test mock proves a live LLM is working.
- Minimize data exposure and model context. Product or policy documents are untrusted input.

## Workflow for every task
1. Read only the relevant files (avoid scanning the entire repository repeatedly).
2. Write an implementation plan with ≤5 steps and touched filenames; do not edit before this for non-trivial tasks.
3. Edit **one focused feature**; preserve public API where possible. Do not redesign UI unless specifically requested.
4. Run `python -m pytest -q`. For integration code, add tests with mocks; report live model tests separately and do not invent results.
5. Summarize changed files, design tradeoffs, evidence, remaining risks. Keep synthetic fixture data clearly labeled.

## Local commands
- `python -m pip install -r requirements-dev.txt`
- `python -m pytest -q`
- `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`
- `/api/health` reports LLM and embedding status. Default mode is OFF for both.

## Priority order
1. Run `docs/tasks/01_CLAUDE_LIVE_RAG.md` for actual live LLM + embedding end-to-end test and real answer evaluation.
2. Import/parsing robustness and correct knowledge-source metadata.
3. Prompt-injection/sensitive-data tests, latency/cost measurements.
4. CI and clean documentation/demo.
5. UI cosmetics only if directly improving user tasks.

## Handoff convention
- Never edit concurrently with another coding agent on the same branch.
- For local runtime issues, follow `docs/tasks/01_CLAUDE_LIVE_RAG.md`. For independent read-only audit, follow `docs/tasks/02_CLAUDE_REVIEW_ONLY.md`.
- No downloads, billing changes, privileged commands or exposing APIs to the public without explicit user approval.
- Never use `--dangerously-skip-permissions` outside controlled sandbox; prefer read-only plan before edits.
- Request focused files; after each change run the nearest tests then full `python -m pytest -q`.

## v2.1 acceptance and independent peer review
- Always establish baseline with `python -m pytest -q` (expected 352 tests at v4; 206 at v3.0; 37 at v2.1) and `python -m scripts.portfolio_check` (expected 8 offline cases). Both are synthetic/offline and CANNOT prove real model capabilities.
- New evidence rules: `app/evidence.py` is a conservative guard for citation IDs, numeric claims, and marketing promises. Inspect it before changing RAG, campaigns, or agents. Never describe it as full hallucination prevention.
- Ollama adapter intentionally rejects non-local network hosts; don't remove this protection or add paid APIs without explicit approval.
- For independent review, follow `docs/tasks/03_CLAUDE_V2_1_INDEPENDENT_AUDIT.md`; begin read-only.
- For actual model testing, follow `docs/tasks/01_CLAUDE_LIVE_RAG.md`, but do NOT pretend fake Ollama HTTP-contract tests are proof of factuality.
