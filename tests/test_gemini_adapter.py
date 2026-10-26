"""Gemini adapter against a FAKE local server. No network, no real key, no real model.

These prove request shape, safety rules and error handling only; they say nothing about
answer quality (that needs the live run documented in docs/LIVE_EVALUATION_GEMINI.md).
"""
import json
import threading
from contextlib import contextmanager
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient

from app import gemini
from app.config import Settings
from app.main import create_app
from app.ollama import ModelUnavailable

FAKE_KEY = 'fake-key-for-tests-0123456789'


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', FAKE_KEY)
    monkeypatch.setattr(gemini, '_check_url', lambda url: None)
    monkeypatch.setattr(gemini.time, 'sleep', lambda s: None)
    gemini.reset_budget()
    yield
    gemini.reset_budget()


@contextmanager
def fake_gemini(handler, monkeypatch):
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def _serve(self):
            length = int(self.headers.get('Content-Length', '0'))
            body = json.loads(self.rfile.read(length)) if length else None
            seen.append({'method': self.command, 'path': self.path, 'body': body,
                         'key': self.headers.get('x-goog-api-key')})
            status, raw = handler(self.command, self.path, body)
            raw = raw if isinstance(raw, bytes) else json.dumps(raw).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        do_GET = do_POST = _serve

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(gemini, 'BASE_URL', f'http://127.0.0.1:{server.server_port}/v1beta')
    try:
        yield seen
    finally:
        server.shutdown()
        server.server_close()


def text_reply(text, tokens_in=11, tokens_out=3):
    return 200, {'candidates': [{'content': {'role': 'model', 'parts': [{'text': text}]}}],
                 'usageMetadata': {'promptTokenCount': tokens_in, 'candidatesTokenCount': tokens_out}}


def cfg(tmp_path, **kw):
    options = {'data_path': tmp_path / 'g.db', 'llm_provider': 'gemini', 'embedding_provider': 'off',
               'gemini_model': 'gemini-2.5-flash', **kw}
    return replace(Settings(), **options)


# request shape and secrecy -------------------------------------------------
def test_chat_request_shape_and_key_only_in_header(tmp_path, monkeypatch):
    with fake_gemini(lambda *a: text_reply('Bàn rộng 120 cm [PRD-101]'), monkeypatch) as seen:
        answer, tin, tout = gemini.chat(cfg(tmp_path), 'SYSTEM TEXT', 'USER TEXT', json_output=True)
    assert (answer, tin, tout) == ('Bàn rộng 120 cm [PRD-101]', 11, 3)
    request = seen[0]
    assert request['path'] == '/v1beta/models/gemini-2.5-flash:generateContent'
    assert request['key'] == FAKE_KEY and FAKE_KEY not in request['path']
    assert FAKE_KEY not in json.dumps(request['body'])
    body = request['body']
    assert body['systemInstruction']['parts'][0]['text'] == 'SYSTEM TEXT'
    assert body['contents'][0] == {'role': 'user', 'parts': [{'text': 'USER TEXT'}]}
    assert body['generationConfig']['responseMimeType'] == 'application/json'
    assert body['generationConfig']['thinkingConfig'] == {'thinkingBudget': 0}


def test_embed_batch_shape_and_validation(tmp_path, monkeypatch):
    reply = lambda m, p, body: (200, {'embeddings': [{'values': [0.1, 0.2, 0.3]} for _ in body['requests']]})
    with fake_gemini(reply, monkeypatch) as seen:
        config = cfg(tmp_path, embedding_provider='gemini', embedding_model='gemini-embedding-001')
        vectors = gemini.embed(config, ['a', 'b'])
    assert vectors == [[0.1, 0.2, 0.3]] * 2
    assert seen[0]['path'].endswith('/models/gemini-embedding-001:batchEmbedContents')
    assert seen[0]['body']['requests'][0]['model'] == 'models/gemini-embedding-001'


@pytest.mark.parametrize('payload', [
    {'embeddings': [{'values': []}]}, {'embeddings': [{'values': ['x']}]}, {'embeddings': 'no'},
    {'embeddings': [{'values': [1.0]}, {'values': [1.0, 2.0]}]}])
def test_malformed_embeddings_rejected(tmp_path, monkeypatch, payload):
    with fake_gemini(lambda *a: (200, payload), monkeypatch):
        config = cfg(tmp_path, embedding_provider='gemini', embedding_model='gemini-embedding-001')
        with pytest.raises(ModelUnavailable):
            gemini.embed(config, ['a', 'b'][: 2 if len(payload.get('embeddings', [])) == 2 else 1])


