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

## Phase 4 — dynamic ingestion and consistency: PASS
- `Store`: new nullable `documents.source` column and `meta` table (both added by the existing ALTER/CREATE-IF-NOT-EXISTS
  migration; verified on the real `runtime/lab.db`, `scripts.check_index` -> ok). `apply()` imports a batch in ONE transaction
  (`replace=True` also drops documents of that source missing from the batch), `delete()`, `delete_source()`, `corpus_version()`
  (bumped in the same transaction as every change, stored in the DB so another process' import is seen by a running server),
  `consistency_report()` (missing / duplicate / stale / orphan text-index rows, unreadable or wrong-model or mixed-size
  vectors, legacy path-hash ids). `_init` now compares document ids with text-index ids (a count could not see one missing
  plus one orphan row). Vocabulary and token lists are cached per `corpus_version`.
- `_upsert`: identical text -> nothing changes and the vector stays valid (and a drifted index row is repaired); changed text
  -> vector removed with the row update, so a vector of old text can never be used for new text.
- `scripts/ingest.py`: ids from source name + SKU (or chunk number), not from the absolute path; source defaults to the file
  name; validation (headers, duplicate SKU, empty rows, UTF-8, size) happens before any write; flags `--source`,
  `--replace-source`, `--delete`, `--delete-source`, `--check`. `scripts/check_index.py` exits 1 on problems.
  `/api/health` gained `vector_missing` and `corpus_version` (additive).
- Where old data can still live and how it is covered: documents, text index, vectors (same row), embedding cache (keyed by
  sha256(model+text), cannot serve changed text), seed JSON (only loaded into an EMPTY database: editing it does not update an
  existing DB; use ingest), orphan chunks (`--replace-source`), moved files (path-independent ids). A pre-existing DB keeps its
  old path-hash ids as "legacy" until re-imported (reported by the check). BM25 is current right after commit; vectors only
  after `python -m scripts.index_embeddings` (not run here: calls an API). No `valid_until`: withdrawing = deleting.
- Not done on purpose: `doc_spans` table (arrives with the semantic work, Phase 7, if it is approved).
- Retrieval metrics unchanged from Phase 3 (dev Hit@3 35/52, leaks 0/10, near-miss leak 1/12, legacy identical). Full suite: 258 passed.

## Phase 5 — evidence gate and numeric constraints: PASS
- New `app/quantities.py`: numbers with units (VND/USD, cm, %, days/months, oz...), comparison conditions ("dưới 2 triệu",
  "cao hơn 70 cm", ranges), and `evaluate()` which returns yes / no / unknown **by comparing numbers found in the document
  text** (no embedding, no LLM). "unknown" = the document gives numbers of that kind but not clearly the attribute asked
  (USD price for a VND question; "120 x 60 cm" does not say which side is the width). No number of that kind at all = "no".
- New `app/gate.py`: `check_document` = the hard constraints every candidate must meet (unknown names / model codes, codes and
  numbers, quantity with unit family, stock figure, comparisons); `admit_semantic` + `SemanticParams` = when a document found
  only by meaning could be admitted (robust z-score over all documents, lead over the runner-up only for single-answer
  questions, group-membership and cap for list questions, a matching sentence required, hard constraints veto first).
  Defaults are UNCALIBRATED. Embedding score, z-score and sentence match are evidence of relevance, never of truth.
- `Store.fts_search` now calls the gate for every lexical candidate; products-only "catalogue" candidates also go through it
  (so "Có món nào dưới 500 nghìn không?" works with no content word). Documents whose comparison could not be confirmed are
  returned last, at most 2, flagged `condition_status: unverified`; confirmed ones are flagged `satisfied`; the extractive
  answer and the LLM context header say so. Trace gets `gate_rejected` {id: reason}.
- Unknown proper names (Capitalised inside the sentence, camelCase, or letter+digit model codes) must be matched; "Focus Pro",
  "Ghế Zephyr" return nothing. Known limitation: a capitalised place or brand the catalogue has never seen also makes a
  question unanswerable (conservative: false abstention, never a leak).
- "That one / nó / cái thứ hai" with only an attribute word left (`needs_referent`) no longer searches (it used to return every
  priced document); Phase 6 will resolve the pointer from the previous turn.
- `retrieval.search`: **fixed the unsafe path** where any document with cosine >= 0.38 entered the results without any check.
  Vectors now only re-rank documents the gate admitted. `admit_semantic` is NOT wired in: it needs sentence vectors, which do
  not exist until the semantic experiment (Phase 7, needs permission). Consequence: with embeddings on and no span vectors,
  hybrid mode can re-rank but not add documents; that is the safe default, and it is NOT evidence that semantic search works.
- Measured, dev (Phase 4 in parentheses): Hit@3 39/52 (35), false abstention 13 (17), numeric_condition 4/4 (0/4), leaks 0/10 (0),
  near-miss leaks 0/12 (1: the "Focus Pro" name case), legacy 31/31, 32/33, 18/18, 12/12 unchanged. Remaining failures are
  synonym_need 0/8 and a few paraphrases; they need meaning, not words.
- Full suite: 301 passed.

## Phase 6 — multi-turn on the real UI: PASS
- Memory is ONE step deep and lives in the client: `/api/chat` accepts an optional `turn_context {ids (<=5), kind}` and every
  response returns one. Nothing is stored server-side; no earlier text reaches a prompt. Ids are untrusted: each is looked up in
  the DB, unknown ones are ignored, content always comes from the DB. `app/dialogue.py` + `Store.analyze/fts_search(only=)`.
- Rules (never guess): "nó / cái này / sản phẩm đó / it" binds only when exactly ONE document was shown; "cái thứ hai / mẫu
  đầu tiên / cái cuối cùng" binds only to a list/clarification (order = sources panel; multi-result extractive answers are now
  numbered "1. [ID] ..."); anything else -> `mode=needs_clarification` with numbered options (answerable by an ordinal).
  A question that names its own subject (a word of a few product titles) ignores the context. A bound follow-up the document
  cannot answer says so, states which product it assumed, and keeps the subject. "thứ hai" alone (Monday) and "đơn đầu tiên"
  are not pointers (a classifier like "cái/mẫu/sản phẩm" is required).
