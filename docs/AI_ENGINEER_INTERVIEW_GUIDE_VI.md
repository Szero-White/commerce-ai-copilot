# Hướng dẫn phỏng vấn AI Engineer — Commerce AI Copilot (bản v4)

> Dự án cá nhân, dữ liệu 100% giả lập, **không phải sản phẩm của NEXGEN BROS hay của bất kỳ doanh nghiệp nào, không phải production**. Mọi con số dưới đây lấy từ `reports/*.json` và `reports/PHASE_LOG.md`; nếu không có trong đó thì không được nói. Không nói "đã có kinh nghiệm sản xuất".

## 1. Bài toán kinh doanh
Một trợ lý trả lời câu hỏi của khách về sản phẩm nội thất, chính sách và quy trình **chỉ dựa trên tài liệu được cấp**, có dẫn nguồn, biết từ chối khi thiếu bằng chứng, và nhận kiến thức mới (sản phẩm/chính sách) mà không phải sửa code. Rủi ro thật của loại sản phẩm này: trả lời sai giá/tồn kho/khuyến mãi, bịa thuộc tính, lộ dữ liệu đơn hàng, "từ chối nhầm" khiến khách bỏ đi.

## 2. Kiến trúc
```
Câu hỏi → dialogue (giải "nó/cái thứ hai") → query (đọc câu hỏi bằng từ vựng của chính tài liệu)
        → BM25/FTS5 → gate (ràng buộc cứng) → xếp hạng → trích xuất có dẫn nguồn  |  LLM + evidence.py kiểm tra
```
`app/query.py`, `quantities.py`, `gate.py`, `dialogue.py`, `storage.py`, `retrieval.py`, `services.py`, `evidence.py`, `gemini.py`/`ollama.py`. Mặc định **LLM tắt, embedding tắt**: câu trả lời là *retrieval* (trích đoạn), không phải generative RAG.

## 3. Dữ liệu đi vào hệ thống thế nào
`scripts/ingest.py`: CSV (`sku,name,description[,price,category]`) hoặc MD/TXT (cắt đoạn ≤800 ký tự). Cả file chạy trong **một transaction** (lỗi → không ghi gì); id sinh từ *tên nguồn + SKU* (không phụ thuộc đường dẫn); giá chỉ có số được hiểu là VND. `--replace-source`, `--delete`, `--delete-source`, `scripts/check_index.py`. **Không có đồng bộ real-time**; dữ liệu vào bằng CLI.

## 4. Parsing, indexing, BM25, embedding, hybrid
SQLite FTS5 với văn bản đã bỏ dấu (`normalize`), BM25 để xếp hạng. Embedding (`gemini-embedding-001`) chỉ được thử trên dev: **tài liệu đúng đứng hạng 1 ở 8/8 câu "theo nhu cầu"**, nhưng không có ngưỡng nào đủ an toàn để *nhận* tài liệu chỉ nhờ độ tương đồng. Hybrid **tắt**; nếu bật, vector chỉ xếp lại những tài liệu gate đã nhận.

## 5. RAG pipeline
Truy hồi → gate → (LLM nếu bật) → `evidence.valid_cited_answer` (ID trích dẫn, số liệu, cam kết, phủ định) → câu trả lời hoặc hạ cấp có nhãn (`llm_citation_rejected_extractive`, `no_evidence`, …). Mỗi nhánh hạ cấp có `mode` riêng để không nhầm "LLM tắt" với "LLM lỗi".

## 6. Chuẩn hóa câu hỏi và lỗi chính tả
Bỏ dấu làm "bàn" (cái bàn), "bạn" (you), "bán" (sell) cùng thành `ban`. Quy tắc: gõ **có dấu** thì dạng gõ quyết định (bạn/bán = từ chức năng; bàn = nội dung); gõ **không dấu** thì "mềm": vẫn tìm nhưng không bắt buộc, trừ khi tài liệu thật sự dùng từ đó (đếm tần suất trong corpus). Sửa lỗi gõ chỉ trên từ **chưa từng thấy** trong từ vựng: hoán vị 2 ký tự, hoặc trượt tay sang phím kề; từ ≥6 ký tự mới cho phép thêm/bớt; chỉ khi có đúng một từ gần nhất; tối đa 2 lần/câu. Bản đầu cho phép thay ký tự tùy ý và biến "khuyến mãi" thành "chuyển khoản": bị test chặn, đã bỏ.

## 7. Vì sao chọn kiến trúc này
Với 15 tài liệu và lỗi quan sát được (từ khóa bị bỏ sai), BM25 + chuẩn hóa tốt là giải pháp rẻ nhất; embedding đã được **đo** rồi mới quyết định (kết quả âm tính). Không dùng LangChain/vector DB vì chưa có bằng chứng cần và chúng che đi đúng phần cần kiểm thử.

