"""Adversarial and HTTP-contract tests for release v2.1; NO paid APIs.

The fake Ollama endpoint exercises real local HTTP serialization and code paths,
but it is explicitly a FAKE MODEL; it cannot prove model-answer quality.
"""
import json
import threading
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.evidence import safe_marketing_copy, valid_cited_answer
from app.main import create_app
from app.ollama import ModelUnavailable, request_json
from app.storage import Store


def client(tmp_path, llm='ollama'):
    config = replace(Settings(), data_path=tmp_path/'release.db', llm_provider=llm,
                     embedding_provider='off')
    return TestClient(create_app(settings=config))


def test_valid_citation_cannot_borrow_numeric_evidence_from_uncited_doc():
    docs = [
        {'id': 'D1', 'title': 'desk', 'content': 'Width is 120 cm.'},
        {'id': 'D2', 'title': 'shipping', 'content': 'Delivery is 7 days.'},
    ]
    assert not valid_cited_answer('Width is 7 cm [D1]', docs)
    assert valid_cited_answer('Width is 120 cm [D1]', docs)
    assert valid_cited_answer('Delivery is 7 days [D2]', docs)
    assert not valid_cited_answer('Delivery is 7 days [D2] [FAKE]', docs)


def test_marketing_rejects_unverified_offer_even_without_numbers():
    product = {'id': 'PRD', 'title': 'Desk', 'content': 'Wooden desk with adjustable legs.'}
    assert not safe_marketing_copy({'headline': 'Free shipping today', 'body': 'Wooden desk', 'cta': 'View'}, product)
    assert not safe_marketing_copy({'headline': 'Wooden desk', 'body': '50% off', 'cta': 'View'}, product)
    assert safe_marketing_copy({'headline': 'Wooden desk', 'body': 'Adjustable legs.', 'cta': 'View'}, product)


def test_campaign_fake_llm_fabrication_falls_back_to_template(tmp_path, monkeypatch):
    from app import services
    monkeypatch.setattr(services, 'ollama_chat', lambda *args, **kwargs: (
        json.dumps({'headline': 'GIẢM 90% NGAY', 'body': 'Mua bàn với free shipping!', 'cta': 'Buy now'}), 20, 7))
    result = client(tmp_path).post('/api/campaign', json={'sku': 'PRD-101', 'audience': 'office staff'}).json()
    assert result['status'] == 'DRAFT_REQUIRES_HUMAN_APPROVAL'
    assert result['mode'] == 'template_safety_fallback'
    assert '90%' not in str(result)


def test_campaign_bounded_draft_from_fake_llm(tmp_path, monkeypatch):
    from app import services
    monkeypatch.setattr(services, 'ollama_chat', lambda *args, **kwargs: (
        json.dumps({'headline': 'Khám phá Oak 120', 'body': 'Mặt bàn gỗ sồi sáng', 'cta': 'Xem thông tin'}), 23, 5))
    result = client(tmp_path).post('/api/campaign', json={'sku': 'PRD-101', 'audience': 'office staff'}).json()
    assert result['mode'] == 'llm_draft_review_required'
    assert result['status'] == 'DRAFT_REQUIRES_HUMAN_APPROVAL'


def test_agent_unsupported_tool_refused(tmp_path, monkeypatch):
    from app import agent
    monkeypatch.setattr(agent, 'request_json', lambda *args, **kwargs: {
        'message': {'tool_calls': [{'function': {'name': 'publish_ad', 'arguments': {'sku': 'PRD-101'}}}]}})
    result = client(tmp_path).post('/api/agent', json={'task': 'Publish ads and spend money'}).json()
    assert result['mode'] == 'agent_tool_blocked'
    assert result['steps'][0]['result']['error'] == 'not_allowed'
    assert 'đánh giá' in result['answer']


def test_agent_llm_response_without_tool_evidence_rejected(tmp_path, monkeypatch):
    from app import agent
    monkeypatch.setattr(agent, 'request_json', lambda *args, **kwargs: {
        'message': {'content': 'Order refund approved [PRD-101]'}})
    result = client(tmp_path).post('/api/agent', json={'task': 'Review a return policy'}).json()
    assert result['mode'] == 'agent_no_verified_evidence'
    assert 'approved' not in result['answer']


