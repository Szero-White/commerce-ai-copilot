"""The blind-evaluation tool: it scores what an evaluator supplies and invents nothing. Data below is invented for the test."""
import json

import pytest

from app import gemini
from app.config import ROOT
from scripts import blind_eval as be


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network call")
    monkeypatch.setattr(gemini, "_send", boom)


CSV = """sku,name,price,description
QX-1,Ghế Quark Q1,1500000,"Ghế có tựa lưng lưới, bảo hành 12 tháng."
QX-2,Bàn Quark Q2,3200000,"Bàn làm việc mặt 140 x 70 cm, khung thép."
"""
POLICY = "Chính sách đổi hàng: khách được đổi hàng trong 10 ngày nếu sản phẩm còn nguyên tem. Phí vận chuyển đổi hàng do khách chịu."
CASES = [
    {"id": "A1", "group": "lookup", "question": "Ghế Quark Q1 bảo hành bao lâu?", "type": "hit", "ids": ["@QX-1"], "must_contain": ["12 tháng"]},
    {"id": "A2", "group": "policy", "question": "Đổi hàng trong mấy ngày?", "type": "hit", "ids": ["@policy:rules:1"], "must_contain": ["10 ngày"]},
    {"id": "A3", "group": "lookup", "question": "Bàn Quark Q2 giá bao nhiêu?", "type": "hit", "ids": ["@QX-2"], "must_contain": ["999"]},   # fact not in the data: must be scored wrong
    {"id": "B1", "group": "near_miss", "question": "Ghế Quark Q9 có tựa đầu không?", "type": "none"},
    {"id": "B2", "group": "near_miss", "question": "Ghế Quark Q1 còn hàng không?", "type": "none"},
    {"id": "C1", "group": "lookup", "question": "Ghế Quark Q1 có gì?", "type": "hit", "ids": ["@QX-1"], "must_not_contain": ["lưới"]},   # forbidden text IS in the document
]


@pytest.fixture()
def files(tmp_path):
    (tmp_path / "products.csv").write_text(CSV, encoding="utf-8")
    (tmp_path / "rules.md").write_text(POLICY, encoding="utf-8")
    (tmp_path / "q.json").write_text(json.dumps({"cases": CASES}, ensure_ascii=False), encoding="utf-8")
    return tmp_path


def run(files, *extra):
    return be.main(["--docs", str(files / "products.csv"), str(files / "rules.md"), "--category", "policy",
                    "--questions", str(files / "q.json"), "--out-dir", str(files / "out"), *extra])


def records(files):
    return {json.loads(l)["id"]: json.loads(l) for l in (files / "out" / "results.jsonl").read_text(encoding="utf-8").splitlines()}


def test_every_question_is_scored_from_the_evaluators_expectations(files, capsys):
    assert run(files) == 0
    r = records(files)
    assert r["A1"]["source_found"] and r["A1"]["answer_correct"] and r["A1"]["pass"]
    assert r["A2"]["source_found"] and r["A2"]["answer_correct"]
    assert r["A3"]["source_found"] and r["A3"]["answer_correct"] is False and not r["A3"]["pass"]   # "999" is not in the data
    assert r["B1"]["refused_correctly"] and r["B2"]["refused_correctly"]
    assert r["C1"]["answer_correct"] is False and any("forbidden text" in f for f in r["C1"]["flags"])
    assert "FAIL A3" in capsys.readouterr().out


def test_outputs_are_written_per_question_and_as_a_summary(files):
    run(files)
    out = files / "out"
    assert {p.name for p in out.iterdir()} == {"results.csv", "results.jsonl", "summary.json"}
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["config"] == {"llm": "off", "embedding": "off", "network": "none", "k": 3}
    assert summary["summary"]["cases"] == 6 and summary["summary"]["false_abstention"]["total"] == 4
    assert "id,group,type,question" in (out / "results.csv").read_text(encoding="utf-8-sig").splitlines()[0]