# safety rules --------------------------------------------------------------
def test_paid_or_unlisted_model_is_refused_before_any_request(tmp_path, monkeypatch):
    with fake_gemini(lambda *a: text_reply('x'), monkeypatch) as seen:
        with pytest.raises(ModelUnavailable, match='free-tier allowlist'):
            gemini.chat(cfg(tmp_path, gemini_model='gemini-2.5-pro-latest-paid'), 's', 'u')
        with pytest.raises(ModelUnavailable, match='free-tier allowlist'):
            gemini.embed(cfg(tmp_path, embedding_model='text-embedding-004-paid'), ['a'])
    assert seen == []


def test_real_url_check_allows_only_google_over_https(monkeypatch):
    monkeypatch.undo()  # drop the autouse permissive patch
    monkeypatch.setenv('GEMINI_API_KEY', FAKE_KEY)
    for bad in ('http://generativelanguage.googleapis.com/v1beta', 'https://example.com/v1beta',
                'https://user:pw@generativelanguage.googleapis.com/v1beta', 'http://127.0.0.1:9/v1beta'):
        with pytest.raises(ModelUnavailable, match='Only https'):
            gemini._check_url(bad)
    gemini._check_url('https://generativelanguage.googleapis.com/v1beta/models')


def test_missing_key_is_a_clean_error(tmp_path, monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY')
    with fake_gemini(lambda *a: text_reply('x'), monkeypatch) as seen:
        with pytest.raises(ModelUnavailable, match='GEMINI_API_KEY is not set'):
            gemini.chat(cfg(tmp_path), 's', 'u')
    assert seen == []


def test_key_is_scrubbed_from_error_messages(tmp_path, monkeypatch):
    leak = lambda *a: (400, {'error': {'message': f'API key not valid: {FAKE_KEY}'}})
    with fake_gemini(leak, monkeypatch):
        with pytest.raises(ModelUnavailable) as caught:
            gemini.chat(cfg(tmp_path), 's', 'u')
    assert FAKE_KEY not in str(caught.value) and '***' in str(caught.value)


def test_billing_or_auth_error_stops_everything(tmp_path, monkeypatch):
    with fake_gemini(lambda *a: (403, {'error': {'message': 'billing must be enabled'}}), monkeypatch) as seen:
        with pytest.raises(ModelUnavailable, match='auth or billing'):
            gemini.chat(cfg(tmp_path), 's', 'u')
        with pytest.raises(ModelUnavailable, match='disabled for this process'):
            gemini.chat(cfg(tmp_path), 's', 'u')
    assert len(seen) == 1  # the second call never reached the network


def test_one_retry_on_429_then_success(tmp_path, monkeypatch):
    calls = iter([(429, {'error': {'message': 'slow down'}}), text_reply('ok [X]')])
    with fake_gemini(lambda *a: next(calls), monkeypatch) as seen:
        assert gemini.chat(cfg(tmp_path), 's', 'u')[0] == 'ok [X]'
    assert len(seen) == 2


def test_persistent_429_stops_instead_of_retrying_forever(tmp_path, monkeypatch):
    with fake_gemini(lambda *a: (429, {'error': {'message': 'quota'}}), monkeypatch) as seen:
        with pytest.raises(ModelUnavailable, match='quota'):
            gemini.chat(cfg(tmp_path), 's', 'u')
        with pytest.raises(ModelUnavailable, match='disabled for this process'):
            gemini.chat(cfg(tmp_path), 's', 'u')
    assert len(seen) == 2  # one try + one retry, nothing after that


def test_daily_quota_is_not_retried_at_all(tmp_path, monkeypatch):
    daily = (429, {'error': {'message': 'Quota exceeded for metric ... PerDay'}})
    with fake_gemini(lambda *a: daily, monkeypatch) as seen:
        with pytest.raises(ModelUnavailable):
            gemini.chat(cfg(tmp_path), 's', 'u')
    assert len(seen) == 1


def test_request_budget_is_enforced(tmp_path, monkeypatch):
    monkeypatch.setattr(gemini, 'MAX_REQUESTS', 2)
    with fake_gemini(lambda *a: text_reply('ok'), monkeypatch) as seen:
        gemini.chat(cfg(tmp_path), 's', 'u')
        gemini.chat(cfg(tmp_path), 's', 'u')
        with pytest.raises(ModelUnavailable, match='budget'):
            gemini.chat(cfg(tmp_path), 's', 'u')
    assert len(seen) == 2 and gemini.requests_made() == 2


@pytest.mark.parametrize('payload', [{'candidates': []}, {'promptFeedback': {'blockReason': 'SAFETY'}},
                                     {'candidates': [{'content': {'parts': [{'text': '  '}]}}]}, []])
def test_empty_blocked_or_odd_responses_are_unavailable(tmp_path, monkeypatch, payload):
    with fake_gemini(lambda *a: (200, payload), monkeypatch):
        with pytest.raises(ModelUnavailable):
            gemini.chat(cfg(tmp_path), 's', 'u')


# integration through the API ----------------------------------------------
def test_rag_through_api_is_labelled_hosted(tmp_path, monkeypatch):
    with fake_gemini(lambda *a: text_reply('Mặt bàn 120 x 60 cm [PRD-101]', 40, 9), monkeypatch):
        api = TestClient(create_app(settings=cfg(tmp_path)))
        result = api.post('/api/chat', json={'question': 'Bàn Oak 120 kích thước bao nhiêu?'}).json()
    assert result['mode'] == 'llm_rag_cited', result
    assert result['llm'] == {'provider': 'gemini', 'model': 'gemini-2.5-flash', 'hosted': True}
    assert (result['tokens_in'], result['tokens_out']) == (40, 9)


def test_agent_function_calling_roundtrip(tmp_path, monkeypatch):
    call_part = {'functionCall': {'name': 'lookup_product', 'args': {'sku': 'PRD-101'}}, 'thoughtSignature': 'sig'}
    replies = iter([(200, {'candidates': [{'content': {'role': 'model', 'parts': [call_part]}}],
                           'usageMetadata': {'promptTokenCount': 30, 'candidatesTokenCount': 5}}),
                    text_reply('Theo tài liệu: bàn Oak 120 x 60 cm [PRD-101]', 50, 12)])
    with fake_gemini(lambda *a: next(replies), monkeypatch) as seen:
        api = TestClient(create_app(settings=cfg(tmp_path)))
        result = api.post('/api/agent', json={'task': 'Tra cứu sản phẩm PRD-101'}).json()
    assert result['mode'] == 'tool_calling_agent', result
    assert result['steps'][0]['tool'] == 'lookup_product' and result['llm']['hosted'] is True
    first, second = seen[0]['body'], seen[1]['body']
    assert [d['name'] for d in first['tools'][0]['functionDeclarations']] == ['lookup_product', 'search_policy']
    assert second['contents'][1] == {'role': 'model', 'parts': [call_part]}  # original part replayed intact
    response = second['contents'][2]['parts'][0]['functionResponse']
    assert response['name'] == 'lookup_product' and response['response']['result']['found'] is True


def test_agent_with_gemini_still_rejects_unknown_tool(tmp_path, monkeypatch):
    bad = (200, {'candidates': [{'content': {'parts': [{'functionCall': {'name': 'publish_ad', 'args': {}}}]}}]})
    with fake_gemini(lambda *a: bad, monkeypatch):
        result = TestClient(create_app(settings=cfg(tmp_path))).post('/api/agent', json={'task': 'Publish ads now'}).json()
    assert result['mode'] == 'agent_tool_blocked'


def test_agent_gemini_failure_has_its_own_mode(tmp_path, monkeypatch):
    with fake_gemini(lambda *a: (500, {'error': 'boom'}), monkeypatch):
        result = TestClient(create_app(settings=cfg(tmp_path))).post('/api/agent', json={'task': 'Tra cứu sản phẩm PRD-101'}).json()
    assert result['mode'] == 'agent_llm_unavailable' and 'gemini' in result['answer']


def test_hybrid_retrieval_with_gemini_embeddings(tmp_path, monkeypatch):
    from app import retrieval
    from app.storage import Store

    def reply(method, path, body):
        vectors = [[1.0, 0.0] if ('mug' in r['content']['parts'][0]['text'].lower()) else [0.0, 1.0]
                   for r in body['requests']]
        return 200, {'embeddings': [{'values': v} for v in vectors]}

    with fake_gemini(reply, monkeypatch):
        config = cfg(tmp_path, llm_provider='off', embedding_provider='gemini', embedding_model='gemini-embedding-001')
        store = Store(config.data_path)
        assert retrieval.index_vectors(store, config)['indexed'] >= 10
        sources, mode = retrieval.search(store, config, 'personalized ceramic mug')
    assert mode == 'hybrid' and sources[0]['id'] == 'POD-201'
    assert store.document('POD-201')['embedding_model'] == 'gemini-embedding-001'


def test_health_probe_for_gemini(tmp_path, monkeypatch):
    tags = (200, {'models': [{'name': 'models/gemini-2.5-flash'}, {'name': 'models/gemini-embedding-001'}]})
    with fake_gemini(lambda *a: tags, monkeypatch):
        config = cfg(tmp_path, embedding_provider='gemini', embedding_model='gemini-embedding-001')
        body = TestClient(create_app(settings=config)).get('/api/health', params={'probe': 'true'}).json()
    assert body['providers']['gemini'] == {'reachable': True, 'llm_model_available': True, 'embedding_model_available': True}
    assert body['llm']['hosted'] is True