def test_agent_llm_invents_discount_with_valid_id_rejected(tmp_path, monkeypatch):
    from app import agent
    responses = iter([
        {'message': {'tool_calls': [{'function': {'name': 'lookup_product', 'arguments': {'sku': 'PRD-101'}}}]}},
        {'message': {'content': 'This product is discounted by 90% [PRD-101]'}}
    ])
    monkeypatch.setattr(agent, 'request_json', lambda *args, **kwargs: next(responses))
    result = client(tmp_path).post('/api/agent', json={'task': 'Read product PRD-101 then tell me price'}).json()
    assert result['mode'] == 'agent_answer_rejected'
    assert '90%' not in result['answer']


def test_local_only_ollama_does_not_call_cloud():
    with pytest.raises(ModelUnavailable, match='Only local Ollama'):
        request_json('https://example.com', '/api/chat', {'model': 'anything'}, 3)
    with pytest.raises(ModelUnavailable, match='Unsupported Ollama'):
        request_json('http://localhost:11434', '/api/delete', {}, 3)


@contextmanager
def fake_local_ollama():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def do_POST(self):
            length = int(self.headers.get('Content-Length', '0'))
            payload = json.loads(self.rfile.read(length))
            if self.path == '/api/embed':
                texts = payload['input']
                result = {'embeddings': [[0.1, 0.9] for _ in texts]}
            elif self.path == '/api/chat':
                result = {'message': {'content': 'Bàn có mặt 120 x 60 cm [PRD-101]'},
                          'prompt_eval_count': 45, 'eval_count': 10}
            else:
                self.send_response(404)
                self.end_headers()
                return
            body = json.dumps(result).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_real_http_adapter_with_fake_local_model(tmp_path):
    from app.retrieval import index_vectors
    with fake_local_ollama() as url:
        settings = replace(Settings(), data_path=tmp_path/'http.db', llm_provider='ollama',
                           embedding_provider='ollama', ollama_url=url, embedding_model='fake-test-model')
        store = Store(settings.data_path)
        result = index_vectors(store, settings)
        assert result['indexed'] >= 10
        response = TestClient(create_app(settings=settings)).post(
            '/api/chat', json={'question': 'Bàn Oak 120 kích thước bao nhiêu?'})
        assert response.status_code == 200
        answer = response.json()
        assert answer['mode'] == 'llm_rag_cited', answer
        assert answer['retrieval_mode'] == 'hybrid', answer
        assert answer['tokens_in'] == 45 and answer['tokens_out'] == 10
        assert 'PRD-101' in [s['id'] for s in answer['sources']]


def test_bad_vector_content_is_skipped_not_crash(tmp_path, monkeypatch):
    from app import retrieval
    store = Store(tmp_path/'corrupt.db')
    store.update_embedding('PRD-101', ['not a float', None], model='local-test')
    monkeypatch.setattr(retrieval, 'embed', lambda *_: [[0.1, 0.9]])
    config = replace(Settings(), embedding_provider='ollama', embedding_model='local-test')
    sources, mode = retrieval.search(store, config, 'Bàn Oak 120 kích thước bao nhiêu?')
    assert sources and sources[0]['id'] == 'PRD-101'
    assert mode == 'lexical'


def test_human_review_summary_does_not_fabricate_accuracy():
    from scripts.review_live_report import summarize_review
    summary = summarize_review({'cases': [
        {'human_factuality_review': 'supported'},
        {'human_factuality_review': 'NOT_COMPLETED'},
        {'human_factuality_review': 'unsupported'}]})
    assert summary['reviewed'] == 2
    assert summary['supported'] == 1
    assert summary['unsupported'] == 1
    assert summary['total'] == 3


def test_human_review_rejects_offline_or_fabricated_report(tmp_path):
    from scripts.review_live_report import review_file
    path = tmp_path / 'fake.json'
    path.write_text(json.dumps({'model_calls_are_local': False, 'cases': [{'question':'Q'}]}))
    with pytest.raises(ValueError, match='not a validated'):
        review_file(path)
