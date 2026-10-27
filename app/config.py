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
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    # The model name tags stored vectors, so it is the one used by retrieval for any provider.
    embedding_model: str = os.getenv("EMBEDDING_MODEL") or (
        os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
        if os.getenv("EMBEDDING_PROVIDER", "off").lower() == "gemini" else "bge-m3")
    timeout_seconds: int = max(3, min(_int_env("LLM_TIMEOUT_SECONDS", 45), 120))
    max_output_tokens: int = max(64, min(_int_env("MAX_OUTPUT_TOKENS", 256), 512))
    num_ctx: int = max(1024, min(_int_env("OLLAMA_NUM_CTX", 4096), 32768))
    max_context_chars: int = max(500, min(_int_env("MAX_CONTEXT_CHARS", 2600), 6000))
    # Document upload (local demo; there is no authentication, so the endpoint can be switched off with DOC_UPLOAD_ENABLED=off).
    doc_upload_enabled: bool = os.getenv("DOC_UPLOAD_ENABLED", "on").lower() not in {"off", "0", "false", "no"}
    doc_chunk_chars: int = max(200, min(_int_env("DOC_CHUNK_CHARS", 800), 3000))
    doc_chunk_overlap: int = max(0, min(_int_env("DOC_CHUNK_OVERLAP", 120), 1500))
    doc_max_upload_bytes: int = max(1000, min(_int_env("DOC_MAX_UPLOAD_BYTES", 5_000_000), 20_000_000))
    doc_max_pdf_pages: int = max(1, min(_int_env("DOC_MAX_PDF_PAGES", 100), 500))
    doc_max_chunks: int = max(1, min(_int_env("DOC_MAX_CHUNKS", 150), 1000))
