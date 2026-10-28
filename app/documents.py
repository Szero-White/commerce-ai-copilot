"""Document ingestion: uploaded bytes -> parse -> clean -> chunk -> metadata -> index (see README, "Document ingestion").

Text-based PDF and UTF-8 TXT only. Scanned PDFs are refused (no OCR). Uploaded text is untrusted data like every other
document: it is only ever stored and retrieved, never executed or used as an instruction.
"""
import hashlib
import io
import re
import unicodedata
from datetime import datetime, timezone

from .retrieval import index_vectors

ALLOWED_EXTENSIONS = {".txt", ".pdf"}
CATEGORY = "document"
MIN_TEXT_CHARS = 20          # fewer characters than this in a whole file means "no text layer", not a short document


class IngestError(ValueError):
    """The upload is refused and nothing was written. `status` is the HTTP status the API answers with."""

    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status


def safe_filename(name):
    """The base name only (no directories), without characters that could be misread, and with an allowed extension."""
    base = re.split(r"[\\/]", name or "")[-1]
    base = re.sub(r"[^\w .()\-]", "_", base, flags=re.UNICODE)
    base = re.sub(r"\s+", " ", base).strip(" .")
    if not base or len(base) > 120:
        raise IngestError("Tên tệp trống hoặc quá dài (tối đa 120 ký tự).")
    extension = "." + base.rsplit(".", 1)[-1].lower() if "." in base else ""
    if extension not in ALLOWED_EXTENSIONS:
        raise IngestError("Chỉ hỗ trợ tệp .txt (UTF-8) và .pdf có lớp văn bản. PDF dạng ảnh scan chưa được hỗ trợ (không có OCR).", 415)
    return base


def clean_text(text):
    """Basic cleaning: NFC, no control characters, line-end hyphenation joined, lines of a paragraph joined, blanks collapsed."""
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f​﻿]", "", text)
    text = re.sub(r"(?<=\w)-\n(?=[a-zà-ỹ])", "", text)          # "chống-\nthấm" -> "chốngthấm" (a hyphen at a line end)
    text = re.sub(r"[ \t]+", " ", text)
    paragraphs = (" ".join(p.split()) for p in re.split(r"\n\s*\n", text))
    return "\n\n".join(p for p in paragraphs if p)


def _decode_txt(data):
    if b"\x00" in data:
        raise IngestError("Tệp .txt chứa byte nhị phân; chỉ nhận văn bản UTF-8.")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise IngestError("Tệp .txt không phải UTF-8.") from exc


_PAGE_NUMBER = re.compile(r"^\s*(?:trang|page)?\s*\d{1,3}(?:\s*/\s*\d{1,3})?\s*$", re.I)


def _read_pdf(data, max_pages):
    """[(page number starting at 1, raw text)] of a text-based PDF."""
    if not data.lstrip().startswith(b"%PDF-"):
        raise IngestError("Tệp có đuôi .pdf nhưng nội dung không phải PDF.")
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise IngestError("Máy chủ chưa cài pypdf (pip install -r requirements.txt).", 503) from exc
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise IngestError("PDF được mã hóa hoặc có mật khẩu; chưa hỗ trợ.")
        if len(reader.pages) > max_pages:
            raise IngestError(f"PDF có {len(reader.pages)} trang, vượt giới hạn demo {max_pages} trang.", 413)
        extracted = [[line for line in (page.extract_text() or "").splitlines() if not _PAGE_NUMBER.match(line)]
                     for page in reader.pages]
        repeated = _running_lines(extracted)
        return [(number, "\n".join(line for line in lines if line.strip() not in repeated))
                for number, lines in enumerate(extracted, 1)]
    except IngestError:
        raise
    except Exception as exc:        # a parser of untrusted bytes can fail in many ways; none may become a server error
        raise IngestError("Không đọc được PDF (tệp hỏng hoặc không hợp lệ).") from exc


def _running_lines(pages, min_pages=4, share=0.6):
    """Lines repeated on most pages: running headers, footers and disclaimers, not content.

    Left in, they are glued to the body text of every chunk: they pollute search and, when they hold a negation ("không phải
    chính sách thật"), make the whole run-on sentence look negated. Only documents of `min_pages`+ pages are judged, and a line
    must be on `share` of the pages, so a heading used twice is never removed."""
    if len(pages) < min_pages:
        return set()
    seen = {}
    for lines in pages:
        for line in {l.strip() for l in lines if len(l.strip()) >= 8}:
            seen[line] = seen.get(line, 0) + 1
    return {line for line, n in seen.items() if n >= max(3, share * len(pages))}