## 8. Ngưỡng liên quan và "từ chối nhầm"
Gate từ vựng: tỉ lệ từ khóa (trọng số IDF) có trong tài liệu ≥ 0,6, các từ khớp phải nằm trong 8 token. Nguyên nhân từ chối nhầm trên dev: từ chức năng/đồng âm, từ đệm ("vậy"), câu "có bàn gì?", lỗi gõ, câu hỏi liệt kê. Không hạ ngưỡng toàn cục: sửa từng nguyên nhân. Còn lại: câu khác từ vựng hoàn toàn (nhu cầu, đồng nghĩa) — BM25 không với tới.

## 9. Grounding và trích dẫn
Trích dẫn là ID tài liệu; `evidence.py` kiểm tra ID, số liệu có trong nguồn được trích, cam kết có câu khẳng định trong nguồn, và không khẳng định điều nguồn phủ định. **Đây là kiểm tra mẫu theo câu, không phải chống bịa tổng quát.**

## 10. Ngữ cảnh LLM và prompt
Tài liệu được đóng gói tối đa `MAX_CONTEXT_CHARS` mà không cắt giữa ID; prompt coi tài liệu là dữ liệu không đáng tin; `num_ctx` tường minh cho Ollama; phản hồi báo mức dùng cửa sổ ngữ cảnh. Với câu hỏi nối tiếp, prompt chỉ thêm "(nói về tài liệu [ID] của lượt trước)", **không** đưa văn bản lịch sử của client vào.

## 11. Chống hallucination (nói đúng mức)
Ba lớp, đều có giới hạn: (1) **gate** quyết định *tài liệu nào được dùng*: tên/mã lạ, số và đơn vị, tồn kho, khuyến mãi, dữ liệu đơn hàng, so sánh giá/kích thước tính bằng code; (2) trích xuất nguyên văn khi LLM tắt; (3) `evidence.py` cho câu LLM. Điểm tương đồng embedding và "câu khớp" chỉ là bằng chứng về **mức liên quan**, không phải bằng chứng một khẳng định đúng.

## 12. Agent và tool calling
2 công cụ chỉ-đọc (`lookup_product`, `search_policy`), tối đa 3 lượt, công cụ lạ → chặn, câu trả lời cuối phải trích tài liệu mà công cụ thật sự trả về. Một lần chạy thật trên Gemini (trước v4). Không tuyên bố độ tin cậy.

## 13. Thêm / sửa / xóa dữ liệu
Xem mục 3. Điểm cần nói được: *thông tin cũ có thể nằm ở đâu* (documents, chỉ mục văn bản, vector cùng dòng, cache embedding khóa theo sha256(model+text), seed JSON chỉ nạp vào DB rỗng, chunk mồ côi, file di chuyển) và cách mỗi chỗ được xử lý; `corpus_version` nằm trong DB để tiến trình đang chạy nhận ra import từ tiến trình khác; vector **chưa** tự cập nhật.

## 14. Đánh giá và số đo thật
`scripts/quality_eval.py`, 4 thước đo tách biệt (truy hồi, đúng sự kiện, dẫn nguồn, trả lời sai câu không thể trả lời). Ba tập: **dev** (được dùng để chỉnh), **holdout** (khóa bằng SHA-256 trước khi đổi code, chạy một lần), **fresh** (sản phẩm/chính sách mới viết *sau* khi đóng băng, chỉ nhập bằng ingest).

| | Baseline | Cuối |
|---|---|---|
| Dev Hit@3 / từ chối nhầm | 26/52, 25/52 | 39/52, 13/52 |
| Holdout Hit@3 / từ chối nhầm / trả lời sai câu không thể trả lời | 12/25, 13/25, 2/8 | **14/25, 11/25, 0/8** |
| Fresh Hit@3 / trả lời sai | 10/19, 3/8 | **12/19, 1/8** |
| Vòng đời dữ liệu (sửa giá, xóa, nhất quán) | không hỗ trợ | 7/7 |

**Không đạt mục tiêu viết trước** (80% hit, ≤20% từ chối nhầm trên dữ liệu chưa thấy): nói thẳng. Khoảng tin cậy rộng (25 câu). Dev và holdout cùng một tác giả.

