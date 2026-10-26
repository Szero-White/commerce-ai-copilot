# CV and application text (claims limited to what was verified)

## Project entry (use as is)

**Commerce AI Copilot — personal project, Python / FastAPI / SQLite** (GitHub: add link)
- Built a RAG-style service for e-commerce on synthetic data: SQLite FTS5/BM25 retrieval with a relevance gate (IDF-weighted coverage, diacritic-aware matching, numeric checks), cited answers and explicit abstention.
- Implemented validation of LLM output (citation IDs, numbers present in the cited sources, unsupported promises, answers that contradict a negated policy) with labelled fallbacks; covered by 196 automated tests, including regression tests for every audited defect.
- Wrote a local-only Ollama adapter (explicit context window, timeouts, malformed-response handling) and a bounded read-only tool-calling agent, **tested with mock models and fake HTTP servers**. Also wrote a hosted free-tier (Gemini) adapter with host/model allowlists, request and per-text embedding budgets, an on-disk embedding cache and a quota stop. Ran one small end-to-end smoke test against the real Gemini free tier (3 cited answers judged correct, 2 out-of-scope refusals, 1 tool-calling agent task); the first live attempts exposed and fixed four defects (response-size limit, per-text rate limiting, misclassified 429 errors, a retired default model).
- Built a 64-question retrieval evaluation (Hit@3 and out-of-scope refusal) and an offline acceptance script; documented limits of every metric.

## Do NOT write (not verified)

"Deployed / production RAG", "reduced hallucinations by X%", "semantic search with BGE-M3", "agent automation", "LangChain/LangGraph experience", "Shopify/Ads integration", "1 year of AI Engineer experience". Quote real-model results only from `docs/LIVE_EVALUATION_GEMINI.md` and always say: hosted Gemini free tier, 3 answers, AI-reviewed, one run. Do not claim the agent works end to end (its final answer was rejected), embeddings/hybrid retrieval were never evaluated, and no local model was run.

## Cover-note paragraph (English)

"I read your AI Engineer posting and built a small RAG and drafting prototype around it. I deliberately spent most effort on failure modes: retrieval that answers off-topic questions, model output that adds unsupported numbers or promises, and fallbacks that hide a failed model. The retrieval, guards and API are tested offline; the LLM and agent paths are tested with mocks, and I have not yet run a real model — I would like to finish that with a faithfulness review. The code and an evaluation report with its limits are in the repository."

## Interview one-liners

- Why a relevance gate? OR-style full-text search returns documents sharing a single word, so a weather question reached a lamp description.
- What would you do first with a real model? Measure prompt tokens against `num_ctx`, calibrate the embedding threshold on a labelled set, and have a person label 30–50 answers supported/unsupported.