def _units(text, size):
    """Sentences, each at most `size` characters (a longer one is cut at a space)."""
    units = []
    for paragraph in text.split("\n\n"):
        for sentence in re.split(r"(?<=[.!?;])\s+", paragraph):
            sentence = sentence.strip()
            while len(sentence) > size:
                cut = sentence.rfind(" ", 0, size)
                cut = cut if cut > size // 2 else size
                units.append(sentence[:cut].strip())
                sentence = sentence[cut:].strip()
            if sentence:
                units.append(sentence)
    return units


def chunk_text(text, size, overlap):
    """Chunks of at most `size` characters that end on a sentence; each starts with the last sentences of the previous
    one (up to `overlap` characters), so a fact that straddles a boundary is whole in at least one chunk."""
    overlap = min(overlap, size // 2)
    chunks, current = [], []
    for unit in _units(text, size):
        if current and len(" ".join(current)) + 1 + len(unit) > size:
            chunks.append(" ".join(current))
            kept = []
            for previous in reversed(current):
                if sum(len(x) + 1 for x in kept) + len(previous) > overlap:
                    break
                kept.insert(0, previous)
            current = kept
            while current and len(" ".join(current)) + 1 + len(unit) > size:
                current.pop(0)
        current.append(unit)
    if current:
        chunks.append(" ".join(current))
    return chunks


def parse_upload(filename, data, settings):
    """Validate and turn an upload into documents. Raises IngestError before anything is written."""
    name = safe_filename(filename)
    if not data:
        raise IngestError("Tệp rỗng.")
    if len(data) > settings.doc_max_upload_bytes:
        raise IngestError(f"Tệp vượt giới hạn {settings.doc_max_upload_bytes // 1000} KB.", 413)
    if name.lower().endswith(".pdf"):
        pages = _read_pdf(data, settings.doc_max_pdf_pages)
    else:
        pages = [(None, _decode_txt(data))]
    pages = [(number, clean_text(text)) for number, text in pages]
    if sum(len(text) for _, text in pages) < MIN_TEXT_CHARS:
        raise IngestError("Không trích được văn bản. Có thể đây là PDF dạng ảnh scan: chưa hỗ trợ OCR.")
    # The id depends on the file NAME and the chunk number, so uploading the same name again replaces its chunks.
    ident = "UPL-" + hashlib.sha256(name.encode("utf-8")).hexdigest()[:12].upper()
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    documents = []
    for number, text in pages:                      # chunks never cross a page, so the page of a citation is exact
        for piece in chunk_text(text, settings.doc_chunk_chars, settings.doc_chunk_overlap):
            index = len(documents) + 1
            if index > settings.doc_max_chunks:
                raise IngestError(f"Tài liệu tạo hơn {settings.doc_max_chunks} đoạn, vượt giới hạn demo.", 413)
            documents.append({"id": f"{ident}-{index:03d}", "title": name, "category": CATEGORY, "content": piece,
                              "filename": name, "page": number, "chunk_index": index, "ingested_at": stamp})
    return {"filename": name, "source": f"upload:{name}", "documents": documents, "pages": len(pages),
            "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def ingest_document(store, settings, filename, data):
    """Parse, then apply every chunk in ONE transaction (replacing earlier chunks of the same file name), then embed.

    Chunk vectors use the configured embedding provider; with it off, or unreachable, the chunks are still searchable by
    BM25 and the response says so. Sentence vectors are not built here (they need many more provider calls): run
    `python -m scripts.index_embeddings` for them.
    """
    parsed = parse_upload(filename, data, settings)
    documents = parsed.pop("documents")
    summary = store.apply(documents, source=parsed["source"], replace=True)
    embedding = index_vectors(store, settings, ids={d["id"] for d in documents}, spans=False)
    return {**parsed, "chunks": len(documents), "chunk_chars": settings.doc_chunk_chars,
            "chunk_overlap": min(settings.doc_chunk_overlap, settings.doc_chunk_chars // 2),
            "ids": [d["id"] for d in documents[:5]] + (["…"] if len(documents) > 5 else []),
            "store": summary, "embedding": embedding,
            "retrieval": "hybrid" if embedding.get("enabled") and embedding.get("indexed") else "bm25_only"}
