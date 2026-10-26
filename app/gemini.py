"""Google Gemini API adapter (HOSTED, free tier only). Separate from the local Ollama adapter.

Rules enforced here, not left to configuration:
- only https://generativelanguage.googleapis.com, no redirects;
- the API key comes from the GEMINI_API_KEY environment variable, is sent in a header (never in a
  URL) and is scrubbed from every error message; it is never stored in Settings or logged;
- only models on the free-tier allowlist may be called (a paid model raises before any request);
- a hard per-process request budget and a hard budget of TEXTS embedded;
- embeddings are metered per TEXT, not per HTTP request, so they go through a rate limiter that
  spaces batches by the number of texts they carry (default 60 texts/minute against a 100 RPM tier);
- an on-disk cache means an unchanged text is never embedded twice (see embedding_cache.py);
- errors are classified by HTTP status first: 429 is ALWAYS a rate/quota problem (never "billing",
  whatever the body says) and stops the process without retrying; 5xx gets one retry; 401/403 or
  FAILED_PRECONDITION stop everything as an auth/billing problem.
Only synthetic catalogue/policy text should ever be sent through this adapter.
"""
import json
import os
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from pathlib import Path
from urllib.request import HTTPRedirectHandler, Request, build_opener
from http.client import HTTPException

from .config import ROOT
from .embedding_cache import EmbeddingCache
from .ollama import ModelUnavailable, count

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
ALLOWED_HOSTS = ("generativelanguage.googleapis.com",)
# "Free of charge" on https://ai.google.dev/gemini-api/docs/pricing (re-checked 2026-10-26). The 2.5
# generation models are kept but are restricted to projects that already used them (a new project
# gets HTTP 404): https://ai.google.dev/gemini-api/docs/deprecations recommends gemini-3.5-flash-lite
# or gemini-3.8-flash for new projects. Anything not listed needs an explicit, deliberate edit here.
FREE_MODELS = {"gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite",
               "gemini-2.5-flash", "gemini-2.5-flash-lite",
               "gemini-embedding-001", "gemini-embedding-2"}
MAX_REQUESTS = int(os.getenv("GEMINI_MAX_REQUESTS", "150"))
MAX_RESPONSE_BYTES = 3_000_000


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


# Embeddings: the 100 RPM free tier counts every text in a batch. Stay well below it.
def _clamp_rate(value) -> int:
    """Texts per minute: default 60, never above 90 (a 100 RPM tier needs headroom), never below 1."""
    try:
        return min(max(int(value), 1), 90)
    except (TypeError, ValueError):
        return 60


EMBED_TEXTS_PER_MINUTE = _clamp_rate(os.getenv("GEMINI_EMBED_TEXTS_PER_MINUTE", "60"))
EMBED_BATCH = 8
MAX_EMBED_TEXTS = _int_env("GEMINI_MAX_EMBED_TEXTS", 200)  # per process; the free tier allows ~1000/day
CACHE_ENABLED = os.getenv("GEMINI_EMBED_CACHE", "on").lower() != "off"
CACHE_PATH = Path(os.getenv("EMBEDDING_CACHE_PATH", str(ROOT / "runtime" / "embedding_cache.db")))

_lock = threading.Lock()
_state = {"requests": 0, "stopped": None, "embed_texts": 0, "embed_next_at": 0.0, "last_error": None}
_no_thinking_config = set()  # models whose server rejected thinkingConfig once


def _now() -> float:
    return time.monotonic()


def _sleep(seconds: float):
    time.sleep(seconds)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


_OPENER = build_opener(_NoRedirect)


def reset_budget():
    with _lock:
        _state.update(requests=0, stopped=None, embed_texts=0, embed_next_at=0.0, last_error=None)
        _no_thinking_config.clear()


def requests_made() -> int:
    return _state["requests"]


def embed_texts_sent() -> int:
    return _state["embed_texts"]


def last_error():
    """The last failure message (key already scrubbed), for reports."""
    return _state["last_error"]


def stopped_reason():
    """Why this process stopped calling Gemini (quota, auth/billing), or None."""
    return _state["stopped"]


def _key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise ModelUnavailable("GEMINI_API_KEY is not set")
    return key


