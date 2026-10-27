# Evaluation report — v3.0 (offline, no LLM)

Produced by running the code in this repository on 2026-10-26 (Windows 11, Python 3.14.6, no GPU). Only one tiny real-model smoke run exists (section 4 and [LIVE_EVALUATION_GEMINI.md](LIVE_EVALUATION_GEMINI.md)). Do not read these numbers as answer quality.

## 1. Test suite

| Check | Result |
|---|---|
| `python -m pytest -q` | **352 passed** (206 before the v4 work; no earlier test was removed or weakened) |
| `python -m scripts.portfolio_check` | **8/8** offline workflow checks (no longer needs `ignore_cleanup_errors`: SQLite connections are now closed) |
| HTTP smoke test against live uvicorn, LLM off | `/`, health, chat (incl. the former leaks), campaign, triage, agent (disabled), evaluation, metrics: all as expected |
| Browser acceptance (real Chrome, headless, driven over the DevTools protocol; server with the LLM off, synthetic data) | **89/89 checks passed** at 390, 768, 1024, 1280, 1366, 1440 and 1920 px on all 6 pages: functional flows, Vietnamese labels with raw API codes kept in tooltips and "Mã kỹ thuật" lines, a scan for leftover English UI words, overflow / clipped or overlapping labels / wrapped status chips / tap targets / menu height budget (28% of the viewport) / content width on tablets, long questions, long support messages and long audiences, all 7 CSS modules answering `200 text/css`, imported in the documented cascade order, loaded, and each module's rules in effect (computed styles), a compact typography scale (every text size is one of 11/12/13/14/15/17/21/24/30 px; icons and fluid headings are measured separately), no JavaScript exceptions, console errors or failed requests (favicon included). Screenshots were inspected by eye. A **HEAD-vs-working-tree parity journey passes 17/17**: the text of all 6 pages after the same interactions and every API response are identical to the pre-refactor `main` (whitespace-insensitive). Defects found and fixed in this pass: status chips wrapping onto two lines (768, 1280, 1366, 1440 px), a 490 px-tall phone menu (now about 226 px), a cramped tablet layout (the sidebar now collapses at 900 px), half-pixel and 10 px font sizes. Three of my own measurement mistakes were also corrected rather than ignored (an unrealistic absolute menu-height limit, a regex lost in a template string, and a CSS-import check that read relative hrefs). **Not tested:** Firefox/Safari/Edge, real touch devices, accessibility tooling, and the UI with a real LLM enabled (Gemini output was never viewed in the browser) |
| Fresh clone check (before the UI polish pass) | `git clone` into a new folder: 199 passed, 8/8 acceptance, server and `/docs` answer HTTP 200 (existing venv; a Linux/CI run and Docker were not executed) |

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

## 4. Live (hosted) evaluation: one smoke run succeeded; the full evaluation has not run

Hosted Google Gemini free tier, synthetic data, key supplied by the owner through `run_gemini_live.ps1`. Five runs were needed: runs 1–2 (full mode) and run 3 (smoke) produced no answers; run 4 (smoke) produced correct RAG answers but its agent answer was rejected; run 5 (smoke, after the fixes) passed everything. Full details, per-case labels, tokens and latency caveats: [LIVE_EVALUATION_GEMINI.md](LIVE_EVALUATION_GEMINI.md).

**Result of the final run, run 5** (`gemini-3.5-flash-lite`, lexical retrieval, 7 requests, 0 texts embedded): 3 answerable questions answered correctly with citations (AI-reviewed; negated policy preserved; injected instruction in a poisoned record not repeated), 2 out-of-scope questions refused before any model call, and 1 tool-calling agent task that used `lookup_product` and `search_policy` and returned a cited answer that passed the evidence validator. One run, one small hand-written set.

**What the earlier attempts exposed** (all fixed, pinned by tests that use fake servers only):

| Observation | Cause and fix |
|---|---|
| Run 1 stopped after 4 requests: a 60-text embedding batch returned more than 3 MB of JSON | the adapter's 3 MB read cap; fixed with chunking and an explicit truncation error |
| Run 2 stopped after 9 requests with HTTP 429; AI Studio showed embedding RPM 96/100 and RPD 172/1K | quota is counted **per text**, not per request; fixed with a per-text rate limiter (60 texts/min, batches of 8 spaced 8 s), a text budget and an on-disk cache |
| That 429 was labelled "auth or billing" because its body said "check your plan and billing details" | classification now starts from the HTTP status; 429 is always rate/quota |
| Run 3: every generation failed with HTTP 404 "models/gemini-2.5-flash is no longer available" | the 2.5 models are closed to new projects (my configuration error); allowlist updated, default `gemini-3.5-flash-lite`, a 404 on generation stops the run |
| Run 4: the agent's final answer was rejected by our validator (the draft was not saved) | a false rejection: document IDs written in prose ("Sản phẩm PRD-101") counted as unsupported numbers, and grouped citations were not read; fixed generally, the last agent turn is text-only |

**Still no measurements of** hybrid retrieval with real embeddings, the 0.38 cosine threshold, faithfulness on a useful sample, agent reliability across tasks, campaign drafts from a real model, or any local model. The full mode (`--full`) has never run.

Tier note: Google offers no API to verify a key's billing status; the free-tier statement is the owner's attestation from the AI Studio page. The per-case labels were written by an AI, not an independent person.

## 5. Reproduce

