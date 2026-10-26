"""Only config that is required for the local demo."""
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    data_path: Path = Path(os.getenv("DATA_PATH", str(ROOT / "runtime" / "lab.db")))
    llm_provider: str = os.getenv("LLM_PROVIDER", "off").lower()
    ollama_url: str = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")
    embedding_provider: str = os.getenv("EMBEDDING_PROVIDER", "off").lower()
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    # The model name tags stored vectors, so it is the one used by retrieval for any provider.
    embedding_model: str = os.getenv("EMBEDDING_MODEL") or (
        os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
        if os.getenv("EMBEDDING_PROVIDER", "off").lower() == "gemini" else "bge-m3")
    timeout_seconds: int = max(3, min(_int_env("LLM_TIMEOUT_SECONDS", 45), 120))
    max_output_tokens: int = max(64, min(_int_env("MAX_OUTPUT_TOKENS", 256), 512))
    num_ctx: int = max(1024, min(_int_env("OLLAMA_NUM_CTX", 4096), 32768))
    max_context_chars: int = max(500, min(_int_env("MAX_CONTEXT_CHARS", 2600), 6000))
