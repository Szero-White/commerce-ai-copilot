# Phase log — branch feature/ai-quality-v4 (plan: PLAN V3)

Short, factual notes per phase so later phases do not re-derive them. Synthetic data only. Baseline start: HEAD 07a626f
on main, `pytest` 206 passed, `portfolio_check` all PASS (measured at the start of this branch).
Editing note: append with the Edit tool (UTF-8); PowerShell `Add-Content` mangles Vietnamese text.

## Phase 1 — root-cause trace: PASS
- Tool: `python -m scripts.trace_query "<question>"` (read-only, throw-away DB). Tests: `tests/test_query_trace.py`.
- Verified by trace (not assumed): `ban` is in `STOP` (`app/storage.py`). **"bàn" (desk), "bạn" (you) and "bán" (sell) all
  normalize to `ban`** and are dropped together.
  - "Có bàn gì?" -> every word is a stopword -> no terms -> search never runs -> `no_evidence` (class: no query).
  - "Có bàn nào vậy?" -> `vay` (filler "vậy") is the only term and matches nothing -> empty (class: filler word).
  - "Bàn Oak 120 kích thước bao nhiêu?" works only through `oak`, `120`, `kich`/`thuoc`; "bàn" contributes nothing.
  - "Bạn có bán ghế không?" works only through `ghe`.
- Desired behaviour is recorded as `xfail(strict=True)`; un-mark (do not edit) when Phase 3 lands.

## Phase 2 — datasets, harness, baseline: PASS
- Commit 2327566 (2a) locks `data/eval_v4/holdout.json` (33 cases, SHA-256 in `HOLDOUT.sha256`, `.gitattributes` keeps bytes
  stable). The holdout has **not been run or inspected** since it was written; `quality_eval --set holdout` refuses without `--final`.
- `scripts/quality_eval.py` (offline, LLM and embeddings off, temp DB, `--root` evaluates another checkout's code):
  dev = 65 cases (`data/eval_v4/dev.json`), near-miss = 12 (`near_miss.json`), legacy = old sets re-measured.
- **Baseline (app code unchanged since 07a626f), `reports/baseline_{dev,near_miss,legacy}.json`:**
  - legacy: dev positives 31/31, dev negatives 32/33 (known miss "Địa chỉ cửa hàng ở đâu?"), old held-out 18/18 and 12/12
    (contaminated). Matches the figures in docs/EVALUATION_REPORT.md.
  - dev (52 positives): Hit@3 26/52 = 0.50 (CI 0.37-0.63); **false abstention 25/52 = 0.48**; wrong-source-only 0/52;
    must_contain answer check 6/8; citation 26/26 of hits; unsupported leaks 0/10; clarify-or-abstain 3/3 (abstains, never asks).
  - groups failing most: discovery 1/7, synonym_need 0/8, numeric_condition 0/4, plus single misses in paraphrase/typo/policy.
  - near-miss: 1/12 leak (NM03 "Đèn bàn Focus Pro ..." returns PRD-103).
  - latency p50 ~8 ms, p95 ~10-13 ms (offline, 15 documents; not a benchmark).
- The harness tests (`tests/test_quality_eval.py`) check set integrity, that holdout matches its hash, and the scoring rules.
- Full suite at this point: 220 passed, 2 xfailed (the two strict xfails from Phase 1).

## Phase 3 — query analyzer (lexical): PASS
- New `app/query.py` (word roles from the indexed documents, typo repair, intents); `storage.fts_search` uses it
  (`trace=` optional dict; `services.question_answer` adds `query_trace`, an additive response field). Phase 1 xfail markers
  were removed (the defect is fixed) and the old diagnosis tests rewritten as regressions.
- Design as built:
  - `FUNCTION_FORMS`: for function words that collide with content words after folding, the readings that ARE function
    words ("ban" -> bạn, bán). Typed with other diacritics ("bàn", "da" vs "đã", "máy" vs "mấy") = content. Typed plain =
    ambiguous: "soft" (searched, not required) when the documents mostly use another reading, promoted to required when
    nothing else is left, otherwise dropped. Corpus counts decide (so "co" stays "có" even though "cố" occurs once).
  - Typo repair against the document vocabulary only: transposition at any length >= 3; insert/delete/adjacent-key slip only
    for words >= 6 letters; unique nearest word only; <= 2 repairs per query; known domain words never repaired. First
    version allowed any substitution and turned "khuyến" into "chuyen" and "vàng" into "van": rejected by tests.
  - Stock questions ("còn hàng", "tồn kho", "stock") need a document that states a number next to a stock word (U01 leaked
    when "bàn" started to count). "available" is deliberately not a stock cue (a legacy positive asks "which sizes are
    available").
  - Catalogue questions with no content word ("xem các sản phẩm") list product documents; discovery questions rank
    documents whose title names the thing first.
- Measured (dev, same harness; baseline in parentheses): Hit@3 35/52 (26), false abstention 17/52 (25), unsupported leaks 0/10 (0),
  near-miss leaks 1/12 (1, NM03 "Focus Pro" unchanged), legacy 31/31, 32/33, old held-out 18/18 and 12/12 (all unchanged).
  Remaining dev failures are synonym_need 0/8 (needs meaning, not words), numeric_condition 0/4 (Phase 5), a few paraphrases
  ("chế độ sáng", "nâng lên hạ xuống") and "áo hoodie". Not solved on purpose: no synonym list was grown from the failures.
- Caveat: dev and holdout were written by the same author; the holdout was not run. Full suite: 235 passed.
