# Phase log — branch feature/ai-quality-v4 (plan: PLAN V3)

Short, factual notes per phase so later phases do not re-derive them. Synthetic data only. Baseline start: HEAD 07a626f
on main, `pytest` 206 passed, `portfolio_check` all PASS (measured at the start of this branch).

## Phase 1 — root-cause trace: PASS
- Tool: `python -m scripts.trace_query "<question>"` (read-only, throw-away DB). Tests: `tests/test_query_trace.py`.
- Verified by trace (not assumed): `ban` is in `STOP` (`app/storage.py`). **"bàn" (desk), "bạn" (you) and "bán" (sell) all
  normalize to `ban`** and are dropped together.
  - "Có bàn gì?" -> every word is a stopword -> no terms -> search never runs -> `no_evidence` (class: no query).
  - "Có bàn nào vậy?" -> `vay` (filler "vậy") is the only term and matches nothing -> empty (class: filler word).
  - "Bàn Oak 120 kích thước bao nhiêu?" works only through `oak`, `120`, `kich`/`thuoc`; "bàn" contributes nothing.
  - "Bạn có bán ghế không?" works only through `ghe`.
- Desired behaviour is recorded as `xfail(strict=True)`; un-mark (do not edit) when Phase 3 lands.
