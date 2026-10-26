import json
from dataclasses import replace
from fastapi.testclient import TestClient
from app.config import Settings, ROOT
from app.main import create_app
from app.storage import Store
from app.services import evaluate_retrieval


def client(tmp_path):
    settings=replace(Settings(),data_path=tmp_path/"test.db",llm_provider="off",embedding_provider="off")
    return TestClient(create_app(settings=settings))


def test_health_and_demo_mode(tmp_path):
    c=client(tmp_path)
    r=c.get("/api/health")
    assert r.status_code==200
    assert r.json()["documents"]>=10
    assert r.json()["llm_provider"]=="off"
    assert r.json()["simulation"] is True


def test_refund_grounds_sources(tmp_path):
    response=client(tmp_path).post("/api/chat",json={"question":"Đổi trả trong 7 ngày được không?"})
    assert response.status_code==200
    assert response.json()["mode"]=="extractive_demo"
    assert "POL-002" in [x["id"] for x in response.json()["sources"]]


def test_unknown_query_does_not_invent_answer(tmp_path):
    response=client(tmp_path).post("/api/chat",json={"question":"quasar neutrino qubit zyzzyva"})
    assert response.status_code==200
    assert response.json()["mode"]=="no_evidence"
    assert "chưa có đủ thông tin" in response.json()["answer"]


def test_campaign_requires_review_and_rejects_non_product(tmp_path):
    c=client(tmp_path)
    r=c.post("/api/campaign",json={"sku":"PRD-101","audience":"nhân viên làm việc tại nhà"})
    assert r.status_code==200
    assert r.json()["status"]=="DRAFT_REQUIRES_HUMAN_APPROVAL"
    assert r.json()["mode"]=="template_preview"
    assert c.post("/api/campaign",json={"sku":"POL-001","audience":"khách hàng"}).status_code==404


def test_eval_dataset(tmp_path):
    store=Store(tmp_path/"eval.db")
    settings=replace(Settings(),embedding_provider="off")
    cases=json.loads((ROOT/"data"/"eval_set.json").read_text(encoding="utf-8"))
    result=evaluate_retrieval(store,settings,cases)
    assert result["total"]==len(cases)
    assert result["score"] >= .7, result


def test_no_public_write_api(tmp_path):
    assert client(tmp_path).post("/api/admin/index-embeddings").status_code==403


def test_unknown_discount_not_replaced_by_policy(tmp_path):
    data = client(tmp_path).post("/api/chat", json={"question": "Có ưu đãi 90% không?"}).json()
    assert data["mode"] == "no_evidence", data
    assert data["sources"] == []


def test_agent_does_not_fake_tool_calls_without_llm(tmp_path):
    d=client(tmp_path).post("/api/agent",json={"task":"Tra cứu thông tin sản phẩm PRD-101"}).json()
    assert d["mode"]=="agent_disabled"
    assert d["steps"]==[]
    assert d["approval_required"] is True


def test_agent_tool_is_read_only(tmp_path):
    from app.agent import execute_tool
    from dataclasses import replace
    store=Store(tmp_path/"tools.db")
    settings=replace(Settings(),embedding_provider="off")
    assert execute_tool(store,settings,"lookup_product",{"sku":"PRD-101"})["found"]
    assert execute_tool(store,settings,"send_ad",{"sku":"PRD-101"})["error"]=="not_allowed"


def test_english_pod_catalog_and_policy(tmp_path):
    c=client(tmp_path)
    r=c.post("/api/chat",json={"question":"Can I return a personalized item because I changed my mind?"})
    assert r.status_code==200
    assert "POD-POL-201" in [x["id"] for x in r.json()["sources"]]
    assert "POD-201" in {x["id"] for x in c.get("/api/products").json()}


def test_evaluation_rejection_set_is_reported(tmp_path):
    d=client(tmp_path).get("/api/evaluation").json()
    assert d["total"]==13
    assert d["negative_rejection"]["total"]==3
    assert d["negative_rejection"]["passed"]>=2, d["negative_rejection"]


