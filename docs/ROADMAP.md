# Roadmap 12 ngày để sẵn sàng nộp hồ sơ trước hạn (06/11/2026)

> Ngày hiện tại 25/10/2026; hạn tin 06/11/2026. **Nộp hồ sơ sớm ngay khi có bản demo ổn, không chờ học xong**. Nhà tuyển dụng yêu cầu 1+ năm kinh nghiệm; hồ sơ cá nhân không thể biến thành 1 năm kinh nghiệm đi làm. Có thể nộp với portfolio rõ ràng và trình bày minh bạch.

| Ngày | Việc cần làm | Bằng chứng |
|---|---|---|
| 1 | Run Windows demo, đọc README, hiểu 3 page | Ảnh chụp giao diện và Swagger |
| 2 | Đọc main.py, theo dấu luồng request/response | Sơ đồ API viết lại bằng lời mình |
| 3 | Hiểu SQLite FTS5, điều chỉnh STOP words | Test retrieval mới |
| 4 | Dùng `scripts/ingest.py` import 1 file CSV khác | Source mới xuất hiện ở UI |
| 5 | Xem cases lỗi Hit@3 và cải thiện ranking | Test đánh giá trước/sau |
| 6 | Giải thích prompt, giới hạn context, phản hồi thiếu bằng chứng | Tài liệu 1 trang |
| 7 | Thử Ollama model nhỏ nếu RAM cho phép | Video LLM thật hoặc ghi rõ không chạy được |
| 8 | Bật embeddings, chạy script index nếu máy đủ RAM | /api/health có vector_indexed > 0 |
| 9 | Viết thêm 5 eval cases từ tài liệu mẫu | Báo cáo retrieval Hit@3 |
| 10 | Tạo nháp campaign, kiểm tra tính trung thực | Draft + kiểm duyệt |
| 11 | Run pytest, sửa vấn đề phát hiện | Screenshot pytest pass |
| 12 | Soạn README tiếng Anh ngắn + quay demo 3 phút | Link video |
| 1–3 (song song) | Soạn CV sát JD, không claim kinh nghiệm không có; nộp trước hạn | CV PDF, GitHub clean |
| 7–12 (song song) | Mock interview Python/RAG/API bằng tiếng Anh cơ bản | Danh sách câu hỏi yếu |

Sau đợt ứng tuyển, nâng production-readiness theo thứ tự: auth → tracing/logging → quality eval/faithfulness → async worker → pgvector → Meta/Google Ads sandbox; các bước này chưa có trong bản demo.