## 15. Gỡ lỗi câu trả lời sai (ví dụ thật)
`python -m scripts.trace_query "Có bàn gì?"` in ra từ nào bị bỏ, từ nào được sửa, ý định và tài liệu tìm được; phản hồi `/api/chat` có `query_trace` (kèm `gate_rejected`: tài liệu nào bị gate loại và vì sao). Ví dụ đã làm: truy vết "Có bàn gì?" → mọi từ đều là stopword; "Cái đó giá bao nhiêu?" từng trả về mọi tài liệu có giá vì chỉ còn từ "giá".

## 16. Token, độ trễ, chi phí
Offline p50 ≈ 10 ms với 15 tài liệu (không phải benchmark). Chế độ extractive ước lượng token = ký tự/3 và nói rõ là ước lượng. Gemini free-tier: trần request, giới hạn 60 text/phút cho embedding, cache đĩa; thí nghiệm B1: 151 text, 19 request, chạy trên free tier theo xác nhận của chủ khóa (không có cách tự xác minh). Không có số liệu chi phí production.

## 17. Bảo mật, prompt injection, lỗi API
Chỉ localhost, không endpoint ghi công khai, adapter Ollama chỉ loopback, Gemini chỉ host cho phép + khóa trong header và bị che. Tài liệu và `turn_context` là dữ liệu không tin cậy. 429 → dừng, không thử lại. Lỗi API được gắn nhãn, không giả làm "LLM tắt".

## 18. Đánh đổi thiết kế
Chắc chắn > độ phủ (từ chối nhầm 44% trên holdout đổi lấy 0 câu trả lời sai); sửa nguyên nhân thay vì hạ ngưỡng; không nuôi bảng đồng nghĩa từ lỗi (sẽ làm bẩn holdout); hybrid tắt dù embedding xếp đúng 8/8, vì độ tương đồng tuyệt đối không tách được "đúng sản phẩm nhưng thiếu thuộc tính" khỏi "đúng nhu cầu".

## 19. Giới hạn
Câu không chung từ với tài liệu (0/6 trên tập chưa thấy); tên riêng viết hoa lạ (kể cả địa danh) làm câu hỏi không trả lời được; thuộc tính thiếu của sản phẩm có thật vẫn trả về văn bản sản phẩm; hội thoại chỉ nhớ 1 lượt, trong tab trình duyệt; 15 tài liệu; một tác giả; **chưa chạy lại LLM thật sau v4**; hai lỗi tìm thấy từ dữ liệu fresh (giá CSV không có tiền tệ, khung "đặc điểm") đã sửa sau phiên đo và **chưa đo lại trên dữ liệu sạch**.

## 20. Cần gì để lên production
Xác thực/tenant, dữ liệu thật và nhiều hơn, holdout do người khác viết, đánh giá LLM đủ mẫu (rubric, người chấm), giám sát và log, hết hiệu lực dữ liệu (`valid_until`), đồng bộ tự động và lập chỉ mục vector theo lô, kiểm thử tải, trình duyệt/thiết bị khác.

---

