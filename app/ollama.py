"""Ollama local API adapter; stdlib HTTP keeps the base demo lightweight."""
import json
import math
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


class ModelUnavailable(Exception):
    pass


def request_json(base_url: str, path: str, payload: dict, timeout: int):
    # This is a zero-paid-API local portfolio. Fail closed if config points to
    # an Internet host (also prevents accidental cloud billing / data leakage).
    parsed = urlsplit(base_url)
    if parsed.scheme != 'http' or parsed.hostname not in ('localhost', '127.0.0.1', '::1') or parsed.username or parsed.password:
        raise ModelUnavailable('Only local Ollama http://127.0.0.1:11434 is allowed in this release')
    if path not in ('/api/embed', '/api/chat'):
        raise ModelUnavailable('Unsupported Ollama API path')
    req = Request(base_url.rstrip("/") + path, data=json.dumps(payload).encode("utf-8"),
                  headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=timeout) as response:
            return json.loads(response.read(3_000_000).decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
        raise ModelUnavailable(str(exc)) from exc


def embed(settings, texts):
    resp = request_json(settings.ollama_url, "/api/embed", {"model": settings.embedding_model, "input": texts}, settings.timeout_seconds)
    vectors = resp.get("embeddings")
    if not isinstance(vectors, list) or len(vectors) != len(texts):
        raise ModelUnavailable("Ollama returned invalid embeddings")
    width = None
    for vector in vectors:
        if not isinstance(vector, list) or not vector:
            raise ModelUnavailable('Ollama returned an empty or malformed embedding vector')
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in vector):
            raise ModelUnavailable('Ollama returned nonfinite embedding values')
        if width is not None and len(vector) != width:
            raise ModelUnavailable('Ollama returned inconsistent embedding dimensions')
        width = len(vector)
    return vectors


def chat(settings, system, user, json_output=False):
    payload = {"model": settings.ollama_model, "stream": False,
               "messages": [{"role":"system","content":system},{"role":"user","content":user}],
               "options": {"num_predict": settings.max_output_tokens, "temperature": 0.2}}
    if json_output:
        payload["format"] = "json"
    resp = request_json(settings.ollama_url, "/api/chat", payload, settings.timeout_seconds)
    answer = (resp.get("message") or {}).get("content", "")
    if not answer:
        raise ModelUnavailable("Ollama returned empty answer")
    return answer, int(resp.get("prompt_eval_count") or 0), int(resp.get("eval_count") or 0)
