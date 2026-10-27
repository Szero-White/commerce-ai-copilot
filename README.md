# Commerce AI Copilot v3.0 — RAG, guarded drafts and evaluation for e-commerce

> **Personal portfolio project on 100% synthetic data.** Not a NEXGEN BROS product and not a production system. It was built around the skills in a public *AI Engineer (LLM/RAG/AI Automation)* job description. The Vietnamese README is kept in [docs/README_VI.md](docs/README_VI.md).

**Honest status in one line:** retrieval, guards, API, evaluation and error handling are implemented and tested offline. The LLM path has been verified against a **real hosted model, as one small smoke run** (Gemini free tier, `gemini-3.5-flash-lite`, 7 requests): 3 cited answers all correct (AI-reviewed), 2 out-of-scope refusals, and 1 tool-calling agent task that called both read-only tools and returned a cited answer that passed the evidence validator. An earlier agent rejection turned out to be a false rejection in our own validator and was fixed. See [docs/LIVE_EVALUATION_GEMINI.md](docs/LIVE_EVALUATION_GEMINI.md). **This is not an accuracy or reliability measurement, and it is not production-ready.** Real embeddings and hybrid retrieval, a meaningful sample size, and any local model remain unverified.

## What works, and how it was verified

| Area | Status | Evidence |
|---|---|---|
| FastAPI service, SQLite FTS5 (BM25) retrieval, source citation, abstention | **Run for real (offline)** | 352 pytest tests, 8/8 offline acceptance, all endpoints exercised over HTTP; real Chrome 89/89 UI checks at 390-1920 px |
| Retrieval relevance gate (IDF coverage, matched words must be close together, domain synonyms, accent-aware match) | **Run for real (offline)** | 31 positive / 33 negative evaluation questions ([report](docs/EVALUATION_REPORT.md)) |
| **v4** Query analyzer: "bàn" / "bạn" / "bán" collision, filler words, typo repair against the document vocabulary, "which X do you have?" and catalogue questions | **Run for real (offline)** | `app/query.py`; measured on 3 separate sets, see [Retrieval quality](#retrieval-quality-measured-v4) |
| **v4** Evidence gate: unknown names / model codes, exact numbers and units, stock, offers, private data, **price/size comparisons computed from the documents' numbers** ("dưới 2 triệu"); unverifiable comparisons are flagged, never claimed | **Run for real (offline)** | `app/gate.py`, `app/quantities.py`; synthetic-score property tests; no similarity score can admit a document |
| **v4** Adding / updating / removing knowledge without code changes: atomic import, `--replace-source`, `--delete`, consistency check, version-aware caches | **Run for real (offline)** | `scripts/ingest.py`, `scripts/check_index.py`; a fresh catalogue imported after the algorithm was frozen was found and updated correctly (lifecycle 7/7) |
| **v4** Follow-up questions in the chat UI ("nó bảo hành thế nào?", "cái thứ hai giá bao nhiêu?"); ambiguous pointers get a numbered question back | **Run for real (offline)** | `app/dialogue.py` + `web/app.js` (JS only); real Chrome 15/15 |
| Evidence guards: numbers, promises, negated policies, audience injection | **Run for real (offline)** | Unit + API regression tests. Pattern matching only; see limits below |
| Support-ticket triage (rules, human review required) | **Run for real (offline)** | Deterministic, **not** an AI agent |
| Ollama adapter robustness (timeouts, bad JSON, redirects, proxies, HTTP errors) | **Real sockets, fake model** | `tests/test_ollama_resilience.py` talks to a local fake server |
| Gemini free-tier adapter (host/model allowlists, key handling, request budget, per-text embedding limiter + cache, stop on quota/billing, function calling) | **Real sockets, fake server, plus one real smoke run** | `tests/test_gemini_adapter.py`; live smoke: [LIVE_EVALUATION_GEMINI.md](docs/LIVE_EVALUATION_GEMINI.md) |
| Real-model answers with citations (3 questions), negated policy preserved, injected instruction not repeated (1 case) | **Real, hosted, tiny sample** | same report; reviewer was an AI, not an independent human |
| Tool-calling agent: 2 read-only tools, 3-turn loop, cited answer passed the validator | **Real, hosted, one task**; also mock-tested | same report |
| Campaign LLM draft; the Ollama (local) LLM and agent paths | **Mock only** | calls are monkeypatched or go to a fake server; proves control flow, not model quality |
| Embeddings (hosted, `gemini-embedding-001`): experiment on the dev questions only (151 texts, 19 requests) | **Real, hosted, dev data only: negative result** | The right document was rank 1 in 8/8 need-based questions, but similarity scores of questions the catalogue cannot answer overlap those of true matches, so no safe threshold admits documents by meaning (best: 1/8). **Hybrid stays OFF**; vectors only re-rank documents the gate already admitted. [Details](reports/PHASE_LOG.md) |
| Gemini answer quality after the v4 changes, faithfulness beyond 3 answers, agent reliability beyond 1 task, any local model | **NOT verified** | The only real LLM run (smoke, 7 requests) predates v4. See [live verification options](docs/LIVE_LLM_VERIFICATION_OPTIONS.md) |
| LangChain / LlamaIndex / LangGraph, vector DB, Shopify / Ads APIs, auth, deployment | **Not implemented** | |

## Quick start (no model, no API key required)

Requires Git and **Python 3.10+** (developed and tested on Python 3.14 / Windows 11; the grammar was checked against 3.9–3.11, and CI uses 3.11 on Ubuntu, which the author has not run). The UI was checked in real Chrome at 390 to 1920 px (see the evaluation report). Docker and the Linux/macOS commands below are provided but **untested by the author**.

```powershell
git clone <your-repo-url> commerce-ai-copilot
cd commerce-ai-copilot
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest -q                       # 352 passed
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
                              ├─ dialogue.py   follow-ups: "nó", "cái thứ hai" -> a document, or a question back
                              ├─ query.py      word roles from the documents' own vocabulary, typos, intents
                              ├─ quantities.py numbers with units, comparisons, computed from document text
                              ├─ gate.py       ONE evidence gate for every candidate document
                              ├─ retrieval.py  gated BM25 candidates; embeddings (if on) only re-rank them
                              ├─ storage.py    SQLite + FTS5, atomic import/delete, consistency check
                              ├─ support.py    rule-based triage (no LLM)
                              ├─ agent.py      bounded read-only tool loop
                              ├─ evidence.py   citation / number / promise / negation guards (LLM answers)
                              └─ ollama.py, gemini.py   local-only / hosted free-tier adapters
```

Question → `dialogue` (resolve pointers) → `query` (read the question) → BM25 candidates → `gate` (hard constraints) → rank → extractive answer, or LLM answer checked by `evidence`.

Details and design decisions: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Adding, updating and removing knowledge (no code changes)

```powershell
python -m scripts.ingest data\fresh_products.csv                       # CSV: sku,name,description[,price,category]; a bare price is read as VND
python -m scripts.ingest policies.md --category policy --replace-source # .md/.txt are chunked; --replace-source also removes chunks that no longer exist
python -m scripts.ingest --delete-source fresh_products                # withdraw everything a source contributed (or --delete <id>)
python -m scripts.check_index                                          # documents vs text index vs vectors; exit code 1 if stale
```

A file is applied in **one transaction** (all or nothing). Ids come from the source name and the SKU, not from the file path. The BM25 index, the vocabulary used for typo repair and the caches follow the documents immediately (a running server notices an import made by another process). Vectors are **not** updated automatically: changed or new documents have none until `python -m scripts.index_embeddings` is run (it calls the embedding provider). The seed JSON is loaded only into an empty database. There is **no real-time sync and no automatic crawler**; data enters through this CLI.

## Retrieval quality (measured, v4)

All numbers: offline, LLM and embeddings off, k = 3, synthetic data, one script (`scripts/quality_eval.py`) run on the baseline commit (07a626f) and on the final code. Wilson intervals are in `reports/*.json`; the sets are small.

| Set | Baseline | Final |
|---|---|---|
| Dev positives, Hit@3 (used while developing) | 26/52 | 39/52 |
| Dev false abstention | 25/52 | 13/52 |
| Dev near-miss questions answered wrongly (premise not in the data) | 1/12 | 0/12 |
| **Holdout** (locked by hash before any change, run once): Hit@3 / false abstention / wrong answers to unanswerable questions | 12/25, 13/25, 2/8 | **14/25, 11/25, 0/8** |
| **Fresh** products + policies added after the freeze, only through `ingest`: Hit@3 / wrong answers | 10/19, 3/8 | **12/19, 1/8** |
| Update, replace-source removal, delete, index consistency on the fresh data | not supported | 7/7 checks |

What this says honestly: the system is **safer** (wrong answers to unanswerable questions: holdout 0/8 instead of 2/8, fresh 1/8 instead of 3/8) and finds more, but on questions it had never seen it still abstains too often (holdout false abstention 44%) and the pre-registered acceptance targets (80% hit rate / 20% false abstention) were **not met**. Need-based paraphrases that share no words with the documents ("something to read by at night") are 0/6 across the unseen sets: lexical search cannot reach them, and in the embedding experiment (above) meaning-based admission could not be made safe on this data. Two defects found by the fresh data (bare CSV price, "đặc điểm" request frame) were fixed after the session and are **not** re-measured on clean data. Full tables and every failing case: [docs/EVALUATION_REPORT.md](docs/EVALUATION_REPORT.md), [reports/PHASE_LOG.md](reports/PHASE_LOG.md).

## Safety model

- Local only: the adapter accepts `http://localhost|127.0.0.1` and nothing else, ignores system proxies and refuses redirects. No paid API, no public write endpoint, no autonomous publishing; every draft is `DRAFT_REQUIRES_HUMAN_APPROVAL`.
- Documents and user text are treated as untrusted. The LLM sees an explicit `num_ctx`, and responses report how close the prompt came to the window.
- **Every LLM answer is validated, then falls back to source passages if rejected.** The validator checks citation IDs, numbers present in the *cited* sources, promises (free shipping, cures, "best price"…) that no source affirms, and answers that affirm what a source negates ("not eligible for return").
- **These guards are sentence-level pattern matching. They do not detect hallucination in general**; a fluent wrong sentence without numbers or listed phrases can pass.
- Fallbacks are labelled, never disguised: `llm_rag_cited`, `llm_citation_rejected_extractive`, `llm_unavailable_extractive`, `extractive_demo`, `no_evidence`; campaign `template_preview` (LLM off) vs `template_llm_unavailable` / `template_llm_invalid_output` / `template_safety_fallback`; agent `agent_disabled` / `agent_llm_unavailable` / `agent_no_verified_evidence` / `agent_answer_rejected` / `agent_tool_blocked`.

## API

`GET /api/health[?probe=true]` · `GET /api/documents` · `GET /api/products` · `POST /api/chat` · `POST /api/campaign` · `POST /api/support/triage` · `POST /api/agent` · `GET /api/evaluation` · `GET /api/metrics`. Embedding indexing is CLI-only (`/api/admin/index-embeddings` returns 403).

## Known limitations

- Lexical retrieval cannot understand meaning: questions that share no words with the answer are not found, and a question about a missing *attribute* of an existing product ("Sofa Terra S1 có màu hồng không?") can still return that product's text (the answer never claims the attribute). 1 of 33 legacy out-of-scope questions ("Địa chỉ cửa hàng ở đâu?") still returns related policy text.
- Capitalised words the catalogue has never seen (a product name, but also a place such as "Hà Nội") make a question unanswerable: conservative by design.
- Follow-ups remember only the previous answer, and only in the browser tab (reload = new conversation); the unaccented pronoun "no" is not recognised.
- Evaluation sets are small and written by one person; the relevance gate was tuned on the dev set; dev and holdout share an author and some vocabulary.
- No authentication, rate limiting or tenant isolation: run on localhost only. Docker cannot reach a host Ollama by design.
- No parsing of PDF/HTML; CSV/TXT/MD import via CLI only.

## Repository map

`app/` service · `data/` synthetic catalogue, policies and evaluation sets · `tests/` unit, contract, and static-asset regressions · `scripts/` ingest, index, offline acceptance, live verification · `docs/` architecture, evaluation, demo script, CV text, audit history and [code quality guide](docs/CODE_QUALITY.md) · `web/` static UI (`app.js`, `index.html`, and the ordered CSS modules in `web/styles/`).

## Job-description mapping (honest)

Python/REST/DB ✅ · RAG parsing + retrieval ✅ (lexical + gate; embeddings tried on dev data, negative result, off) · ingestion update/delete ✅ · LLM API integration 🟡 (Ollama and Gemini adapters, mock-tested; one pre-v4 smoke run) · output evaluation ✅ for retrieval (baseline vs final, dev/holdout/fresh), ❌ for answer faithfulness · agent/loop 🟡 (mock-tested) · FastAPI/Docker/CI ✅ files + offline CI · LangChain/LangGraph/vector DBs/Platform APIs ❌.