- Subject detection uses PRODUCT titles only, rare words only (<= 30% of titles): policy titles ("Bảo hành") are topics, and
  repeated words ("giả lập", "demo") label the whole catalogue. Two accent collisions found and fixed on the way: giá/giả
  and cao/cáo (typed accents are compared with the raw title words).
- Frontend: ONLY `web/app.js` changed (+8/-1: a `lastTurnContext` variable sent and refreshed per question, reset on error,
  and one Vietnamese label for the new mode). `test_frontend_assets.py` now pins the sha256 of index.html, style.css, the 7 CSS
  modules and favicon, so a layout change fails the suite.
- Real Chrome (headless, CDP, server LLM off, fresh DB): 15/15 checks. Pronoun after one result; list -> "cái thứ hai";
  pronoun after a list asks back with numbered options and "cái đầu tiên" answers it; page reload forgets; own-subject
  questions ignore context; "Có bàn gì?" finds the desk; no overflow at 390 px; no JS errors / console errors / failed
  requests. Screenshots inspected by eye (1366 and 390). Not tested: other browsers, touch, LLM-on output.
- Limits: one previous turn only; no summary; no far references; the unaccented pronoun "no" is not recognised (only "nó");
  Agent / Support / Campaign are single-turn. Metrics unchanged (dev 39/52, leaks 0/10, near-miss 0/12, legacy identical).
- Full suite: 324 passed.

## Phase 7 — B1 embedding experiment: PREPARED, WAITING FOR THE OWNER TO RUN IT (status: NOT VERIFIED)
- Permission for B1 was given by the owner ("Cho phép B1"); no API call has been made by this agent, and none will be.
- `scripts/embedding_experiment.py` (offline-testable): embeds the 15 synthetic documents, their 60 sentences and the 77 DEV +
  near-miss questions = **151 texts, about 19 requests, about 2.5 minutes** at the adapter's 60 texts/min (slightly above the
  "about 130 texts / 17 requests" estimate given when asking; hard limits 180 texts / 30 requests). The locked holdout is not
  read. Modes: `--dry-run` (counts only), `--cache-only` (analyses vectors already cached, refuses to send anything), `--run`.
- Analysis on DEV: lexical alone vs lexical + `gate.admit_semantic` over a 9x9x3x3x2 grid; zero leaks on negatives and
  near-misses is the calibration target; picks the zero-leak point whose grid neighbours are also zero-leak (a plateau), best
  synonym/need recall, then most conservative; ablation of every gate clause; the pre-registered rule: hybrid may be enabled
  only if (a) synonym/need Hit@3 gain >= 15 points, (b) zero dev leaks, (c) every clause shows a measured effect, (d) <= 25
  requests. Result goes to `reports/b1_embedding_dev.json` (no key inside).
