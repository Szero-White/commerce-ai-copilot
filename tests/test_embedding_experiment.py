"""B1 experiment harness, tested with invented vectors. NOTHING here calls an API or says anything about a real embedding model."""
import json

import pytest

from app import gemini
from app.embedding_cache import EmbeddingCache
from app.storage import Store
from scripts import embedding_experiment as ex


@pytest.fixture(autouse=True)
def never_touch_the_network(monkeypatch, tmp_path):
    def boom(*args, **kwargs):
        raise AssertionError("the experiment tried to call the network")
    monkeypatch.setattr(gemini, "_send", boom)
    monkeypatch.setattr(gemini, "CACHE_PATH", tmp_path / "cache.db")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_CONFIRM_FREE_TIER", raising=False)


def test_the_planned_texts_are_dev_data_only_and_fit_the_budget(tmp_path):
    cases = ex.load_cases()
    assert cases and all(c["id"][0] in "DUAN" for c in cases)          # D/U/A = dev, NM = near-miss; never H = holdout
    store = Store(tmp_path / "s.db")
    plan = ex.plan_texts(store.documents(), cases)
    assert len(plan["texts"]) == len(set(plan["texts"])) <= ex.EMBED_TEXT_BUDGET
    assert all(len(s) >= ex.SPAN_MIN_CHARS for spans in plan["spans"].values() for s in spans)


def test_dry_run_sends_nothing_and_says_what_it_would_send(capsys):
    assert ex.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "new:" in out and "embedding requests" in out and "nothing was sent" in out.lower()


def test_a_real_run_refuses_without_the_key_and_the_free_tier_confirmation(capsys, monkeypatch):
    assert ex.main(["--run"]) == 2
    monkeypatch.setenv("GEMINI_API_KEY", "x" * 30)
    assert ex.main(["--run"]) == 2                                       # key but no confirmation
    assert "Nothing was sent" in capsys.readouterr().out


def test_cache_only_mode_never_embeds_and_reports_what_is_missing(capsys):
    assert ex.main(["--cache-only"]) == 3
    assert "not in the embedding cache" in capsys.readouterr().out


def test_cache_only_mode_analyses_cached_vectors(tmp_path, capsys, monkeypatch):
    from app.config import Settings
    model = Settings().embedding_model if False else "gemini-embedding-001"
    store = Store(tmp_path / "x.db")
    cases = ex.load_cases()
    texts = ex.plan_texts(store.documents(), cases)["texts"]
    EmbeddingCache(gemini.CACHE_PATH).put_many(model, {t: [float(i % 7) + 1, float(i % 5) + 1, 1.0] for i, t in enumerate(texts)})
    out = tmp_path / "report.json"
    assert ex.main(["--cache-only", "--out", str(out)]) == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["requests_made"] == 0 and "decision" in report and report["lexical_only"]["positives"] > 0
    assert "relevance, not truth" in report["caveat"]


# ---- the analysis, on an invented catalogue --------------------------------------------------------------------------
TOPICS = ["amber", "birch", "cedar", "dune", "ember", "fjord"]
DIM = 8


def vec(**weights):
    v = [0.0] * DIM
    for name, w in weights.items():
        v[(TOPICS + ["noise", "other"]).index(name)] = w
    return v


@pytest.fixture()
def mini(tmp_path):
    store = Store(tmp_path / "mini.db")
    store.delete_source("seed")
    docs = [{"id": f"X-{t}", "title": f"Item {t}", "category": "product",
             "content": f"Item {t} is described here in one plain sentence about {t}."} for t in TOPICS]
    store.apply(docs, source="mini")
    vectors, spans = {}, {}
    for d in store.documents():
        topic = d["id"][2:]
        vectors[ex.doc_text(d)] = vec(**{topic: 1.0})
        spans[d["id"]] = ex.split_sentences(d["content"])
        for s in spans[d["id"]]:
            vectors[s] = vec(**{topic: 0.95, "noise": 0.1})
    return store, vectors, spans


def run(mini, cases, question_vectors):
    store, vectors, spans = mini
    vectors = {**vectors, **{c["question"]: question_vectors[c["id"]] for c in cases}}
    return ex.analyse(store, cases, vectors, spans, requests_made=10)


