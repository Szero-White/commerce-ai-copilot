# Commerce AI Copilot — Kịch bản demo phỏng vấn (bản lưu riêng)

**Mục tiêu:** Demo 4 mô-đun với dữ liệu giả lập, trong khoảng 5–7 phút. Đây là **prototype AI Engineering**, không phải chatbot đảm bảo đúng 100% hoặc sản phẩm production.

## 0. Chuẩn bị trước buổi phỏng vấn

- Mở VS Code tại `D:\Commerce_AI_Copilot_v2_1`. Kiểm tra `git log -1 --oneline` để biết phiên bản đang dùng; đảm bảo đã lưu/push bản cần trình bày.
- Giữ file `runtime\lab.db` (SQLite chứa dữ liệu và chỉ mục); **không xóa thư mục `runtime`**, không chạy lệnh reset dữ liệu. File DB không tự được lưu lên GitHub nếu thuộc `.gitignore`.
- Nếu chạy trực tiếp Gemini online, xác nhận project Google AI Studio đang ở **Free Tier, không bật billing**, chỉ sử dụng dữ liệu giả lập. Trong PowerShell mới:

```powershell
cd D:\Commerce_AI_Copilot_v2_1
$env:LLM_PROVIDER='gemini'
$env:EMBEDDING_PROVIDER='gemini'
$secret = Read-Host 'Gemini API key' -AsSecureString
$env:GEMINI_API_KEY = [System.Net.NetworkCredential]::new('', $secret).Password
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- Mở `http://127.0.0.1:8000`, kiểm tra nhãn **LLM: Gemini · Vector + BM25**. Không cần chạy lại `index_embeddings` nếu file DB còn nguyên và tài liệu chưa thay đổi; nếu thiếu vectors, lập chỉ mục lại có thể phát sinh lượt gọi API.
- Không lưu/chụp màn hình API key, không đưa `.env`, DB riêng tư hay dữ liệu thật lên GitHub.
- Nếu không có mạng hoặc không có quyền dùng Gemini API, nói rõ chế độ offline chỉ là **tra cứu trích xuất**, không tự nhận đó là LLM online.

## 1. Trợ lý RAG — Gemini, truy hồi và dẫn nguồn (1,5–2 phút)

**Thao tác:** Menu trái → **Trợ lý RAG**. Bắt đầu phiên chat mới.

**Câu demo chính:**

> Tối nào cũng học khuya mà đèn trong phòng yếu quá, có gì hợp không?

**Kỳ vọng đã được kiểm thử tay ngày 27/10/2026:** Gợi ý **Đèn bàn Focus LED**, nguồn `[PRD-103]`, nêu được **ba mức sáng** và dẫn câu trích thật từ tài liệu. Không hứa rằng đèn đủ chiếu sáng cả phòng hoặc bảo vệ mắt.

**Câu hỏi trực tiếp:**

> Bàn Oak 120 kích thước bao nhiêu?

**Kỳ vọng:** 120 × 60 cm, cao 75 cm, dẫn `[PRD-101]`.

**Kiểm tra không bịa:**

> Đèn Focus LED có chống nước không?

**Kỳ vọng:** Không khẳng định chống nước khi tài liệu không có bằng chứng. Có thể trả lời thiếu thông tin.

**Giải thích:** Gemini Embedding + BM25 đề cử tài liệu; LLM tạo câu trả lời; code kiểm tra mã nguồn/trích dẫn, số liệu và một số loại cam kết. Trích dẫn **không bảo đảm mọi khẳng định đều đúng**.

## 2. Agent tra cứu — gọi công cụ (1 phút)

**Thao tác:** Menu trái → **Agent tra cứu**. Nhập:

> Hãy tìm thông tin bàn Oak 120, gồm kích thước, giá bán và chính sách bảo hành. Dẫn nguồn cho từng thông tin.

**Kỳ vọng đã kiểm thử tay:** Gọi `lookup_product` và `search_policy`; nêu 120 × 60 cm, cao 75 cm, giá **1.890.000 VNĐ**, thông tin bảo hành từ `POL-003`; hiển thị dấu vết công cụ. Agent chỉ đọc, không tự sửa dữ liệu hay đặt hàng.

## 3. Phân loại hỗ trợ — quy tắc nghiệp vụ (1 phút)

**Thao tác:** Menu trái → **Phân loại hỗ trợ**. Nhập:

> Tôi mua bàn Oak 120 nhưng nhận hàng bị trầy xước. Tôi muốn đổi sản phẩm và cần nhân viên hỗ trợ.

**Kỳ vọng đã kiểm thử tay sau khi sửa:** **Hàng hư hỏng / giao sai**, ưu tiên **Cao**, bộ phận **CSKH / xử lý khiếu nại**, chính sách `POL-002`, trạng thái `DRAFT_REQUIRES_HUMAN_REVIEW`. Không hứa đã đổi hàng/hoàn tiền.

**Nói rõ:** Mô-đun này dùng **rule-based classification**, không được giới thiệu là AI Agent.

## 4. Soạn nháp quảng cáo — LLM tạo nội dung có người duyệt (1 phút)

**Thao tác:** Menu trái → **Soạn nháp quảng cáo**.

- Chọn sản phẩm: **Đèn bàn Focus LED — DEMO-LAMP**.
- Nhóm khách hàng: **Sinh viên học tập buổi tối**.
- Nhấn **Tạo bản nháp nội dung**.

**Kỳ vọng đã kiểm thử tay:** Tiêu đề, nội dung nói đúng đặc điểm **ba mức sáng**, **USB-C 5V**, giá giả lập **390.000 VNĐ**; bản nháp cần người duyệt, không tự đăng quảng cáo. Kiểm tra nút **Sao chép nháp**.

## Khi nhà tuyển dụng hỏi về độ chính xác

> Em không cam kết 100%. Trong quá trình kiểm thử thực tế, em đã gặp lỗi truy hồi câu hỏi theo nhu cầu và lỗi bộ kiểm chứng nhầm số trong citation `[PRD-103]` với thông số sản phẩm. Em dùng log, vector cache và kết quả Gemini thật để xác định vị trí lỗi, sửa code và bổ sung regression tests. Hệ thống hiện là prototype có dẫn nguồn, giới hạn an toàn và cần đánh giá thêm trên dữ liệu mới trước khi dùng production.

## Cách lưu để không mất khi xóa chat ChatGPT

- Lưu chính file này tại `docs\INTERVIEW_DEMO_VI.md` trong repository, và commit tài liệu lên Git **sau khi rà soát thông tin**.
- Source code và tài liệu đã commit vẫn còn trong repo. **Lịch sử tin nhắn trong UI chat chỉ ở bộ nhớ trình duyệt, reload là bắt đầu lại**.
- Dữ liệu sản phẩm/chính sách nằm trong `runtime\lab.db`; hãy backup **khi server đã dừng**:

```powershell
Copy-Item .\runtime\lab.db "$HOME\Documents\commerce-ai-lab-backup.db"
```

- File backup SQLite là dữ liệu demo, không phải lịch sử hội thoại; API key chỉ nhập lại vào môi trường khi cần.
