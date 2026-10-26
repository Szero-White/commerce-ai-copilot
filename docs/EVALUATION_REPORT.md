# Evaluation report — v3.0 (offline, no LLM)

Produced by running the code in this repository on 2026-10-26 (Windows 11, Python 3.14.6, no GPU). **No language-model answer was evaluated.** Two aborted live attempts against the Gemini free tier are described in section 4. Do not read these numbers as answer quality.

## 1. Test suite

| Check | Result |
|---|---|
| `python -m pytest -q` | **186 passed** |
| `python -m scripts.portfolio_check` | **8/8** offline workflow checks (no longer needs `ignore_cleanup_errors`: SQLite connections are now closed) |
| HTTP smoke test against live uvicorn, LLM off | `/`, health, chat (incl. the former leaks), campaign, triage, agent (disabled), evaluation, metrics: all as expected |
| Browser rendering | **Not tested** (no browser tool available). `node --check web/app.js` passes and all element IDs used by the script exist in the HTML |

Test kinds: *offline deterministic* (retrieval, triage, guards, connection closing), *real sockets + fake server* (`test_ollama_resilience.py`, `test_gemini_adapter.py`, `test_release.py`), *monkeypatched LLM* (answer, campaign, agent). A passing mocked test proves control flow only.

## 2. Retrieval evaluation (lexical BM25 + relevance gate)

| Set | Size | Result |
|---|---|---|
| Development positives, Hit@3 | 31 | 31/31 |
| Development out-of-scope ("correctly returns nothing") | 33 | 32/33 |
| **Held-out** positives (written before the last logic change) | 18 | 18/18 (first measurement 18/18) |
| **Held-out** out-of-scope | 12 | 12/12 (first measurement 11/12) |

Known remaining miss: "Địa chỉ cửa hàng ở đâu?" returns the privacy policy (it contains "địa chỉ"). It is kept in the set. The held-out first-measurement miss was "Thời gian bảo hành của máy lạnh là bao lâu?" (matched the warranty sentence of a lamp).

**What changed since the previous report.** The two earlier leaks ("Bạn có bán điều hòa không?", "Mã giảm giá tháng này là gì?") are now rejected by general rules, and the hard-coded out-of-scope phrase list was removed:

1. matched query terms must lie within 8 tokens of each other (scattered matches such as "điều … hòa" are coincidence);
2. a small domain synonym table (kích thước→cm, giá→VND, màu→color…) lets legitimate paraphrases match, which allowed raising the IDF-coverage threshold from 0.5 to 0.6;
3. English inflections match (changed/change, sizes/size), and question-frame words (áp dụng, phải, come, because…) are stopwords, except accented forms whose unaccented spelling is a product word (tủ, đèn, tải).

**Validity limits (read before quoting).** The held-out set was *not* clean after the first look: stopwords and the inflection rule were added after seeing held-out misses, so the "after" numbers are a second look, not an unbiased estimate. All sets are small, written by one person, on a 15-document knowledge base. The coverage threshold, proximity window and synonym table were chosen on these sets. Offline cost: the 64-query development evaluation took about 120 ms in one run (not a benchmark).

## 3. Guard evaluation (unit/regression level)

| Guard | Examples now rejected |
|---|---|
| Numbers glued to units | `130x60cm` vs source `120 x 60 cm`; `50k`; `Sale50%` |
| Promises not affirmed by the source | miễn phí giao hàng, tốt nhất, chữa khỏi, khuyến mãi, quà tặng, "best", "ship free"… |
| Affirming a negated policy | "You can return a personalized item" vs "…not eligible for return"; "được hoàn tiền" vs "hoàn tiền thật chưa được tích hợp" |
| Audience injection | digits, promises, `[ID]`, newlines, "ignore previous instructions", "bỏ qua chỉ thị" |

Known bypasses: wording not in the lists; a sentence mixing a true and a false clause that contains a negation word; false statements without numbers or listed phrases; URLs in answers.

Demo-visible fixes in this round: extractive answers now cut at sentence boundaries (the "not eligible for free return" exclusion of POL-002 was previously cut off); campaign templates no longer include internal notes ("Do not claim stock…"), SKUs or prices; the agent's `search_policy` tool is no longer starved by product hits.

## 4. Live (hosted) evaluation: attempted twice, NOT completed

The owner created a Google AI Studio project (Free Tier, billing not set up), supplied a key through `run_gemini_live.ps1`, and ran `scripts/live_eval.py` twice. **Neither run reached the answer-quality part, so there are still no measurements of answer faithfulness, hybrid retrieval quality, the 0.38 cosine threshold, generation latency or token use, or tool-calling reliability.** What the attempts did show (hosted `gemini-embedding-001` / `gemini-2.5-flash`, synthetic data, free tier):

| Observation | Evidence |
|---|---|
| The key works and sees 60 models; embeddings are 3072-dimensional; indexing the 16 documents took about 3.5 s | report of both runs |
| Run 1 stopped after 4 requests: a 60-text batch returned >3 MB JSON, over the adapter's 3 MB read cap | adapter bug, fixed (chunking + explicit truncation error) |
| Run 2 stopped after 9 HTTP requests with HTTP 429. AI Studio showed embedding RPM peak 96/100 and RPD 172/1K: **quota is counted per text, not per request**; 16 documents plus 16-text batches exceeded 100 texts/minute | adapter bug, fixed (per-text rate limiter, 60 texts/min, batches of 8 spaced 8 s, text budget, on-disk cache) |
| That 429's body says "check your plan and billing details"; the old adapter therefore labelled it "auth or billing" | misclassification, fixed (HTTP status decides; 429 is always rate/quota; billing only for 401/403/FAILED_PRECONDITION) |

Tests that pin these fixes use fake servers only (`tests/test_gemini_adapter.py`). `live_eval` now defaults to a **smoke** mode (lexical retrieval + Gemini generation for 3 RAG questions, 1 agent task, about 7 requests, no embeddings) and records any stop reason in the report. The full mode is available but has not run.

Tier note: Google offers no API to verify a key's billing status; the free-tier statement is the owner's attestation from the AI Studio page.

## 5. Reproduce

```powershell
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m scripts.portfolio_check     # writes reports/offline_acceptance_report.json (git-ignored)
```
