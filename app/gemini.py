"""Google Gemini API adapter (HOSTED, free tier only). Separate from the local Ollama adapter.

Rules enforced here, not left to configuration:
- only https://generativelanguage.googleapis.com, no redirects;
- the API key comes from the GEMINI_API_KEY environment variable, is sent in a header (never in a
  URL) and is scrubbed from every error message; it is never stored in Settings or logged;
- only models on the free-tier allowlist may be called (a paid model raises before any request);
- a hard per-process request budget, at most one retry, and a permanent stop on quota/billing errors.
Only synthetic catalogue/policy text should ever be sent through this adapter.
"""
import json
import os
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from http.client import HTTPException

from .ollama import ModelUnavailable, count

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
ALLOWED_HOSTS = ("generativelanguage.googleapis.com",)
# Listed as "Free of charge" on https://ai.google.dev/gemini-api/docs/pricing (checked 2026-10-26).
# Anything else needs an explicit, deliberate edit here.
FREE_MODELS = {"gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-embedding-001", "gemini-embedding-2"}
MAX_REQUESTS = int(os.getenv("GEMINI_MAX_REQUESTS", "150"))
MAX_RESPONSE_BYTES = 3_000_000
# One 3072-dimension vector is about 60 KB of JSON; 16 per request stays far below the cap.
EMBED_BATCH = 16

_lock = threading.Lock()
_state = {"requests": 0, "stopped": None}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


_OPENER = build_opener(_NoRedirect)


def reset_budget():
    with _lock:
        _state.update(requests=0, stopped=None)


def requests_made() -> int:
    return _state["requests"]


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
                body = exc.read(500).decode("utf-8", "replace")
            except Exception:
                body = ""
            body = _scrub(body)
            lowered = body.lower()
            if exc.code in (401, 403) or "billing" in lowered or "failed_precondition" in lowered:
                _state["stopped"] = f"HTTP {exc.code} (auth/billing); not retrying"
                raise ModelUnavailable(f"HTTP {exc.code} from Gemini (auth or billing): {body[:200]}") from exc
            if exc.code == 429:
                if attempt == 1 and "perday" not in lowered.replace(" ", "").replace("_", ""):
                    time.sleep(min(_retry_after(exc), 30))
                    continue
                _state["stopped"] = "HTTP 429 quota/rate limit; stopped instead of retrying"
                raise ModelUnavailable(f"HTTP 429 from Gemini (quota): {body[:200]}") from exc
            raise ModelUnavailable(f"HTTP {exc.code} from Gemini: {body[:200]}") from exc
        except (URLError, TimeoutError, ValueError, OSError, HTTPException) as exc:
            raise ModelUnavailable(_scrub(str(exc))) from exc
    raise ModelUnavailable("Gemini request failed")


def _retry_after(exc) -> float:
    try:
        return float(exc.headers.get("Retry-After", "10"))
    except (TypeError, ValueError):
        return 10.0


def list_models(settings) -> list[str]:
    """Names (without the 'models/' prefix) the key can see; read-only, no generation cost."""
    data = _send("GET", "/models?pageSize=200", None, min(settings.timeout_seconds, 20))
    models = data.get("models")
    if not isinstance(models, list):
        raise ModelUnavailable("Gemini returned an unexpected models response")
    return [m.get("name", "").removeprefix("models/") for m in models if isinstance(m, dict)]


def _generation_config(settings, model: str, json_output: bool) -> dict:
    config = {"temperature": 0.2, "maxOutputTokens": settings.max_output_tokens}
    if json_output:
        config["responseMimeType"] = "application/json"
    if "flash" in model:
        config["thinkingConfig"] = {"thinkingBudget": 0}  # thinking tokens would eat the output budget
    return config


def _parse(data: dict):
    feedback = data.get("promptFeedback") or {}
    if feedback.get("blockReason"):
        raise ModelUnavailable(f"Gemini blocked the prompt: {feedback['blockReason']}")
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates or not isinstance(candidates[0], dict):
        raise ModelUnavailable("Gemini returned no candidates")
    content = candidates[0].get("content")
    parts = content.get("parts") if isinstance(content, dict) else None
    usage = data.get("usageMetadata") if isinstance(data.get("usageMetadata"), dict) else {}
    return (parts if isinstance(parts, list) else []), count(usage.get("promptTokenCount")), count(usage.get("candidatesTokenCount"))


def chat(settings, system, user, json_output=False):
    model = settings.gemini_model
    _check_model(model)
    payload = {"systemInstruction": {"parts": [{"text": system}]},
               "contents": [{"role": "user", "parts": [{"text": user}]}],
               "generationConfig": _generation_config(settings, model, json_output)}
    data = _send("POST", f"/models/{model}:generateContent", payload, settings.timeout_seconds)
    parts, tokens_in, tokens_out = _parse(data)
    answer = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and isinstance(p.get("text"), str)).strip()
    if not answer:
        raise ModelUnavailable("Gemini returned an empty answer")
    return answer, tokens_in, tokens_out


def embed(settings, texts):
    model = settings.embedding_model
    _check_model(model)
    vectors = []
    for start in range(0, len(texts), EMBED_BATCH):
        chunk = texts[start:start + EMBED_BATCH]
        payload = {"requests": [{"model": f"models/{model}", "content": {"parts": [{"text": x}]}} for x in chunk]}
        data = _send("POST", f"/models/{model}:batchEmbedContents", payload, settings.timeout_seconds)
        items = data.get("embeddings")
        if not isinstance(items, list) or len(items) != len(chunk):
            raise ModelUnavailable("Gemini returned invalid embeddings")
        for item in items:
            values = item.get("values") if isinstance(item, dict) else None
            if (not isinstance(values, list) or not values
                    or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in values)):
                raise ModelUnavailable("Gemini returned a malformed embedding vector")
            vectors.append(values)
    if len({len(v) for v in vectors}) != 1:
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


def chat_with_tools(settings, messages, tools):
    """One tool-calling turn; returns an Ollama-shaped result so agent.py handles both providers."""
    model = settings.gemini_model
    _check_model(model)
    system, contents = _contents(messages)
    payload = {"contents": contents,
               "tools": [{"functionDeclarations": [t["function"] for t in tools]}],
               "generationConfig": _generation_config(settings, model, False)}
    if system:
        payload["systemInstruction"] = system
    data = _send("POST", f"/models/{model}:generateContent", payload, settings.timeout_seconds)
    parts, tokens_in, tokens_out = _parse(data)
    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and isinstance(p.get("text"), str))
    calls = [{"function": {"name": p["functionCall"].get("name", ""), "arguments": p["functionCall"].get("args") or {}},
              "_gemini_part": p}
             for p in parts if isinstance(p, dict) and isinstance(p.get("functionCall"), dict)]
    return {"message": {"role": "assistant", "content": text, "tool_calls": calls},
            "prompt_eval_count": tokens_in, "eval_count": tokens_out}