def _scrub(text: str) -> str:
    key = os.environ.get("GEMINI_API_KEY", "")
    return text.replace(key, "***") if key else text


def _check_url(url: str):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS or parsed.username or parsed.password:
        raise ModelUnavailable("Only https://generativelanguage.googleapis.com is allowed")


def _check_model(model: str):
    if model not in FREE_MODELS:
        raise ModelUnavailable(f"Model '{model}' is not on the free-tier allowlist; refusing to call it")


def _error_info(body: str) -> dict:
    try:
        data = json.loads(body)
    except ValueError:
        return {}
    error = data.get("error") if isinstance(data, dict) else None
    return error if isinstance(error, dict) else {}


def _is_daily_quota(error: dict, body: str) -> bool:
    ids = []
    for detail in error.get("details") or []:
        if isinstance(detail, dict):
            for violation in detail.get("violations") or []:
                if isinstance(violation, dict):
                    ids.append(f"{violation.get('quotaId', '')} {violation.get('quotaMetric', '')}")
    text = (" ".join(ids) or body).lower().replace("_", "").replace(" ", "")
    return "perday" in text or "daily" in text


def _send(method: str, path: str, payload, timeout: int):
    url = BASE_URL + path
    _check_url(url)
    with _lock:
        if _state["stopped"]:
            raise ModelUnavailable(f"Gemini disabled for this process: {_state['stopped']}")
        if _state["requests"] >= MAX_REQUESTS:
            raise ModelUnavailable(f"Gemini request budget ({MAX_REQUESTS}) exhausted for this process")
    for attempt in (1, 2):
        with _lock:
            _state["requests"] += 1
        req = Request(url, data=None if payload is None else json.dumps(payload).encode("utf-8"), method=method,
                      headers={"Content-Type": "application/json", "x-goog-api-key": _key()})
        try:
            with _OPENER.open(req, timeout=timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ModelUnavailable(f"Gemini response larger than {MAX_RESPONSE_BYTES} bytes; refusing to parse a truncated body")
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict):
                raise ModelUnavailable("Gemini returned unexpected JSON (not an object)")
            return data
        except HTTPError as exc:
            try:
                body = exc.read(4000).decode("utf-8", "replace")
            except Exception:
                body = ""
            body = _scrub(body)
            error = _error_info(body)
            status = str(error.get("status", "")).upper()
            if exc.code == 429:
                # Classified by status code ALONE: the body of a rate-limit error may mention
                # "billing" or "plan" without the project having any billing problem.
                kind = "daily quota" if _is_daily_quota(error, body) else "per-minute rate limit"
                _state["stopped"] = f"HTTP 429 {kind}; stopped without retrying"
                _fail(f"HTTP 429 from Gemini ({kind}, not an auth/billing error): {body[:400]}", exc)
            if exc.code in (401, 403) or status in ("PERMISSION_DENIED", "UNAUTHENTICATED", "FAILED_PRECONDITION"):
                _state["stopped"] = f"HTTP {exc.code} (auth/billing); not retrying"
                _fail(f"HTTP {exc.code} from Gemini (auth or billing): {body[:400]}", exc)
            if exc.code == 404 and "generateContent" in path:
                # e.g. "This model models/gemini-2.5-flash is no longer available to new users": retrying
                # or looping over cases would only burn requests.
                _state["stopped"] = "HTTP 404 model not available to this project; choose a current model"
                _fail(f"HTTP 404 from Gemini (model not available to this project; for a new project use "
                      f"gemini-3.5-flash-lite or gemini-3.8-flash): {body[:400]}", exc)
            if exc.code in (500, 502, 503, 504) and attempt == 1:
                _sleep(5)  # one retry for a transient server error, nothing more
                continue
            _fail(f"HTTP {exc.code} from Gemini: {body[:400]}", exc)
        except (URLError, TimeoutError, ValueError, OSError, HTTPException) as exc:
            _fail(_scrub(str(exc)), exc)
    raise ModelUnavailable("Gemini request failed")


def _fail(message: str, cause):
    _state["last_error"] = message
    raise ModelUnavailable(message) from cause


