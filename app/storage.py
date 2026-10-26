"""SQLite for the demo. Normalized FTS5 index avoids fragile Vietnamese diacritics matching."""
import json
import math
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


STOP = set("""toi minh ban cho ve va la co khong nao gi bao nhieu the nao thu duoc cua voi trong mot khi hay can
giup xem tim san pham loai hang lau may nhu nay hom muon xin mua tai tren cac nhung moi da dang se rat qua
hoac neu thi de di den tu ra vao what is the a an of in do you can i how much are there for to who tell me
it be on at by with and or my your we this that does did will would should could any some about""".split())
STOP_ACCENTED = {"mất"}
# Spoken form -> the form used in the documents (checked on normalized text).
ALIASES = {"thanh pho ho chi minh": "tp hcm", "sai gon": "tp hcm", "ho chi minh": "tp hcm"}
# Obvious non-commerce topics. A lexical index cannot tell that "thời tiết" only matches the
# unrelated words "thời gian" and "tiết kiệm", so these are refused before searching.
OUT_OF_SCOPE = ("thoi tiet", "bitcoin", "tien ao", "gia vang", "ty gia", "co phieu", "chung khoan",
                "bong da", "weather", "football", "horoscope", "tu vi")
# A query is answerable only if its (IDF-weighted) terms are mostly present in one document.
MIN_COVERAGE = 0.5


def _inflectable(term: str) -> bool:
    return len(term) >= 4 and not term.isdigit()


def _present(term: str, doc_terms: set) -> bool:
    """Exact token, or an English inflection such as size -> sizes (at most 2 extra letters)."""
    return term in doc_terms or (_inflectable(term) and any(
        d.startswith(term) and len(d) - len(term) <= 2 for d in doc_terms))


def _raw_tokens(text: str) -> list[str]:
    return re.findall(r"\w+", unicodedata.normalize("NFC", text).lower())


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
        padded = " " + " ".join(normalize(query).split()) + " "
        if any(f" {phrase} " in padded for phrase in OUT_OF_SCOPE):
            return []
        # Single digits are kept: "giảm 5%" must be checked against the documents like "90" is.
        spoken = " ".join(normalize(query).split())
        for alias, canonical in ALIASES.items():
            spoken = spoken.replace(alias, canonical)
        terms = [t for t in spoken.split() if (len(t) >= 2 or t.isdigit()) and t not in STOP]
        terms = list(dict.fromkeys(terms))[:10]
        if not terms:
            return []
        # Words typed WITH diacritics must match with diacritics ("nhân viên" != "nhận"); only a
        # diacritic-free query word may match loosely.
        accented = {}
        for raw in _raw_tokens(query):
            norm = normalize(raw).strip()
            if raw in STOP_ACCENTED and norm in terms:
                terms.remove(norm)  # "mất" (how long) is a question word, unlike "mặt" (surface)
            elif norm in terms and raw != norm:
                accented[norm] = raw
        if not terms:
            return []
        expression = " OR ".join('"' + t + '"' + ("*" if _inflectable(t) else "") for t in terms)
        with self.connect() as cx:
            rows = cx.execute("""SELECT d.*,bm25(document_fts) AS fts_score
                FROM document_fts JOIN documents d ON document_fts.doc_id=d.id
                WHERE document_fts MATCH ? ORDER BY fts_score LIMIT ?""", (expression, limit * 3)).fetchall()
            corpus = [set(normalize(r[0] + " " + r[1]).split()) for r in
                      cx.execute("SELECT title,content FROM documents")]
            df = {t: sum(_present(t, d) for d in corpus) for t in terms}
            # Rare or unknown words carry more weight than words found in most documents.
            weight = {t: math.log(1 + len(corpus) / ((df[t] or 0.1) + 0.1)) for t in terms}
            filtered = []
            for row in rows:
                doc = dict(row)
                # OR-based BM25 alone will happily return irrelevant documents sharing one word.
                text = doc["title"] + " " + doc["content"]
                doc_terms = set(normalize(text).split())
                doc_raw = set(_raw_tokens(text))
                hits = [t for t in terms if _present(t, doc_terms) and (t not in accented or accented[t] in doc_raw)]
                numeric = [t for t in terms if t.isdigit()]
                if len(terms) >= 3 and (len(hits) < 2 or len(hits) / len(terms) < 0.34):
                    continue
                if any(t not in doc_terms for t in numeric):
                    continue  # Do not answer a made-up discount/size/price by loose keyword match.
                if sum(weight[t] for t in hits) / sum(weight.values()) < MIN_COVERAGE:
                    continue
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
