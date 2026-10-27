"""Guards for the v4 evaluation data and harness (they protect the measurement, not the product)."""
import json
import re

import pytest

from app.config import ROOT
from app.storage import normalize
from scripts import quality_eval as qe

EVAL = ROOT / "data" / "eval_v4"
SEED_IDS = {d["id"] for d in json.loads((ROOT / "data" / "seed_documents.json").read_text(encoding="utf-8"))}
TYPES = {"hit", "none", "none_or_clarify"}


def _cases(name):
    return json.loads((EVAL / name).read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("name", ["dev.json", "near_miss.json", "holdout.json"])
def test_case_files_are_well_formed_and_expect_only_seed_documents(name):
    cases = _cases(name)
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids))
    for c in cases:
        assert c["type"] in TYPES and c["group"] and len(c["question"]) >= 3, c
        if c["type"] == "hit":
            assert c["ids"] and set(c["ids"]) <= SEED_IDS, c
            assert set(c.get("exclude", [])) <= SEED_IDS and c.get("min", 1) <= len(c["ids"]), c
        assert set(c.get("allow", [])) <= SEED_IDS, c


def test_sets_do_not_share_questions():
    seen = {}
    for name in ("dev.json", "near_miss.json", "holdout.json"):
        for c in _cases(name):
            key = " ".join(normalize(c["question"]).split())
            assert key not in seen, (name, c["id"], seen[key])
            seen[key] = (name, c["id"])


def test_holdout_matches_its_recorded_hash():
    # If this fails the holdout was edited after it was locked: it is no longer independent.
    qe.check_holdout_lock()


def test_holdout_cannot_be_run_without_final_flag():
    with pytest.raises(SystemExit):
        qe.main(["--set", "holdout"])


def test_wilson_interval_is_sane():
    low, high = qe.wilson(5, 10)
    assert 0.23 < low < 0.5 < high < 0.77
    assert qe.wilson(0, 0) == [None, None]
    assert qe.wilson(10, 10)[1] == 1.0


def _response(ids, mode="extractive_demo", answer=None):
    return {"sources": [{"id": i} for i in ids], "mode": mode,
            "answer": answer if answer is not None else "\n".join(f"[{i}] text" for i in ids)}


def test_judge_scores_each_case_type_from_the_expectation():
    hit = {"id": "x", "group": "g", "question": "q", "type": "hit", "ids": ["A", "B"], "min": 2, "exclude": ["Z"]}
    assert qe.judge(hit, _response(["A", "B"]), normalize)["pass"]
    assert not qe.judge(hit, _response(["A"]), normalize)["pass"]                # too few expected documents
    assert not qe.judge(hit, _response(["A", "B", "Z"]), normalize)["pass"]      # excluded document returned
    empty = qe.judge(hit, _response([]), normalize)
    assert empty["abstained"] and not empty["pass"]
    wrong = qe.judge({**hit, "min": 1}, _response(["Q"]), normalize)
    assert wrong["wrong_source_only"] and not wrong["pass"]

    none = {"id": "n", "group": "g", "question": "q", "type": "none", "allow": ["P"]}
    assert qe.judge(none, _response([]), normalize)["pass"]
    assert qe.judge(none, _response(["P"]), normalize)["pass"]
    leak = qe.judge(none, _response(["P", "Q"]), normalize)
    assert not leak["pass"] and leak["leaked"] == ["Q"]

    clarify = {"id": "c", "group": "g", "question": "q", "type": "none_or_clarify"}
    assert qe.judge(clarify, _response([]), normalize)["pass"]
    assert qe.judge(clarify, _response(["A"], mode="needs_clarification"), normalize)["pass"]
    assert not qe.judge(clarify, _response(["A"]), normalize)["pass"]


def test_answer_correctness_ignores_case_and_diacritics_but_not_missing_facts():
    case = {"id": "x", "group": "g", "question": "q", "type": "hit", "ids": ["A"], "must_contain": ["thép"]}
    assert qe.judge(case, _response(["A"], answer="[A] Chân THEP sơn tĩnh điện"), normalize)["answer_ok"]
    assert not qe.judge(case, _response(["A"], answer="[A] chân gỗ"), normalize)["answer_ok"]


def test_citation_correctness_rejects_ids_that_were_not_returned():
    case = {"id": "x", "group": "g", "question": "q", "type": "hit", "ids": ["A"]}
    assert qe.judge(case, _response(["A"], answer="[A] ok"), normalize)["citation_ok"]
    assert not qe.judge(case, _response(["A"], answer="[A] [B] ok"), normalize)["citation_ok"]


def test_summary_reports_rates_with_intervals_and_groups():
    results = [
        qe.judge({"id": "1", "group": "a", "question": "q", "type": "hit", "ids": ["A"]}, _response(["A"]), normalize),
        qe.judge({"id": "2", "group": "a", "question": "q", "type": "hit", "ids": ["A"]}, _response([]), normalize),
        qe.judge({"id": "3", "group": "b", "question": "q", "type": "none"}, _response(["A"]), normalize),
    ]
    s = qe.summarize(results, [1.0, 2.0, 3.0])
    assert s["retrieval_hit_at_3"]["passed"] == 1 and s["false_abstention"]["passed"] == 1
    assert s["unsupported_answer_leaks"]["passed"] == 1 and s["unsupported_answer_leaks"]["total"] == 1
    assert s["by_group"]["a"]["total"] == 2 and s["latency_ms"]["p50"] == 2.0
    assert re.fullmatch(r"[0-9a-f]{64}", qe.sha256_file(EVAL / "dev.json"))
