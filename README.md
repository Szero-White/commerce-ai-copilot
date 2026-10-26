# Commerce AI Copilot v2.1 — RAG, Support Triage & Marketing Workflow

> **Portfolio giả lập, KHÔNG phải phần mềm của NEXGEN BROS.** Được xây theo những nhóm kỹ năng trong tin AI Engineer (LLM/RAG/AI Automation), nhưng dữ liệu sản phẩm/chính sách hoàn toàn hư cấu. Không dùng cho khách hàng thật hoặc mở public Internet nếu chưa có xác thực, rate limiting và security review.


## RELEASE v2.1 — 26/10/2026: verified changes

**Đây là bản portfolio hoàn thiện để chạy, học, trình bày và tự kiểm tra offline — KHÔNG phải hệ thống AI production.** LLM và embeddings chạy thật chỉ được xác nhận nếu bạn thực hiện thành công kiểm tra Ollama local. Không có API trả phí bắt buộc.

**Điểm mới so với v2.0:**

- Bảo vệ marketing copy: bản nháp LLM thêm số liệu, ưu đãi hoặc cam kết thương mại không có nguồn bị hạ về template; không tự đăng quảng cáo. Đây là bộ lọc theo mẫu bảo thủ, **không phải bộ chứng minh mọi tuyên bố đều đúng**.
- Agent tool-calling: chặn tool ngoài whitelist; từ chối câu trả lời nếu không có nguồn từ tool, viện dẫn ID giả hoặc tự bịa số liệu. Agent read-only, vẫn phải được con người kiểm tra.
- Bảo vệ RAG: số liệu trong câu trả lời phải có trong **nguồn được dẫn**, không chỉ trong một tài liệu bất kỳ của knowledge base.
- Adapter Ollama được giới hạn HTTP localhost và kiểm tra vector hữu hạn, nhất quán kích thước; vector bị lỗi được bỏ qua thay vì làm API crash. **Không truyền dữ liệu người dùng lên host Ollama từ Internet trong bản này.**
- Kiểm thử tự động **37/37 PASS** tại thời điểm đóng gói; thêm bài test HTTP với **fake Ollama** (đo hợp đồng phần mềm, không đo chất lượng mô hình).
- Chạy `verify_portfolio_windows.bat` để có báo cáo offline 8 luồng trong `reports/offline_acceptance_report.json`, được tạo bởi script thực chạy và không tự bịa chỉ số AI.
- Có quy trình Claude Code review độc lập tại `docs/tasks/03_CLAUDE_V2_1_INDEPENDENT_AUDIT.md` và checklist bàn giao `docs/RELEASE_ACCEPTANCE_V2_1.md`.

**Mốc đánh giá đúng:** Offline demo/API đã kiểm chứng; live Ollama (LLM, embedding, tool calling), kết nối Shopify thật, tải thật và độ chính xác nghiệp vụ chưa được xác minh. Không công khai public Internet do chưa có auth/rate limiting/tenant isolation.

## What changed in v2.0 (26 Oct 2026)

This is a **working local portfolio repository**, not a company website or a production deployment. It contains **real Python/FastAPI endpoints** and an offline mode. **Live generative RAG is optional and cannot be claimed until it runs with a real model on your computer.**

- **New Support Ticket Triage page and API:** classify simulated English/Vietnamese requests, route to a team, retrieve policy evidence and prepare a response for **human review only**. It is intentionally deterministic, **not an AI agent**.
- **Stale-vector protection:** saved vectors now track `embedding_model`; changing the model cannot silently reuse incompatible embeddings.
- **LLM numeric-claim guard:** if a generated answer adds a number that the selected sources do not contain, fall back to source excerpts. Citation IDs and numbers alone **do not establish factual correctness**.
- **New live-model verification script:** `python -m scripts.verify_live_rag` writes a measured report only after actual local model execution; it refuses to run when providers are off or vectors are missing.
- **Engineering handoff:** `docs/ENGINEERING_HANDOFF.md`, `docs/JOB_MATCH_SCORECARD.md`, `docs/AI_TEAM_WORKFLOW.md` and scoped Claude Code tasks in `docs/tasks/`.

