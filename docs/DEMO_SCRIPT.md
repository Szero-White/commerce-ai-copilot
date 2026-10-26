# Interview demo script (6–8 minutes)

Setup: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`, open http://127.0.0.1:8000. LLM is off unless you configured it; **say so at the start**.

1. **Framing (30 s).** "Synthetic furniture and print-on-demand data. I wanted to practise the parts of an AI feature that fail in practice: bad retrieval, unsupported claims, silent fallbacks. The LLM path is implemented and tested with mocks; I have not run a real model yet, and I can show you exactly where that boundary is."
2. **RAG Assistant (1 min).** Ask "Bàn Oak 120 kích thước bao nhiêu?" → point at the source `PRD-101` and the `mode` badge `extractive_demo`: "retrieval with citations, not generation."
3. **Refusal (1 min).** Ask "Hôm nay thời tiết thế nào?" and "Có giảm 5% không?" → `no_evidence`. Explain the relevance gate (IDF coverage, accent-aware, numbers always checked) and show `tests/test_retrieval_gate.py`.
4. **Campaign Studio (1 min).** Generate a draft, then type the audience `giảm 90% hôm nay` → the offer is not echoed (`audience_used: false`). Explain `safe_marketing_copy` and why it is a blocklist, not proof.
5. **Support triage (1 min).** `My personalized mug arrived damaged. Can I get a refund?` → intent, priority, policy evidence, human review. "Deterministic on purpose; not an agent."
6. **Quality Lab (1 min).** Run evaluation: 31/31 Hit@3, 31/33 correct refusals. Show the two failures in [EVALUATION_REPORT.md](EVALUATION_REPORT.md) and say the sets are small and partly used for tuning.
7. **Code walk (2 min).** `app/evidence.py` (numbers, negation: "not eligible for return" cannot be answered "you can return"), `app/ollama.py` (loopback only, `num_ctx`, error handling), a failing-then-passing test such as `tests/test_negation_claims.py`.
8. **Limits and next step (30 s).** "Next is a real model run with a faithfulness review, calibrating the embedding threshold, and measuring latency and tokens. Without that I will not claim generative RAG works."

**Likely questions.** *Why not LangChain/LangGraph?* The loop is 3 steps with a whitelist; a framework would hide the parts I wanted to test. I can use them; I have not shipped with them. *Does the guard stop hallucination?* No: numbers, listed promises, negated policies and citation IDs only. *Is the agent real?* The loop and whitelist are real and mock-tested; no model has driven it yet.
