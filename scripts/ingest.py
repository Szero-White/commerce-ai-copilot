"""Offline knowledge import for .txt, .md or .csv files. No unauthenticated upload endpoint.

    python -m scripts.ingest data/sample_products.csv                 # add or update (source = file name)
    python -m scripts.ingest policies.md --category policy --source shop-policies --replace-source
    python -m scripts.ingest --delete-source shop-policies            # withdraw everything that file contributed
    python -m scripts.ingest --delete PRD-101                         # withdraw one document
    python -m scripts.ingest --check                                  # compare documents with their indexes

A whole file is applied in ONE transaction (all or nothing). Ids depend on the source name and the SKU / chunk number,
never on the file path, so moving or re-running a file updates the same documents instead of duplicating them.
The text index (BM25) is updated in the same transaction. Vectors are NOT: changed or new documents have none until
`python -m scripts.index_embeddings` is run (that step calls the embedding provider, so it is a separate, explicit action).
"""
import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from app.config import Settings
from app.storage import Store

CHUNK = 800


def _ident(prefix, *parts):
    return prefix + "-" + hashlib.sha256("\0".join(parts).encode()).hexdigest()[:12].upper()


def parse_file(path, category="knowledge", source=None):
    """Read a file into (documents, source). Raises ValueError, writing nothing, when the file is not acceptable."""
    path = Path(path)
    if not path.is_file() or path.suffix.lower() not in {".txt", ".md", ".csv"}:
        raise ValueError("Only .txt, .md and .csv files are allowed")
    if path.stat().st_size > 2_000_000:
        raise ValueError("File exceeds 2 MB demo import limit")
    source = (source or path.stem).strip()
    if not source:
        raise ValueError("A source name is required")
    try:
        if path.suffix.lower() == ".csv":
            return _parse_csv(path, source), source
        return _parse_text(path, category, source), source
    except UnicodeDecodeError as exc:
        raise ValueError(f"{path.name} is not valid UTF-8 text") from exc


def _parse_csv(path, source):
    docs, seen = [], set()
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = {(h or "").strip().lower() for h in (reader.fieldnames or [])}
        if not {"name", "description"} <= headers:
            raise ValueError("CSV requires name and description headers")
        for index, raw in enumerate(reader, 1):
            if index > 500:
                raise ValueError("CSV exceeds 500 rows")
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
            if not any(row.values()):
                continue
            name, description = row.get("name"), row.get("description")
            if not name or not description:
                raise ValueError(f"Row {index}: name and description are required")
            sku = row.get("sku") or f"ROW-{index}"
            if sku.lower() in seen:
                raise ValueError(f"Row {index}: duplicate sku {sku!r}")
            seen.add(sku.lower())
            price = row.get("price") or "chưa có dữ liệu"
            if re.fullmatch(r"\d+(?:[.,]\d+)*", price):
                price += " VND"     # a bare number is read as VND, so that "giá dưới 1 triệu" can compare it (see README)
            docs.append({"id": _ident("CSV", source, sku.lower()), "title": f"{name} - {sku}",
                         "category": row.get("category") or "product",
                         "content": f"Tên: {name}. Mã: {sku}. Giá: {price}. Mô tả: {description}"})
    if not docs:
        raise ValueError("CSV has no data rows")
    return docs


def _parse_text(path, category, source):
    content = path.read_text(encoding="utf-8-sig").strip()
    if len(content) < 10:
        raise ValueError("Document too short")
    ident, docs, start = _ident("DOC", source), [], 0
    # Character-based chunks; word boundaries preserved where possible.
    while start < len(content):
        chunk = content[start:start + CHUNK]
        if len(chunk) == CHUNK and start + CHUNK < len(content):
            cut = chunk.rfind(" ", 500)
            if cut > 0:
                chunk = chunk[:cut]
        docs.append({"id": f"{ident}-{len(docs) + 1:03d}", "title": f"{path.stem} / phần {len(docs) + 1}",
                     "category": category, "content": chunk})
        start += len(chunk)
    return docs


def ingest_file(store, path, category="knowledge", source=None, replace=False):
    """Add or update the documents of a file atomically. Returns the counts (added, updated, unchanged, deleted)."""
    docs, source = parse_file(path, category, source)
    return {"source": source, **store.apply(docs, source=source, replace=replace)}


def import_file(store, path, category="knowledge"):
    """Backwards compatible helper: number of documents in the file."""
    result = ingest_file(store, path, category)
    return result["added"] + result["updated"] + result["unchanged"]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file", nargs="?", help="Path to .csv, .md or .txt")
    p.add_argument("--category", default="knowledge")
    p.add_argument("--source", help="name of the source (default: the file name without extension)")
    p.add_argument("--replace-source", action="store_true",
                   help="also remove documents of this source that are no longer in the file")
    p.add_argument("--delete", metavar="ID", help="remove one document")
    p.add_argument("--delete-source", metavar="SOURCE", help="remove every document that came from a source")
    p.add_argument("--check", action="store_true", help="report whether the indexes match the documents")
    args = p.parse_args(argv)
    settings = Settings()
    store = Store(settings.data_path)
    if args.check:
        report = store.consistency_report(settings.embedding_model if settings.embedding_provider != "off" else None)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1
    if args.delete:
        print(f"Deleted {int(store.delete(args.delete))} document(s).")
        return 0
    if args.delete_source:
        print(f"Deleted {store.delete_source(args.delete_source)} document(s) of source {args.delete_source!r}.")
        return 0
    if not args.file:
        p.error("a file, --delete, --delete-source or --check is required")
    try:
        result = ingest_file(store, args.file, args.category, args.source, args.replace_source)
    except ValueError as exc:
        print(f"Import refused, nothing was written: {exc}")
        return 2
    print("Imported " + ", ".join(f"{k}={v}" for k, v in result.items()))
    missing = store.consistency_report()["missing_vector"]
    if missing:
        print(f"{missing} document(s) have no vector. If embedding mode is enabled, run: python -m scripts.index_embeddings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
