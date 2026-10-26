"""Ollama local API adapter; stdlib HTTP keeps the base demo lightweight."""
import json
import math
from http.client import HTTPException
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from urllib.error import HTTPError, URLError


class ModelUnavailable(Exception):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # A local model server has no reason to bounce us to another host.


# ProxyHandler({}) ignores HTTP(S)_PROXY and Windows proxy settings: prompts and documents
# must only ever travel to the loopback Ollama server.
_OPENER = build_opener(ProxyHandler({}), _NoRedirect)


def _check_local(base_url: str):
    # This is a zero-paid-API local portfolio. Fail closed if config points to
    # an Internet host (also prevents accidental cloud billing / data leakage).
    parsed = urlsplit(base_url)
    if parsed.scheme != 'http' or parsed.hostname not in ('localhost', '127.0.0.1', '::1') or parsed.username or parsed.password:
        raise ModelUnavailable('Only local Ollama http://127.0.0.1:11434 is allowed in this release')


def _send(req: Request, timeout: int):
    try:
        with _OPENER.open(req, timeout=timeout) as response:
            data = json.loads(response.read(3_000_000).decode("utf-8"))
    except HTTPError as exc:
        # Ollama explains failures in the body, e.g. {"error": "model 'x' not found"}.
        try:
            detail = exc.read(300).decode("utf-8", "replace")
        except Exception:
            detail = ""
        raise ModelUnavailable(f"HTTP {exc.code} from Ollama: {detail or exc.reason}") from exc
    except (URLError, TimeoutError, ValueError, OSError, HTTPException) as exc:
        raise ModelUnavailable(str(exc)) from exc
    if not isinstance(data, dict):
        raise ModelUnavailable('Ollama returned unexpected JSON (not an object)')
    return data


def request_json(base_url: str, path: str, payload: dict, timeout: int):
    _check_local(base_url)
    if path not in ('/api/embed', '/api/chat'):
        raise ModelUnavailable('Unsupported Ollama API path')
    req = Request(base_url.rstrip("/") + path, data=json.dumps(payload).encode("utf-8"),
                  headers={"Content-Type": "application/json"}, method="POST")
    return _send(req, timeout)


def list_models(settings) -> list[str]:
    """Installed model names from GET /api/tags (read-only reachability probe)."""
    _check_local(settings.ollama_url)
    data = _send(Request(settings.ollama_url.rstrip("/") + "/api/tags", method="GET"),
                 min(settings.timeout_seconds, 5))
    models = data.get("models")
    if not isinstance(models, list):
        raise ModelUnavailable('Ollama returned an unexpected /api/tags response')
    return [m.get("name", "") for m in models if isinstance(m, dict)]


def has_model(installed: list[str], wanted: str) -> bool:
    return any(name == wanted or name.startswith(wanted + ":") for name in installed)


def count(value) -> int:
    """Token counters from the server; anything that is not a number counts as 0."""
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else 0


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
    # num_ctx is explicit: otherwise Ollama applies its own default window and silently
    # drops the START of an over-long prompt, which is where the system instructions are.
    payload = {"model": settings.ollama_model, "stream": False,
               "messages": [{"role":"system","content":system},{"role":"user","content":user}],
               "options": {"num_predict": settings.max_output_tokens, "temperature": 0.2,
                           "num_ctx": settings.num_ctx}}
    if json_output:
        payload["format"] = "json"
    resp = request_json(settings.ollama_url, "/api/chat", payload, settings.timeout_seconds)
    message = resp.get("message")
    answer = message.get("content", "") if isinstance(message, dict) else ""
    if not isinstance(answer, str) or not answer.strip():
        raise ModelUnavailable("Ollama returned empty answer")
    return answer, count(resp.get("prompt_eval_count")), count(resp.get("eval_count"))
