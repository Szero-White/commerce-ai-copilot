# 4-minute interview demo — AI Engineer (RAG/AI Automation)

**Opening (20s):** "I built a local-first, synthetic-data AI e-commerce copilot to explore support automation, grounded answers, and safe marketing drafts. I chose Python/FastAPI so each feature is an API that can be independently tested. This is a portfolio prototype, not the company's system."

**Minute 1 — customer problem.** Ask about Oak 120 dimensions; open its source `PRD-101`. Ask an unsupported 90% discount; verify it abstains. Explain BM25 FTS5, top-k, model-citation ID and numeric guard. In offline mode, state that it's **retrieval**, not generative AI.

**Minute 2 — operational workflow.** In Support Triage, ask "My personalized mug arrived damaged. Can I get a refund?". Show classification, high priority, policy citation, human approval. Explain why support decisions and refunds are not autonomous.

**Minute 3 — AI workflow + engineering.** Generate a marketing draft; explain the no-publication boundary. Show `app/evidence.py` fallback logic. If **real Ollama** is available, show `llm_rag_cited` run and `reports/live_rag_report.json`; otherwise explicitly show that live verification is pending. Never claim mocked HTTP as real model.

**Minute 4 — measurable QA.** Run Quality Lab and `python -m pytest -q`, describe Hit@3 vs factual answer quality. Show the eight-case acceptance report. Discuss next steps: human-labeled answer evaluation, real provider integration with consent, security/auth, production data, and latency baselines.

## Deep-dive Q&A

**Why not build a full Shopify clone?** The job is about AI integrations into e-commerce operations, not replacing storefront or checkout. My source adapters currently import synthetic CSV/text; real APIs would require data contracts and secure credentials.

**Why not introduce LangGraph today?** A bounded, two-tool agent is enough to show the core. Orchestration frameworks could be added if branching, persistence or multi-step retries justify their costs.

**What does source citation prove?** It proves the source ID exists among retrieved passages, NOT that every assertion is logically entailed. Numeric checks catch some hallucinations; need annotated faithfulness evaluation and robust guardrails for real use.

**How to limit token costs?** Retrieve top-k relevant chunks, cap context and output, avoid repeated agent calls, log observed token usage from model responses. Offline metrics are token *estimates*, not billed tokens.

**What would I change before production?** Authentication, authorization, PII handling, secrets, tenant isolation, rate limiting, evals on representative customer data, observability and incident paths, platform API contracts, fallback behavior, human approval.
