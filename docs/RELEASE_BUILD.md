# Release build evidence — Commerce AI Copilot v2.1

Source release generated on 26 October 2026 from the user's previous v2.0 portfolio. New code and all tests in the archive can be independently inspected.

- `python -m pytest -q`: **37 passed**.
- `python -m scripts.portfolio_check`: **8/8 passed** on a disposable local SQLite database, with observed JSON report under `reports/offline_acceptance_report.json`.
- A fake local HTTP Ollama server is exercised by a regression test. This verifies request/response wiring; **NO actual model quality has been measured in this release**.
- Chromium UI interaction was tested with inline assets and API fixtures generated from the backend; RAG Chat, Support Triage, Campaign and Quality Lab displayed results with zero JS page errors. Network navigation to localhost from Chromium was blocked by the sandbox, so this browser test is NOT a real live-browser/backend integration test. The server's `/api/health` was separately reachable over localhost HTTP.
- Default mode is local retrieval, deterministic business rules and template drafts. No paid external AI APIs are required. Ollama is optional and restricted to localhost.

## What a human must still do

Download this ZIP to Windows, run `run_windows.bat`, run `verify_portfolio_windows.bat`, optionally configure local Ollama and run `start_live_ai_windows.bat`, audit its actual outputs with `python -m scripts.review_live_report`, and have Claude Code perform independent read-only audit from `docs/tasks/03_CLAUDE_V2_1_INDEPENDENT_AUDIT.md`.

## What is NOT verified

No actual LLM model inference in the build environment, no validated semantic vector benchmark, no real merchant integration, no measured company ROI and no public production deployment.
