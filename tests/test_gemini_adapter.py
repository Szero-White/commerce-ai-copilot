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
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv('GEMINI_API_KEY', FAKE_KEY)
    # Never touch the real runtime/embedding_cache.db: fake vectors must not survive into a live run.
    monkeypatch.setattr(gemini, 'CACHE_ENABLED', False)
    monkeypatch.setattr(gemini, 'CACHE_PATH', tmp_path / 'test_cache.db')
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


def test_one_retry_on_transient_5xx_then_success(tmp_path, monkeypatch):
    calls = iter([(503, {'error': {'message': 'overloaded'}}), text_reply('ok [X]')])
    with fake_gemini(lambda *a: next(calls), monkeypatch) as seen:
        assert gemini.chat(cfg(tmp_path), 's', 'u')[0] == 'ok [X]'
    assert len(seen) == 2


def test_5xx_twice_fails_without_disabling_the_process(tmp_path, monkeypatch):
    replies = iter([(503, {'error': {}}), (503, {'error': {}}), text_reply('later ok')])
    with fake_gemini(lambda *a: next(replies), monkeypatch) as seen:
        with pytest.raises(ModelUnavailable, match='HTTP 503'):
            gemini.chat(cfg(tmp_path), 's', 'u')
        assert gemini.chat(cfg(tmp_path), 's', 'u')[0] == 'later ok'
    assert len(seen) == 3


def test_429_stops_at_once_without_retry(tmp_path, monkeypatch):
    with fake_gemini(lambda *a: (429, {'error': {'message': 'quota'}}), monkeypatch) as seen:
        with pytest.raises(ModelUnavailable, match='rate limit'):
            gemini.chat(cfg(tmp_path), 's', 'u')
        with pytest.raises(ModelUnavailable, match='disabled for this process'):
            gemini.chat(cfg(tmp_path), 's', 'u')
    assert len(seen) == 1  # no retry, and nothing after the stop


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


def test_embed_splits_large_inputs_into_small_requests(tmp_path, monkeypatch):
    reply = lambda m, p, body: (200, {'embeddings': [{'values': [0.5, 0.5]} for _ in body['requests']]})
    with fake_gemini(reply, monkeypatch) as seen:
        config = cfg(tmp_path, embedding_provider='gemini', embedding_model='gemini-embedding-001')
        vectors = gemini.embed(config, [f'text {i}' for i in range(40)])
    assert len(vectors) == 40
    assert [len(r['body']['requests']) for r in seen] == [8, 8, 8, 8, 8]  # a 60-text batch overflowed the 3 MB cap live


def test_truncated_oversized_response_is_a_clear_error(tmp_path, monkeypatch):
    monkeypatch.setattr(gemini, 'MAX_RESPONSE_BYTES', 200)
    big = {'candidates': [{'content': {'parts': [{'text': 'x' * 1000}]}}]}
    with fake_gemini(lambda *a: (200, big), monkeypatch):
        with pytest.raises(ModelUnavailable, match='larger than'):
            gemini.chat(cfg(tmp_path), 's', 'u')


# ------------------------------------------------------------------------------------------------
# Embedding rate limiter (per TEXT), text budget, cache, 429 classification, smoke mode
# ------------------------------------------------------------------------------------------------
import sqlite3

from app.embedding_cache import EmbeddingCache
from scripts import live_eval


@pytest.fixture
def fake_clock(monkeypatch):
    clock = {'t': 1000.0, 'sleeps': []}
    monkeypatch.setattr(gemini, '_now', lambda: clock['t'])

    def sleep(seconds):
        clock['sleeps'].append(round(seconds, 3))
        clock['t'] += seconds
    monkeypatch.setattr(gemini, '_sleep', sleep)
    return clock


def vector_reply(method, path, body):
    """One deterministic 3-d vector per text, so cache hits can be compared exactly."""
    return 200, {'embeddings': [{'values': [float(len(r['content']['parts'][0]['text'])), 1.0, 0.5]}
                                for r in body['requests']]}


def emb_cfg(tmp_path, **kw):
    return cfg(tmp_path, embedding_provider='gemini', embedding_model='gemini-embedding-001', **kw)


def texts_in(request):
    return [r['content']['parts'][0]['text'] for r in request['body']['requests']]


