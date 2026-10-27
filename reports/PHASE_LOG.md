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
