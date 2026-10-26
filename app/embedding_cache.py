"""Persistent embedding cache (SQLite, on the project drive).

Hosted embeddings are metered per TEXT, so a vector that was already paid for must never be
requested again: the key is sha256(model + text), so a changed text or a different model is a
miss. Only the model name, a hash, and the vector are stored; no key, no request, no answer.
"""
import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path


def _key(model: str, text: str) -> str:
    return hashlib.sha256(f"{model}\0{text}".encode("utf-8")).hexdigest()


class EmbeddingCache:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=20)) as cx, cx:
            cx.execute("CREATE TABLE IF NOT EXISTS embeddings (key TEXT PRIMARY KEY, model TEXT NOT NULL, "
                       "vector_json TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")

    def get_many(self, model: str, texts) -> dict:
        """{text: vector} for the texts already cached; unreadable rows count as misses."""
        found = {}
        with closing(sqlite3.connect(self.path, timeout=20)) as cx:
            for text in dict.fromkeys(texts):
                row = cx.execute("SELECT vector_json FROM embeddings WHERE key=?", (_key(model, text),)).fetchone()
                if not row:
                    continue
                try:
                    vector = json.loads(row[0])
                except ValueError:
                    continue
                if isinstance(vector, list) and vector and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vector):
                    found[text] = vector
        return found

    def put_many(self, model: str, vectors: dict):
        with closing(sqlite3.connect(self.path, timeout=20)) as cx, cx:
            cx.executemany("INSERT OR REPLACE INTO embeddings(key, model, vector_json) VALUES(?,?,?)",
                           [(_key(model, text), model, json.dumps(vector)) for text, vector in vectors.items()])

    def count(self) -> int:
        with closing(sqlite3.connect(self.path, timeout=20)) as cx:
            return cx.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
