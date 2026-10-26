# Giao việc cho Claude Code — chỉ dùng khi cần sửa thật trên máy

## TASK 1 — Chỉ AUDIT môi trường local và Ollama (không sửa code ngay)

```text
You are helping validate a Python/FastAPI e-commerce RAG portfolio project.
Read CLAUDE.md, README.md, app/ollama.py, app/retrieval.py, app/services.py, and the relevant tests ONLY.
First inspect Python version, installed Ollama availability, and selected model names; do not download models or install paid services without my approval.
Goal: verify an end-to-end local LLM and vector retrieval run using synthetic fixture data.
Do not change files yet. Return: prerequisites, exact commands to reproduce, model/RAM constraints, and a minimal test plan.
Clearly distinguish mocked integration tests from live model tests.
```

## TASK 2 — Sau khi có một lỗi cụ thể

```text
Bug report: [paste exact traceback, command, expected vs actual result].
Reproduce this issue using the smallest test possible. Inspect only directly related files.
Propose a 3-step fix and list files to change before editing.
Implement minimal changes without architectural rewrite, new frameworks, or UI changes.
Run focused pytest and then the full pytest suite. Report actual results and any test not runnable.
Never commit secrets or make the demo public.
```

## TASK 3 — Đánh giá RAG thật, không cố làm đẹp demo

```text
Improve real-model evaluation for our local RAG prototype using the existing data fixtures.
Focus ONLY on answer faithfulness and failure cases: unsupported claims, missing evidence,
wrong policy, out-of-scope questions, and prompt injection in source content.
Create reproducible test inputs with expected behavior and record actual outputs.
Do not claim any accuracy value without running the model and logging the dataset/model/version.
Ask before adding dependencies or calling paid APIs. Keep changes small and testable.
```

**Tiết kiệm quota:** dùng `/model` chọn model phù hợp; nếu phiên bị dài, dùng `/compact`; chuyển sang công việc khác dùng `/clear`; nếu dùng API key, kiểm tra `/cost` theo hướng dẫn chính thức. Bắt đầu với 1 task/1 phiên, không paste toàn bộ repo vào chat.
