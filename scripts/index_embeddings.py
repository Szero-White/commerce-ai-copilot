"""Explicitly index semantic vectors, using local Ollama; avoids surprise downloads on startup."""
from app.config import Settings
from app.storage import Store
from app.retrieval import index_vectors

if __name__ == "__main__":
    settings=Settings()
    result=index_vectors(Store(settings.data_path),settings)
    print(result)
    if not result['enabled']:
        raise SystemExit("Embedding not enabled or model unavailable. Read README first.")
