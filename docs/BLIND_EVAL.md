# Blind evaluation: scoring the system on data you wrote

`scripts/blind_eval.py` scores the system on documents and questions **supplied by an evaluator**. It never creates a question or an expected answer, runs on a throw-away database (nothing in `runtime/` is touched), with LLM and embeddings off and no network.

```powershell
python -m scripts.blind_eval --docs products.csv policies.md --category policy --questions questions.csv
python -m scripts.blind_eval --docs ... --questions ... --validate-only     # check the files, evaluate nothing
```

## 1. Documents (`--docs`, one or more files)
- `.csv`: columns `sku,name,description[,price,category]` (a bare price is read as VND).
- `.md` / `.txt`: chunked like `scripts.ingest`; `--category policy` sets their category.
- `.json`: a list of `{"id","title","category","content"}`.
- `--with-seed` also keeps the built-in synthetic seed documents (default: only your files).

## 2. Questions (`--questions`, `.json` or `.csv`; you write the expectations)
| Field | Meaning |
|---|---|
| `id`, `question` | required |
| `type` | `hit` (the documents answer it), `none` (they cannot), `none_or_clarify` (ambiguous: no source, or a question back) |
| `ids` | for `hit`: expected documents. `@SKU` = the CSV row with that sku; `@policy:<file name without extension>:<n>` = the n-th chunk of a .md/.txt file; or a plain id from a .json file |
| `min` | how many of `ids` must be returned (default 1) |
| `exclude` | documents that must **not** be returned |
| `must_contain` / `must_not_contain` | text the answer must / must not contain (facts you took from your documents) |
| `allow` | for `none`: documents that may still be returned (e.g. a policy that explains why not) |
| `group`, `tag` | free grouping label; `tag: llm_rubric` marks a case that needs a human to read the answer |

CSV questions use the same column names; list fields use `|` between items (`ids` = `@A-1|@B-2`).

Example (JSON): `{"cases":[{"id":"Q1","question":"Ghế X7 bảo hành bao lâu?","type":"hit","ids":["@AERO-X7"],"must_contain":["24 tháng"]},{"id":"Q2","question":"Ghế X9 có tựa đầu không?","type":"none"}]}`

Files that are unusable (unknown type, `hit` without `ids`, duplicate id, an `@SKU` that is not in `--docs`) are refused before anything is scored.

## 3. Results (`--out-dir`, default `reports/blind_eval/`)
`results.csv` and `results.jsonl` (one row per question) and `summary.json`. Per question: `source_found`, `answer_correct` (only where you gave `must_contain` / `must_not_contain`), `refused_correctly` (for `none` cases), `abstained`, the returned ids, the answer text, and `flags` (hallucination risks): a source returned for a question you marked unanswerable, an excluded document returned, forbidden text in the answer, an answer that fails the evidence check (ids, numbers, promises).

## 4. What the numbers mean
The run is offline, so the answer is quoted document text: `answer_correct` checks the facts you listed, not language quality, and an LLM answer needs a human rubric (see `tag`). Use a **new** set for each measurement: once the system has been changed because of a set's failures, that set is no longer blind. Keep question and expectation authorship separate from whoever changes the code.
