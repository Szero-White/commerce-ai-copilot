# CV và cách nộp hồ sơ cho vị trí AI Engineer (LLM/RAG/AI Automation)

> Không sao chép nguyên bản vào CV nếu bạn chưa tự chạy, hiểu và giải thích được. Portfolio không thể biến thành kinh nghiệm làm việc chuyên môn 1+ năm.

## 1. Tiêu đề dự án phù hợp

**Commerce AI Lab – E-commerce RAG & AI Tool-Calling (Personal Portfolio)**

Nếu chỉ chạy chế độ mặc định, đổi tên thành **Commerce Knowledge Retrieval & Marketing Automation Demo**. Đừng ghi “AI Agent”, “vector RAG” nếu chưa thật sự bật model và kiểm chứng.

## 2. CV bullets – khi chỉ chạy bản mặc định

- Phát triển demo ứng dụng hỗ trợ nghiệp vụ e-commerce bằng **Python, FastAPI, SQLite**, cung cấp REST API truy vấn thông tin sản phẩm, chính sách bán hàng và tạo bản nháp nội dung quảng cáo.
- Xây dựng pipeline **lexical retrieval (SQLite FTS5/BM25)**, hiển thị tài liệu tham chiếu và từ chối các câu hỏi thiếu bằng chứng.
- Thiết lập bộ **retrieval evaluation Hit@3** với dữ liệu giả lập, theo dõi token estimate và API latency; viết kiểm thử tự động với pytest.
- Tổ chức mã nguồn thành API, storage, retrieval và business services; xây dashboard phục vụ demo và tài liệu hướng dẫn chạy trên Windows/Docker.

## 3. CV bullets – chỉ khi đã chạy Ollama LLM và embeddings

- Tích hợp **Ollama `/api/chat` và `/api/embed`** cho generative RAG, cosine vector retrieval kết hợp BM25 thông qua Reciprocal Rank Fusion, giới hạn context và output tokens.
- Xây dựng bounded **read-only tool-calling agent** với hai công cụ `lookup_product` và `search_policy`, tool whitelist và giới hạn số vòng gọi để tránh hành động không được phép.
- Đánh giá truy xuất theo bộ Hit@3 tự xây, báo cáo kết quả và thảo luận trade-off giữa retrieval accuracy, token budget, latency và bảo mật trước prompt injection.

Không viết “đạt accuracy 100%” hoặc “tối ưu 80% chi phí” khi không có tập đánh giá và cách đo phù hợp. Nếu bộ mẫu 10 câu đạt 10/10, có thể ghi “10/10 retrieval cases on synthetic dataset”, nhưng tốt nhất để kết quả trong README và nói giới hạn khi phỏng vấn.

## 4. Lời giới thiệu 35 giây khi phỏng vấn

“Em xây một ứng dụng mô phỏng bài toán AI trong e-commerce: nhân viên muốn tra cứu thông số sản phẩm và chính sách mà không phải tìm thủ công, còn marketing cần bản nháp nội dung từ dữ liệu đã có. Em dùng FastAPI, SQLite FTS5 cho retrieval và tạo ứng dụng demo có đánh giá Hit@3. Em có thêm adapter cho Ollama để chạy mô hình local và tool-calling read-only, đồng thời có đo token/độ trễ. Em biết rõ hạn chế của demo, nhất là về factuality, authentication và production integration. Em muốn áp dụng những kỹ năng này vào bài toán thật dưới sự hướng dẫn của team.”

Nếu chưa thực sự bật Ollama, nói “Em đã thiết kế adapter tùy chọn” thay vì “Em đã chạy mô hình”.

## 5. Những câu hỏi cần hỏi nhà tuyển dụng

1. Với tiêu chí 1+ năm, công ty có xem xét ứng viên mới ra trường có portfolio chạy được không?
2. Team đang dùng nền tảng LLM/embedding/vector database nào? Có người review code và hướng dẫn junior không?
3. Workflow AI cụ thể đang cần là FAQ chatbot, tạo ad copy, phân tích chiến dịch hay đồng bộ platform APIs?
4. Công ty đánh giá chất lượng RAG bằng benchmark nào, có dữ liệu kiểm thử và chính sách bảo vệ dữ liệu khách hàng không?
5. Quy định thử việc, BHXH/BHYT/BHTN, lịch thứ bảy cách tuần và tiêu chí tăng lương được ghi thế nào trong hợp đồng?

## 6. Lời nhắc quan trọng

NEXGEN BROS tuyển **1** vị trí và JD yêu cầu **1+ năm kinh nghiệm**. Gửi CV sát JD cùng GitHub và video demo **sớm**, không chờ học hết 6–12 tháng. Nếu bị từ chối, repo này vẫn dùng ứng tuyển các vị trí AI Application Engineer, AI Automation/Integration Developer và Python Backend Junior phù hợp hơn.