def test_context_pack_and_citation_validator():
    from app.services import _context_from_sources, _supported_citations
    docs=[{"id":"D-1","title":"Long","content":"a"*600},{"id":"D-2","title":"Next","content":"b"*600}]
    context,included=_context_from_sources(docs,500)
    assert len(context)<=500
    assert included[0]["id"]=="D-1"
    assert "[D-2]" not in context
    assert _supported_citations("Verified [D-1]",included)
    assert not _supported_citations("Fake [D-999]",included)
    assert not _supported_citations("No references",included)


def test_mock_llm_answer_has_valid_citation(tmp_path,monkeypatch):
    from app import services
    monkeypatch.setattr(services,"ollama_chat",lambda *args,**kwargs:("Kích thước: xem dữ liệu [PRD-101]",43,18))
    settings=replace(Settings(),data_path=tmp_path/"llm.db",llm_provider="ollama",embedding_provider="off")
    c=TestClient(create_app(settings=settings))
    result=c.post("/api/chat",json={"question":"Bàn Oak 120 kích thước bao nhiêu?"}).json()
    assert result["mode"]=="llm_rag_cited",result
    assert result["tokens_in"]==43
    assert result["citation_ids_checked"] is True


def test_mock_llm_answer_without_source_is_rejected(tmp_path,monkeypatch):
    from app import services
    monkeypatch.setattr(services,"ollama_chat",lambda *args,**kwargs:("Mọi sản phẩm đều giảm 90% [FAKE-123]",43,18))
    settings=replace(Settings(),data_path=tmp_path/"llm.db",llm_provider="ollama",embedding_provider="off")
    c=TestClient(create_app(settings=settings))
    result=c.post("/api/chat",json={"question":"Bàn Oak 120 kích thước bao nhiêu?"}).json()
    assert result["mode"]=="llm_citation_rejected_extractive",result
    assert "90%" not in result["answer"]
    assert result["tokens_out"]==18


def test_mock_vector_index_and_hybrid_retrieval(tmp_path, monkeypatch):
    """Offline contract test: embedding integration logic, not actual semantic quality."""
    from app import retrieval
    store=Store(tmp_path/"vector.db")
    settings=replace(Settings(),embedding_provider="ollama",llm_provider="off")

    def fake_embed(settings, texts):
        # Deterministic mock verifies batch indexing and vector-mode wiring.
        return [[1.0,0.0] if 'POD-' in text or 'personalized' in text.lower() else [0.0,1.0]
                for text in texts]

    monkeypatch.setattr(retrieval,"embed",fake_embed)
    indexed=retrieval.index_vectors(store,settings)
    assert indexed["enabled"] and indexed["indexed"] >= 10
    docs, mode=retrieval.search(store,settings,"personalized ceramic mug",k=3)
    assert mode=="hybrid" and docs
    assert any(doc["id"]=="POD-201" for doc in docs)


def test_mock_agent_executes_only_whitelisted_read_tools(tmp_path,monkeypatch):
    from app import agent
    settings=replace(Settings(),data_path=tmp_path/"agent.db",llm_provider="ollama",embedding_provider="off")
    outputs=iter([
        {"message":{"role":"assistant","content":"","tool_calls":[{"function":{"name":"lookup_product","arguments":{"sku":"PRD-101"}}}]},"prompt_eval_count":20,"eval_count":4},
        {"message":{"role":"assistant","content":"Theo tài liệu sản phẩm [PRD-101]"},"prompt_eval_count":21,"eval_count":9},
    ])
    monkeypatch.setattr(agent,"request_json",lambda *args,**kwargs:next(outputs))
    c=TestClient(create_app(settings=settings))
    r=c.post("/api/agent",json={"task":"Look up product PRD-101 and cite source"})
    assert r.status_code==200
    data=r.json()
    assert data["mode"]=="tool_calling_agent",data
    assert len(data["steps"])==1
    assert data["steps"][0]["tool"]=="lookup_product"
    assert data["steps"][0]["result"]["found"]
    assert data["approval_required"] is True
