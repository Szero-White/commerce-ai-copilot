"""Conservative evidence checks, NOT semantic fact verification.

A citation with an existing ID is not sufficient proof of factual accuracy.
These guards catch a narrow, testable class of bad numerical and unsupported
marketing claims; all LLM-created copy still requires a human to review it.
"""
import re
from .storage import normalize

_CITE = re.compile(r"\[([A-Za-z0-9-]+)\]")
_NUM = re.compile(r"(?<![A-Za-z0-9])\d+(?:[.,]\d+)*(?![A-Za-z0-9])")
# Commercial promises with serious consequences, regardless of whether they
# contain a number. Compare against evidence, not a language model's confidence.
_CLAIMS = (
    "free shipping", "free returns", "guaranteed delivery", "money back guarantee",
    "no questions asked", "lowest price", "best price", "limited offer",
    "giao hang mien phi", "mien phi van chuyen", "doi tra mien phi",
    "hoan tien 100", "giam gia", "bao dam hoan tien", "re nhat",
)


def numbers(value: str) -> set[str]:
    return {re.sub(r"[^0-9]", "", n) for n in _NUM.findall(value)}


def citation_ids(text: str) -> set[str]:
    return set(_CITE.findall(text))


def evidence_text(items: list[dict]) -> str:
    return "\n".join(f"{d.get('title','')}\n{d.get('content','')}" for d in items)


def valid_cited_answer(answer: str, sources: list[dict]) -> bool:
    """Checks source IDs and numerical literals ONLY (not semantic grounding).

    Numerical literals in the answer must be present in *cited* sources. This
    prevents a fabricated 90% offer even when another uncited document has 90%.
    """
    ids = citation_ids(answer)
    by_id = {s['id']: s for s in sources}
    if not ids or not ids <= set(by_id):
        return False
    body = _CITE.sub("", answer)
    allowed = evidence_text([by_id[doc_id] for doc_id in ids])
    return not (numbers(body) - numbers(allowed))


def safe_marketing_copy(candidate: dict, product: dict) -> bool:
    """Reject risky unsupported claims; this is a guard, not copy approval."""
    combined = "\n".join(candidate[k] for k in ('headline', 'body', 'cta'))
    source = evidence_text([product])
    if numbers(combined) - numbers(source):
        return False
    norm_copy, norm_source = normalize(combined), normalize(source)
    # For all promises, require that the source itself mentions that promise.
    return all(claim not in norm_copy or claim in norm_source for claim in _CLAIMS)
