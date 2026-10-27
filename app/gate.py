"""The evidence gate: one set of hard constraints for every candidate document, lexical or semantic.

What is decided here:
* `check_document` - constraints a document must meet whatever found it: names and model codes, exact numbers and
  quantities, a stock figure when stock is asked, comparison conditions computed from the document's numbers.
* `admit_semantic` - when a document found only by meaning may be admitted at all.

What is NOT claimed: a similarity score, a z-score or a matching sentence ("span") shows that a document is probably
RELEVANT to the question. None of them shows that a statement is TRUE. Facts reach the answer only as quoted text,
as a number comparison done by `quantities.evaluate`, or through the checks in `evidence.py`.
"""
import statistics
from dataclasses import dataclass

from .quantities import evaluate, exact_matches
from .query import POLICY_CATEGORIES, states_offer, states_stock


@dataclass(frozen=True)
class Verdict:
    admitted: bool
    condition: str | None = None     # None (no comparison asked) | 'satisfied' | 'unverified'
    reason: str = ""


def check_document(analysis, text: str, tokens: list[str], category: str | None = None) -> Verdict:
    """Hard constraints taken from the question; independent of how the document was found."""
    present = set(tokens)
    if analysis.asks_private and category is not None and category not in POLICY_CATEGORIES:
        return Verdict(False, reason="private data or an action on an order was asked: only policy documents may answer")
    if analysis.asks_offer and not states_offer(tokens):
        return Verdict(False, reason="an offer was asked and the document states none")
    if any(name not in present for name in analysis.names):
        return Verdict(False, reason="a name or model code in the question is not in the document")
    if any(any(c.isdigit() for c in t) and t not in present for t in analysis.terms):
        return Verdict(False, reason="a number or code in the question is not in the document")
    if analysis.quantities and not exact_matches(analysis.quantities, text):
        return Verdict(False, reason="a quantity with its unit is not stated in the document")
    if analysis.asks_stock and not states_stock(tokens):
        return Verdict(False, reason="stock was asked and the document states no figure")
    if not analysis.conditions:
        return Verdict(True)
    results = [evaluate(c, text) for c in analysis.conditions]
    if "no" in results:
        return Verdict(False, reason="a comparison condition is not met")
    return Verdict(True, "satisfied" if set(results) == {"yes"} else "unverified")


@dataclass(frozen=True)
class SemanticParams:
    """Defaults are deliberately strict and UNCALIBRATED; they are meaningless until measured on real embeddings."""
    tau: float = 0.55            # minimum similarity of the document
    z_min: float = 3.0           # robust z-score: spreads above the median score of all documents for this question
    min_spread: float = 0.02     # floor of the spread, so identical scores cannot produce a huge z-score
    gap_min: float = 0.03        # single-answer questions: lead over the runner-up
    delta: float = 0.05          # list questions: distance below the best score that still counts as the same group
    tau_span: float = 0.55       # minimum similarity of the best matching sentence of the document
    max_single: int = 2
    max_list: int = 5


def admit_semantic(scores: dict, spans: dict, single_answer: bool, passes, params: SemanticParams = SemanticParams()):
    """Document ids admitted by meaning alone, each with the sentence that is shown as the evidence.

    scores: {doc_id: similarity of the whole document}; spans: {doc_id: (similarity, sentence)} of its best sentence.
    passes: callable(doc_id) -> bool applying `check_document`. Nothing is admitted without a matching sentence, so
    a database without sentence vectors admits nothing (a safe default, not a bug).
    """
    if len(scores) < 3:
        return []                              # no distribution to compare a score against
    # Robust z-score (median and MAD): a handful of relevant documents must not inflate the spread they are judged by.
    values = list(scores.values())
    centre = statistics.median(values)
    spread = max(1.4826 * statistics.median(abs(v - centre) for v in values), params.min_spread)
    limit = params.max_single if single_answer else params.max_list
    ranked = sorted(scores, key=scores.get, reverse=True)
    eligible = [d for d in ranked[:limit * 3] if passes(d)]     # the hard constraints veto before anything else
    if not eligible:
        return []
    best = scores[eligible[0]]
    if single_answer and len(eligible) > 1 and best - scores[eligible[1]] < params.gap_min:
        return []                              # two documents are equally good: ask, do not pick one
    admitted = []
    for doc_id in eligible:
        score = scores[doc_id]
        if score < params.tau or (score - centre) / spread < params.z_min:
            break
        if score < best - params.delta:
            break                              # the tail: another, clearly lower group
        span = spans.get(doc_id)
        if not span or span[0] < params.tau_span:
            continue
        admitted.append((doc_id, span[1]))
        if len(admitted) >= limit:
            break
    return admitted
