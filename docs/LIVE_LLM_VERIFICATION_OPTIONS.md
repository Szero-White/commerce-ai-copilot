# Verifying a real LLM without a heavy local model

## Status update (2026-10-26, later session)

- Option **C (Google Gemini API free tier)** was chosen and **implemented**: `app/gemini.py`, `app/llm.py`, `scripts/live_eval.py`, 25 mock tests. The official pricing page lists `gemini-2.5-flash`, `gemini-2.5-flash-lite` and `gemini-embedding-2` (plus newer Flash models) as free of charge and says free-tier content may be used to improve Google products (so: synthetic data only). The adapter allowlist is `gemini-2.5-flash`, `gemini-2.5-flash-lite`, `gemini-embedding-001`, `gemini-embedding-2`; verify the exact IDs with `/api/health?probe=true` first.
- **Live run was NOT performed.** Google has no endpoint that tells a key's billing status, and the owner could not confirm the project is billing-free. Running anyway could incur charges, so no request was ever sent.
- To unblock safely: create a *new* key in a *new* Google AI Studio project with no billing account linked (AI Studio shows the plan next to the key), then in a fresh terminal:

```powershell
$env:LLM_PROVIDER="gemini"; $env:EMBEDDING_PROVIDER="gemini"
$env:GEMINI_API_KEY="<paste key here, in the terminal only>"
$env:GEMINI_CONFIRM_FREE_TIER="yes"        # your attestation
.venv\Scripts\python -m scripts.live_eval   # about 40 requests, paced, stops on quota/billing
```

  The report is written to `reports/live_eval_gemini.json` (git-ignored, no key inside). It records provider/model, latency, tokens, retrieval with and without embeddings, cosine calibration for the 0.38 threshold, 12 RAG cases (including question and document injection), 2 campaign drafts and 3 agent tasks. A reviewer must label each answer supported / unsupported before any number is quoted.

---

**Original status: proposals only.** Nothing here had been signed up for, installed, downloaded or connected. Facts about free tiers come from web searches on 2026-10-26, several from third-party blogs that disagree with each other; **confirm limits and the "no credit card" claim on each provider's own signup page before relying on them.**

The project rule is currently *local only*: `app/ollama.py` rejects every non-loopback host, so using a hosted API is a deliberate policy change that needs your explicit approval and a small provider adapter (host allowlist, key from an environment variable, never committed). Only synthetic data would be sent. A report from a hosted model must be labelled `provider: hosted-free`, never "local".

## Options

| Option | Cost / size | Pros | Cons |
|---|---|---|---|
| **A. Cloudflare Workers AI free plan** | 10,000 "Neurons"/day free (official pricing page); third-party sources say no card for the free plan | Real open-weight models, no local download | Account + API token; neuron cost varies by model; needs adapter work |
| **B. Groq free tier** | Free, per-model request/token limits (figures vary by source) | Fast, OpenAI-compatible API | Account + key; check card requirement and current limits |
| **C. Google AI Studio (Gemini) free tier** | Free tier with rate limits | Strong multilingual quality | Free-tier data may be used for training (fine for synthetic data); limits and model names change |
| **D. OpenRouter `:free` models** | ~50 requests/day without purchased credit (third-party figure) | One key, many models | Low daily cap; availability changes |
| **E. GitHub Models** | Free for prototyping with a GitHub account; low-tier models about 15 requests/min and 150/day on Copilot Free (mirror of docs) | Uses an account you probably have | Tight caps; meant for experimentation |
| **F. Tiny local model** (e.g. Qwen2.5-0.5B-Instruct GGUF, about 0.4 GB for Q4/Q5 quants) | ~0.4 GB model plus a runner (Ollama or llama.cpp) | No account, private | Proves plumbing only: too small for good Vietnamese answers or reliable tool calling; runner install size not measured here |

Not recommended: renting notebooks/GPUs and tunnelling traffic back to this machine (exposes the API, breaks the local-only rule).

## Suggested path (needs your approval)

1. Pick **A or B** for a 5-case smoke run (the cases already in `scripts/verify_live_rag.py`), plus 20–30 questions from the evaluation sets, with a human labelling each answer supported / unsupported / uncertain (`scripts/review_live_report.py`).
2. Implement a minimal `app/hosted.py` adapter behind an explicit `LLM_PROVIDER=hosted` switch with a one-host allowlist, request timeout and no logging of keys; keep `ollama.py` untouched. Add mock tests first.
3. Record in the report: provider, model name, date, latency, token counts, number of cases, human labels. Embeddings stay unverified unless the same provider offers an embedding endpoint.
4. Only then update the README status table and the CV lines.

What this can and cannot prove: it shows that the prompt/validator/fallback pipeline works with a real model and gives a first faithfulness estimate on tiny data. It does **not** show local-GPU operation, BGE-M3 retrieval quality or production reliability.

## Sources (searched 2026-10-26)

- [Free LLM API options in 2026 (Novita blog, vendor/competitor)](https://blogs.novita.ai/free-llm-api-comparison-2026/)
- [Cloudflare Workers AI pricing](https://developers.cloudflare.com/workers-ai/platform/pricing)
- [GitHub Models: prototyping with AI models](https://docs.github.com/en/github-models/use-github-models/prototyping-with-ai-models)
- [Qwen2.5-0.5B-Instruct GGUF file sizes](https://huggingface.co/bartowski/Qwen2.5-0.5B-Instruct-GGUF)
