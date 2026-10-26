"""SQLite for the demo. Normalized FTS5 index avoids fragile Vietnamese diacritics matching."""
import json
import re
import sqlite3
import threading
import unicodedata
from pathlib import Path
from .config import ROOT


def normalize(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower())


STOP = set("toi minh ban cho ve va la co khong nao gi bao nhieu the nao thu duoc cua voi trong mot khi hay can giup xem tim san pham loai hang".split())


class Store:
    def __init__(self, db_path: Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init()

    def connect(self):
        cx = sqlite3.connect(self.path, timeout=20, check_same_thread=False)
        cx.row_factory = sqlite3.Row
        cx.execute("PRAGMA busy_timeout=20000")
        return cx

    def _init(self):
        with self.connect() as cx:
            cx.executescript("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, category TEXT NOT NULL,
                content TEXT NOT NULL, embedding_json TEXT, embedding_model TEXT
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS document_fts USING fts5(doc_id UNINDEXED, normalized_text, tokenize='unicode61');
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, mode TEXT NOT NULL,
                latency_ms INTEGER NOT NULL, input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """)
            columns = {row[1] for row in cx.execute("PRAGMA table_info(documents)")}
            if "embedding_model" not in columns:
                cx.execute("ALTER TABLE documents ADD COLUMN embedding_model TEXT")
            count = cx.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            if count == 0:
                docs = json.loads((ROOT / "data" / "seed_documents.json").read_text(encoding="utf-8"))
                for d in docs:
                    self._upsert(cx, d)
            elif cx.execute("SELECT COUNT(*) FROM document_fts").fetchone()[0] != count:
                cx.execute("DELETE FROM document_fts")
                for d in cx.execute("SELECT * FROM documents").fetchall():
                    cx.execute("INSERT INTO document_fts(doc_id,normalized_text) VALUES(?,?)", (d["id"], normalize(d["title"] + " " + d["content"])))

    @staticmethod
    def _upsert(cx, d):
        cx.execute("INSERT INTO documents(id,title,category,content,embedding_json,embedding_model) VALUES(?,?,?,?,NULL,NULL) "
                   "ON CONFLICT(id) DO UPDATE SET title=excluded.title,category=excluded.category,content=excluded.content,embedding_json=NULL,embedding_model=NULL",
                   (d["id"], d["title"], d["category"], d["content"]))
        cx.execute("DELETE FROM document_fts WHERE doc_id=?", (d["id"],))
        cx.execute("INSERT INTO document_fts(doc_id,normalized_text) VALUES(?,?)", (d["id"], normalize(d["title"] + " " + d["content"])))

    def upsert(self, doc):
        with self._lock, self.connect() as cx:
            self._upsert(cx, doc)

    def documents(self):
        with self.connect() as cx:
            return [dict(x) for x in cx.execute("SELECT * FROM documents ORDER BY id")]

    def document(self, doc_id):
        with self.connect() as cx:
            row = cx.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
            return dict(row) if row else None

    def update_embedding(self, doc_id, embedding, model=None):
        with self._lock, self.connect() as cx:
            cx.execute("UPDATE documents SET embedding_json=?, embedding_model=? WHERE id=?", (json.dumps(embedding), model, doc_id))

    def fts_search(self, query, limit=12):
        terms = [t for t in normalize(query).split() if len(t) >= 2 and t not in STOP]
        terms = list(dict.fromkeys(terms))[:10]
        if not terms:
            return []
        expression = " OR ".join('"' + t + '"' for t in terms)
        with self.connect() as cx:
            rows = cx.execute("""SELECT d.*,bm25(document_fts) AS fts_score
                FROM document_fts JOIN documents d ON document_fts.doc_id=d.id
                WHERE document_fts MATCH ? ORDER BY fts_score LIMIT ?""", (expression, limit * 3)).fetchall()
            filtered = []
            for row in rows:
                doc = dict(row)
                # OR-based BM25 alone will happily return irrelevant documents sharing one word.
                doc_terms = set(normalize(doc["title"] + " " + doc["content"]).split())
                hits = [t for t in terms if t in doc_terms]
                numeric = [t for t in terms if t.isdigit()]
                if len(terms) >= 3 and (len(hits) < 2 or len(hits) / len(terms) < 0.34):
                    continue
                if any(t not in doc_terms for t in numeric):
                    continue  # Do not answer a made-up discount/size/price by loose keyword match.
                filtered.append(doc)
                if len(filtered) >= limit:
                    break
            return filtered

    def log(self, kind, mode, ms, input_tokens=0, output_tokens=0):
        with self._lock, self.connect() as cx:
            cx.execute("INSERT INTO events(kind,mode,latency_ms,input_tokens,output_tokens) VALUES(?,?,?,?,?)",
                       (kind, mode, ms, input_tokens, output_tokens))

    def metrics(self):
        with self.connect() as cx:
            row = cx.execute("""SELECT COUNT(*) AS calls,COALESCE(AVG(latency_ms),0) AS avg_ms,
                COALESCE(SUM(input_tokens),0) AS tokens_in,COALESCE(SUM(output_tokens),0) AS tokens_out
                FROM events""").fetchone()
            return dict(row)
