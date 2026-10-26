# Engineering handoff — Commerce AI Copilot v2

## Product thesis
Make operational knowledge reusable for e-commerce customer support and marketing, with a visible human approval gate. This is an **individual portfolio prototype** with synthetic catalog and policies, not a tool affiliated with NEXGEN BROS.

## Verified scope
- FastAPI, SQLite FTS5 / BM25 retrieval, source references, no-source refusal.
- Optional **actual** Ollama chat `/api/chat` and embeddings `/api/embed` with RRF hybrid search; MUST be tested with models on the target computer before claiming functioning generative RAG.
- `Support Ticket Triage`: deterministic, auditable routing, human-review draft, evidence retrieval. **Not** a LLM agent and cannot approve refunds or access customers' orders.
- Read-only agent tool adapter (Ollama optional), human-review marketing drafts, retrieval Hit@3 evaluation and negative questions.
- Embedding model version identity stored alongside vectors to avoid reusing stale vectors after changing models.
- Citations and numeric-value checks for LLM candidate answers. These are limited heuristics, **not factual grounding guarantees**.
- CI on GitHub Actions and automated API, rules, storage-migration and mock-provider tests.

## Architecture choices
- **Modular monolith** instead of microservices (simpler maintenance for prototype scope).
- **SQLite FTS5** instead of hosting vector DB for the small synthetic corpus. Brute-force cosine is intentionally limited to small datasets.
- **Human approval gate** in workflow: no write, send, ad budget, customer PII or order lookup actions exist.
- **LLM optional**, with explicit degraded extractive mode. ChatGPT Plus and Claude subscriptions do NOT automatically provide an API key or cover external model API charges.
- **Measured evidence** kept separately: unit tests / synthetic Hit@3 vs live-model performance vs business impact. Do not mix these categories.

## Threat model / limitations
1. **Prompt injection in source docs:** the system tells the LLM not to follow retrieved instructions, but this alone is not sufficient. Use untrusted-source boundaries, allowlist tools, red-team tests and human review before external actions.
2. **Hallucination:** IDs/numeric consistency checks only cover a subset; an LLM could produce a false claim using numbers already present in sources. Manual evaluation and larger held-out datasets needed.
3. **Unauthorized data:** no authentication, tenant separation or rate limiting. NEVER expose this local demo to public Internet as-is.
4. **Retrieval drift:** changing an embedding model invalidates old vectors; no semantic index build on file upload. Reindex explicitly.
5. **Scale:** SQLite and cosine loop are for demo. Production candidate: PostgreSQL+pgvector, asynchronous ingestion, encrypted secret storage, observability, request budgets, per-tenant controls and read-only staging integrations.
6. **Compliance:** synthesize all catalog, policy, order and support data; never scrape or claim access to a prospective employer's internal data.

## Suggested 5-minute interview sequence
1. State business problem, boundaries and what is genuinely powered by an LLM (0:40).
2. Ask `Can I return a personalized item because I changed my mind?`; show `[POD-POL-201]`, source limitations (1:00).
3. Support Triage: submit damaged personalized mug ticket, show intent, priority, routing and evidence (1:00).
4. Quality Lab: show Hit@3 on synthetic questions, then discuss how to add faithfulness evaluation (0:50).
5. Marketing: create draft, demonstrate approval requirement and no auto-publish (0:40).
6. Show test suite and at least one genuine failure / fix, then discuss production architecture (0:50).

## To upgrade to production (not implemented)
Authentication/RBAC, tenant-isolated data, rate limits, document versioning, approval record+audit trail, evaluation dataset representative of real customers, human escalation integrations, secure Shopify API, secrets management, resilience and operational monitoring.
