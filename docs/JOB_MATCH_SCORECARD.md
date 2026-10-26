# JD skill matching — AI Engineer LLM/RAG/Automation

| Requirement from pasted JD | Evidence in this repo | Honest status |
|---|---|---|
| Python, REST API, database | FastAPI, SQLite, source tests | Implemented |
| Parsing/data preparation | CSV/TXT/MD CLI ingestion | Small demo, not industrial parser |
| Retrieval and vector search | FTS5+BM25; optional Ollama /api/embed & cosine RRF | Lexical tested; real embeddings require owner machine verification |
| LLM integration | Optional Ollama /api/chat adapter | Mock-tested; local model end-to-end unverified here |
| RAG workflow and source references | Retrieval, constrained context, citation and numeric guards | Implemented with explicit limited guarantees |
| Prompt evaluation / prompt optimization | Compact prompts, 13 retrieval questions & 3 negatives | Retrieval evaluation only; model factuality not measured yet |
| AI agents & automation | Read-only tool calling (optional); support triage rules workflow | Optional agent mock-tested; triage is not agent |
| Code review, sprint discipline | Tests, CI, docs, task briefs, acceptance criteria | Engineering artifacts, not proof of team work experience |
| Python FastAPI, Docker, CI/CD | Included Docker, compose and GitHub Actions | Local test and workflow config; no public deployment claim |
| LangChain/LlamaIndex/LangGraph | None | Not implemented; not mandatory per JD |
| Shopify/Meta/Google Ads platform APIs | None | Synthetic catalog; no external permissions |
| MLOps/vLLM/Kubernetes | None | Not implemented |
| Quantified business impact | No real customer or business data | Not measured; can propose pilot metrics only |

**Gap to prioritize:** real LLM+embeddings on an accessible machine and a measured answer-quality report with human annotations. Do NOT chase LangGraph, Kubernetes or a perfect marketing UI before these pass.
