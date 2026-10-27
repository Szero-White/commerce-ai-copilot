"""SQLite for the demo. Normalized FTS5 index avoids fragile Vietnamese diacritics matching."""
import json
import math
import sqlite3
import threading
from pathlib import Path
from .config import ROOT
# Query-side vocabulary and text normalisation live in query.py; re-exported for existing importers.
from .gate import check_document
from .query import (ALIASES, STOP, STOP_ACCENTED, Lexicon, analyze, normalize,  # noqa: F401
                    raw_tokens as _raw_tokens)

# Domain synonyms (query term -> tokens that may carry the same meaning in the documents).
# Generic e-commerce vocabulary, not tied to any evaluation question.
SYNONYMS = {
    "kich": ("cm", "mm"), "thuoc": ("cm", "mm"), "rong": ("cm",), "dai": ("cm",),
    "gia": ("vnd", "usd", "price"), "price": ("gia", "vnd", "usd"),
    "mau": ("color", "colors", "colour"), "color": ("mau",), "colors": ("mau",), "colour": ("mau",),
    "return": ("doi", "tra"), "refund": ("hoan", "tien"), "ship": ("giao", "van"), "shipping": ("giao", "van"),
    "delivery": ("giao",), "warranty": ("bao", "hanh"), "payment": ("thanh", "toan"),
}
# A query is answerable only if its (IDF-weighted) terms are mostly present in one document.
MIN_COVERAGE = 0.6
# Two matched query terms must sit within this many tokens of each other: words scattered over
# unrelated clauses ("điều kiện ... hòa") are coincidence, not a match.
PROXIMITY = 8


MAX_UNVERIFIED = 2


def _verified_first(docs):
    """Documents whose comparison could be confirmed come first; those it could not be confirmed for are capped."""
    confirmed = [d for d in docs if d.get("condition_status") != "unverified"]
    unconfirmed = [d for d in docs if d.get("condition_status") == "unverified"]
    return confirmed + unconfirmed[:MAX_UNVERIFIED]


def _inflectable(term: str) -> bool:
    return len(term) >= 4 and not term.isdigit()


def _stems(token: str) -> set[str]:
    """Token plus crude English stems so that changed/change and sizes/size match."""
    out = {token}
    if token.isalpha() and token.isascii() and len(token) > 3:
        for suffix in ("ing", "ed", "es", "s"):
            if token.endswith(suffix) and len(token) - len(suffix) >= 3:
                out.add(token[: -len(suffix)])
    return out


def _positions(term: str, tokens: list[str]) -> list[int]:
    """Token positions where the term (or an inflection / listed synonym) occurs."""
    wanted = set().union(*(_stems(w) for w in (term,) + SYNONYMS.get(term, ())))
    return [i for i, token in enumerate(tokens) if _stems(token) & wanted]


def _near(positions: dict[str, list[int]]) -> bool:
    items = [p for p in positions.values() if p]
    return len(items) < 2 or any(
        abs(x - y) <= PROXIMITY
        for i, a in enumerate(items) for b in items[i + 1:] for x in a for y in b)


class _ClosingConnection(sqlite3.Connection):
    """`with store.connect() as cx:` commits/rolls back AND closes (plain sqlite3 only commits).

    Unclosed connections keep the file locked on Windows until garbage collection.
    """

    def __exit__(self, *exc_info):
        try:
            return super().__exit__(*exc_info)
        finally:
            self.close()