```powershell
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m scripts.portfolio_check     # writes reports/offline_acceptance_report.json (git-ignored)
.venv\Scripts\python -m scripts.quality_eval --set dev            # also: near_miss, legacy, fresh
.venv\Scripts\python -m scripts.quality_eval --set dev --root <checkout of another commit> --label baseline
```

## 6. v4 quality evaluation (retrieval, offline; baseline commit 07a626f vs final)

**Method.** `scripts/quality_eval.py` measures four things separately: retrieval success (expected documents in the top 3), answer correctness (the extractive text contains facts taken from the documents), citation correctness (cited ids are returned ids), and unsupported answers (a source returned for a question the data cannot answer). A passing unit test is not used as a quality measure. All sets are synthetic and expectations come from `data/seed_documents.json` or the fresh files, never from system output. LLM and embeddings are off; every report records the commit, date, dataset hash and configuration.

**Three sets with different roles.** *Dev* (65 + 12 near-miss): used freely to find defects and calibrate. *Holdout* (33): written before any change, its SHA-256 committed first (`data/eval_v4/HOLDOUT.sha256`), never used to tune, opened once in the final session for both commits. *Fresh* (27 + lifecycle): new products and policies written **after** the freeze (git tag `freeze-v4`), imported only through `scripts.ingest` logic, no code knows them. The legacy sets (31, 33, 18, 12) were tuned on and are shown only to prove nothing regressed.

| Set | Metric | Baseline 07a626f | Final |
|---|---|---|---|
| Dev | Hit@3 | 26/52 | 39/52 |
| Dev | false abstention | 25/52 | 13/52 |
| Dev | unsupported leaks / near-miss leaks | 0/10, 1/12 | 0/10, 0/12 |
| Legacy (contaminated) | 31 pos, 33 neg, 18 pos, 12 neg | 31/31, 32/33, 18/18, 12/12 | identical |
| **Holdout** | Hit@3 (95% CI) | 12/25 (0.30-0.67) | **14/25 (0.37-0.73)** |
| Holdout | false abstention | 13/25 | **11/25** |
| Holdout | unanswerable questions answered wrongly | 2/8 | **0/8** |
| **Fresh** | Hit@3 (95% CI) | 10/19 (0.32-0.73) | **12/19 (0.41-0.81)** |
| Fresh | unanswerable questions answered wrongly | 3/8 | 1/8 |
| Fresh | update / replace-source / delete / index consistency | not supported | **7/7 pass** |
| All sets | latency p50 (15 documents, offline, not a benchmark) | ~8-10 ms | ~10-11 ms |

**Acceptance verdicts against the targets written before the work.** Holdout: no-diacritics + typo + discovery questions 7/9 (78%) with false abstention 44% against targets of 80% and 20%: **FAIL**. No more wrong answers than baseline (0 vs 2) and none on near-misses: PASS. Fresh: Hit@3 63% against 80%: **FAIL**; lifecycle: PASS. Nothing was tuned on holdout or fresh.

**Why it fails, from the failing cases.** (1) Need-based paraphrases with no shared words are 0/6 on the unseen sets. (2) Holdout paraphrases use words that are not in the documents ("kéo dài", "giao nhầm kiểu", "nhiều ngăn", "bị vỡ"). (3) Two typos fall outside the repair rules ("Fexl" is a rotation, "Thanh tóan ... hnagf" has an accent slip plus two edits). (4) Fresh data exposed an ingest-contract gap (a bare CSV price had no currency, so "dưới 1 triệu" could not compare it), a request frame ("đặc điểm gì") counted as a content word, and a generic-word false positive ("đổi màu sau khi mua" returned the delivery policy). (5) A missing attribute of an existing product ("màu hồng") still returns the product text. The first two defects of (4) were fixed after the session; they are **not** re-measured on clean data (see section 8).

## 7. Embedding experiment on dev data (hosted, free tier): negative result

`scripts/embedding_experiment.py`, run by the key owner through `run_gemini_live.ps1 -Task embedding-dev`: 151 synthetic texts (documents, their sentences, dev and near-miss questions; never the holdout), 19 requests, `gemini-embedding-001`; results are cached and were analysed offline. Findings: for 8/8 need-based dev questions the expected document ranked **first** of 15 (scores 0.66-0.76), so the embedding carries real signal; but the best score of questions the catalogue cannot answer is 0.61-0.82, overlapping the true matches, and part of that is questions about stock, offers or order data for a product that exists, which are semantically close to its document. After adding gate rules for those data classes (a general fix that also protects the lexical path) the best zero-leak, stable setting admitted 1/8 (12.5 points, below the 15-point rule written beforehand). A setting admitting 2/8 existed only because 0.708 (a near-miss) and 0.722 (a true match) could be split, a margin of 0.014 on 65 cases: not used. **Decision: hybrid stays off; similarity may only re-rank documents the gate has admitted.** This does not show embeddings are useless in general; it shows that on 15 documents and 65 questions no safe admission threshold can be calibrated.

## 8. What is verified and what is not

Verified here (offline, deterministic): everything in sections 1, 6 and 7 (the latter with real embeddings on dev data only); real Chrome 89/89 UI checks at 390-1920 px and 15/15 multi-turn checks; API shapes identical to main plus additive fields (`query_trace`, `turn_context`, `vector_missing`, `corpus_version`). **Not verified:** the quality of any LLM answer after the v4 changes (the only hosted run is the pre-v4 smoke test); embeddings on holdout or fresh data; Firefox/Safari/Edge, touch devices; more than 15 documents of realistic data; the two post-session fixes on clean data; any claim about production use.
