"""Verified answers for documents that were found by MEANING.

A document nominated by similarity is relevant; that does not mean it states what the customer asked. So the model is not
asked to "cite an id" (any text can end in "[PRD-1]"). It must return a structured verdict with the exact sentence of the
document that supports its answer, and the CODE checks that evidence instead of trusting the model:

* the quoted sentence really occurs in the cited document (not paraphrased, not invented);
* every number in the answer occurs in that quoted sentence (so a figure cannot be attached to a quote that lacks it);
* the answer passes the existing evidence guard against the whole document (promises, negated policies, numbers);
* a decline, an unreadable reply or a missing quote means "not enough information": nothing is claimed.

What this does NOT prove: that the answer is entailed by the quote (a fluent wrong sentence without numbers can pass, and
numbers are compared as digit strings, not with their units: "5 levels" is accepted if the quote contains "5V"). It removes
the cheap failures (invented evidence, ids pasted onto anything, numbers from nowhere) and makes the evidence visible.
"""
import json
import re
from typing import NamedTuple

from .evidence import _CITE, citation_ids, question_numbers_for, valid_cited_answer
from .storage import normalize

MIN_QUOTE_CHARS = 12
MAX_ANSWER_CHARS = 700
INSUFFICIENT = "Tôi chưa có đủ thông tin trong tài liệu để xác nhận"

INSTRUCTIONS = """Trả về MỘT đối tượng JSON, không thêm chữ nào khác, với các khóa:
"decision": "answer" hoặc "decline";
"kind": "recommendation" (khách mô tả nhu cầu, bạn gợi ý sản phẩm phù hợp) hoặc "fact" (khách hỏi một thông tin cụ thể);
"source_id": mã tài liệu bạn dựa vào;
"quote": NGUYÊN VĂN một câu của tài liệu đó làm căn cứ (sao chép đúng từng chữ);
"answer": câu trả lời ngắn bằng tiếng Việt, chỉ nêu điều câu trích dẫn nói. Với "recommendation", chỉ nói sản phẩm có đặc điểm nào trong câu trích dẫn phù hợp với nhu cầu, không khẳng định thêm thuộc tính nào khác.
Một số tài liệu chỉ được tìm theo ngữ nghĩa nên liên quan chưa chắc đã nêu điều được hỏi. Nếu không có câu nào trong tài liệu làm căn cứ, trả {"decision": "decline"}."""


def _fold(text: str) -> str:
    return " ".join(normalize(text).split())


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+", text))


def parse(reply: str) -> dict | None:
    try:
        data = json.loads(reply)
    except (TypeError, ValueError):
        match = re.search(r"\{.*\}", reply or "", re.S)      # a model sometimes wraps the object in prose or code fences
        try:
            data = json.loads(match.group(0)) if match else None
        except ValueError:
            return None
    return data if isinstance(data, dict) else None


# Connective words an answer may use without them being a claim (accent-folded). Anything else in the answer must come from
# the quoted sentence or from the customer's own question, otherwise it is a capability nobody showed evidence for.
GLUE = set("""nen the phu hop de khi cho va la co duoc nhu cung thi ma nay do kia rat hon nhat them san pham mon cai thu minh khach
phai can muon dung dang se van chi cac nhung mot nhieu it hay hoac neu vi nen boi tai tu den voi trong ngoai tren duoi sau truoc
that this for and the with can you your is are to of a an in on at it be goi loai nhu cau thich ung tot nhe giup""".split())


class Result(NamedTuple):
    ok: bool
    reason: str
    text: str             # what may be shown; the citation is appended by the code, never taken from the model
    source: dict | None
    quote: str
    info: dict            # safe diagnostics: the verdict fields and why it was accepted or refused (no key, no prompt)


def _unsupported(answer: str, quote: str, question: str) -> list[str]:
    from .query import STOP
    allowed = set(_fold(quote).split()) | set(_fold(question).split()) | STOP | GLUE
    return sorted({w for w in _fold(answer).split() if len(w) >= 3 and not w.isdigit() and w not in allowed})


def verify(reply: str, sources: list[dict], question: str = "") -> Result:
    """Check a model reply about meaning-found documents. See the module docstring for what is and is not proven."""
    verdict = parse(reply)
    info = {"reply_excerpt": (reply or "")[:400]}

    def refuse(reason, source=None, quote=""):
        info["reason"] = reason
        return Result(False, reason, "", source, quote, info)
    if not verdict:
        return refuse("unreadable reply")
    wanted = re.sub(r"[\[\]\s]", "", str(verdict.get("source_id") or "")).lower()     # "[PRD-103]" and "prd-103 " are the same id
    info.update(decision=verdict.get("decision"), kind=verdict.get("kind"), source_id=verdict.get("source_id"),
                quote=str(verdict.get("quote") or "")[:200])
    if verdict.get("decision") != "answer":
        return refuse("declined")
    source = next((s for s in sources if s["id"].lower() == wanted), None)
    quote, answer = str(verdict.get("quote") or "").strip(), str(verdict.get("answer") or "").strip()
    if not source:
        return refuse("source id is not one of the documents")
    if len(quote) < MIN_QUOTE_CHARS or _fold(quote) not in _fold(source["title"] + " " + source["content"]):
        return refuse("the quoted sentence is not in the document", source, quote)
    # A citation tag in the answer is a label, not a claim. It must name exactly the source of the verdict; the well-formed tags
    # are then removed (digits of "[PRD-103]" are not product data) and the CODE appends the one citation shown to the user.
    if any(c.lower() != source["id"].lower() for c in citation_ids(answer)):
        return refuse("a citation in the answer is not the source of the verdict", source, quote)
    answer = " ".join(_CITE.sub(" ", answer).split())
    if not answer or len(answer) > MAX_ANSWER_CHARS:
        return refuse("no usable answer", source, quote)
    asked = question_numbers_for(question, [source])      # the customer's own figures, only next to a computed comparison
    if _numbers(answer) - _numbers(quote) - _numbers(" ".join(asked)):
        return refuse("a number in the answer is not in the quoted sentence", source, quote)
    text = f"{answer} [{source['id']}]"
    if not valid_cited_answer(text, [source], asked):
        return refuse("the answer fails the evidence check", source, quote)
    extra = _unsupported(answer, quote, question)
    if extra:
        info["unsupported_words"] = extra[:12]
        if verdict.get("kind") != "recommendation":
            return refuse("the answer states something the quoted sentence does not", source, quote)
        # A suggestion may rest on the product's real features but must not assert capabilities nobody showed: the model's
        # own sentence is dropped and the CODE states only what the document says.
        info["reason"] = "recommendation reduced to the quoted evidence"
        shown = (f"Gợi ý theo nhu cầu bạn mô tả: «{source['title']}». Tài liệu nêu: «{quote}» [{source['id']}]. "
                 "Ngoài trích dẫn này, tài liệu không xác nhận thêm khả năng nào.")
        return Result(True, info["reason"], shown, source, quote, info)
    info["reason"] = "ok"
    return Result(True, "ok", f"{text}\nCăn cứ trong tài liệu: «{quote}»", source, quote, info)
