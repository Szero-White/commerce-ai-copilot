"""Conservative evidence checks, NOT semantic fact verification.

A citation with an existing ID is not sufficient proof of factual accuracy.
These guards catch a narrow, testable class of bad numerical and unsupported
marketing claims; all LLM-created copy still requires a human to review it.
"""
import re
import unicodedata
from .storage import normalize

_CITE = re.compile(r"\[([A-Za-z0-9-]+)\]")
# No letter/digit boundary: "130x60cm", "50k" and "Sale50%" must still yield numbers.
_NUM = re.compile(r"\d+(?:[.,]\d+)*")
# Commercial promises with serious consequences, regardless of whether they
# contain a number. Compare against evidence, not a language model's confidence.
# Normalized (ASCII, lowercase) and matched on word boundaries. This is a
# blocklist, not a complete policy: unlisted wording can still pass.
_CLAIMS = (
    "free shipping", "free delivery", "free ship", "ship free", "free returns", "free gift",
    "guaranteed delivery", "money back", "no questions asked", "lowest price", "best price",
    "best", "cheapest", "limited offer", "limited time", "sale", "discount", "promotion",
    "guarantee", "guaranteed", "cure", "cures", "heal", "heals", "clinically proven",
    "mien phi", "freeship", "hoan tien", "bao dam", "cam ket", "khuyen mai", "giam gia",
    "giam", "uu dai", "tang kem", "qua tang", "tang qua", "tot nhat", "re nhat", "gia tot",
    "chua khoi", "chua benh", "khoi benh", "dieu tri", "suc khoe", "nua gia", "so 1",
)
_NEGATIONS = ("không", "khong", "chưa", "chẳng", "not", "no", "cannot", "never", "without",
              "isnt", "dont", "cant")
# Commerce topics where affirming a source that only negates them is a policy error.
_TOPICS = ("doi tra", "hoan tien", "tra hang", "bao hanh", "giam gia", "mien phi", "giao hang",
           "van chuyen", "lap dat", "tai trong", "chung nhan", "kiem nghiem", "kiem dinh",
           "cong thai hoc", "tiet kiem dien", "ton kho", "cam ket", "return", "refund", "warranty",
           "discount", "shipping", "delivery", "stock", "installation", "eligible")
# Words that try to steer the model rather than describe an audience.
_STEERING = ("ignore", "instruction", "instructions", "system", "prompt", "assistant",
             "developer", "json", "headline", "bo qua", "chi thi")
_AUDIENCE_CHARS = re.compile(r"^[\w ,/\-]{1,120}$")


def numbers(value: str) -> set[str]:
    return {re.sub(r"[^0-9]", "", n) for n in _NUM.findall(value)}


def _has_phrase(norm_text: str, phrases) -> list[str]:
    padded = f" {' '.join(norm_text.split())} "
    return [p for p in phrases if f" {p} " in padded]


def context_window(settings, prompt_tokens: int) -> dict:
    """Prompt size reported by Ollama vs the configured window; near_limit means likely truncation."""
    return {"num_ctx": settings.num_ctx, "prompt_tokens": prompt_tokens,
            "near_limit": prompt_tokens >= 0.9 * settings.num_ctx}


def citation_ids(text: str) -> set[str]:
    return set(_CITE.findall(text))


def evidence_text(items: list[dict]) -> str:
    return "\n".join(f"{d.get('title','')}\n{d.get('content','')}" for d in items)


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?:[.!?;:]+(?:\s+|$))|\n+", text) if s.strip()]


def _negated(sentence: str) -> bool:
    """Accent-aware: "chưa" (not yet) is a negation, "chữa" (cure) is not; "không gian" is space."""
    padded = " " + " ".join(re.findall(r"\w+", unicodedata.normalize("NFC", sentence).lower())) + " "
    padded = padded.replace(" không gian ", " ").replace(" khong gian ", " ")
    return any(f" {w} " in padded for w in _NEGATIONS)


def _mentions(norm_sentence: str, topic: str) -> bool:
    return re.search(rf"\b{re.escape(topic)}(?:s|es|ed|ing)?\b", norm_sentence) is not None


def _source_sentences(sources: list[dict]) -> list[tuple[str, bool]]:
    # Titles are labels, not statements; only document content can affirm or negate a policy.
    content = "\n".join(d.get('content', '') for d in sources)
    return [(normalize(sentence), _negated(sentence)) for sentence in _sentences(content)]


def _sentence_problems(text: str, source: list[tuple[str, bool]]) -> list[str]:
    """Non-negated sentences that promise something the source negates or never affirms."""
    problems = []
    for sentence in _sentences(text):
        norm = normalize(sentence)
        if _negated(sentence):
            continue  # Restating a limitation ("not eligible", "chưa tích hợp") is safe.
        for claim in _has_phrase(norm, _CLAIMS):
            if not any(_mentions(s, claim) and not neg for s, neg in source):
                problems.append(f"promise '{claim}' is not affirmed by the source")
        for topic in _TOPICS:
            related = [neg for s, neg in source if _mentions(s, topic)]
            if related and all(related) and _mentions(norm, topic):
                problems.append(f"'{topic}' is negated in the source")
    return problems


def unsupported_claims(answer: str, sources: list[dict]) -> list[str]:
    """Sentence-level check against the CITED sources: reasons, empty if nothing flagged.

    Catches affirming a policy the source negates and promises the source never
    affirms. Pattern matching only; a mixed sentence ("yes, but not X") passes.
    """
    return _sentence_problems(_CITE.sub("", answer), _source_sentences(sources))


def valid_cited_answer(answer: str, sources: list[dict]) -> bool:
    """Checks source IDs, numerical literals and negated/unaffirmed promises (NOT semantic grounding).

    Numerical literals in the answer must be present in *cited* sources. This
    prevents a fabricated 90% offer even when another uncited document has 90%.
    """
    ids = citation_ids(answer)
    by_id = {s['id']: s for s in sources}
    if not ids or not ids <= set(by_id):
        return False
    body = _CITE.sub("", answer)
    cited = [by_id[doc_id] for doc_id in ids]
    if numbers(body) - numbers(evidence_text(cited)):
        return False
    return not unsupported_claims(answer, cited)


def safe_marketing_copy(candidate: dict, product: dict) -> bool:
    """Reject risky unsupported claims; this is a guard, not copy approval."""
    combined = "\n".join(candidate[k] for k in ('headline', 'body', 'cta'))
    if numbers(combined) - numbers(evidence_text([product])):
        return False
    # A promise needs an AFFIRMATIVE sentence in the product source; a source that only
    # negates it ("Không cam kết ...") does not license it.
    return not _sentence_problems(combined, _source_sentences([product]))


def safe_audience(audience: str) -> bool:
    """True only for a plain descriptive audience: no digits, promises or steering words.

    The audience is user input that is copied into marketing text and a model
    prompt, so anything that could carry an offer or instruction is refused.
    """
    audience = unicodedata.normalize("NFC", audience).strip()
    if not _AUDIENCE_CHARS.match(audience) or any(c.isdigit() for c in audience) or "_" in audience:
        return False
    norm = normalize(audience)
    return not (_has_phrase(norm, _CLAIMS) or _has_phrase(norm, _STEERING))
