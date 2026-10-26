"""Offline import for .txt, .md, or CSV products. No unauthenticated upload endpoint."""
import argparse
import csv
import hashlib
from pathlib import Path
from app.config import Settings
from app.storage import Store


def import_file(store, path, category="knowledge"):
    path=Path(path)
    if not path.is_file() or path.suffix.lower() not in {".txt",".md",".csv"}:
        raise ValueError("Only .txt, .md and .csv files are allowed")
    if path.stat().st_size > 2_000_000:
        raise ValueError("File exceeds 2 MB demo import limit")
    docs=[]
    if path.suffix.lower()==".csv":
        with path.open(encoding="utf-8-sig",newline="") as f:
            rows=csv.DictReader(f)
            for index, row in enumerate(rows,1):
                if index>500:
                    raise ValueError("CSV exceeds 500 rows")
                name=(row.get("name") or "").strip()
                description=(row.get("description") or "").strip()
                if not name or not description:
                    raise ValueError("CSV requires name and description headers")
                sku=(row.get("sku") or f"ROW-{index}").strip()
                price=(row.get("price") or "chưa có dữ liệu").strip()
                # Namespaced hash prevents collisions with existing sample IDs.
                ident="CSV-"+hashlib.sha256((str(path.resolve())+sku).encode()).hexdigest()[:12].upper()
                docs.append({"id":ident,"title":f"{name} - {sku}","category":"product",
                             "content":f"Tên: {name}. Mã: {sku}. Giá: {price}. Mô tả: {description}"})
    else:
        content=path.read_text(encoding="utf-8-sig").strip()
        if len(content)<10:
            raise ValueError("Document too short")
        ident="DOC-"+hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:12].upper()
        # Character-based chunks with overlap; word boundaries preserved where possible.
        start=0
        while start<len(content):
            chunk=content[start:start+800]
            if len(chunk)==800 and start+800<len(content):
                cut=chunk.rfind(" ",500)
                if cut>0: chunk=chunk[:cut]
            docs.append({"id":ident+f"-{len(docs)+1:03d}","title":f"{path.stem} / phần {len(docs)+1}",
                         "category":category,"content":chunk})
            start+=len(chunk)
    for d in docs:
        store.upsert(d)
    return len(docs)


if __name__=="__main__":
    p=argparse.ArgumentParser(description="Import local sample knowledge into the demo")
    p.add_argument("file",help="Path to .csv, .md or .txt")
    p.add_argument("--category",default="knowledge")
    args=p.parse_args()
    print(f"Imported {import_file(Store(Settings().data_path),args.file,args.category)} documents. ")
    print("If embedding mode is enabled, re-run: python -m scripts.index_embeddings")
