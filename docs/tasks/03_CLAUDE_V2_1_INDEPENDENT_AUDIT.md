# Claude Code task 03 — Independent technical audit of ChatGPT v2.1

This is an independent **read-only first** review. You are a skeptical senior AI Engineer reviewing a local-only e-commerce portfolio. **Do not trust previous agent claims.** Do not rewrite the product or modify files unless I explicitly approve a scoped patch.

## Context, boundaries
- This is a personal demo using synthetic documents; NOT an NEXGEN BROS product, Shopify integration or production AI service.
- No paid cloud API, no public deployment, no passwords, no customer data, no installation/download without explicit consent.
- `app/evidence.py` is a narrow numeric/citation/copy guard, **not a factuality guarantee**.
- Local Ollama model inference is NOT verified by existing tests; `tests/test_release.py` includes a fake HTTP server.

## Work strictly in this sequence
1. Read only: `CLAUDE.md`, `README.md` release summary, `app/evidence.py`, `app/services.py`, `app/agent.py`, `app/ollama.py`, `app/retrieval.py`, `tests/test_release.py`, `docs/RELEASE_ACCEPTANCE_V2_1.md`.
2. Run **read-only** tests `python -m pytest -q` and `python -m scripts.portfolio_check`. If dependencies are not installed, STOP and ask before installing.
3. Report up to 10 **reproducible** findings, prioritized P0/P1/P2. For each: filename:line, issue, plausible failure, reproduction/test, minimum patch. Flag any hallucinated test/performance claims.
4. Independently inspect whether marketing claim validation can be bypassed, whether agent could return unauthorised claims, whether prompt injection in documents could cross boundaries, and whether model/vector fallback is accurately labelled. Check API/CLI safety and Windows scripts.
5. Evaluate match with JD: Python/REST/database, RAG parsing/embedding/retrieval, LLM integration, evaluation, agent workflows, relevant business value; distinguish **implemented**, **test-mocked**, **needs local live proof**, **not implemented**.
6. Ask approval before any edit. If approved, implement **one** smallest targeted patch in a separate named commit or diff, then run focused tests and full pytest. Do not change tests just to make them pass.

## Review report format (paste into ChatGPT after audit)

```
Repository version: v2.1
Baseline pytest: N passed/N failed (real output)
Offline acceptance: N/N (real output)
Ollama live tested: yes/no; models/commands if yes
P0 findings: ...
P1 findings: ...
P2 findings: ...
False/misleading claims in README/CV: ...
Recommended single next fix: ...
Files modified: NONE (unless approved)
```

## Audit success criteria
A third party can reproduce each finding. No changes to production accounts or external data. Results clearly separate mocked HTTP paths from **actual downloaded-model inference**. A passing unit test is not evidence the system is production safe.
