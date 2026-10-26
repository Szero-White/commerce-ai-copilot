"""Business-workflow and migration regressions; do not require model downloads."""
from dataclasses import replace
import sqlite3
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.storage import Store
from app.retrieval import index_vectors, search


def api(tmp_path):
    return TestClient(create_app(settings=replace(Settings(),data_path=tmp_path/'v2.db',llm_provider='off',embedding_provider='off')))


def test_support_damaged_requires_review_and_policy(tmp_path):
    result=api(tmp_path).post('/api/support/triage',json={'message':'My personalized mug arrived damaged. Can I get a refund?'})
    assert result.status_code==200
    body=result.json()
    assert body['intent']=='damaged_product'
    assert body['priority']=='high'
    assert body['status']=='DRAFT_REQUIRES_HUMAN_REVIEW'
    assert not body['autonomous_action']
    assert body['evidence']
    assert all(x['category']=='policy' for x in body['evidence'])
    assert 'human review' in body['draft_reply'].lower()


def test_support_order_privacy(tmp_path):
    response=api(tmp_path).post('/api/support/triage',json={'message':'Please provide my order status and my customer address'})
    assert response.status_code==200
    result=response.json()
    assert result['intent']=='privacy_order'
    assert result['priority']=='high'
    assert result['evidence'][0]['id']=='POL-005'
    assert not result['autonomous_action']


def test_support_unknown_no_false_auto_resolution(tmp_path):
    result=api(tmp_path).post('/api/support/triage',json={'message':'quasar zyzzyva neutrino quantum teleport'}).json()
    assert result['intent']=='unknown'
    assert result['status']=='DRAFT_REQUIRES_HUMAN_REVIEW'
    assert 'refund_approved' not in str(result).lower()


def test_support_validation(tmp_path):
    assert api(tmp_path).post('/api/support/triage',json={'message':'short'}).status_code==422


def test_embeddings_invalidate_when_model_changes(tmp_path,monkeypatch):
    from app import retrieval
    store=Store(tmp_path/'vectors.db')
    mocked=[]
    def fake_embed(settings,texts):
        mocked.append(settings.embedding_model)
        return [[0.9,0.1] for _ in texts]
    monkeypatch.setattr(retrieval,'embed',fake_embed)
    first=replace(Settings(),embedding_provider='ollama',embedding_model='model-a')
    second=replace(first,embedding_model='model-b')
    assert index_vectors(store,first)['indexed']>0
    assert store.document('POD-201')['embedding_model']=='model-a'
    # Stale vectors are ignored, never silently treated as model-b vectors.
    _,mode=search(store,second,'personalized ceramic mug',k=3)
    assert mode=='lexical'
    assert index_vectors(store,second)['indexed']>0
    assert store.document('POD-201')['embedding_model']=='model-b'
    assert set(mocked)=={'model-a','model-b'}


def test_legacy_database_migration(tmp_path):
    path=tmp_path/'legacy.db'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE documents (id TEXT PRIMARY KEY,title TEXT NOT NULL,category TEXT NOT NULL,content TEXT NOT NULL,embedding_json TEXT)')
    store=Store(path)
    assert 'embedding_model' in store.documents()[0]


def test_frontend_has_workflow_page():
    from app.config import ROOT
    html=(ROOT/'web/index.html').read_text(encoding='utf8')
    js=(ROOT/'web/app.js').read_text(encoding='utf8')
    assert 'id="page-support"' in html
    assert "api('/api/support/triage'" in js


def test_numeric_fabrication_is_not_served_as_cited_rag(tmp_path,monkeypatch):
    from app import services
    monkeypatch.setattr(services,'ollama_chat',lambda *a,**k: ('Sản phẩm đang giảm giá 90% [PRD-101]',32,9))
    config=replace(Settings(),data_path=tmp_path/'hallucination.db',llm_provider='ollama',embedding_provider='off')
    result=TestClient(create_app(settings=config)).post('/api/chat',json={'question':'Bàn Oak 120 kích thước bao nhiêu?'}).json()
    assert result['mode']=='llm_citation_rejected_extractive'
    assert '90%' not in result['answer']


def test_existing_numeric_citation_is_accepted(tmp_path,monkeypatch):
    from app import services
    monkeypatch.setattr(services,'ollama_chat',lambda *a,**k: ('Bàn rộng 120 x 60 cm [PRD-101]',32,9))
    config=replace(Settings(),data_path=tmp_path/'numbers.db',llm_provider='ollama',embedding_provider='off')
    result=TestClient(create_app(settings=config)).post('/api/chat',json={'question':'Bàn Oak 120 kích thước bao nhiêu?'}).json()
    assert result['mode']=='llm_rag_cited',result
