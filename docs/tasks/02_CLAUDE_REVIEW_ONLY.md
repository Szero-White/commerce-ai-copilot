# CLAUDE TASK 02 — READ-ONLY CODE + SECURITY REVIEW

Only perform this AFTER Task 01 has observed an actual local LLM run.

1. Inspect `app/`, `scripts/`, `tests/`, and configuration files. Start in plan/read-only mode.
2. Identify **up to 5 specific, reproducible** issues relevant to e-commerce RAG: hallucinated claims, prompt injection in retrieved documents, input validation, stale embeddings, concurrency, or API exposure.
3. For every issue provide file:line, reproduction, severity, smallest fix and matching regression test.
4. DO NOT edit code. Return your review in a concise Markdown report, so ChatGPT and the developer can choose and implement scoped fixes.
5. Clearly separate bugs from recommendations and avoid inventing vulnerabilities you did not verify.

Run `python -m pytest -q` for baseline if environment allows. No paid API, no public data or secret access.
