# Code quality and safe maintenance

This repository is a portfolio demo, not a production deployment. The rule for cosmetic refactors is **keep behavior unchanged and prove it with tests**.

## Structure

- `web/index.html`: six UI sections and their DOM IDs. Event bindings depend on these IDs and on the `data-page` / `data-to` attributes; do not rename them without a functional review.
- `web/app.js`: UI event handling and API calls (about 400 lines). Keep API paths, request/response contracts and the display-label tables stable. Do not split it into modules merely to shorten the file: that changes load order and global scope.
- `web/style.css`: the stylesheet entry point; it only `@import`s the web font and the modules in `web/styles/`, **in this order** (the cascade depends on it): `foundation` (tokens, shell, sidebar, topbar) → `overview` → `assistant` (panels, chips, chat) → `workflows` (forms, drafts, quality) → `responsive` → `agent-support` → `responsive-overrides`. The modules are not standalone.
- **Typography scale** (`foundation.css`): `--font-2xs … --font-3xl` = 11 / 12 / 13 / 14 / 15 / 17 / 21 / 24 / 30 px. Text uses these tokens; fluid display sizes (page `h1`, hero `h1`, score) use `clamp()`; glyph icons are sized individually. No half-pixel sizes, nothing below 11 px.
- **Responsive rules**: ≤1050 px single-column content; ≤900 px the sidebar collapses into a compact 3 × 2 header so tablets keep the full width; ≤700 px the menu items stack icon-over-label; ≤480 px only the routing grid changes. Status chips never wrap (`white-space: nowrap; flex: none`) and panel titles shrink instead (`min-width: 0`).
- `app/`: backend (storage, RAG, evidence validation, support triage, providers, read-only agent). Not touched by UI work.
- `tests/`: contract and safety regressions plus `test_frontend_assets.py`, which statically guards the CSS entry point and import order, the typography scale, chip wrapping, the absence of `!important` / `:has()` cascade hacks (apart from the `.hidden` utility) and the responsive breakpoints. `scripts/portfolio_check` checks offline portfolio behaviour.

A file with hundreds of lines is not inherently bad: cohesive modules, clear names, consistent indentation, short functions, and tests matter more than arbitrary line-count limits. Prioritize extracting actual responsibilities, not moving code merely to make files shorter.

## Safe editing workflow

1. Work on a branch separate from `main`; run `git status --short` first and keep one editor per branch.
2. Inspect `git diff --check` and `git diff --stat`. Confirm that backend code and API contracts were not changed by a cosmetic edit.
3. Run `node --check web/app.js`, `python -m pytest -q` and `python -m scripts.portfolio_check` (offline; no Gemini API).
4. Start the app on localhost with `LLM_PROVIDER=off` and `EMBEDDING_PROVIDER=off`. Check the UI in real Chrome at 390, 768, 1024, 1280, 1366, 1440 and 1920 px: every page, form and route; also long content; console and network, including each `/assets/styles/*.css` import.
5. Compare against the previous `main`: the text of each page after the same interactions and every API response must be identical unless the change is intentional.
6. Merge only after a human visual check and passing regressions. Never weaken a test to report PASS; if a measuring tool is wrong, fix the tool and say so.

The initial hosted Gemini smoke test is historical evidence of **one small run**, not a reliability claim. Changes here make no new live-Gemini claim.
