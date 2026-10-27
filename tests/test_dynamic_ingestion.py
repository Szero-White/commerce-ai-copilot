"""Adding, changing and withdrawing knowledge: every index follows the documents, no old data is served.

All products and policies here are invented for the test; nothing in the code under test knows them.
"""
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services import question_answer
from app.storage import Store
from scripts import ingest


@pytest.fixture()
def db(tmp_path):
    return tmp_path / "kb.db"


@pytest.fixture()
def store(db):
    return Store(db)


def write(path: Path, text: str):
    path.write_text(text, encoding="utf-8")
    return path


CATALOGUE = """sku,name,price,description
LMP-1,Đèn đọc sách Nimbus,320000,Đèn đọc sách kẹp đầu giường ánh sáng ấm
SFA-2,Sofa Cumulus hai chỗ,6900000,Sofa vải bố hai chỗ ngồi cho phòng khách nhỏ
"""


def ids(store, question, limit=5):
    return [d["id"] for d in store.fts_search(question, limit=limit)]


def source_ids(store, source):
    return sorted(d["id"] for d in store.documents() if d.get("source") == source)


def answer(db, question):
    settings = Settings(data_path=db, llm_provider="off", embedding_provider="off")
    return question_answer(Store(db), settings, question)


# ---- add ----------------------------------------------------------------------------------------------------------
def test_new_products_are_searchable_right_after_the_import_by_name_need_and_without_diacritics(store, tmp_path):
    result = ingest.ingest_file(store, write(tmp_path / "shop.csv", CATALOGUE))
    assert result == {"source": "shop", "added": 2, "updated": 0, "unchanged": 0, "deleted": 0}
    lamp = source_ids(store, "shop")
    assert ids(store, "Có sofa nào không?")[0] in lamp
    assert ids(store, "den doc sach nimbus gia bao nhieu")[0] in lamp
    assert "320000" in answer(store.path, "den doc sach nimbus gia bao nhieu")["answer"]
    assert store.consistency_report()["ok"]


def test_a_running_server_sees_an_import_made_by_another_process(db, tmp_path):
    server = Store(db)
    assert ids(server, "sofa cumulus") == []
    ingest.ingest_file(Store(db), write(tmp_path / "shop.csv", CATALOGUE))   # the CLI opens its own Store
    assert ids(server, "sofa cumulus")                                         # no restart, no cache flush


def test_vocabulary_is_cached_until_the_documents_change(store, tmp_path):
    first = store._corpus()
    assert store._corpus() is first
    version = store.corpus_version()
    ingest.ingest_file(store, write(tmp_path / "shop.csv", CATALOGUE))
    assert store.corpus_version() > version and store._corpus() is not first
    again = store.corpus_version()
    ingest.ingest_file(store, tmp_path / "shop.csv")                           # identical content: nothing changes
    assert store.corpus_version() == again


# ---- update -------------------------------------------------------------------------------------------------------
def test_an_update_replaces_the_old_text_everywhere(db, tmp_path):
    store = Store(db)
    path = write(tmp_path / "shop.csv", CATALOGUE)
    ingest.ingest_file(store, path)
    assert "6900000" in answer(db, "Sofa Cumulus hai chỗ giá bao nhiêu?")["answer"]
    write(path, CATALOGUE.replace("6900000", "5490000"))
    result = ingest.ingest_file(store, path)
    assert result["updated"] == 1 and result["unchanged"] == 1
    now = answer(db, "Sofa Cumulus hai chỗ giá bao nhiêu?")["answer"]
    assert "5490000" in now and "6900000" not in now
    stale = store.fts_search("sofa cumulus 6900000")                            # a question quoting the OLD figure
    assert [d.get("condition_status") for d in stale] == ["premise_mismatch"]   # flagged as contradicted, not confirmed
    assert "6900000" not in stale[0]["content"] and "5490000" in stale[0]["content"]
    assert store.consistency_report()["ok"]


def test_a_changed_document_loses_its_vector_but_an_unchanged_one_keeps_it(store, tmp_path):
    path = write(tmp_path / "shop.csv", CATALOGUE)
    ingest.ingest_file(store, path)
    for doc in source_ids(store, "shop"):
        store.update_embedding(doc, [0.1, 0.2], "model-x")
    ingest.ingest_file(store, path)                                            # same file again
    assert all(store.document(d)["embedding_json"] for d in source_ids(store, "shop"))
    write(path, CATALOGUE.replace("6900000", "5490000"))
    ingest.ingest_file(store, path)
    sofa = [d for d in store.documents() if "Sofa" in d["title"]][0]
    lamp = [d for d in store.documents() if "Nimbus" in d["title"]][0]
    assert sofa["embedding_json"] is None and sofa["embedding_model"] is None   # a vector of the old text is never reused
    assert lamp["embedding_json"] is not None
    report = store.consistency_report()
    assert report["missing_vector"] >= 1 and report["ok"]


