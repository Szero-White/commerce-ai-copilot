# AI Coding Playbook — dùng ChatGPT + Claude Code với chi phí/Token có kiểm soát

## Quy trình chia việc hợp lý

- **ChatGPT**: đọc JD, tạo yêu cầu sản phẩm, xác định scope/acceptance criteria, lập test cases, review thiết kế, tập phỏng vấn.
- **Claude Code**: thao tác trên repo và patch từng module, giải thích thay đổi, chạy tests/linter, tạo commit nhỏ (khi bạn đã review).
- **Người phát triển**: chịu trách nhiệm nghiệp vụ, data security, xem diff, chạy và xác minh bằng chứng, quyết định trade-off.

Không bắt hai agent tranh luận vô hạn để “cải thiện” code; mỗi yêu cầu phải có tiêu chí xong rõ ràng.

## Prompt ngắn, hiệu quả cho Claude Code

### 1. Khảo sát (không cho phép sửa)

> Đọc README.md, app/main.py, app/services.py, app/retrieval.py. Tóm tắt data flow từ POST /api/chat tới câu trả lời. KHÔNG sửa file. Liệt kê 3 rủi ro kỹ thuật lớn nhất kèm file/hàm và cách kiểm chứng. Viết ngắn dưới 400 từ.

### 2. Implement một chức năng có test

> Nhiệm vụ: thêm endpoint GET /api/documents/{id} chỉ trả về tài liệu công khai trong DB demo. Chỉ sửa app/main.py và tests/test_api.py. Có test id hợp lệ, 404, id bất thường; không sửa API đang có. Trước khi code đề xuất plan tối đa 5 dòng; sau đó patch tối thiểu và chạy `python -m pytest -q`. Báo kết quả thật, không đoán.

### 3. Fix bug không phá code cũ

> Reproduce lỗi từ test, xác định root cause, chỉ sửa phần cần thiết. Không làm refactor lớn. Sau sửa: chạy test liên quan và full test. Show unified diff, giải thích trade-off và còn rủi ro gì.

### 4. Review bảo mật

> Threat-model local FastAPI app giả định sẽ được deploy public. Không sửa code. Ưu tiên auth, prompt injection, PII, SSRF, rate limiting, vector poisoning. Phân nhóm Critical/High/Medium; đưa test chứng minh cho từng lỗ hổng. Không giả định code đang an toàn.

## Tiết kiệm token mà không giảm chất lượng

1. Gửi **mục tiêu + file liên quan + tiêu chí nghiệm thu**, không dán cả repository vào một prompt.
2. Giới hạn scope: 'chỉ sửa app/retrieval.py và tests/test_api.py' khi phù hợp.
3. Yêu cầu diff thay vì giải thích toàn bộ code hàng ngàn dòng.
4. Tạo test lỗi trước, AI sửa theo test, giảm vòng lặp suy đoán.
5. Đưa log lỗi nguyên văn 20–50 dòng liên quan, tránh ảnh màn hình không cần thiết.
6. Rõ ngân sách: tối đa N lời gọi LLM mỗi workflow, max output tokens, giới hạn context; đo lại chất lượng sau tối ưu.
7. Chốt trạng thái thành `docs/DECISIONS.md` ngắn, không lặp lại toàn bộ lịch sử chat.

## Không nên làm

- Không copy code mà không chạy test và tự đọc.
- Không gọi một bản template là 'AI Agent' độc lập.
- Không sử dụng dữ liệu thật của khách hàng khi chưa được phép.
- Không viết vào CV các benchmark không đo trên máy bạn.
- Không bật tự gửi quảng cáo/đơn hàng thật cho agent tự trị.