def list_models(settings) -> list[str]:
    """Names (without the 'models/' prefix) the key can see; read-only, no generation cost."""
    data = _send("GET", "/models?pageSize=200", None, min(settings.timeout_seconds, 20))
    models = data.get("models")
    if not isinstance(models, list):
        raise ModelUnavailable("Gemini returned an unexpected models response")
    return [m.get("name", "").removeprefix("models/") for m in models if isinstance(m, dict)]


def list_model_details(settings) -> list[dict]:
    """[{name, methods}] for every model the key can see (read-only, one request)."""
    data = _send("GET", "/models?pageSize=200", None, min(settings.timeout_seconds, 20))
    models = data.get("models")
    if not isinstance(models, list):
        raise ModelUnavailable("Gemini returned an unexpected models response")
    return [{"name": m.get("name", "").removeprefix("models/"),
             "methods": [x for x in (m.get("supportedGenerationMethods") or []) if isinstance(x, str)]}
            for m in models if isinstance(m, dict)]


def _generation_config(settings, model: str, json_output: bool) -> dict:
    config = {"temperature": 0.2, "maxOutputTokens": settings.max_output_tokens}
    if json_output:
        config["responseMimeType"] = "application/json"
    if model.startswith("gemini-2.5-flash"):
        config["thinkingConfig"] = {"thinkingBudget": 0}  # thinking tokens would eat the output budget
    elif model.startswith("gemini-3") and model not in _no_thinking_config:
        # Gemini 3 uses a thinking *level*; leave headroom because thought tokens may count as output.
        config["thinkingConfig"] = {"thinkingLevel": "minimal"}
        config["maxOutputTokens"] = max(settings.max_output_tokens, 1024)
    return config


def _generate(settings, model: str, payload: dict):
    """POST generateContent; if the server rejects thinkingConfig, retry ONCE without it."""
    path = f"/models/{model}:generateContent"
    try:
        return _send("POST", path, payload, settings.timeout_seconds)
    except ModelUnavailable as exc:
        config = payload.get("generationConfig", {})
        if "thinkingConfig" in config and "HTTP 400" in str(exc) and "thinking" in str(exc).lower():
            _no_thinking_config.add(model)
            stripped = {**payload, "generationConfig": {k: v for k, v in config.items() if k != "thinkingConfig"}}
            return _send("POST", path, stripped, settings.timeout_seconds)
        raise


def _parse(data: dict):
    feedback = data.get("promptFeedback") or {}
    if feedback.get("blockReason"):
        raise ModelUnavailable(f"Gemini blocked the prompt: {feedback['blockReason']}")
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates or not isinstance(candidates[0], dict):
        raise ModelUnavailable("Gemini returned no candidates")
    content = candidates[0].get("content")
    parts = content.get("parts") if isinstance(content, dict) else None
    if not parts and candidates[0].get("finishReason"):
        raise ModelUnavailable(f"Gemini returned no content (finishReason={candidates[0]['finishReason']})")
    usage = data.get("usageMetadata") if isinstance(data.get("usageMetadata"), dict) else {}
    return (parts if isinstance(parts, list) else []), count(usage.get("promptTokenCount")), count(usage.get("candidatesTokenCount"))


def chat(settings, system, user, json_output=False):
    model = settings.gemini_model
    _check_model(model)
    payload = {"systemInstruction": {"parts": [{"text": system}]},
               "contents": [{"role": "user", "parts": [{"text": user}]}],
               "generationConfig": _generation_config(settings, model, json_output)}
    data = _generate(settings, model, payload)
    parts, tokens_in, tokens_out = _parse(data)
    answer = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and isinstance(p.get("text"), str)).strip()
    if not answer:
        raise ModelUnavailable("Gemini returned an empty answer")
    return answer, tokens_in, tokens_out


def _wait_for_embed_slot(n_texts: int):
    """Reserve the next slot so that batches are spaced by the number of TEXTS they carry."""
    with _lock:
        now = _now()
        start = max(now, _state["embed_next_at"])
        _state["embed_next_at"] = start + n_texts * 60.0 / EMBED_TEXTS_PER_MINUTE
    if start > now:
        _sleep(start - now)