def test_batches_are_spaced_by_the_number_of_texts(tmp_path, monkeypatch, fake_clock):
    with fake_gemini(vector_reply, monkeypatch) as seen:
        gemini.embed(emb_cfg(tmp_path), [f'text {i}' for i in range(24)])
    assert [len(r['body']['requests']) for r in seen] == [8, 8, 8]
    assert fake_clock['sleeps'] == [8.0, 8.0]        # 8 texts at 60/min = 8 s between batches
    assert gemini.embed_texts_sent() == 24


def test_spacing_also_applies_across_separate_calls(tmp_path, monkeypatch, fake_clock):
    with fake_gemini(vector_reply, monkeypatch):
        gemini.embed(emb_cfg(tmp_path), [f'a{i}' for i in range(8)])
        gemini.embed(emb_cfg(tmp_path), [f'b{i}' for i in range(8)])    # immediately after
        fake_clock['t'] += 100                                           # a quiet minute and a half
        gemini.embed(emb_cfg(tmp_path), [f'c{i}' for i in range(8)])
    assert fake_clock['sleeps'] == [8.0]


def test_slower_configured_rate_spaces_batches_further(tmp_path, monkeypatch, fake_clock):
    monkeypatch.setattr(gemini, 'EMBED_TEXTS_PER_MINUTE', 30)
    with fake_gemini(vector_reply, monkeypatch):
        gemini.embed(emb_cfg(tmp_path), [f'text {i}' for i in range(16)])
    assert fake_clock['sleeps'] == [16.0]


def test_rate_setting_is_clamped_below_the_tier_limit():
    assert gemini._clamp_rate('500') == 90 and gemini._clamp_rate('0') == 1
    assert gemini._clamp_rate('abc') == 60 and gemini._clamp_rate(None) == 60 and gemini.EMBED_TEXTS_PER_MINUTE == 60


def test_embed_text_budget_blocks_before_anything_is_sent(tmp_path, monkeypatch, fake_clock):
    monkeypatch.setattr(gemini, 'MAX_EMBED_TEXTS', 10)
    with fake_gemini(vector_reply, monkeypatch) as seen:
        with pytest.raises(ModelUnavailable, match='embed-text budget'):
            gemini.embed(emb_cfg(tmp_path), [f'x{i}' for i in range(12)])
        assert seen == []
        gemini.embed(emb_cfg(tmp_path), [f'y{i}' for i in range(8)])
        with pytest.raises(ModelUnavailable, match='embed-text budget'):
            gemini.embed(emb_cfg(tmp_path), [f'z{i}' for i in range(8)])
    assert len(seen) == 1


def test_cache_means_unchanged_texts_are_never_embedded_twice(tmp_path, monkeypatch, fake_clock):
    monkeypatch.setattr(gemini, 'CACHE_ENABLED', True)
    config = emb_cfg(tmp_path)
    with fake_gemini(vector_reply, monkeypatch) as seen:
        first = gemini.embed(config, ['alpha', 'beta', 'alpha'])            # duplicate sent once
        assert texts_in(seen[0]) == ['alpha', 'beta'] and first[0] == first[2]
        gemini.reset_budget()                                                # "a new process"
        again = gemini.embed(config, ['alpha', 'beta', 'alpha'])
        assert again == first and len(seen) == 1 and gemini.requests_made() == 0
        gemini.embed(config, ['alpha', 'gamma'])                            # only the new text travels
        assert texts_in(seen[1]) == ['gamma'] and len(seen) == 2
        gemini.embed(replace(config, embedding_model='gemini-embedding-2'), ['alpha'])   # other model = miss
        assert len(seen) == 3 and seen[2]['path'].endswith('gemini-embedding-2:batchEmbedContents')


def test_changed_text_is_a_miss_and_cache_holds_no_secret(tmp_path, monkeypatch, fake_clock):
    monkeypatch.setattr(gemini, 'CACHE_ENABLED', True)
    with fake_gemini(vector_reply, monkeypatch) as seen:
        gemini.embed(emb_cfg(tmp_path), ['Bàn Oak 120'])
        gemini.embed(emb_cfg(tmp_path), ['Bàn Oak 121'])
    assert len(seen) == 2
    assert FAKE_KEY.encode() not in (tmp_path / 'test_cache.db').read_bytes()


