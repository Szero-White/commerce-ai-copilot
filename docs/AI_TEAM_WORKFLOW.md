# Two ChatGPT Plus accounts + Claude Code: practical collaboration workflow

This repo does not need an expensive multi-agent orchestra. **One active coding agent per branch.** Multiple agents modifying the same files at the same time create conflicts and duplicate token usage.

| Phase | Owner | Deliverable | Stop criteria |
|---|---|---|---|
| Product/JD analysis, acceptance criteria, scope | ChatGPT | User stories, risks, testable outcomes | Clear spec |
| Code and offline tests in this chat | ChatGPT | Updated ZIP, passing pytest, change log | Reproducible test output |
| Local Ollama or machine-specific problems | Claude Code | Actual commands/results on the user's machine | Live evidence or precise blocker |
| Independent security/code review | Claude Code (read-only) or ChatGPT | Small issue list with test cases | No unverified accusations |
| Final application narrative | ChatGPT + human | Accurate CV, README, 2–3 min video | Can explain every bullet |

## Token discipline
1. Use Task 01/02 briefs rather than giving an open-ended “make the whole product professional” instruction.
2. Start Claude Code with `/plan`, then provide one task at a time. `CLAUDE.md` stores repo conventions.
3. Keep edits small: test failing case → one fix → focused tests → full tests → commit. Avoid unnecessary dependency/framework rewrites.
4. Use `/clear` between independent tasks and `/compact` only when continuing a long task.
5. Prove real model behavior with `python -m scripts.verify_live_rag`; screenshots/metrics should not be invented.
6. Git branches for isolation. Never let multiple agents change the same branch concurrently. Avoid unattended or unsafe permission bypass.
7. ChatGPT Plus/Codex and Claude Code subscription usage have their own limits; **API billing is distinct**. Always obtain approval before downloads, subscriptions or public cloud deployment.

## What NOT to outsource
The developer must be able to explain retrieval scores, model limitations, which modules use templates vs AI, SQLite transactions, security risks, source-check weakness, every demo output and actual measurement. Never claim industry work experience from a self-built portfolio.
