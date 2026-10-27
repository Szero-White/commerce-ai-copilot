"""Rules-first customer support routing demo. No external side effects or PII access.

This is NOT an autonomous AI agent: it demonstrates a guarded operational workflow,
with transparent routing rules, retrieval evidence and a human approval gate.
"""
import re
import time
from .retrieval import search
from .storage import normalize

# Routing is intentionally deterministic so that no LLM can approve a refund,
# invent an order status, or write to a customer without human review.
# Phrases are accent-folded and matched on word boundaries. They describe the KIND of request (a defect, an exchange, a data
# request), never a product: the product named in a message must not decide how it is routed. Where a folded word has an
# unrelated everyday meaning ("hỏng" / "hồng" = pink, "nứt" / "nút" = button, "đổi" / "đợi" = wait) the phrase is anchored
# to a context word ("bị hỏng", "hư hỏng", "đổi hàng") instead of using the bare word.
# Order matters: a defect claim that quotes an order number is still a defect claim, so it is checked before the data rules.
RULES = (
    ("damaged_product", "high", "Customer support / claims", (
        "damaged", "broken", "defective", "wrong item", "faulty", "scratched", "scratch", "cracked", "dented", "defect",
        "not working", "does not work", "doesn t work", "stopped working", "missing part", "missing parts",
        "bi loi", "hu hong", "be vo", "giao sai", "giao nham", "giao thieu", "bi tray", "tray xuoc", "xuoc", "bi mop", "bi meo",
        "bi nut", "bi vo", "bi gay", "bi hong", "bi hu", "bi rach", "bi mong", "bi tray xuoc", "hang loi", "san pham loi",
        "loi san xuat", "hong hoc", "khong hoat dong", "khong chay", "khong dung duoc", "sai mau", "sai size", "sai kich thuoc")),
    ("privacy_order", "high", "Customer support / identity verification", (
        "my order", "order status", "tracking number", "track order", "don hang", "kiem tra don", "ma don", "dia chi", "phone number",
        "so dien thoai")),
    ("return_policy", "medium", "Customer support / returns", (
        "return", "refund", "exchange", "replace", "replacement", "send back", "money back", "doi tra", "hoan tien", "tra hang",
        "tra lai", "hoan lai", "doi hang", "doi san pham", "doi mau", "doi size", "doi lai", "doi cai", "doi sang", "muon doi",
        "can doi", "xin doi", "bao hanh", "warranty", "guarantee")),
    ("shipping_question", "low", "Customer support / shipping", (
        "shipping", "delivery", "ship", "giao hang", "van chuyen")),
    ("product_question", "low", "Product support", (
        "size", "sizes", "dimensions", "price", "gia", "kich thuoc", "kich co", "chat lieu", "san pham")),
)


def route(text):
    lowered = text.lower()
    norm = " ".join(normalize(text).split())
    waiting = "đợi" in lowered and "đổi" not in lowered       # "đợi hàng" (waiting for goods) folds to the same words as "đổi hàng"
    for intent, priority, owner, phrases in RULES:
        for phrase in phrases:
            if waiting and phrase.startswith(("doi ", "muon doi", "can doi", "xin doi")):
                continue
            if re.search(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", norm):
                return intent, priority, owner
    return "unknown", "medium", "Customer support / manual review"


def triage_message(store, settings, message):
    started = time.perf_counter()
    intent, priority, team = route(message)
    # Constrain document use: no private order lookup available in this demo.
    sources, retrieval_mode = search(store, settings, message, k=3)
    if intent == "privacy_order":
        # Force approved-safe policy for personal data; no order data access.
        doc = store.document("POL-005")
        sources = [{**doc, "score": None}] if doc else []
    elif intent in ("damaged_product", "return_policy"):
        # Prefer relevant return policies over potentially unrelated catalog hits.
        policies = [s for s in sources if s["category"] == "policy"]
        if not policies:
            source = store.document("POD-POL-201" if "personal" in normalize(message) else "POL-002")
            if source:
                policies = [{**source, "score": None}]
        sources = policies[:3]
    evidence = [{"id": s["id"], "title": s["title"], "category": s["category"],
                 "excerpt": s["content"][:360]} for s in sources]
    english = bool(re.search(r"\b(hello|my|can|how|what|return|refund|shipping|order|damaged|size)\b", message.lower()))
    if english:
        response = ("Thanks for contacting support. This request needs human review. "
                    "Please use the official support channel for any order-specific information. "
                    "Here are the relevant reference documents for our team to verify.")
    else:
        response = ("Cảm ơn bạn đã liên hệ. Yêu cầu này cần nhân viên kiểm tra trước khi phản hồi chính thức. "
                    "Vui lòng sử dụng kênh hỗ trợ được xác minh nếu liên quan đến đơn hàng. "
                    "Nhân viên có thể đối chiếu các tài liệu tham khảo bên dưới.")
    if not evidence:
        response += " We couldn't find a relevant policy." if english else " Hiện chưa có tài liệu phù hợp."
    elapsed = round((time.perf_counter() - started) * 1000)
    store.log("support_triage", "rules_review_required", elapsed)
    return {
        "intent": intent, "priority": priority, "assigned_team": team,
        "status": "DRAFT_REQUIRES_HUMAN_REVIEW", "autonomous_action": False,
        "draft_reply": response, "evidence": evidence,
        "retrieval_mode": retrieval_mode, "latency_ms": elapsed,
        "explanation": "Deterministic classification and source retrieval; no LLM and no order/payment data access.",
    }
