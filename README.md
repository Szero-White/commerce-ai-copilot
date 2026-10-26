# Commerce AI Copilot v3.0 — RAG, guarded drafts and evaluation for e-commerce

> **Personal portfolio project on 100% synthetic data.** Not a NEXGEN BROS product and not a production system. It was built around the skills in a public *AI Engineer (LLM/RAG/AI Automation)* job description. The Vietnamese README is kept in [docs/README_VI.md](docs/README_VI.md).

**Honest status in one line:** the retrieval, guards, API, evaluation and error handling are implemented and tested offline; the generative-LLM, embedding and agent paths (Ollama **and** a hosted Gemini free-tier adapter) are implemented but have **only been exercised with mocks and fake HTTP servers. No real model has been run, and no request has ever been sent to Google or any hosted service.**

## What works, and how it was verified

| Area | Status | Evidence |
|---|---|---|
| FastAPI service, SQLite FTS5 (BM25) retrieval, source citation, abstention | **Run for real (offline)** | 165 pytest tests, 8/8 offline acceptance, all endpoints exercised over HTTP against a live uvicorn |
| Retrieval relevance gate (IDF coverage, accent-aware match, out-of-scope phrases) | **Run for real (offline)** | 31 positive / 33 negative evaluation questions ([report](docs/EVALUATION_REPORT.md)) |
| Evidence guards: numbers, promises, negated policies, audience injection | **Run for real (offline)** | Unit + API regression tests. Pattern matching only; see limits below |
| Support-ticket triage (rules, human review required) | **Run for real (offline)** | Deterministic, **not** an AI agent |
| Ollama adapter robustness (timeouts, bad JSON, redirects, proxies, HTTP errors) | **Real sockets, fake model** | `tests/test_ollama_resilience.py` talks to a local fake server |
| Gemini free-tier adapter (host/model allowlists, key handling, request budget, stop on quota/billing, function calling) | **Real sockets, fake server** | `tests/test_gemini_adapter.py` (25 tests); `scripts/live_eval.py` is written but **never run** |
| LLM answer path with citation/claim checks, campaign LLM draft | **Mock only** | `ollama_chat` is monkeypatched; proves control flow, not model quality |
| Tool-calling agent (2 read-only tools, 3-step loop) | **Mock only** | `request_json` is monkeypatched |
| Hybrid BM25 + vector (RRF) retrieval | **Mock only** | Fake embeddings; the 0.38 similarity threshold is **uncalibrated** |
| Real LLM / embedding quality, latency, token counts, faithfulness, `num_ctx` behaviour | **NOT verified** | Needs a real model: see [live verification options](docs/LIVE_LLM_VERIFICATION_OPTIONS.md) |
| LangChain / LlamaIndex / LangGraph, vector DB, Shopify / Ads APIs, auth, deployment | **Not implemented** | |

## Quick start (Windows, no model required)

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest -q                       # 165 passed
.venv\Scripts\python -m scripts.portfolio_check         # 8/8 offline acceptance
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 (UI) or http://127.0.0.1:8000/docs (Swagger). By default `LLM_PROVIDER=off` and `EMBEDDING_PROVIDER=off`, so `/api/chat` returns **extractive, cited passages — this is retrieval, not generative RAG**.

Optional hosted LLM (**not run**; see `docs/LIVE_LLM_VERIFICATION_OPTIONS.md`): `LLM_PROVIDER=gemini EMBEDDING_PROVIDER=gemini`, key only in the `GEMINI_API_KEY` environment variable, then `GEMINI_CONFIRM_FREE_TIER=yes python -m scripts.live_eval` (about 40 requests, free-tier models only, stops on quota/billing). Free-tier content may be used by Google to improve its products, so only synthetic data is ever sent, and any report must say "hosted", not "local".

Optional local LLM (not run by the author): set `LLM_PROVIDER=ollama`, `EMBEDDING_PROVIDER=ollama`, pull models, run `python -m scripts.index_embeddings`, then `python -m scripts.verify_live_rag`, which refuses to run (and claims nothing) unless Ollama and both models are actually present.

## Architecture (short)

```
web/ (static UI) ──HTTP──> app/main.py (FastAPI)
                              ├─ services.py   RAG answer, campaign draft, evaluation
                              ├─ support.py    rule-based triage (no LLM)
                              ├─ agent.py      bounded read-only tool loop
                              ├─ retrieval.py  FTS5 BM25 (+ optional Ollama embeddings, RRF)
                              ├─ evidence.py   citation / number / promise / negation guards
                              ├─ ollama.py     local-only HTTP adapter
                              └─ storage.py    SQLite + FTS5, relevance gate
```

Details and design decisions: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Safety model

- Local only: the adapter accepts `http://localhost|127.0.0.1` and nothing else, ignores system proxies and refuses redirects. No paid API, no public write endpoint, no autonomous publishing; every draft is `DRAFT_REQUIRES_HUMAN_APPROVAL`.
- Documents and user text are treated as untrusted. The LLM sees an explicit `num_ctx`, and responses report how close the prompt came to the window.
- **Every LLM answer is validated, then falls back to source passages if rejected.** The validator checks citation IDs, numbers present in the *cited* sources, promises (free shipping, cures, "best price"…) that no source affirms, and answers that affirm what a source negates ("not eligible for return").
- **These guards are sentence-level pattern matching. They do not detect hallucination in general**; a fluent wrong sentence without numbers or listed phrases can pass.
- Fallbacks are labelled, never disguised: `llm_rag_cited`, `llm_citation_rejected_extractive`, `llm_unavailable_extractive`, `extractive_demo`, `no_evidence`; campaign `template_preview` (LLM off) vs `template_llm_unavailable` / `template_llm_invalid_output` / `template_safety_fallback`; agent `agent_disabled` / `agent_llm_unavailable` / `agent_no_verified_evidence` / `agent_answer_rejected` / `agent_tool_blocked`.

## API

`GET /api/health[?probe=true]` · `GET /api/documents` · `GET /api/products` · `POST /api/chat` · `POST /api/campaign` · `POST /api/support/triage` · `POST /api/agent` · `GET /api/evaluation` · `GET /api/metrics`. Embedding indexing is CLI-only (`/api/admin/index-embeddings` returns 403).

## Known limitations

- Lexical retrieval cannot understand meaning: 1 of 33 development out-of-scope questions ("Địa chỉ cửa hàng ở đâu?") still returns related policy text (see the evaluation report). The embedding layer that should help is unverified.
- Evaluation sets are small, written by the author, and the relevance gate was tuned on part of them.
- No authentication, rate limiting or tenant isolation: run on localhost only. Docker cannot reach a host Ollama by design.
- No parsing of PDF/HTML; CSV/TXT/MD import via CLI only.

## Repository map

`app/` service · `data/` synthetic catalogue, policies and evaluation sets · `tests/` 165 tests · `scripts/` ingest, index, offline acceptance, live verification · `docs/` architecture, evaluation, demo script, CV text, live-verification options, audit history · `web/` static UI.

## Job-description mapping (honest)

Python/REST/DB ✅ · RAG parsing + retrieval ✅ (lexical; vector optional/unverified) · LLM API integration 🟡 (Ollama and Gemini adapters, mock-tested only) · output evaluation ✅ for retrieval, ❌ for answer faithfulness · agent/loop 🟡 (mock-tested) · FastAPI/Docker/CI ✅ files + offline CI · LangChain/LangGraph/vector DBs/Platform APIs ❌.