def test_corrupt_cache_row_is_ignored_not_trusted(tmp_path, monkeypatch, fake_clock):
    monkeypatch.setattr(gemini, 'CACHE_ENABLED', True)
    cache = EmbeddingCache(gemini.CACHE_PATH)
    cache.put_many('gemini-embedding-001', {'x': [1.0, 2.0]})
    with sqlite3.connect(gemini.CACHE_PATH) as cx:
        cx.execute("UPDATE embeddings SET vector_json='[\"not a number\"]'")
    with fake_gemini(vector_reply, monkeypatch) as seen:
        vectors = gemini.embed(emb_cfg(tmp_path), ['x'])
    assert len(seen) == 1 and vectors == [[1.0, 1.0, 0.5]]


def test_work_done_before_a_429_is_kept_for_the_next_run(tmp_path, monkeypatch, fake_clock):
    monkeypatch.setattr(gemini, 'CACHE_ENABLED', True)
    texts = [f'doc {i}' for i in range(12)]
    state = {'calls': 0}

    def flaky(method, path, body):
        state['calls'] += 1
        return vector_reply(method, path, body) if state['calls'] == 1 else (429, {'error': {'message': 'quota'}})

    with fake_gemini(flaky, monkeypatch):
        with pytest.raises(ModelUnavailable, match='429'):
            gemini.embed(emb_cfg(tmp_path), texts)
    assert EmbeddingCache(gemini.CACHE_PATH).count() == 8      # the first batch was saved
    gemini.reset_budget()
    with fake_gemini(vector_reply, monkeypatch) as seen:
        gemini.embed(emb_cfg(tmp_path), texts)
    assert texts_in(seen[0]) == texts[8:]                      # only the missing 4 are requested


def test_embedding_limiter_does_not_slow_chat_calls(tmp_path, monkeypatch, fake_clock):
    with fake_gemini(lambda *a: text_reply('ok'), monkeypatch):
        for _ in range(3):
            gemini.chat(cfg(tmp_path), 's', 'u')
    assert fake_clock['sleeps'] == []


# 429 classification ---------------------------------------------------------------------------
BILLING_WORDING = {'error': {'code': 429, 'status': 'RESOURCE_EXHAUSTED',
                             'message': 'You exceeded your current quota, please check your plan and billing details.'}}


def test_429_mentioning_billing_is_a_rate_limit_not_a_billing_error(tmp_path, monkeypatch):
    with fake_gemini(lambda *a: (429, BILLING_WORDING), monkeypatch) as seen:
        with pytest.raises(ModelUnavailable) as caught:
            gemini.chat(cfg(tmp_path), 's', 'u')
    message = str(caught.value)
    assert 'per-minute rate limit' in message and 'not an auth/billing error' in message
    assert 'auth or billing' not in message.replace('not an auth/billing error', '')
    assert len(seen) == 1 and '429' in gemini._state['stopped'] and 'auth' not in gemini._state['stopped']


def test_429_with_daily_quota_detail_is_reported_as_daily(tmp_path, monkeypatch):
    daily = {'error': {'code': 429, 'message': 'quota', 'details': [{'@type': 'type.googleapis.com/google.rpc.QuotaFailure',
             'violations': [{'quotaId': 'EmbedContentRequestsPerDayPerProjectPerModel-FreeTier'}]}]}}
    with fake_gemini(lambda *a: (429, daily), monkeypatch):
        with pytest.raises(ModelUnavailable, match='daily quota'):
            gemini.chat(cfg(tmp_path), 's', 'u')


def test_real_auth_and_precondition_errors_still_stop_as_billing(tmp_path, monkeypatch):
    for status, body in ((403, {'error': {'status': 'PERMISSION_DENIED', 'message': 'denied'}}),
                         (400, {'error': {'status': 'FAILED_PRECONDITION', 'message': 'not available'}})):
        gemini.reset_budget()
        with fake_gemini(lambda *a: (status, body), monkeypatch):
            with pytest.raises(ModelUnavailable, match='auth or billing'):
                gemini.chat(cfg(tmp_path), 's', 'u')
        assert 'auth/billing' in gemini._state['stopped']