- Launcher: `run_gemini_live.ps1 -Task embedding-dev` (default task stays the smoke test): hidden key prompt, YES confirmation,
  `LLM_PROVIDER=off`, 30 requests / 180 texts hard limits, env restored in `finally`. Only its PowerShell syntax was checked
  (parser, nothing executed); the auto-mode classifier refused to run its `-SelfTest`, so please run
  `powershell -NoProfile -ExecutionPolicy Bypass -File .\run_gemini_live.ps1 -SelfTest -Task embedding-dev` yourself first.
- Tests (`tests/test_embedding_experiment.py`, 10): dry-run and cache-only never touch the network (the HTTP function is
  patched to explode), `--run` refuses without key + free-tier confirmation, texts are dev-only and within budget, and on an
  invented catalogue with invented vectors: meaning-only matches admitted, near-miss similarity refused by the thresholds, an
  unknown name refused by the hard constraint (ablation shows the veto matters), no configuration chosen when a negative looks
  exactly like a positive, every unmet condition of the decision rule reported. They prove the harness logic, not any model.
- Until the owner runs it: semantic retrieval = designed and unit-tested with synthetic vectors, **NOT VERIFIED** with real
  embeddings; hybrid stays OFF. Phases 8-11 that depend on the outcome (freeze, fresh data, final session) wait for it.
- Full suite: 334 passed.

### Phase 7 result — B1 was run by the owner (19 requests, 151 texts, no 429); analysed from the cache, no further API call
Status: **hybrid NOT enabled (pre-registered rule not met). Semantic retrieval: tested on dev only, negative result, NOT VERIFIED for use.**
- Diagnosis (cache only, `reports/b1_embedding_dev_run1.json` = analysis before the fix, `b1_embedding_dev.json` = after):
  1. The embedding itself works as a ranker: for all **8/8 synonym_need questions the expected document is rank 1 of 15** (scores
     0.656-0.761, runner-up lead 0.012-0.184).
  2. `(lexical + extra)[:k]` does NOT push semantic results out: with every threshold removed the expected document is returned
     first in 8/8 (lexical is empty for these questions, so there is nothing ahead of them).
  3. The hard gate does NOT block the positives: the expected document passes it in 8/8. It only blocks negatives (names, codes,
     numbers, stock): removing it adds 3 leaks, the only clause with a measured effect.
  4. Why zero hits were admitted: the absolute similarity of negatives overlaps the positives (best score of an unsupported
     question 0.608-0.816, median 0.716; of the expected document 0.567-0.855, median 0.727). Several negatives were questions
     about data the catalogue does not hold (promotion, stock/availability, order or phone data, refund requests) for a product
     that exists, so meaning-wise they are very close to its document.
- Real algorithmic gap found and fixed (general, in the gate, also protects the lexical path): "data classes" a catalogue of
  descriptions cannot answer unless a document states them. `stock` (now also "trong kho", "hàng mới về"), `offer` (needs a
  discount word with a figure next to it in the document), `private` (order status, phone/address of customers, refunds,
  cancellations: only policy/operations documents may answer). Language cues only, no product names. Unit tests:
  `tests/test_data_classes.py`. Lexical results unchanged (dev 39/52, leaks 0/10, near-miss 0/12, legacy identical).
- After the fix, over the grid (zero-leak and stable-plateau required): best = tau 0.70 / span 0.70 / z 4 / delta 0.03 / gap
  0.02 -> 42/52 hits, 0 leaks, synonym_need **1/8 (+12.5 points < the 15 required)**; rule unmet: (a) gain, and (c) no measured
  effect of tau/z/span/delta/gap on dev leaks (on dev the hard gate alone keeps the negatives out).
- NOT done on purpose: finer thresholds. A zero-leak point admitting 2/8 exists (e.g. similarity between 0.708 and 0.722) but the
  margin is 0.014 between a near-miss ("Có đèn bàn chạy bằng pin không?", 0.708) and a true match (0.722): that would be fitting
  noise in 65 cases. The plateau requirement exists to prevent exactly this. Meaning-only matches also cannot tell "the right
  product, but the attribute asked for is missing" from "the right product for this need": both look equally relevant.
- Practical conclusion: semantic ranking is useful (rank 1 in 8/8) but not as an admission rule. If it is ever used, the safe role
  is re-ranking already admitted documents, which `retrieval.search` already does when embeddings are enabled. Hybrid stays OFF
  by default; no B2 is needed. Phase 8-11 continue with the lexical system.
- Full suite: 350 passed.
