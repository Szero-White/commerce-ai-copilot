# CLAUDE TASK 01 — LIVE RAG VERIFICATION (LOCAL ONLY)

## Goal
Validate a real **Ollama LLM + embeddings** run. Do not claim live RAG works before it has passed end-to-end with actual downloaded models on this machine.

## Instructions for Claude Code
1. Read only `CLAUDE.md`, `README.md` (local-model section), `app/ollama.py`, `app/retrieval.py`, `scripts/index_embeddings.py`, `scripts/verify_live_rag.py`.
2. Run `python -m pytest -q`. Note the baseline result.
3. Check installed Python, Ollama, available RAM/disk and local models. Never install software without my approval; never choose paid API.
4. In plan mode, propose the **smallest** steps needed to enable local generative RAG. Prefer existing `qwen2.5:1.5b` and `bge-m3` if installed; otherwise recommend hardware-appropriate models and ASK before downloading.
5. When I approve, enable providers using terminal-scoped env vars (never commit secrets), run the embedding index and `python -m scripts.verify_live_rag`.
6. Open `reports/live_rag_report.json` and describe passed/failed cases. Manually check factual content against retrieved policy text with `python -m scripts.review_live_report`; report mistakes and uncertainty instead of hiding them.
7. Fix only failures that you can reproduce. No new UI/website redesign or microservices.
8. Run all tests after your changes and summarize files changed, known limitations, exact commands and true observed metrics.

## Acceptance criteria
- Real model responses reported with `llm_rag_cited` for positive cases.
- Actual embedding index for the configured model, not mock embeddings.
- At least one out-of-scope question safely abstains.
- Report JSON exists with real measured latency/token counts and `human_factuality_review` completed by a person.
- `pytest` passes after any code change.

## Strict exclusions
No real Shopify customer accounts, Meta Ads credentials, bulk web scraping, real payment/refund actions, production deployment or fabricated performance claims.
