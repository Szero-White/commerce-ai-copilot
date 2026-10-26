"""Provider switch: 'ollama' (local) or 'gemini' (hosted, free tier). The adapters stay separate."""
from . import gemini, ollama
from .ollama import ModelUnavailable

PROVIDERS = ("ollama", "gemini")


def llm_enabled(settings) -> bool:
    return settings.llm_provider in PROVIDERS


def embedding_enabled(settings) -> bool:
    return settings.embedding_provider in PROVIDERS


def chat(settings, system, user, json_output=False):
    if settings.llm_provider == "gemini":
        return gemini.chat(settings, system, user, json_output)
    return ollama.chat(settings, system, user, json_output)


def embed(settings, texts):
    if settings.embedding_provider == "gemini":
        return gemini.embed(settings, texts)
    return ollama.embed(settings, texts)


def llm_info(settings) -> dict:
    """Who actually answered: a hosted model must never be reported as local."""
    if settings.llm_provider == "gemini":
        return {"provider": "gemini", "model": settings.gemini_model, "hosted": True}
    if settings.llm_provider == "ollama":
        return {"provider": "ollama", "model": settings.ollama_model, "hosted": False}
    return {"provider": "off", "model": None, "hosted": False}


__all__ = ["chat", "embed", "llm_enabled", "embedding_enabled", "llm_info", "ModelUnavailable"]
