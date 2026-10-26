# Architecture and design decisions

## Request flows

**`POST /api/chat`**
1. `retrieval.search` → `storage.fts_search` (FTS5/BM25 over diacritic-stripped text) → relevance gate. If Ollama embeddings are enabled and indexed, cosine scores are fused with BM25 by reciprocal-rank fusion (RRF).
2. No sources → `no_evidence` (no model call).
3. `LLM_PROVIDER=off` → `extractive_demo` (cited passages; this is retrieval, not generation).
4. `LLM_PROVIDER=ollama|gemini` → context packed to `MAX_CONTEXT_CHARS` without cutting source IDs → `ollama.chat` with explicit `num_ctx` → `evidence.valid_cited_answer`. Accepted → `llm_rag_cited`; rejected → `llm_citation_rejected_extractive`; Ollama failure → `llm_unavailable_extractive`. The response carries `context_window` (`prompt_tokens`, `num_ctx`, `near_limit`) when a model was called.

**`POST /api/campaign`** — builds a template from the product record; with Ollama, asks for a JSON draft. Every candidate (template included) passes `safe_marketing_copy`. The free-text `audience` is only used if `safe_audience` accepts it. Always `DRAFT_REQUIRES_HUMAN_APPROVAL`; nothing is published.

**`POST /api/agent`** — only with an LLM provider (Ollama or Gemini function calling). At most 3 model turns, 2 tool calls, tools `lookup_product` and `search_policy` (read-only, bounded output). Unknown tool → `agent_tool_blocked`. The final answer must cite documents the tools actually returned, else `agent_answer_rejected`.

**`POST /api/support/triage`** — keyword rules decide intent, priority and team; retrieval only supplies policy evidence. No LLM, no order data, human review required.

**`GET /api/evaluation`** — Hit@3 over `data/eval_set.json` and "correct refusal" over `data/negative_eval_set.json`. It measures retrieval, not answers.

## Modules

| File | Responsibility |
|---|---|
| `app/storage.py` | SQLite schema, FTS5 index, `fts_search` with the relevance gate |
| `app/retrieval.py` | hybrid search, vector indexing, stale-model protection (`embedding_model` column) |
| `app/evidence.py` | citation IDs, numbers, promise blocklist, negation check, audience filter, context-window report |
| `app/ollama.py` | local network code: loopback-only HTTP, no proxies, no redirects, bounded reads, defensive JSON handling, `/api/tags` probe |
| `app/gemini.py` | hosted free-tier adapter (separate file): only `generativelanguage.googleapis.com` over https, key from the environment sent in a header and scrubbed from errors, free-model allowlist, per-process request budget, one retry, permanent stop on quota/billing errors, function calling for the agent |
| `app/llm.py` | provider switch and `llm_info` (every model-backed response says provider, model and `hosted: true/false`) |
| `app/services.py`, `app/agent.py`, `app/support.py` | workflows |
| `app/main.py`, `web/` | API and static UI |

## Key decisions

- **Fail closed, label everything.** Each degraded path has its own `mode` string so metrics and the UI cannot confuse "LLM off", "LLM failed", "answer rejected" and "no evidence".
- **Relevance gate before the LLM.** FTS OR-queries return anything sharing one word. The gate requires that the IDF-weighted share of query terms found in a document (directly, as an English inflection or through a small domain synonym table such as kích thước→cm) reaches 0.6; that the matched terms lie within 8 tokens of each other; that words typed with diacritics match with diacritics; and that every number, including single digits, occurs. Rare and unknown words weigh more than common ones. There is no list of forbidden topics.
- **Guards are sentence-level and conservative.** A promise in the answer needs an *affirmative* sentence in the cited source; a topic that the source only negates may not be affirmed; a sentence that itself contains a negation is allowed. This is a pattern check, not entailment.
- **Explicit `num_ctx`.** Otherwise the server's default window can silently drop the start of a long prompt, where the instructions are.
- **Local by default, hosted only by explicit choice.** With `LLM_PROVIDER=off|ollama` nothing leaves the machine and the Ollama adapter refuses other hosts. `gemini` is an explicit opt-in with its own adapter; it must only ever receive synthetic data because free-tier content may be used by the provider.
- **SQLite + brute-force cosine** is fine for 15 documents; pgvector or a vector DB would be the next step at scale. Not implemented.

## Not built (on purpose)

LangGraph/LangChain, vector databases, Shopify/Meta/Google Ads integrations, authentication, queues, deployment. They would add surface area without making the unverified LLM path any more proven.