def embed(settings, texts):
    model = settings.embedding_model
    _check_model(model)
    texts = list(texts)
    cache = EmbeddingCache(CACHE_PATH) if CACHE_ENABLED else None
    known = cache.get_many(model, texts) if cache else {}
    missing = [x for x in dict.fromkeys(texts) if x not in known]
    with _lock:
        remaining = MAX_EMBED_TEXTS - _state["embed_texts"]
    if len(missing) > remaining:
        raise ModelUnavailable(f"Gemini embed-text budget ({MAX_EMBED_TEXTS}) would be exceeded: "
                               f"{len(missing)} new texts requested, {max(remaining, 0)} left; nothing was sent")
    for start in range(0, len(missing), EMBED_BATCH):
        chunk = missing[start:start + EMBED_BATCH]
        _wait_for_embed_slot(len(chunk))
        payload = {"requests": [{"model": f"models/{model}", "content": {"parts": [{"text": x}]}} for x in chunk]}
        with _lock:
            _state["embed_texts"] += len(chunk)
        data = _send("POST", f"/models/{model}:batchEmbedContents", payload, settings.timeout_seconds)
        items = data.get("embeddings")
        if not isinstance(items, list) or len(items) != len(chunk):
            raise ModelUnavailable("Gemini returned invalid embeddings")
        fresh = {}
        for text, item in zip(chunk, items):
            values = item.get("values") if isinstance(item, dict) else None
            if (not isinstance(values, list) or not values
                    or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in values)):
                raise ModelUnavailable("Gemini returned a malformed embedding vector")
            fresh[text] = values
        known.update(fresh)
        if cache:
            cache.put_many(model, fresh)  # saved per batch: a later 429 must not waste this work
    vectors = [known[x] for x in texts]
    if len({len(v) for v in vectors}) > 1:
        raise ModelUnavailable("Gemini returned inconsistent embedding dimensions")
    return vectors


def _contents(messages: list[dict]):
    """Ollama-style message list -> Gemini (systemInstruction, contents)."""
    system, contents = None, []
    for message in messages:
        role = message.get("role")
        if role == "system":
            system = {"parts": [{"text": message.get("content", "")}]}
        elif role == "user":
            contents.append({"role": "user", "parts": [{"text": message.get("content", "")}]})
        elif role == "assistant":
            parts = []
            if message.get("content"):
                parts.append({"text": message["content"]})
            for call in message.get("tool_calls") or []:
                parts.append(call.get("_gemini_part") or {"functionCall": {
                    "name": (call.get("function") or {}).get("name", ""),
                    "args": (call.get("function") or {}).get("arguments") or {}}})
            contents.append({"role": "model", "parts": parts or [{"text": ""}]})
        elif role == "tool":
            try:
                result = json.loads(message.get("content", "{}"))
            except ValueError:
                result = {"raw": message.get("content", "")[:500]}
            contents.append({"role": "user", "parts": [{"functionResponse": {
                "name": message.get("tool_name", ""), "response": {"result": result}}}]})
    return system, contents


def chat_with_tools(settings, messages, tools, allow_tools=True):
    """One tool-calling turn; returns an Ollama-shaped result so agent.py handles both providers."""
    model = settings.gemini_model
    _check_model(model)
    system, contents = _contents(messages)
    payload = {"contents": contents,
               "tools": [{"functionDeclarations": [t["function"] for t in tools]}],
               "generationConfig": _generation_config(settings, model, False)}
    if system:
        payload["systemInstruction"] = system
    if not allow_tools:
        payload["toolConfig"] = {"functionCallingConfig": {"mode": "NONE"}}  # final turn: text only
    data = _generate(settings, model, payload)
    parts, tokens_in, tokens_out = _parse(data)
    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and isinstance(p.get("text"), str))
    calls = [{"function": {"name": p["functionCall"].get("name", ""), "arguments": p["functionCall"].get("args") or {}},
              "_gemini_part": p}
             for p in parts if isinstance(p, dict) and isinstance(p.get("functionCall"), dict)]
    return {"message": {"role": "assistant", "content": text, "tool_calls": calls},
            "prompt_eval_count": tokens_in, "eval_count": tokens_out}
