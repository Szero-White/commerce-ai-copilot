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

from .evidence import valid_cited_answer
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


def verify(reply: str, sources: list[dict]):
    """(ok, reason, answer_text, source, quote). answer_text already ends with the citation the CODE appended."""
    verdict = parse(reply)
    if not verdict:
        return False, "unreadable reply", "", None, ""
    if verdict.get("decision") != "answer":
        return False, "declined", "", None, ""
    source = next((s for s in sources if s["id"] == verdict.get("source_id")), None)
    quote, answer = str(verdict.get("quote") or "").strip(), str(verdict.get("answer") or "").strip()
    if not source:
        return False, "source id is not one of the documents", "", None, ""
    if len(quote) < MIN_QUOTE_CHARS or _fold(quote) not in _fold(source["title"] + " " + source["content"]):
        return False, "the quoted sentence is not in the document", "", source, quote
    if not answer or len(answer) > MAX_ANSWER_CHARS:
        return False, "no usable answer", "", source, quote
    if _numbers(answer) - _numbers(quote):
        return False, "a number in the answer is not in the quoted sentence", "", source, quote
    text = f"{answer} [{source['id']}]"
    if not valid_cited_answer(text, [source]):
        return False, "the answer fails the evidence check", "", source, quote
    return True, "ok", text, source, quote
