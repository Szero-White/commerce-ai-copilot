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
RULES = (
    ("privacy_order", "high", "Customer support / identity verification", (
        "my order", "order status", "tracking number", "track order", "don hang", "kiem tra don", "ma don", "dia chi", "phone number")),
    ("damaged_product", "high", "Customer support / claims", (
        "damaged", "broken", "defective", "wrong item", "faulty", "bi loi", "hu hong", "be vo", "giao sai")),
    ("return_policy", "medium", "Customer support / returns", (
        "return", "refund", "exchange", "doi tra", "hoan tien", "tra hang")),
    ("shipping_question", "low", "Customer support / shipping", (
        "shipping", "delivery", "ship", "giao hang", "van chuyen")),
    ("product_question", "low", "Product support", (
        "size", "sizes", "mug", "hoodie", "oak", "chair", "dimensions", "price", "gia", "kich thuoc", "san pham")),
)


def route(text):
    norm = " ".join(normalize(text).split())
    for intent, priority, owner, phrases in RULES:
        if any(re.search(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", norm) for phrase in phrases):
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