CASES = [
    {"id": "S1", "group": "synonym_need", "type": "hit", "ids": ["X-amber"], "question": "qqq wxyz amberish need"},
    {"id": "S2", "group": "synonym_need", "type": "hit", "ids": ["X-birch"], "question": "rrr wxyz birchish need"},
    {"id": "N1", "group": "unsupported", "type": "none", "question": "totally unrelated qqq"},
    {"id": "NM1", "group": "near_miss", "type": "none", "question": "almost cedar qqq"},
    {"id": "NM2", "group": "near_miss", "type": "none", "question": "Có Zephyr Pro dune không"},
]
QV = {"S1": vec(amber=0.9, noise=0.1), "S2": vec(birch=0.9, noise=0.1), "N1": vec(other=1.0),
      "NM1": vec(cedar=0.5, other=0.8), "NM2": vec(dune=0.95, noise=0.05)}


def test_semantic_matches_are_admitted_and_near_misses_are_not(mini):
    report = run(mini, CASES, QV)
    assert report["lexical_only"]["synonym_hits"] == 0 and report["lexical_only"]["leaks"] == 0
    chosen, m = report["chosen_params"], report["chosen_metrics"]
    assert chosen and m["synonym_hits"] == 2 and m["leaks"] == 0          # NM1 is only 0.53 similar: tau must exclude it
    assert report["decision"]["synonym_gain_points"] == 100.0           # 2 of 2 synonym cases found, lexical found none
    final = {c["id"]: c["final"] for c in report["cases_with_chosen_params"]}
    assert final["S1"] == ["X-amber"] and final["S2"] == ["X-birch"] and final["N1"] == [] and final["NM1"] == []


def test_the_hard_constraint_is_what_stops_an_unknown_name_that_looks_similar(mini):
    report = run(mini, CASES, QV)
    final = {c["id"]: c["final"] for c in report["cases_with_chosen_params"]}
    assert final["NM2"] == []                                              # "Zephyr Pro" is not in any document
    assert report["ablation"]["hard"]["has_measured_effect"] is True        # without the veto it leaks


def test_no_configuration_is_chosen_when_a_negative_looks_exactly_like_a_positive(mini):
    cases = [CASES[0], {"id": "N2", "group": "unsupported", "type": "none", "question": "lookalike qqq"}]
    report = run(mini, cases, {"S1": vec(amber=0.9, noise=0.1), "N2": vec(amber=0.9, noise=0.1)})
    assert report["chosen_params"] is None
    assert not report["decision"]["enable_hybrid_allowed"] and any("(b)" in r for r in report["decision"]["unmet"])


def test_the_decision_rule_reports_every_unmet_condition():
    lexical = {"synonym_hits": 0, "synonym_total": 8}
    good = {"synonym_hits": 4, "synonym_total": 8, "leaks": 0}
    effect = {c: {"has_measured_effect": True} for c in ("tau", "z", "span", "delta", "gap", "hard")}
    assert ex.decide(lexical, {"tau": 0.5}, good, effect, 18)["enable_hybrid_allowed"] is True
    small = ex.decide(lexical, {"tau": 0.5}, {**good, "synonym_hits": 1}, effect, 18)       # 12.5 points < 15
    assert small["unmet"] and "(a)" in small["unmet"][0]
    assert any("(b)" in r for r in ex.decide(lexical, {"tau": 0.5}, {**good, "leaks": 1}, effect, 18)["unmet"])
    idle = {**effect, "z": {"has_measured_effect": False}}
    assert any("(c)" in r and "z" in r for r in ex.decide(lexical, {"tau": 0.5}, good, idle, 18)["unmet"])
    assert any("(d)" in r for r in ex.decide(lexical, {"tau": 0.5}, good, effect, 30)["unmet"])
    assert ex.decide(lexical, None, None, {}, 18)["enable_hybrid_allowed"] is False


def test_sentences_are_split_for_evidence_spans():
    text = "Short. Giá niêm yết 450.000 VND cho bản tiêu chuẩn; bảo hành 12 tháng theo chính sách. Thêm một câu đủ dài để làm bằng chứng."
    spans = ex.split_sentences(text)
    assert len(spans) == 3 and spans[0].startswith("Giá niêm yết 450.000 VND")      # a decimal point is not a boundary
    assert all(len(s) >= ex.SPAN_MIN_CHARS for s in spans) and not any(s == "Short." for s in spans)
