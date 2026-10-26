# Chuẩn bị phỏng vấn AI Engineer – không học thuộc dự án do AI tạo

## 10 câu hỏi nhà tuyển dụng có thể hỏi

1. **RAG là gì?** Chỉ ra 4 bước: ingestion -> retrieval -> context assembly -> generation. Chỉ rõ mặc định của demo chưa có generation.
2. **Vì sao dùng BM25 và vector search cùng lúc?** Keyword mạnh về SKU/tên chính xác; embeddings hữu ích câu hỏi khác từ nhưng cùng nghĩa; RRF hợp nhất thứ hạng.
3. **Embedding tạo từ đâu?** Trong demo dùng Ollama `/api/embed`, optional model `bge-m3` đã tải thủ công; không có vector khi chưa bật.
4. **Hit@3 đo gì?** Tài liệu được gắn nhãn kỳ vọng nằm trong 3 kết quả đầu, không đo câu trả lời LLM đúng hay sai.
5. **Nếu bot bịa chính sách giảm giá?** Không cho giao dịch, chỉ lấy nguồn, giới hạn context, kiểm thử câu không đủ dữ liệu; production cần post-generation grounding checks và human escalation.
6. **Tại sao không dùng LangChain/LangGraph?** Scope nhỏ, pipeline tuyến tính, API adapter tự viết để nhìn rõ luồng và phụ thuộc. Dùng LangGraph khi workflow có nhiều trạng thái, nhánh, tool và kiểm soát rollback.
7. **Token optimization ở đâu?** Top-k retrieval, giới hạn context 2600 ký tự, output 256 token, không loop, đo metadata provider. Trade-off: rút context quá tay khiến mất bằng chứng.
8. **Dự án này có phải AI agent?** Mặc định không; có API tool-calling agent tùy chọn khi bật Ollama có model hỗ trợ tool calls. Agent chỉ chọn 2 read-only tools trong whitelist, không phải autonomous production agent; không có LangGraph hay persistence cho agent state.
9. **Thêm Shopify/Meta Ads thế nào?** OAuth + scopes tối thiểu, webhook xác minh chữ ký, queue async, idempotency, audit logs, sandbox, human approval, rate limiting.
10. **Triển khai production thế nào?** Postgres/pgvector, queue, worker, secret manager, auth/RBAC, observability, red-team, evaluation, cost budgets và CI/CD; không dùng SQLite local demo làm production ngay.

## Một bài coding interview 60–90 phút để tự thực hành

Thêm API `POST /api/feedback` lưu (question_id, helpful:boolean, issue_type) đã validate và không ghi PII. Có migration SQLite, test input sai, test race condition khi hai request cập nhật đồng thời. Sau đó giải thích vì sao những thông tin feedback không đồng nghĩa với factual accuracy.

## Tiêu chuẩn chỉ được đưa vào CV khi hoàn thành

- Chạy được trên máy khác bằng README, không nhờ AI giải thích thay.
- Tự sửa một bug backend nhỏ trong tối đa 45 phút.
- Phân biệt prompt injection, hallucination, relevancy và answer faithfulness.
- Nói rõ trade-off cost vs latency vs accuracy và giới hạn demo.
- Có link code + demo 2–3 phút và script khởi chạy, không tự nhận đã có khách hàng thật.