# ---- delete -------------------------------------------------------------------------------------------------------
def test_deleting_a_source_removes_text_index_and_vectors(store, tmp_path):
    ingest.ingest_file(store, write(tmp_path / "shop.csv", CATALOGUE))
    gone = source_ids(store, "shop")
    store.update_embedding(gone[0], [1.0], "m")
    assert store.delete_source("shop") == 2
    assert ids(store, "sofa cumulus") == [] and ids(store, "đèn đọc sách nimbus") == []
    assert not any(d["id"] in gone for d in store.documents())
    assert store.consistency_report()["ok"]
    assert "Nimbus" not in answer(store.path, "Đèn đọc sách Nimbus giá bao nhiêu?")["answer"]


def test_delete_one_document_and_unknown_ids_are_harmless(store, tmp_path):
    ingest.ingest_file(store, write(tmp_path / "shop.csv", CATALOGUE))
    first, second = source_ids(store, "shop")
    assert store.delete(first) is True and store.delete(first) is False and store.delete("NOPE") is False
    assert store.document(second) and store.consistency_report()["ok"]
    with pytest.raises(ValueError):
        store.delete_source("")


def test_replace_source_removes_chunks_that_no_longer_exist(store, tmp_path):
    long_text = ("Chính sách giao nhanh áp dụng cho khu vực nội thành. " * 40) + "Điều khoản cuối cùng về đổi hàng."
    path = write(tmp_path / "policy.md", long_text)
    ingest.ingest_file(store, path, category="policy")
    chunks = source_ids(store, "policy")
    assert len(chunks) >= 2
    write(path, "Chính sách mới: chỉ giao trong ngày.")
    result = ingest.ingest_file(store, path, category="policy", replace=True)
    assert result["deleted"] == len(chunks) - 1 and len(source_ids(store, "policy")) == 1
    assert ids(store, "điều khoản cuối cùng về đổi hàng") == []
    assert store.consistency_report()["ok"]


# ---- atomicity and validation -------------------------------------------------------------------------------------
def test_a_failure_in_the_middle_of_an_import_changes_nothing(store):
    before = (len(store.documents()), store.corpus_version())
    good = {"id": "G-1", "title": "Hợp lệ", "category": "product", "content": "Mô tả hợp lệ"}
    broken = {"id": "G-2", "title": "Thiếu nội dung", "category": "product"}      # no content: fails after G-1 was written
    with pytest.raises(KeyError):
        store.apply([good, broken], source="batch")
    assert store.document("G-1") is None and ids(store, "hợp lệ") == []
    assert (len(store.documents()), store.corpus_version()) == before
    assert store.consistency_report()["ok"]


@pytest.mark.parametrize("name,body,message", [
    ("dup.csv", "sku,name,description\nA,x,y\nA,z,w\n", "duplicate sku"),
    ("nohead.csv", "foo,bar\n1,2\n", "name and description"),
    ("emptyrow.csv", "sku,name,description\nA,,y\n", "required"),
    ("blank.csv", "sku,name,description\n", "no data rows"),
    ("short.txt", "ngắn", "too short"),
    ("data.json", "{}", "Only .txt"),
])
def test_unacceptable_files_are_refused_before_anything_is_written(store, tmp_path, name, body, message):
    before = store.corpus_version()
    with pytest.raises(ValueError, match=message):
        ingest.ingest_file(store, write(tmp_path / name, body))
    assert store.corpus_version() == before


def test_a_file_that_is_not_utf8_is_refused(store, tmp_path):
    bad = tmp_path / "bad.txt"
    bad.write_bytes(b"\xff\xfe\xfa" * 10)
    with pytest.raises(ValueError, match="UTF-8"):
        ingest.ingest_file(store, bad)


def test_ids_do_not_depend_on_the_path_so_moving_a_file_never_duplicates(store, tmp_path):
    (tmp_path / "a").mkdir(); (tmp_path / "b").mkdir()
    ingest.ingest_file(store, write(tmp_path / "a" / "shop.csv", CATALOGUE))
    count = len(store.documents())
    again = ingest.ingest_file(store, write(tmp_path / "b" / "shop.csv", CATALOGUE))
    assert again["unchanged"] == 2 and len(store.documents()) == count
    other = ingest.ingest_file(store, tmp_path / "b" / "shop.csv", source="shop-b")   # a different source is a different id space
    assert other["added"] == 2