def test_the_word_billing_alone_does_not_stop_the_process(tmp_path, monkeypatch):
    replies = iter([(400, {'error': {'status': 'INVALID_ARGUMENT', 'message': 'see billing docs'}}), text_reply('fine')])
    with fake_gemini(lambda *a: next(replies), monkeypatch):
        with pytest.raises(ModelUnavailable, match='HTTP 400'):
            gemini.chat(cfg(tmp_path), 's', 'u')
        assert gemini.chat(cfg(tmp_path), 's', 'u')[0] == 'fine'


# smoke mode -------------------------------------------------------------------------------------
@pytest.fixture
def smoke_env(tmp_path, monkeypatch):
    monkeypatch.setenv('GEMINI_CONFIRM_FREE_TIER', 'yes')
    monkeypatch.setattr(live_eval, 'Settings', lambda: replace(
        Settings(), llm_provider='gemini', embedding_provider='gemini', gemini_model='gemini-2.5-flash',
        embedding_model='gemini-embedding-001'))
    monkeypatch.setattr(live_eval, 'REPORT_DIR', tmp_path / 'reports')
    monkeypatch.setattr(live_eval, 'DB_PATH', tmp_path / 'live.db')
    monkeypatch.setattr(live_eval, 'PACE_SECONDS', 0)


def smoke_handler(method, path, body):
    if method == 'GET':
        return 200, {'models': [{'name': 'models/gemini-2.5-flash'}, {'name': 'models/gemini-embedding-001'}]}
    return text_reply('Mặt bàn 120 x 60 cm [PRD-101]', 40, 9)


def test_smoke_mode_embeds_nothing_and_stays_small(tmp_path, monkeypatch, smoke_env):
    with fake_gemini(smoke_handler, monkeypatch) as seen:
        assert live_eval.main([]) == 0
    assert not any('Embed' in r['path'] for r in seen), [r['path'] for r in seen]
    report = json.loads((tmp_path / 'reports' / 'live_eval_gemini_smoke.json').read_text(encoding='utf-8'))
    assert report['mode'] == 'smoke' and report['embedding_model'] is None
    assert report['embed_texts_sent'] == 0 and report['requests_made'] <= 7
    assert {c['id'] for c in report['rag_cases']} == {'dims', 'negated-policy', 'document-injection', 'off-topic', 'coupon'}
    assert [c['mode'] for c in report['rag_cases'] if c['expect'] == 'abstain'] == ['no_evidence', 'no_evidence']
    assert all(c['retrieval_mode'] == 'lexical' for c in report['rag_cases'])
    assert len(report['agent']) == 1 and 'campaign' in report and report['campaign'] == []
    assert FAKE_KEY not in json.dumps(report)


def test_smoke_refuses_without_free_tier_confirmation(tmp_path, monkeypatch, smoke_env, capsys):
    monkeypatch.delenv('GEMINI_CONFIRM_FREE_TIER')
    with fake_gemini(smoke_handler, monkeypatch) as seen:
        assert live_eval.main([]) == 2
    assert seen == [] and 'Nothing was called' in capsys.readouterr().out


def test_full_mode_needs_the_embedding_provider(tmp_path, monkeypatch, smoke_env, capsys):
    monkeypatch.setattr(live_eval, 'Settings', lambda: replace(Settings(), llm_provider='gemini', embedding_provider='off'))
    with fake_gemini(smoke_handler, monkeypatch) as seen:
        assert live_eval.main(['--full']) == 2
    assert seen == []


def test_smoke_stops_on_429_and_records_why(tmp_path, monkeypatch, smoke_env):
    def handler(method, path, body):
        return (200, {'models': [{'name': 'models/gemini-2.5-flash'}]}) if method == 'GET' else (429, BILLING_WORDING)
    with fake_gemini(handler, monkeypatch) as seen:
        assert live_eval.main([]) == 1
    report = json.loads((tmp_path / 'reports' / 'live_eval_gemini_smoke.json').read_text(encoding='utf-8'))
    assert 'per-minute rate limit' in report['stopped_early'] and report['requests_made'] == 2
    assert len(seen) == 2   # the model list and the first generation; nothing retried, nothing switched
