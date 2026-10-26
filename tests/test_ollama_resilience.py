"""Adapter robustness against a FAKE local Ollama (HTTP contract only, not model quality)."""
import json
import threading
from contextlib import contextmanager
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.ollama import ModelUnavailable, chat, list_models, request_json


@contextmanager
def fake_ollama(handler_fn):
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def _serve(self):
            length = int(self.headers.get('Content-Length', '0'))
            body = json.loads(self.rfile.read(length)) if length else None
            seen.append((self.command, self.path, body))
            status, headers, raw = handler_fn(self.command, self.path, body)
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        do_GET = do_POST = _serve

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', seen
    finally:
        server.shutdown()
        server.server_close()


def json_reply(obj, status=200):
    return status, {'Content-Type': 'application/json'}, json.dumps(obj).encode()


def settings_for(url, **kw):
    options = {'ollama_url': url, 'llm_provider': 'ollama', 'embedding_provider': 'off', **kw}
    return replace(Settings(), **options)


def test_chat_sends_explicit_num_ctx():
    with fake_ollama(lambda *a: json_reply({'message': {'content': 'ok [X]'}, 'prompt_eval_count': 10, 'eval_count': 2})) as (url, seen):
        answer, tin, tout = chat(settings_for(url, num_ctx=3000), 'sys', 'user')
    assert (answer, tin, tout) == ('ok [X]', 10, 2)
    assert seen[0][2]['options']['num_ctx'] == 3000


def test_agent_sends_explicit_num_ctx(tmp_path):
    with fake_ollama(lambda *a: json_reply({'message': {'content': 'x'}})) as (url, seen):
        config = settings_for(url, data_path=tmp_path / 'a.db', num_ctx=2048)
        TestClient(create_app(settings=config)).post('/api/agent', json={'task': 'Tra cứu PRD-101'})
    assert seen and seen[0][2]['options']['num_ctx'] == 2048


@pytest.mark.parametrize('payload', [[1, 2], 'text', {'message': 'a string'}, {'message': {'content': ''}},
                                     {'message': {'content': ['x']}}])
def test_unexpected_json_shapes_are_model_unavailable_not_500(payload):
    with fake_ollama(lambda *a: json_reply(payload)) as (url, _):
        with pytest.raises(ModelUnavailable):
            chat(settings_for(url), 'sys', 'user')


def test_non_numeric_token_counts_do_not_crash():
    with fake_ollama(lambda *a: json_reply({'message': {'content': 'ok'}, 'prompt_eval_count': 'many', 'eval_count': None})) as (url, _):
        assert chat(settings_for(url), 's', 'u') == ('ok', 0, 0)


def test_http_error_body_is_reported():
    with fake_ollama(lambda *a: json_reply({'error': "model 'nope' not found"}, status=404)) as (url, _):
        with pytest.raises(ModelUnavailable, match="not found"):
            chat(settings_for(url), 's', 'u')


def test_redirects_are_not_followed():
    handler = lambda *a: (302, {'Location': 'http://example.com/api/chat'}, b'')
    with fake_ollama(handler) as (url, _):
        with pytest.raises(ModelUnavailable):
            request_json(url, '/api/chat', {'model': 'm'}, 3)


def test_system_proxy_is_ignored(monkeypatch):
    monkeypatch.setenv('HTTP_PROXY', 'http://127.0.0.1:9')
    monkeypatch.setenv('http_proxy', 'http://127.0.0.1:9')
    with fake_ollama(lambda *a: json_reply({'message': {'content': 'direct'}})) as (url, _):
        assert chat(settings_for(url), 's', 'u')[0] == 'direct'


def test_connection_refused_is_model_unavailable():
    with pytest.raises(ModelUnavailable):
        chat(settings_for('http://127.0.0.1:9'), 's', 'u')


def test_list_models_and_health_probe(tmp_path):
    tags = {'models': [{'name': 'qwen2.5:7b'}, {'name': 'bge-m3:latest'}]}
    with fake_ollama(lambda *a: json_reply(tags)) as (url, seen):
        config = settings_for(url, data_path=tmp_path / 'h.db', ollama_model='qwen2.5:7b',
                              embedding_provider='ollama', embedding_model='bge-m3')
        assert list_models(config) == ['qwen2.5:7b', 'bge-m3:latest']
        api = TestClient(create_app(settings=config))
        assert 'ollama' not in api.get('/api/health').json()          # default: no network call
        probe = api.get('/api/health', params={'probe': 'true'}).json()['ollama']
        assert probe == {'reachable': True, 'llm_model_available': True, 'embedding_model_available': True}
        missing = replace(config, ollama_model='llama3:8b')
        assert TestClient(create_app(settings=missing)).get('/api/health', params={'probe': 'true'}
                                                           ).json()['ollama']['llm_model_available'] is False


def test_health_probe_reports_unreachable(tmp_path):
    config = settings_for('http://127.0.0.1:9', data_path=tmp_path / 'h.db')
    body = TestClient(create_app(settings=config)).get('/api/health', params={'probe': 'true'}).json()
    assert body['status'] == 'ok' and body['ollama']['reachable'] is False


def test_context_window_flag_reports_near_limit(tmp_path, monkeypatch):
    from app import services
    monkeypatch.setattr(services, 'ollama_chat', lambda *a, **k: ('Theo tài liệu sản phẩm [PRD-101]', 1900, 8))
    config = replace(Settings(), data_path=tmp_path / 'c.db', llm_provider='ollama', embedding_provider='off', num_ctx=2048)
    result = TestClient(create_app(settings=config)).post('/api/chat', json={'question': 'Bàn Oak 120 kích thước bao nhiêu?'}).json()
    assert result['context_window'] == {'num_ctx': 2048, 'prompt_tokens': 1900, 'near_limit': True}
    off = replace(config, llm_provider='off')
    assert TestClient(create_app(settings=off)).post('/api/chat', json={'question': 'Bàn Oak 120 kích thước bao nhiêu?'}).json()['context_window'] is None