class Store:
    def __init__(self, db_path: Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._cached = None   # (corpus_version, vocabulary and token lists), see _corpus()
        self._init()

    def connect(self):
        cx = sqlite3.connect(self.path, timeout=20, check_same_thread=False, factory=_ClosingConnection)
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
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """)
            columns = {row[1] for row in cx.execute("PRAGMA table_info(documents)")}
            if "embedding_model" not in columns:
                cx.execute("ALTER TABLE documents ADD COLUMN embedding_model TEXT")
            if "source" not in columns:
                cx.execute("ALTER TABLE documents ADD COLUMN source TEXT")
            count = cx.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            if count == 0:
                docs = json.loads((ROOT / "data" / "seed_documents.json").read_text(encoding="utf-8"))
                for d in docs:
                    self._upsert(cx, {**d, "source": "seed"})
            elif sorted(r[0] for r in cx.execute("SELECT doc_id FROM document_fts")) != \
                    sorted(r[0] for r in cx.execute("SELECT id FROM documents")):
                # Compared by id, not by count: one missing and one orphan row would cancel out in a count.
                cx.execute("DELETE FROM document_fts")
                for d in cx.execute("SELECT * FROM documents").fetchall():
                    cx.execute("INSERT INTO document_fts(doc_id,normalized_text) VALUES(?,?)", (d["id"], normalize(d["title"] + " " + d["content"])))
                self._bump(cx)

    @staticmethod
    def _bump(cx):
        """The corpus version changes inside the same transaction as any change to the documents."""
        cx.execute("INSERT INTO meta(key,value) VALUES('corpus_version','1') "
                   "ON CONFLICT(key) DO UPDATE SET value=CAST(value AS INTEGER)+1")

    @staticmethod
    def _index_fts(cx, d):
        cx.execute("DELETE FROM document_fts WHERE doc_id=?", (d["id"],))
        cx.execute("INSERT INTO document_fts(doc_id,normalized_text) VALUES(?,?)", (d["id"], normalize(d["title"] + " " + d["content"])))

    @classmethod
    def _upsert(cls, cx, d):
        """Insert or replace one document. Returns 'added', 'updated' or 'unchanged'.

        A document whose text did not change keeps its vector (still valid); a changed one loses it, so a vector
        of the old text can never be used for the new text.
        """
        old = cx.execute("SELECT title,category,content,source FROM documents WHERE id=?", (d["id"],)).fetchone()
        source = d.get("source")
        if old and (old["title"], old["category"], old["content"]) == (d["title"], d["category"], d["content"]):
            fts = [r[0] for r in cx.execute("SELECT normalized_text FROM document_fts WHERE doc_id=?", (d["id"],))]
            if fts != [normalize(d["title"] + " " + d["content"])]:
                cls._index_fts(cx, d)       # the text index drifted from the document: repair it
                cls._bump(cx)
            if source is not None and old["source"] != source:
                cx.execute("UPDATE documents SET source=? WHERE id=?", (source, d["id"]))
            return "unchanged"
        cx.execute("INSERT INTO documents(id,title,category,content,embedding_json,embedding_model,source) VALUES(?,?,?,?,NULL,NULL,?) "
                   "ON CONFLICT(id) DO UPDATE SET title=excluded.title,category=excluded.category,content=excluded.content,"
                   "embedding_json=NULL,embedding_model=NULL,source=COALESCE(excluded.source,documents.source)",
                   (d["id"], d["title"], d["category"], d["content"], source))
        cls._index_fts(cx, d)
        cls._bump(cx)
        return "updated" if old else "added"

    @classmethod
    def _delete(cls, cx, doc_id):
        gone = cx.execute("DELETE FROM documents WHERE id=?", (doc_id,)).rowcount
        cx.execute("DELETE FROM document_fts WHERE doc_id=?", (doc_id,))
        if gone:
            cls._bump(cx)
        return bool(gone)

    def upsert(self, doc):
        with self._lock, self.connect() as cx:
            return self._upsert(cx, doc)

    def apply(self, docs, source=None, replace=False):
        """Import a batch in ONE transaction: either every document is applied or none is.

        With `replace`, documents of `source` that are absent from the batch are removed (no orphans).
        """
        ids = [d["id"] for d in docs]
        if len(ids) != len(set(ids)):
            raise ValueError("The import contains duplicate document ids")
        if replace and not source:
            raise ValueError("Replacing a source needs a source name")
        summary = {"added": 0, "updated": 0, "unchanged": 0, "deleted": 0}
        with self._lock, self.connect() as cx:
            for d in docs:
                summary[self._upsert(cx, {**d, "source": source or d.get("source")})] += 1
            if replace:
                for (doc_id,) in cx.execute("SELECT id FROM documents WHERE source=?", (source,)).fetchall():
                    if doc_id not in set(ids):
                        summary["deleted"] += self._delete(cx, doc_id)
        return summary

    def delete(self, doc_id):
        """Remove a document with its text index row and vector (they live in the same row/transaction)."""
        with self._lock, self.connect() as cx:
            return self._delete(cx, doc_id)

    def delete_source(self, source):
        if not source:
            raise ValueError("A source name is required")
        with self._lock, self.connect() as cx:
            ids = [r[0] for r in cx.execute("SELECT id FROM documents WHERE source=?", (source,))]
            return sum(self._delete(cx, i) for i in ids)

    def corpus_version(self):
        with self.connect() as cx:
            return self._version(cx)

    @staticmethod
    def _version(cx):
        row = cx.execute("SELECT value FROM meta WHERE key='corpus_version'").fetchone()
        return int(row[0]) if row else 0

    def consistency_report(self, embedding_model=None):
        """Compare the documents with the indexes derived from them. `ok` is False when anything is stale."""
        problems = []
        with self.connect() as cx:
            docs = {r["id"]: dict(r) for r in cx.execute("SELECT * FROM documents")}
            fts = {}
            for r in cx.execute("SELECT doc_id, normalized_text FROM document_fts"):
                fts.setdefault(r["doc_id"], []).append(r["normalized_text"])
        for doc_id, d in docs.items():
            rows = fts.get(doc_id, [])
            if not rows:
                problems.append({"id": doc_id, "problem": "missing from the text index"})
            elif len(rows) > 1:
                problems.append({"id": doc_id, "problem": "duplicated in the text index"})
            elif rows[0] != normalize(d["title"] + " " + d["content"]):
                problems.append({"id": doc_id, "problem": "text index is stale (differs from the document)"})
        problems += [{"id": i, "problem": "text index row without a document"} for i in fts if i not in docs]
        vectors, dims = 0, set()
        for doc_id, d in docs.items():
            if not d.get("embedding_json"):
                continue
            vectors += 1
            try:
                vector = json.loads(d["embedding_json"])
                if not isinstance(vector, list) or not vector:
                    raise ValueError
                dims.add(len(vector))
            except (TypeError, ValueError):
                problems.append({"id": doc_id, "problem": "unreadable vector"})
            if embedding_model and d.get("embedding_model") != embedding_model:
                problems.append({"id": doc_id, "problem": f"vector built by {d.get('embedding_model')!r}, expected {embedding_model!r}"})
        if len(dims) > 1:
            problems.append({"id": None, "problem": f"vectors of different sizes: {sorted(dims)}"})
        legacy = [i for i, d in docs.items() if not d.get("source") and (i.startswith("CSV-") or i.startswith("DOC-"))]
        return {"ok": not problems, "documents": len(docs), "with_vector": vectors, "missing_vector": len(docs) - vectors,
                "corpus_version": self.corpus_version(), "problems": problems,
                "legacy_ids_without_source": legacy}

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

    def _corpus(self):
        """Vocabulary and token lists of the documents, rebuilt only when `corpus_version` changes.

        The version is stored in the database, so a change made by another process (an ingest script) is noticed
        by the next query of a running server without restarting it.
        """
        with self.connect() as cx:
            version = self._version(cx)
            cached = self._cached
            if cached and cached[0] == version:
                return cached[1]
            rows = [(r[0], r[1]) for r in cx.execute("SELECT title,content FROM documents")]
            product_titles = [r[0] for r in cx.execute("SELECT title FROM documents WHERE category='product'")]
        texts = [t + " " + c for t, c in rows]
        # Only products are "things" a follow-up can point at; policy titles ("Bảo hành") are topics.
        data = {"lexicon": Lexicon(texts, known=SYNONYMS, titles=product_titles),
                "tokens": [normalize(t).split() for t in texts]}
        self._cached = (version, data)
        return data

    def _catalogue(self, analysis, limit, trace=None):
        """Product documents that pass the hard constraints of the question (comparisons, quantities, names)."""
        with self.connect() as cx:
            products = [dict(r) for r in cx.execute("SELECT * FROM documents WHERE category='product' ORDER BY id")]
        found, rejected = [], {}
        for doc in products:
            text = doc["title"] + " " + doc["content"]
            verdict = check_document(analysis, text, normalize(text).split(), doc["category"])
            if not verdict.admitted:
                rejected[doc["id"]] = verdict.reason
                continue
            if verdict.condition:
                doc["condition_status"] = verdict.condition
            found.append(doc)
        if trace is not None and rejected:
            trace["gate_rejected"] = rejected
        return _verified_first(found)[:limit]

    def analyze(self, query):
        return analyze(query, self._corpus()["lexicon"])

    def _only(self, ids, analysis, trace=None):
        """The given documents, if they pass the hard constraints of the question ("tell me about that one")."""
        found = []
        for doc_id in ids:
            doc = self.document(doc_id)
            if not doc:
                continue
            text = doc["title"] + " " + doc["content"]
            verdict = check_document(analysis, text, normalize(text).split(), doc["category"])
            if verdict.admitted:
                found.append({**doc, **({"condition_status": verdict.condition} if verdict.condition else {})})
        return found

    def fts_search(self, query, limit=12, trace=None, only=None):
        """Lexical candidates for `query`. `trace` (a dict) receives how the question was read.

        `only` restricts the search to those document ids: a follow-up question that points at one of them.
        """
        corpus = self._corpus()
        # Words are classified against the vocabulary of the documents themselves (see query.py).
        analysis = analyze(query, corpus["lexicon"])
        if trace is not None:
            trace.update(analysis.trace())
        terms, accented = analysis.terms, analysis.accented
        if analysis.needs_referent and only is None:
            return []   # "that one" with no earlier turn to point at: asking which one is the caller's job
        if only is not None and not terms:
            return self._only(only, analysis, trace)
        if not terms:
            # "Which products do you sell?" / "anything under 500k?": nothing to match by word, so look at the products.
            return self._catalogue(analysis, limit, trace) if analysis.catalog or analysis.conditions else []
        # Words typed WITH diacritics must match with diacritics ("nhân viên" != "nhận"); only a
        # diacritic-free query word may match loosely.
        wanted = list(dict.fromkeys(w for term in terms + analysis.soft for w in (term,) + SYNONYMS.get(term, ())))
        expression = " OR ".join('"' + w + '"' + ("*" if _inflectable(w) else "") for w in wanted)
        scope, scope_args = "", ()
        if only is not None:
            scope, scope_args = f" AND d.id IN ({','.join('?' * len(only))})", tuple(only)
        with self.connect() as cx:
            rows = cx.execute(f"""SELECT d.*,bm25(document_fts) AS fts_score
                FROM document_fts JOIN documents d ON document_fts.doc_id=d.id
                WHERE document_fts MATCH ?{scope} ORDER BY fts_score LIMIT ?""",
                (expression, *scope_args, limit * 3)).fetchall()
            tokenized = corpus["tokens"]
            df = {t: sum(bool(_positions(t, d)) for d in tokenized) for t in terms}
            # Rare or unknown words carry more weight than words found in most documents.
            weight = {t: math.log(1 + len(tokenized) / ((df[t] or 0.1) + 0.1)) for t in terms}
            filtered, rejected = [], {}
            for row in rows:
                doc = dict(row)
                # OR-based BM25 alone will happily return irrelevant documents sharing one word.
                text = doc["title"] + " " + doc["content"]
                tokens = normalize(text).split()
                doc_raw = set(_raw_tokens(text))
                where = {t: _positions(t, tokens) for t in terms}
                for t in terms:
                    if t in accented and accented[t] not in doc_raw and not any(
                            s in tokens for s in SYNONYMS.get(t, ())):
                        where[t] = []  # typed with diacritics but only the loose spelling occurs
                hits = [t for t in terms if where[t]]
                numeric = [t for t in terms if t.isdigit()]
                if len(terms) >= 3 and (len(hits) < 2 or len(hits) / len(terms) < 0.34):
                    continue
                if any(not where[t] for t in numeric):
                    continue  # Do not answer a made-up discount/size/price by loose keyword match.
                if sum(weight[t] for t in hits) / sum(weight.values()) < MIN_COVERAGE:
                    continue
                if not _near({t: where[t] for t in hits if not t.isdigit()}):
                    continue
                verdict = check_document(analysis, text, tokens, doc["category"])
                if not verdict.admitted:
                    rejected[doc["id"]] = verdict.reason
                    continue
                if verdict.condition:
                    doc["condition_status"] = verdict.condition
                filtered.append(doc)
                if len(filtered) >= limit:
                    break
            if trace is not None and rejected:
                trace["gate_rejected"] = rejected
            if analysis.discovery and len(terms) <= 2:
                # "Which X do you have?": documents whose TITLE names X (products first) before passing mentions.
                def names_it(doc):
                    return any(_positions(t, normalize(doc["title"]).split()) for t in terms)
                filtered.sort(key=lambda doc: (not names_it(doc), doc["category"] != "product"))
            return _verified_first(filtered)

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