def test_apply_rejects_duplicate_ids_and_replace_without_source(store):
    doc = {"id": "X", "title": "t", "category": "c", "content": "body text here"}
    with pytest.raises(ValueError):
        store.apply([doc, doc])
    with pytest.raises(ValueError):
        store.apply([doc], replace=True)


# ---- consistency --------------------------------------------------------------------------------------------------
def _sql(db, *statements):
    cx = sqlite3.connect(db)
    for s in statements:
        cx.execute(s)
    cx.commit(); cx.close()


def test_consistency_report_detects_each_kind_of_drift(store, db):
    ingest.ingest_file(store, write(db.parent / "shop.csv", CATALOGUE))
    sofa = [d["id"] for d in store.documents() if "Sofa" in d["title"]][0]
    lamp = [d["id"] for d in store.documents() if "Nimbus" in d["title"]][0]
    assert store.consistency_report()["ok"]
    _sql(db, f"DELETE FROM document_fts WHERE doc_id='{lamp}'",
         "INSERT INTO document_fts(doc_id,normalized_text) VALUES('GHOST','orphan row')",
         f"UPDATE document_fts SET normalized_text='old text' WHERE doc_id='{sofa}'",
         f"UPDATE documents SET embedding_json='not json', embedding_model='other' WHERE id='{sofa}'",
         "INSERT INTO documents(id,title,category,content) VALUES('CSV-LEGACY','t','product','legacy row')")
    text = json.dumps(store.consistency_report("wanted-model"))
    for expected in ("missing from the text index", "text index row without a document", "text index is stale",
                     "unreadable vector", "expected 'wanted-model'", "CSV-LEGACY"):
        assert expected in text
    assert store.consistency_report()["ok"] is False


def test_opening_a_database_repairs_a_text_index_whose_count_still_matches(store, db):
    ingest.ingest_file(store, write(db.parent / "shop.csv", CATALOGUE))
    lamp = [d["id"] for d in store.documents() if "Nimbus" in d["title"]][0]
    _sql(db, f"DELETE FROM document_fts WHERE doc_id='{lamp}'",
         "INSERT INTO document_fts(doc_id,normalized_text) VALUES('GHOST','orphan row')")   # same row count as documents
    reopened = Store(db)
    assert reopened.consistency_report()["ok"] and ids(reopened, "đèn đọc sách nimbus")


def test_re_importing_an_unchanged_file_repairs_a_drifted_index_row(store, db):
    path = write(db.parent / "shop.csv", CATALOGUE)
    ingest.ingest_file(store, path)
    sofa = [d["id"] for d in store.documents() if "Sofa" in d["title"]][0]
    _sql(db, f"UPDATE document_fts SET normalized_text='old text' WHERE doc_id='{sofa}'")
    assert not store.consistency_report()["ok"]
    ingest.ingest_file(store, path)
    assert store.consistency_report()["ok"]


# ---- CLI and API --------------------------------------------------------------------------------------------------
def test_command_line_flow_add_check_delete(db, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DATA_PATH", str(db))
    monkeypatch.setattr(ingest, "Settings", lambda: Settings(data_path=db, embedding_provider="off"))
    path = write(tmp_path / "shop.csv", CATALOGUE)
    assert ingest.main([str(path)]) == 0 and "added=2" in capsys.readouterr().out
    assert ingest.main(["--check"]) == 0
    assert ingest.main([str(write(tmp_path / "bad.csv", "sku,name,description\nA,,y\n"))]) == 2
    assert "nothing was written" in capsys.readouterr().out
    assert ingest.main(["--delete-source", "shop"]) == 0 and "Deleted 2" in capsys.readouterr().out
    assert ingest.main(["--delete", "NOPE"]) == 0 and "Deleted 0" in capsys.readouterr().out


def test_health_reports_documents_still_waiting_for_a_vector(db, tmp_path):
    off = TestClient(create_app(data_path=db)).get("/api/health").json()
    assert off["vector_missing"] is None and off["corpus_version"] >= 1
    settings = Settings(data_path=db, llm_provider="off", embedding_provider="ollama", embedding_model="m")
    client = TestClient(create_app(data_path=db, settings=settings))
    on = client.get("/api/health").json()
    assert on["vector_missing"] == on["documents"] and on["vector_indexed"] == 0
