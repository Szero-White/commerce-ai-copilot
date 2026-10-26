# JD NEXGEN BROS: trạng thái và kế hoạch ngắn hạn (26–31/10/2026)

> Quan trọng: website TopCV hiển thị hạn **31/10/2026** tại thời điểm kiểm tra, mặc dù bản JD người dùng sao chép từng ghi 06/11/2026. Ứng tuyển sớm, không chờ dự án hoàn hảo.

## Đã chạy và đã kiểm thử trong v1.1
- FastAPI, SQLite FTS5, document import TXT/MD/CSV (CLI), product & policy lookup, extractive retrieval demo, campaign template drafts, read-only agent disabled when LLM off.
- Optional Ollama integration for LLM chat, embeddings, hybrid RRF, tool calls. Contract paths covered by **mocks**; actual local models **NOT tested** here.
- Synthetic sample products including two POD products and a fictional personalized-return policy; no relation to the real company.
- Positive retrieval evaluation (13 cases) and no-match rejection evaluation (3 cases); metrics are **toy test metrics**. LLM factual accuracy remains unmeasured.
- Response with unknown or fabricated citation ID is downgraded to extractive text; citation ID checking is NOT proof of truth of each claim.
- `.github/workflows/ci.yml` prepared; workflow runs after push to GitHub, NOT yet verified via GitHub Actions.

## Chưa đạt đầy đủ JD
- End-to-end live LLM + embeddings from real model on a user's computer; source faithfulness/answer correctness grading.
- Real data ingestion beyond simple text/CSV, catalog updates, operational observability under load.
- Real Shopify/Meta/Google Ads API integrations (optional in JD); auth/rate-limits not ready for Internet.
- The repo has no meaningful sprint or team code-review history; can't claim professional work experience.

## Hợp tác hiệu quả: ChatGPT và Claude Code

| Công việc | Giao cho ai | Tại sao |
|---|---|---|
| Phân tích JD, chọn scope và acceptance criteria | ChatGPT | Tránh làm thừa tính năng |
| Viết test case, dataset, đánh giá kiến trúc, sửa lỗi cục bộ | ChatGPT | Có thể làm trực tiếp mà không mất phí Claude |
| Sửa lỗi sau khi người dùng chạy trên Windows (gửi log, không gửi khóa API) | ChatGPT trước | Chẩn đoán và đưa patch nhỏ |
| Debug môi trường local/Ollama, sửa code đa file sau khi có test fail thực | Claude Code **nếu có sẵn và thực sự cần** | Có thể duyệt, sửa, chạy local trong một phiên |
| Recheck diff/test/doc trước khi gửi CV | ChatGPT | Independent review |
| Bật Ollama/đưa project GitHub/cấu hình thật trên máy | Người dùng | Chỉ người dùng kiểm soát máy/tài khoản/dữ liệu |

## Ngày 26/10: ưu tiên
1. Bảo đảm ZIP chạy với `run_windows.bat` (LLM OFF) và truy vấn demo hoạt động.
2. Thử câu hỏi chính sách hàng cá nhân hóa bằng tiếng Anh.
3. Cài và chạy một LLM + embedding local **nếu máy chịu được**; nếu không, tìm môi trường khác (trường/lab/máy bạn bè) hoặc cân nhắc bản API có ngân sách trần. Không mua API trước khi cần.
4. Ghi rõ lúc nào là extractive và lúc nào là LLM mode trên video demo.

## Ngày 27–29/10: chứng minh AI thật
1. Test `LLM_PROVIDER=ollama`, `EMBEDDING_PROVIDER=ollama`, index embeddings bằng CLI, demo generative mode. Ghi lại model/version/RAM/latency.
2. Tạo thêm 15–20 câu hỏi tiếng Anh/Việt, bao gồm chính xác, mơ hồ, không có câu trả lời, prompt injection, sai giá/ưu đãi.
3. Chấm riêng retrieval Hit@k và answer faithfulness (bằng người đánh giá), công khai cả trường hợp FAIL.
4. Nếu trục trặc, dùng Claude Code cho **một bug tái hiện cụ thể**. Không yêu cầu viết lại toàn bộ app.

## Ngày 29–31/10: ứng tuyển
1. CV: ghi đúng phần đã chạy, liên kết GitHub, 1 video demo 2–3 phút (link có thể chia sẻ được).
2. Ưu tiên nộp trước 31/10, rồi mới bổ sung phần ít quan trọng như agent orchestration/Shopify API.
3. Chuẩn bị trả lời: chunking, BM25 vs vectors, RRF, citations vs groundedness, abstention, token use, tool whitelist, tradeoffs.

## Tiêu chí hoàn thành phiên bản phỏng vấn (không phải production)
- Trả lời ít nhất 5 câu hỏi thực tế từ tài liệu với LLM sinh câu trả lời + nguồn được đối chiếu thủ công.
- Từ chối các câu ngoài scope và mô tả ít nhất 1 failure case của model.
- Benchmark có máy/model/cỡ dữ liệu/test set, không công bố accuracy = 100% như cam kết thật.
- Không có private credentials/PII trong repository, không có đường tự động xuất bản ads.