**Verified in this environment:** 37/37 offline automated tests; FastAPI endpoint smoke tests; local HTTP server health; UI rendering with mocked API responses. **Not verified:** actual Ollama model inference/embeddings on your machine, paid cloud APIs, public deployment, business ROI, real customer data. Do not report those as achievements.

### Quick interview demo sequence

1. **RAG Assistant:** Ask about a personalized product return, review its cited policy.
2. **Support Triage:** Send `My personalized mug arrived damaged. Can I get a refund?` and inspect policy, priority, routing and required human review.
3. **Campaign Studio:** Create a draft; demonstrate that no advertising API is allowed to publish it.
4. **Quality Lab:** Run synthetic retrieval evaluation; explain why this is not an answer-factuality score.
5. **Engineering:** Open `/docs` and show test suite, source files, model-version control and LLM caveats.

Read [JD scorecard](docs/JOB_MATCH_SCORECARD.md) and [Claude handoff](docs/tasks/01_CLAUDE_LIVE_RAG.md) before claiming the product is interview-ready for the full AI Engineer description.

## 1. Chạy ngay trên Windows (không API trả phí)

1. Cài [Python](https://www.python.org/downloads/) phiên bản **3.10+** và chọn **Add Python to PATH** nếu trình cài đặt có tùy chọn này.
2. Giải nén ZIP, mở thư mục, nhấp đúp `run_windows.bat`.
3. Trình duyệt mở `http://127.0.0.1:8000`. Nếu không mở tự động, sao chép URL đó vào Chrome/Edge.
4. Dùng **RAG Assistant**, **Campaign Studio**, **Quality Lab**. Không cần khóa API trong chế độ mặc định.

Yêu cầu kết nối mạng lần đầu để tải gói Python. Chạy trên `127.0.0.1` để tránh vô tình công khai dữ liệu. Để dừng ứng dụng: quay lại cửa sổ terminal và nhấn `Ctrl+C`.

**Lệnh tương đương Linux/macOS:**

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## 2. Đúng bản chất kỹ thuật — không đánh tráo demo thành AI

| Tính năng | Mặc định, không API | Khi cấu hình Ollama |
|---|---|---|
| Retrieval theo từ khóa (BM25 FTS5) | ✅ Hoạt động | ✅ |
| Tài liệu và dẫn nguồn | ✅ | ✅ |
| LLM sinh câu trả lời | ❌ Chỉ trích xuất tài liệu | ✅ LLM local qua `/api/chat` |
| Vector embeddings, cosine similarity, hybrid RRF | ❌ | ✅ Nếu bật embedding và chạy script index |
| Bản nháp quảng cáo | ✅ Bằng template | ✅ Bằng LLM nếu output JSON hợp lệ |
| Kiểm duyệt trước khi đăng | ✅ Luôn yêu cầu | ✅ Luôn yêu cầu |
| Evaluation Hit@3, metrics | ✅ | ✅ |
| Agent tool-calling có giới hạn 2 tool | ❌ Báo chưa bật agent | ✅ Ollama tool calling (nếu model hỗ trợ) |
| LangGraph, LangChain, MLOps, real ads APIs | Chưa triển khai | Chưa triển khai |

**Không gọi bản extractive mặc định là generative RAG.** Đây là retrieval-only proof-of-concept. Khi bật mô hình sinh, luồng thực sự là query → (lexical/vector) retrieval → context → LLM → answer + source display. Chú ý: hiển thị source không chứng minh mọi mệnh đề của LLM đều grounded. Cần đánh giá faithfulness trước production.

## 3. Bật generative RAG + embeddings thực với mô hình local (tùy chọn)

Nếu RAM và dung lượng đĩa cho phép (máy 8 GB RAM có thể chạy chậm), cài [Ollama](https://ollama.com/download), sau đó dùng terminal **ở thư mục dự án**:

```powershell
ollama pull qwen2.5:1.5b
ollama pull bge-m3
# Windows PowerShell, chỉ ảnh hưởng phiên terminal hiện tại
$env:LLM_PROVIDER="ollama"
$env:EMBEDDING_PROVIDER="ollama"
$env:OLLAMA_MODEL="qwen2.5:1.5b"
$env:EMBEDDING_MODEL="bge-m3"
.venv\Scripts\python.exe -m scripts.index_embeddings
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Không chạy song song `run_windows.bat` để tránh trùng cổng. Mô hình được tải và chạy **local**; không cần phí API nhưng sẽ dùng RAM, CPU và bộ nhớ máy tính. Nếu Ollama lỗi, app sẽ xuống chế độ extractive và thông báo rõ. Việc chuyển `EMBEDDING_MODEL` đòi hỏi tạo lại chỉ mục (xem bên dưới).

### Tùy chỉnh model / tiết kiệm token

- Chỉ truy xuất **top 3**, cắt context theo `MAX_CONTEXT_CHARS=2600`, giới hạn output qua `MAX_OUTPUT_TOKENS=256`.
- Dùng một lần gọi LLM cho mỗi câu hỏi; không tạo vòng lặp agent vô hạn hoặc cho model gọi tool tự do.
- Kỹ thuật thực tế: trước hết tối ưu retrieval để tránh nhét cả tài liệu dài vào prompt. Đánh giá tác động lên Hit@3 và chất lượng trả lời.
- Metrics lấy token thực từ `prompt_eval_count/eval_count` khi LLM hoạt động; chế độ mặc định chỉ **ước lượng** bằng độ dài ký tự, không dùng tính tiền.
- Không mặc định lưu conversation, dữ liệu người dùng hay embedding của query vào cơ sở dữ liệu.

**Chưa triển khai caching kết quả LLM, routing đa model, semantic chunking, prompt versioning, A/B test hoặc cost tracking API theo hóa đơn.** Đây là những mục nâng cấp đề xuất; tuyệt đối không khai là đã làm trong CV.

### Re-index khi đổi embedding model

Các vector của model cũ không tương thích với model mới. Trong SQLite database demo, chạy:

```powershell
.venv\Scripts\python.exe -c "from app.config import Settings; from app.storage import Store; s=Store(Settings().data_path); c=s.connect(); c.execute('UPDATE documents SET embedding_json=NULL, embedding_model=NULL'); c.commit(); c.close()"
.venv\Scripts\python.exe -m scripts.index_embeddings
```

### Human factuality review sau khi chạy mô hình thật

Sau khi `python -m scripts.verify_live_rag` tạo `reports/live_rag_report.json`, chạy `python -m scripts.review_live_report` để gắn nhãn **supported / unsupported / uncertain** cho từng đáp án; đối chiếu với đoạn nguồn được lưu trong báo cáo và văn bản đầy đủ trong Knowledge Base. Không đánh đồng nhãn của một người trên vài câu hỏi với số liệu độ chính xác production. **Nếu không có mô hình thật, không có báo cáo live để đánh giá.**

## 4. Import tài liệu và CSV (offline, chủ sở hữu thực hiện)

```powershell
.venv\Scripts\python.exe -m scripts.ingest data\sample_products.csv
.venv\Scripts\python.exe -m scripts.ingest duong-dan-file.md
```

- CSV yêu cầu `sku,name,price,description` (UTF-8), tối đa 500 sản phẩm, file tối đa 2 MB.
- TXT/MD được tách thành các phần khoảng 800 ký tự để demo.
- Dữ liệu mẫu không phản ánh giá, chính sách hoặc hàng hóa thật của công ty nào.
- Import chỉ qua CLI local, **không có public upload**; nội dung tài liệu vẫn cần rà soát trước khi cung cấp cho LLM.
- Nếu đã bật embedding mode, chạy lại `scripts.index_embeddings` sau import.

## 5. API chính

- `GET /api/health`: trạng thái các provider, số tài liệu / vector
- `GET /api/documents`: knowledge base giả lập
- `GET /api/products`: catalogue giả lập
- `POST /api/chat` body `{ "question": "Bàn Oak 120 kích thước bao nhiêu?" }`: đáp án + `sources` + diagnostic
- `POST /api/agent` body `{ "task": "Tra cứu sản phẩm PRD-101 và chính sách giao hàng" }`: Ollama tool-calling agent đọc dữ liệu; tối đa 2 tool, backend whitelist, không tự ghi/gửi
- `POST /api/support/triage` body `{ "message": "My personalized mug arrived damaged. Can I get a refund?" }`: quyết định phân loại và dẫn chính sách, **luôn yêu cầu người duyệt**, không truy cập đơn hàng thật
- `POST /api/campaign` body `{ "sku": "PRD-101", "audience": "nhân viên văn phòng" }`: bản nháp cần phê duyệt
- `GET /api/evaluation`: Hit@3 và danh sách kết quả
- `GET /api/metrics`: request count, latency, token count/estimate
- `python -m scripts.verify_live_rag`: chỉ chạy khi đã bật Ollama LLM + embeddings và index đủ tài liệu; sinh báo cáo đo từ mô hình thật vào `reports/live_rag_report.json`
- Swagger: `http://127.0.0.1:8000/docs`

## 6. Kiểm thử

Để kiểm tra offline trên Windows sau lần đầu chạy `run_windows.bat`, nhấp đúp `verify_portfolio_windows.bat`. Bản này chạy pytest và 8 kiểm tra API trên database tạm. **Không dùng Ollama trong bước này**. Nếu muốn chạy từ terminal: `python -m pytest -q` và `python -m scripts.portfolio_check` sau khi cài `requirements-dev.txt`.


```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Kỳ vọng test các hành vi: chatbot có nguồn, câu hỏi không liên quan phải từ chối, không có workflow gửi ads, endpoint ghi public bị cấm, số liệu evaluation hợp lệ. Evaluation có 13 câu retrieval tích cực và 3 câu negative do tác giả biên soạn; **không phản ánh accuracy trên tập khách hàng thật**. Hit@3 retrieval khác faithfulness hoặc answer correctness.

## 7. Hạn chế quan trọng / trước khi production

- Không có authentication/authorization người dùng, rate limit, tenant isolation; **CHỈ chạy local**.
- SQLite FTS5 + brute force cosine thích hợp demo quy mô nhỏ; production cần xem xét PostgreSQL/pgvector hoặc vector DB và chiến lược tái lập chỉ mục.
- Knowledge base hiện là các tài liệu ngắn, không parsing PDF/HTML thực tế, không đồng bộ Shopify/Google Ads/Meta.
- Chưa có human-approval backend bảo mật: tác vụ marketing chỉ tạo nháp và không thể tự gửi. Đó là lựa chọn an toàn cho portfolio.
- Retrieval có thể sai do stopword, tiếng Việt, ranking và mức độ liên quan; demo có báo cáo lỗi thay vì che giấu.
- LLM có thể hallucinate hoặc làm theo chỉ thị trong nguồn ngoài ý muốn. Không có guarantee ngăn prompt injection; cần red-team, đánh giá và cơ chế policy ở tầng ứng dụng trước khi sản phẩm thật.
- Hiện chưa có bảo vệ API public chống DoS ngoài validation input. Đừng expose Internet.

## 8. Kịch bản demo phỏng vấn (5–8 phút)

1. **30 giây:** Nêu bài toán: nhân viên CSKH e-commerce phải tra cứu thông số/chính sách, marketing mất thời gian soạn nháp, công ty cần đo chất lượng AI.
2. **1 phút:** Chat hỏi “Bàn Oak 120 kích thước bao nhiêu?”; chỉ ra mã nguồn `PRD-101` và kết quả truy xuất.
3. **1 phút:** Hỏi câu ngoài phạm vi “quasar neutrino qubit zyzzyva” để chứng minh hệ thống nói không biết thay vì bịa.
4. **1 phút:** Tạo campaign draft cho sản phẩm; giải thích vì sao **không tự gửi quảng cáo**. Nếu đã bật Ollama, mở Agent Workbench để xem tool-calling trace và whitelist.
5. **1 phút:** Vào Quality Lab, bấm đánh giá; giải thích Hit@3 và xem bất kỳ test FAIL nào.
6. **1 phút:** Mở `app/retrieval.py`, `app/services.py`, `app/ollama.py`; chỉ ra BM25, optional embedding, RRF, giới hạn context/token và response metadata.
7. **1 phút:** Trình bày hạn chế và bước tiếp theo: đánh giá factual correctness, PostgreSQL + pgvector, xác thực, job queue, API integration, log redaction, đo chi phí thật.

**CV trung thực:** “Xây dựng e-commerce AI demo bằng Python/FastAPI, SQLite FTS5, retrieval có nguồn, optional Ollama embeddings/LLM, workflow tạo nháp nội dung và automated retrieval evaluation.” Chỉ nói “semantic vector search”, “generative RAG” hoặc “tool-calling agent” nếu đã thực sự bật và chạy chúng. Xem `docs/CV_AND_APPLICATION.md` để có gợi ý mô tả theo hai mức triển khai.

## 9. Liên hệ với JD

Tham khảo tin TopCV “AI Engineer (LLM/RAG/AI Automation) – NEXGEN BROS” hạn 06/11/2026. Repository này là sản phẩm **cá nhân** lấy cảm hứng từ JD và dữ liệu giả lập, không có quan hệ với nhà tuyển dụng.

- Mạnh: Python, REST API, DB, parsing CSV/text, lexical RAG, LLM API adapter, prompt, KPI Hit@3, code review-friendly, Docker optional.
- Mới chỉ mở rộng tùy chọn: semantic embeddings, model serving thông qua Ollama, vector retrieval.
- Chưa có: orchestration LangGraph, APIs nền tảng quảng cáo, fine tuning, MLOps, microservices, real production deployments. Agent tool-calling tối giản chỉ hoạt động khi cấu hình model hỗ trợ.

Nguồn kỹ thuật: [FastAPI](https://fastapi.tiangolo.com/), [Ollama API](https://docs.ollama.com/api), [Sentence Transformers semantic search](https://www.sbert.net/examples/sentence_transformer/applications/semantic-search/README.html). Thông tin kỹ năng tuyển dụng từ bài JD do người tìm việc cung cấp và [tin TopCV](https://www.topcv.vn/viec-lam/ai-engineer-llm-rag-ai-automation-thu-duc-thu-nhap-15-25-trieu/2236920.html).

## 10. Lịch sử bản nâng cấp v1.1 (26/10/2026)

- Thêm **3 tài liệu e-commerce Print-on-Demand giả lập** (câu hỏi tiếng Anh về hàng cá nhân hóa) và 3 retrieval tests tích cực; không liên quan đến chính sách thực của nhà tuyển dụng.
- Thêm **3 kiểm tra câu ngoài phạm vi** ở Quality Lab, tách khỏi chỉ số Hit@3. Đây chỉ là kiểm tra khớp tài liệu, không đo chất lượng câu trả lời sinh bởi LLM.
- Nếu LLM trả lời thiếu citation hoặc gắn ID nguồn không có trong context, backend hạ xuống chế độ hiển thị nguồn gốc để người dùng đối chiếu. Đây là validation ID, **không phải bộ xác minh tính đúng của từng mệnh đề**.
- Thêm test giả lập hai chiều (câu trả lời LLM có/không có trích dẫn, embedding giả lập, agent tool-calling giả lập). **Các bài test này không chứng minh Ollama đã thực sự chạy.**
- Thêm GitHub Actions CI config (`.github/workflows/ci.yml`) để có thể chạy pytest trên push/PR.
- Thêm `CLAUDE.md`, `docs/NEXT_STEPS_NEXGEN_2026.md`, `docs/CLAUDE_CODE_HANDOFF.md` để phối hợp AI coding tiết kiệm chi phí.

**Xem hướng dẫn thực hiện trước khi nộp CV:** [`docs/NEXT_STEPS_NEXGEN_2026.md`](docs/NEXT_STEPS_NEXGEN_2026.md). Sau khi chạy với model thật, bổ sung benchmark có số liệu thực và lỗi thực; không ghi kinh nghiệm production nếu chưa có.
