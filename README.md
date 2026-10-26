# Commerce AI Copilot v3.0 — RAG, guarded drafts and evaluation for e-commerce

> **Personal portfolio project on 100% synthetic data.** Not a NEXGEN BROS product and not a production system. It was built around the skills in a public *AI Engineer (LLM/RAG/AI Automation)* job description. The Vietnamese README is kept in [docs/README_VI.md](docs/README_VI.md).

**Honest status in one line:** retrieval, guards, API, evaluation and error handling are implemented and tested offline. The LLM path has been verified against a **real hosted model, as one small smoke run** (Gemini free tier, `gemini-3.5-flash-lite`, 7 requests): 3 cited answers all correct (AI-reviewed), 2 out-of-scope refusals, and 1 tool-calling agent task that called both read-only tools and returned a cited answer that passed the evidence validator. An earlier agent rejection turned out to be a false rejection in our own validator and was fixed. See [docs/LIVE_EVALUATION_GEMINI.md](docs/LIVE_EVALUATION_GEMINI.md). **This is not an accuracy or reliability measurement, and it is not production-ready.** Real embeddings and hybrid retrieval, a meaningful sample size, and any local model remain unverified.

## What works, and how it was verified

| Area | Status | Evidence |
|---|---|---|
| FastAPI service, SQLite FTS5 (BM25) retrieval, source citation, abstention | **Run for real (offline)** | 206 pytest tests (199 original + 7 static UI-asset and CSS regressions), 8/8 offline acceptance, all endpoints exercised over HTTP against a live uvicorn |
| Retrieval relevance gate (IDF coverage, matched words must be close together, domain synonyms, accent-aware match) | **Run for real (offline)** | 31 positive / 33 negative evaluation questions ([report](docs/EVALUATION_REPORT.md)) |
| Evidence guards: numbers, promises, negated policies, audience injection | **Run for real (offline)** | Unit + API regression tests. Pattern matching only; see limits below |
| Support-ticket triage (rules, human review required) | **Run for real (offline)** | Deterministic, **not** an AI agent |
| Ollama adapter robustness (timeouts, bad JSON, redirects, proxies, HTTP errors) | **Real sockets, fake model** | `tests/test_ollama_resilience.py` talks to a local fake server |
| Gemini free-tier adapter (host/model allowlists, key handling, request budget, per-text embedding limiter + cache, stop on quota/billing, function calling) | **Real sockets, fake server, plus one real smoke run** | `tests/test_gemini_adapter.py`; live smoke: [LIVE_EVALUATION_GEMINI.md](docs/LIVE_EVALUATION_GEMINI.md) |
| Real-model answers with citations (3 questions), negated policy preserved, injected instruction not repeated (1 case) | **Real, hosted, tiny sample** | same report; reviewer was an AI, not an independent human |
| Tool-calling agent: 2 read-only tools, 3-turn loop, cited answer passed the validator | **Real, hosted, one task**; also mock-tested | same report |
| Campaign LLM draft; the Ollama (local) LLM and agent paths | **Mock only** | calls are monkeypatched or go to a fake server; proves control flow, not model quality |
| Hybrid BM25 + vector (RRF) retrieval | **Mock only** | Fake embeddings; the 0.38 similarity threshold is **uncalibrated** |
| Real embeddings / hybrid retrieval, the 0.38 threshold, faithfulness beyond 3 answers, agent reliability beyond 1 task, any local model | **NOT verified** | Needs a real model: see [live verification options](docs/LIVE_LLM_VERIFICATION_OPTIONS.md) |
| LangChain / LlamaIndex / LangGraph, vector DB, Shopify / Ads APIs, auth, deployment | **Not implemented** | |

## Quick start (no model, no API key required)

Requires Git and **Python 3.10+** (developed and tested on Python 3.14 / Windows 11; the grammar was checked against 3.9–3.11, and CI uses 3.11 on Ubuntu, which the author has not run). The UI was checked in real Chrome at 390 to 1920 px (see the evaluation report). Docker and the Linux/macOS commands below are provided but **untested by the author**.

```powershell
git clone <your-repo-url> commerce-ai-copilot
cd commerce-ai-copilot
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest -q                       # 206 passed
.venv\Scripts\python -m scripts.portfolio_check         # 8/8 offline acceptance
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Linux/macOS (untested): `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements-dev.txt`, then the same `python -m pytest -q`, `python -m scripts.portfolio_check` and `python -m uvicorn ...` commands. On Windows you can also double-click `run_windows.bat` (it installs only `requirements.txt` and starts the app). The first start creates `runtime/lab.db` (git-ignored).

Open http://127.0.0.1:8000 (UI) or http://127.0.0.1:8000/docs (Swagger). By default `LLM_PROVIDER=off` and `EMBEDDING_PROVIDER=off`, so `/api/chat` returns **extractive, cited passages — this is retrieval, not generative RAG**.

Optional hosted LLM (smoke-tested once, see `docs/LIVE_EVALUATION_GEMINI.md`; options in `docs/LIVE_LLM_VERIFICATION_OPTIONS.md`): `LLM_PROVIDER=gemini EMBEDDING_PROVIDER=gemini`, key only in the `GEMINI_API_KEY` environment variable, then run the secure launcher `run_gemini_live.ps1` (hidden key prompt, key only in that process). Default is a **smoke test**: 3 RAG answers + 1 agent task with lexical retrieval and Gemini generation, about 7 requests, nothing embedded. `python -m scripts.live_eval --full` (**never run**) would add embeddings (metered per text: 60 texts/minute, on-disk cache, text budget), hybrid retrieval, calibration and campaigns. Free-tier content may be used by Google to improve its products, so only synthetic data is ever sent, and any report must say "hosted", not "local".

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

`app/` service · `data/` synthetic catalogue, policies and evaluation sets · `tests/` unit, contract, and static-asset regressions · `scripts/` ingest, index, offline acceptance, live verification · `docs/` architecture, evaluation, demo script, CV text, audit history and [code quality guide](docs/CODE_QUALITY.md) · `web/` static UI (`app.js`, `index.html`, and the ordered CSS modules in `web/styles/`).

## Job-description mapping (honest)

Python/REST/DB ✅ · RAG parsing + retrieval ✅ (lexical; vector optional/unverified) · LLM API integration 🟡 (Ollama and Gemini adapters, mock-tested only) · output evaluation ✅ for retrieval, ❌ for answer faithfulness · agent/loop 🟡 (mock-tested) · FastAPI/Docker/CI ✅ files + offline CI · LangChain/LangGraph/vector DBs/Platform APIs ❌.
