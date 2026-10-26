# Commerce AI Copilot v2.1 — release acceptance record

> **Historical (v2.1).** Superseded by [EVALUATION_REPORT.md](EVALUATION_REPORT.md) (v3.0: 127 tests). Correction found in the independent audit: v2.1 actually contains **37** tests; the 35 below was stale.

## What has actually been measured in the build environment

- `python -m pytest -q` — **35 passed** (offline; includes a **fake Ollama local HTTP server**, not a real model).
- `python -m scripts.portfolio_check` — **8/8 local API workflow checks passed**; saved JSON in `reports/offline_acceptance_report.json`. Cases use a temporary SQLite database and synthetic fixtures.
- HTTP boundaries: no required SaaS API; Ollama adapter accepts localhost HTTP only; external host rejected.
- Marketing: unsupported numeric promises trigger fallback to a deterministic preview. Copy still needs **human approval**.
- Agent: cannot invoke tools outside its whitelist and rejects an answer lacking cited tool evidence or inventing numbers. This is NOT equivalent to instruction-hierarchy proof, safety certification, or full fact-checking.

## Important gaps (must not claim to have completed)

- **No actual LLM or embedding model was run by ChatGPT in this release build.** Do not write "deployed production RAG" or "validated semantic accuracy" in your CV.
- Human factuality reviews not completed. LLM may still hallucinate **non-numeric** claims with valid citations; retrieval may be semantically irrelevant.
- No authenticated users, tenant boundaries, rate limit, production secret handling or public deployment hardening.
- No real Shopify / Meta Ads / Google Ads accounts or APIs connected; no sale/refund performed; no proven cost/time savings for a business.
- Not a viable public customer-facing system without data/privacy/security and deployment review.

## Acceptance gates for a demonstrable *live* AI portfolio

- [ ] On the user's PC, real Ollama `ollama list` shows chosen **local** LLM and embedding model.
- [ ] `start_live_ai_windows.bat` completes index and reports actual observed model output; failing models are reported honestly.
- [ ] Inspect `reports/live_rag_report.json`: meaningful citation, no fabricated discount/price, appropriate abstention. Review each answer with `python -m scripts.review_live_report` (supported/unsupported/uncertain).
- [ ] Negative cases include unknown product, made-up 90% discount, prompt injection, sensitive order request; record weaknesses.
- [ ] Record hardware, model versions, query latency, token counts and test setup without inventing measurements.
- [ ] Video demo showing UI + source + code + actual test results. Explain which components are rules vs LLM.
- [ ] GitHub repo contains **source only**, no real PII, no .env, no local SQLite runtime database, no downloaded LLMs.

## How to ask Claude Code to cross-review
Read `docs/tasks/03_CLAUDE_V2_1_INDEPENDENT_AUDIT.md`, have Claude run the offline checks and review read-only first, then paste its factual report into the ChatGPT conversation for a second assessment. **The two assistants cannot automatically communicate**. Keep one active code editor at a time; share a diff/ZIP for final review.
