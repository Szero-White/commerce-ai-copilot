# CV and application text (claims limited to what was verified)

## Project entry (use as is)

**Commerce AI Copilot — personal project, Python / FastAPI / SQLite** (GitHub: add link)
- Built a RAG-style service for e-commerce on synthetic data: SQLite FTS5/BM25 retrieval with a relevance gate (IDF-weighted coverage, diacritic-aware matching, numeric checks), cited answers and explicit abstention.
- Implemented validation of LLM output (citation IDs, numbers present in the cited sources, unsupported promises, answers that contradict a negated policy) with labelled fallbacks; covered by 199 automated tests, including regression tests for every audited defect.
- Wrote a local-only Ollama adapter (explicit context window, timeouts, malformed-response handling; **mock-tested only**) and a hosted free-tier Gemini adapter with host/model allowlists, request and per-text embedding budgets, an on-disk embedding cache and a quota stop. Built a bounded read-only tool-calling agent (2 tools, 3 turns) and ran one small end-to-end smoke test on the real Gemini free tier: 3 cited answers judged correct, 2 out-of-scope refusals, and one agent task that called both tools and passed the evidence validator. The live runs exposed and fixed five defects (response-size cap, per-text rate limiting, misclassified 429s, a retired default model, and a false rejection of document IDs in the validator).
- Built a 64-question retrieval evaluation (Hit@3 and out-of-scope refusal) and an offline acceptance script; documented limits of every metric.

## Do NOT write (not verified)

"Deployed / production RAG", "reduced hallucinations by X%", "semantic search with BGE-M3", "agent automation", "LangChain/LangGraph experience", "Shopify/Ads integration", "1 year of AI Engineer experience". Quote real-model results only from `docs/LIVE_EVALUATION_GEMINI.md` and always say: hosted Gemini free tier, one smoke run, 3 answers and 1 agent task, AI-reviewed. Do not claim agent reliability, embeddings/hybrid retrieval (never evaluated), a local model (never run), accuracy percentages, or production readiness.

## Cover-note paragraph (English)

"I read your AI Engineer posting and built a small RAG and drafting prototype around it. I deliberately spent most effort on failure modes: retrieval that answers off-topic questions, model output that adds unsupported numbers or promises, and fallbacks that hide a failed model. The retrieval, guards and API are tested offline (199 tests). I also ran one small smoke test against a real hosted model (Gemini free tier): three cited answers I judged correct, two refusals, and one tool-calling agent task. That is a tiny sample, so I would like to extend it with a larger faithfulness review and real embeddings. The code, the live report and an evaluation report with its limits are in the repository."

## Interview one-liners

- Why a relevance gate? OR-style full-text search returns documents sharing a single word, so a weather question reached a lamp description.
- What did running a real model teach you? Five bugs that no mock found: a response-size cap, embeddings metered per text rather than per request, a 429 mislabelled as billing, a retired default model, and my own validator rejecting a correct agent answer because it treated the digits of a document ID as a number.
- What would you do next? Calibrate the embedding threshold on a labelled set, have a person label 30–50 answers supported/unsupported, and run a local model.