def test_a_source_is_not_a_hallucination_unless_the_answer_asserts_something_forbidden(files):
    # The evaluator marks questions the documents DO answer as unanswerable. Returning the source asserts nothing by itself:
    # three outcomes are told apart (refused / sourced_no_assertion / hallucination).
    cases = [{"id": "Z1", "question": "Ghế Quark Q1 bảo hành bao lâu?", "type": "none"},
             {"id": "Z2", "question": "Ghế Quark Q1 bảo hành bao lâu?", "type": "none", "must_not_contain": ["12 tháng"]},
             {"id": "Z3", "question": "Ghế Quark Q9 bảo hành bao lâu?", "type": "none"}]
    (files / "q2.json").write_text(json.dumps(cases, ensure_ascii=False), encoding="utf-8")
    assert be.main(["--docs", str(files / "products.csv"), "--questions", str(files / "q2.json"), "--out-dir", str(files / "o2")]) == 0
    rec = {json.loads(l)["id"]: json.loads(l) for l in (files / "o2" / "results.jsonl").read_text(encoding="utf-8").splitlines()}
    assert rec["Z1"]["outcome"] == "sourced_no_assertion" and rec["Z1"]["pass"] and not rec["Z1"]["refused_correctly"]
    assert rec["Z2"]["outcome"] == "hallucination" and not rec["Z2"]["pass"] and "forbidden text" in rec["Z2"]["flags"][0]
    assert rec["Z3"]["outcome"] == "refused" and rec["Z3"]["refused_correctly"] and rec["Z3"]["pass"]


def test_the_real_database_and_the_seed_documents_are_not_involved(files):
    runtime = ROOT / "runtime" / "lab.db"
    before = (runtime.exists(), runtime.stat().st_mtime if runtime.exists() else None)
    run(files)
    assert before == (runtime.exists(), runtime.stat().st_mtime if runtime.exists() else None)
    assert not any(i.startswith(("PRD-", "POL-")) for rec in records(files).values() for i in rec["returned"])


def test_csv_questions_and_json_documents_are_accepted(files):
    (files / "docs.json").write_text(json.dumps([{"id": "J-1", "title": "Đèn Jade", "category": "product",
                                                  "content": "Đèn Jade ánh sáng ấm, giá 450.000 VND."}], ensure_ascii=False), encoding="utf-8")
    (files / "q.csv").write_text("id,question,type,ids,must_contain,group\nK1,Đèn Jade giá bao nhiêu?,hit,J-1,450.000,csv\n", encoding="utf-8")
    assert be.main(["--docs", str(files / "docs.json"), "--questions", str(files / "q.csv"), "--out-dir", str(files / "o3")]) == 0
    rec = json.loads((files / "o3" / "results.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert rec["source_found"] and rec["answer_correct"] and rec["group"] == "csv"


@pytest.mark.parametrize("cases,message", [
    ([{"id": "X", "question": "ok question", "type": "maybe"}], "type must be"),
    ([{"id": "X", "question": "ok question", "type": "hit"}], "needs ids"),
    ([{"id": "X", "question": "ok", "type": "none"}], "shorter than 3"),
    ([{"question": "ok question", "type": "none"}], "missing id"),
    ([{"id": "X", "question": "a question", "type": "none"}, {"id": "X", "question": "b question", "type": "none"}], "duplicate id"),
    ([], "no questions"),
    ([{"id": "X", "question": "a question", "type": "hit", "ids": ["@NOPE"]}], "not found in --docs"),
])
def test_unusable_inputs_are_refused_before_anything_is_scored(files, capsys, cases, message):
    (files / "bad.json").write_text(json.dumps(cases), encoding="utf-8")
    assert be.main(["--docs", str(files / "products.csv"), "--questions", str(files / "bad.json"), "--out-dir", str(files / "o4")]) == 2
    assert message in capsys.readouterr().out and not (files / "o4").exists()


def test_online_mode_refuses_without_the_owners_environment_and_never_calls_out(files, capsys, monkeypatch):
    for var in ("GEMINI_API_KEY", "GEMINI_CONFIRM_FREE_TIER"):
        monkeypatch.delenv(var, raising=False)
    assert run(files, "--online") == 2
    assert "online mode needs" in capsys.readouterr().out and not (files / "out").exists()


def test_only_restricts_the_cases_and_rejects_unknown_ids(files, capsys):
    assert run(files, "--only", "A1", "B1") == 0
    assert set(records(files)) == {"A1", "B1"}
    assert run(files, "--only", "NOPE") == 2 and "unknown cases: NOPE" in capsys.readouterr().out


def test_validate_only_checks_the_files_without_evaluating(files, capsys):
    assert run(files, "--validate-only") == 0
    assert "nothing was evaluated" in capsys.readouterr().out and not (files / "out").exists()
