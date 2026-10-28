# Generalisation audit (synthetic data, offline)

Scope: why new questions, new wordings and new documents failed, and what was changed in general logic. No product, SKU,
number or question is hard-coded in `app/`. **Nothing here was verified with a live Gemini/Ollama model**; the offline checks
cannot show real model wording or real embedding quality.

## Root causes (each reproduced with `scripts/trace_query.py::trace_pipeline` on synthetic documents)
| # | Symptom | Cause (stage) | General change |
|---|---|---|---|
| RC1 | "chịu được 80 kg không?" → source found, "not enough evidence" | A correct answer repeats the customer's own figure (80). `evidence.answer_problems` and `verification.verify` reject every number absent from the source (answer stage) | The customer's figures are allowed in the answer **only** next to a comparison computed in code (`condition_status` limit_*). Fabricated figures are still rejected (tests) |
| RC2 | The source was flagged "số liệu KHÁC" and a question without a product name was refused | No limit semantics: "tối đa 45 kg" is a ceiling, not a contradicted number (gate stage) | `quantities.limit_results`: one stated limit of the same kind (max/min cues, closed language list) is compared in code; zero or several limits conclude nothing; "nặng 20 kg" (weight of a thing) is not a load; a document with no figure of that kind is rejected, not flagged |
| RC3 | "Kệ Linden có chịu nổi 45 kg không?" → no_evidence | The predicate words next to a weight/volume ("chịu nổi") were required to occur in the document, which says "tải trọng" (query stage) | Those words are searched but not required (`Analysis.soft`); names and title words are never softened |
| RC4 | After a policy, "điều kiện liên quan" jumped to another product's policy | Typo repair rewrote the ordinary word "liên" into the brand "Linden" (query stage) | A word typed with diacritics is never repaired towards a brand/model name; "liên quan" is a pointer, not a term |
| RC5 | "Còn phí vận chuyển thì sao?" left the previous topic | Elliptical follow-ups had no pointer, so retrieval ran over all documents (dialogue stage) | Pointers `topic`/`related` bind the follow-up to the documents about the **same named thing** as last turn (`Store.entity_scope`); no own words left → the documents just shown; different things shown or nothing shown → ask. A newly named thing switches topic |

### Second pass: failures seen with a live Gemini on an uploaded 16-page PDF (traced on a copy of the real DB)
| # | Symptom | Cause (stage) | General change |
|---|---|---|---|
| RC6 | "Có điều kiện gì không?" answered with another policy (WELCOME8) and a warranty | The question has no subject and was no pointer, so it ran over the whole corpus where "điều kiện" matched whichever document used the word (dialogue stage: `resolution=standalone`) | A question made only of generic aspect words ("điều kiện", "yêu cầu") is a `related` pointer: it follows the previous turn, or is asked back when nothing / two different things were shown |
| RC7 | "điều kiện liên quan" scope was the whole corpus (50 docs) | `entity_scope` took a label shared by most documents ("Demo") for a named thing | Names occurring in more than 25% of documents (min 3) are labels; with no named thing the follow-up stays on the documents just shown |
| RC8 | "Còn mã WELCOME8 thì sao?" would be stuck on the old topic | A topic pointer treated every remaining term as an aspect | A code (letters + digits) or an unknown name is a new subject and switches topic |
| RC9 | `llm_citation_rejected_extractive` for a correct answer on the right document | In the PDF the page header ("… KHÔNG PHẢI CHÍNH SÁCH THẬT …") ran into the body as one unpunctuated "sentence", and a negation anywhere in it ("không", or "chưa" in "nếu sản phẩm chưa sử dụng") made `'doi tra' is negated in the source` (answer stage) | Headers/footers repeated on ≥60% of pages (≥4 pages) are removed at ingestion (re-upload the file to apply); `•` separates items; a negation inside a conditional clause of a SOURCE sentence does not negate the policy. A policy that really is negated, and numbers not in the cited sources, are still rejected (tests) |

Also: "điều kiện" is searched but not required when the question has another content word; the response carries `answer_check`
(reason + a cut of the model reply) for LLM answers on the lexical path, so the next live rejection names its cause.
The exact Gemini text of the two live rejections was not available (not stored); RC9 is the reproduced cause that matches
`mode` + the reason string, not a confirmed reading of that exact reply. Not verified live after these changes.

Checked and **not** changed: chunking drops the product name from later chunks of a long file (shown on a synthetic spec sheet),
but retrieval still found the chunk and prefixing a heading would mis-attribute multi-product files. Recorded as a risk.

## Measures (never merged into one accuracy number)
`python -m scripts.generalization_eval` prints retrieval Hit@3, answer facts, groundedness (no wrong product/policy),
refusal/clarification and multi-turn separately, and writes passes **and** failures with `--out`.

Dev set `data/eval_generalization/dev.json` (SYNTHETIC; 10 capability groups incl. counter-examples; written after the
analysis, so it is a regression set, not independent evidence). Last run: retrieval 28/29, answer 18/19, groundedness 8/8,
refusal 8/8, multi-turn 12/12. The one failure is declared (`known_limit`): "tiêu thụ" vs "công suất" share no word, so BM25
cannot reach it; it needs embeddings (not verified). Old benchmarks unchanged: positives 31/31, negatives 32/33 (known case).

## Running an independent evaluation (do not show the cases to the coding agent)
1. Freeze: commit, then `git tag freeze-generalization-1`. Do not change code after looking at the results.
2. Copy the schema of `dev.json` to a file OUTSIDE the repo (e.g. `D:\holdout\mine.json`). Write **your own** synthetic documents
   (`documents`, optional `uploads`) and questions, with expectations per turn (`hit`, `hit_any`, `hit_prefix`, `contains`,
   `not_contains`, `forbid`, `refuse`, `clarify`). Use wordings and products you have never discussed with the agent.
3. Run: `python -m scripts.generalization_eval --cases D:\holdout\mine.json --out reports\generalization_blind_<date>.json`.
   The report keeps passing and failing turns, plus the commit hash you recorded in step 1.
4. If you then fix anything, that file is no longer independent: write a new one.
5. For real model behaviour run `scripts/live_eval.py` yourself with your key. An LLM judge may help with meaning, but it can
   share the model's blind spots and be lenient to fluent wrong answers: read a sample by hand.

Not claimed: production readiness, absolute accuracy, hallucination prevention (`evidence.py` is a pattern guard).
