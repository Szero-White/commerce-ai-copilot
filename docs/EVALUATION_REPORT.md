# Evaluation report — v3.0 (offline, no LLM)

Everything below was produced by running the code in this repository on 2026-10-26 (Windows 11, Python 3.14.6, no GPU used). **No language model or embedding model was run.** Do not read these numbers as answer quality.

## 1. Test suite

| Check | Result |
|---|---|
| `python -m pytest -q` | **127 passed** |
| `python -m scripts.portfolio_check` | **8/8** offline workflow checks |
| Per-commit check (each git commit exported and tested alone) | 37 → 37 → 90 → 109 → 127 passed |
| HTTP smoke test against live uvicorn (no model) | `/`, `/assets/*`, health, products, chat, campaign, triage, agent, evaluation, metrics, 403 admin, 422 validation all as expected |
| Browser rendering | **Not tested** (no browser automation). `node --check web/app.js` passes and all 48 element IDs used by the script exist in the HTML |

Test kinds: *offline deterministic* (retrieval, triage, guards), *real sockets + fake model* (`tests/test_ollama_resilience.py`, `tests/test_release.py`), *monkeypatched LLM* (answer, campaign, agent). A passing mocked test proves control flow only.

## 2. Retrieval evaluation (lexical BM25 + relevance gate)

| Set | Size | Result |
|---|---|---|
| Positive questions, metric Hit@3 | 31 | 31/31 = 1.00 |
| Out-of-scope questions, "correctly returns nothing" | 33 | 31/33 = 0.94 |

Still leaking: "Bạn có bán điều hòa không?" (matches the word "điều" in a warranty clause) and "Mã giảm giá tháng này là gì?" (returns the marketing-rules document that mentions discounts). They are kept in the set on purpose.

Before the gate, 6 of 24 development negatives leaked (weather, bitcoin, motorbike warranty, "giảm 5%", employee count…). The weather query is blocked by a small out-of-scope phrase list because a lexical index cannot know that "thời tiết" only matches the unrelated words "thời gian" and "tiết kiệm".

**Validity limits.** The 22 development positives and 24 development negatives were used to choose the coverage threshold (0.5) and term weights. A further 9 positives and 10 negatives were written afterwards as a held-out check: all 9 positives passed after one more rule (English plural tolerance, added after one miss), and 2 of the 10 negatives leaked. Because of the rule added after seeing the miss and because the held-out questions were then merged into the evaluation set, **the final numbers are not an unbiased estimate.** The sets are small and written by one person on a 15-document knowledge base.

Offline cost: the whole 64-query evaluation took 121 ms in one measured run on SQLite (no tokens, single run, not a benchmark).

## 3. Guard evaluation (unit/regression level)

| Guard | Examples now rejected |
|---|---|
| Numbers glued to units | `130x60cm` vs source `120 x 60 cm`; `50k`; `Sale50%` |
| Promises not affirmed by the source | miễn phí giao hàng, tốt nhất, chữa khỏi, khuyến mãi, quà tặng, "best", "ship free"… |
| Affirming a negated policy | "You can return a personalized item" vs "…not eligible for return"; "được hoàn tiền" vs "hoàn tiền thật chưa được tích hợp" |
| Audience injection | digits, promises, `[ID]`, newlines, "ignore previous instructions", "bỏ qua chỉ thị" |

Known bypasses: wording that is not in the lists; a sentence that mixes a true and a false clause and contains a negation word; false statements without numbers or listed phrases; URLs in answers.

## 4. What this report does NOT show

Answer faithfulness, hallucination rate, semantic retrieval quality, latency or token use of a real model, tool-calling reliability of any model, behaviour of Ollama's context window, or anything about real customers. See [LIVE_LLM_VERIFICATION_OPTIONS.md](LIVE_LLM_VERIFICATION_OPTIONS.md) for how to obtain that evidence.

## 5. Reproduce

```powershell
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m scripts.portfolio_check     # writes reports/offline_acceptance_report.json (git-ignored)
```