## 18 câu hỏi phỏng vấn (trả lời dựa trên code thật)
1. **RAG là gì, dự án của bạn có generative không?** Mặc định không: LLM tắt → trích đoạn có dẫn nguồn (`extractive_demo`). Với LLM bật: ngữ cảnh → LLM → `evidence.valid_cited_answer`; chỉ một lần smoke thật (7 request, trước v4).
2. **Vì sao "Có bàn gì?" từng bị từ chối?** `ban` nằm trong STOP; bỏ dấu khiến bàn/bạn/bán trùng nhau, nên mọi từ đều bị loại và không có truy vấn (`scripts/trace_query.py`).
3. **Bạn sửa thế nào mà không hardcode?** `query.py`: vai trò từ quyết định bởi dạng gõ có dấu và bởi từ vựng của chính tài liệu (`Lexicon.has_other_reading`); test dùng danh mục tự chế để không thể "thuộc lòng" seed.
4. **Sửa lỗi gõ có nguy hiểm không?** Có: bản đầu biến "khuyến" thành "chuyen". Giờ chỉ hoán vị/phím kề, chỉ từ chưa thấy, từ ngắn chỉ hoán vị, phải có đúng một ứng viên.
5. **Vì sao BM25 mà không phải embedding?** Lỗi là xử lý token, không thiếu ngữ nghĩa; và tôi đã **đo** embedding: xếp đúng 8/8 nhưng không ngưỡng nào an toàn → bài học về hiệu chuẩn.
6. **Gate khác gì ngưỡng cosine?** Gate là ràng buộc cứng (tên, mã, số+đơn vị, tồn kho, khuyến mãi, dữ liệu riêng, so sánh số) áp cho *mọi* ứng viên; cosine chỉ cho biết liên quan.
7. **"Giá dưới 2 triệu" xử lý thế nào?** `quantities.py` tách điều kiện, quy đổi đơn vị, trích giá trị từ văn bản tài liệu, so sánh bằng code; không trích được rõ ràng → "unverified", xếp cuối và gắn nhãn, không khẳng định thỏa.
8. **Lỗ hổng bạn tìm ra trong hybrid cũ?** Mọi tài liệu cosine ≥0,38 vào kết quả mà không qua kiểm tra nào; giờ vector chỉ xếp lại tài liệu đã được gate nhận.
9. **Kết quả embedding nói gì?** Hạng 1 ở 8/8, nhưng điểm của câu hỏi *không thể trả lời* (0,61–0,82) chồng lên điểm đúng (0,66–0,76); phần lớn là hỏi tồn kho/khuyến mãi/đơn hàng cho sản phẩm có thật. Tôi thêm lớp chặn theo loại dữ liệu rồi mới kết luận: tốt nhất 1/8 < quy tắc 15 điểm → không bật.
10. **Vì sao không chọn ngưỡng cho 2/8?** Khe hở 0,014 giữa một near-miss (0,708) và một ca đúng (0,722) trên 65 ca: đó là khớp nhiễu.
11. **Holdout độc lập thế nào?** Hash SHA-256 commit trước khi đổi code, script từ chối chạy nếu thiếu `--final`, chạy một lần cho cả hai commit; test kiểm hash.
12. **Kết quả holdout?** 14/25 vs 12/25; sai câu không thể trả lời 0/8 vs 2/8; từ chối nhầm 11/25. Không đạt 80%/20%. Nguyên nhân: câu khác từ vựng, lỗi gõ ngoài luật, khoảng cách dev 75% → holdout 56%.
13. **Thêm sản phẩm mới thế nào, ai chịu trách nhiệm cập nhật chỉ mục?** `ingest` (transaction, id ổn định); BM25 và từ vựng cập nhật ngay nhờ `corpus_version`; vector theo lô thủ công; không có real-time sync.
14. **Xóa/sửa mà không dùng dữ liệu cũ?** Sửa nội dung → xóa vector cùng dòng; xóa → documents + chỉ mục văn bản cùng transaction; cache embedding khóa theo hash nội dung; `check_index` phát hiện lệch.
15. **Hội thoại nhiều lượt làm thế nào, không đoán ra sao?** Client gửi lại `turn_context` (id đã hiển thị); "nó" chỉ gắn khi lượt trước có đúng 1 tài liệu; "cái thứ hai" chỉ với danh sách; còn lại hỏi lại. Chỉ sửa `web/app.js` (test khóa hash HTML/CSS).
16. **Prompt injection?** Tài liệu/`turn_context` là dữ liệu không tin cậy; gate chặn yêu cầu hành động/dữ liệu riêng trừ tài liệu chính sách; `evidence.py` chặn câu LLM có cam kết không có nguồn; lệnh "bỏ qua chỉ dẫn" chưa có bộ kiểm thử LLM thật sau v4.
17. **Bạn đo độ trễ/chi phí thế nào?** Offline p50 ≈10 ms (15 tài liệu, không phải benchmark); token chế độ extractive là ước lượng; embedding thật 151 text/19 request trên free tier (chủ khóa xác nhận); không có số production.
18. **Điều gì bạn muốn làm tiếp?** Holdout do người khác viết và lớn hơn; rubric đánh giá LLM với người chấm; đo lại hai bản sửa sau phiên đo trên dữ liệu sạch mới; `valid_until`; dữ liệu nhiều hơn rồi mới xét lại embedding.

## Kịch bản demo 5 phút
1. (30 giây) Nêu rõ: dữ liệu giả lập, LLM tắt, đây là retrieval có dẫn nguồn.
2. (60 giây) "Có bàn gì?" → sản phẩm bàn; giải thích lỗi bàn/bạn/bán; mở `python -m scripts.trace_query "Có bàn gì?"`.
3. (60 giây) "Cho mình xem các sản phẩm đang bán" → "Cái thứ hai giá bao nhiêu?" → rồi "Nó giá bao nhiêu?" ngay sau danh sách → hệ thống hỏi lại.
4. (45 giây) "Có món nào dưới 500 nghìn không?"; "Bàn Oak 120 còn hàng không?" → từ chối vì không tài liệu nào nêu tồn kho.
5. (60 giây) `scripts.ingest` file mới → hỏi ngay; đổi giá, nhập lại; xóa nguồn; `scripts.check_index`.
6. (45 giây) Mở bảng đo (mục 14): nói trước điểm **không đạt**, và kết quả embedding âm tính; kết bằng giới hạn và việc cần làm tiếp.
