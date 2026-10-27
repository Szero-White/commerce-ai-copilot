"""Support routing: the KIND of request decides, never a product name. Rules only, no model; humans approve every reply."""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.support import route


@pytest.mark.parametrize("message,intent", [
    # the reported message, and other ways to describe a defect
    ("Tôi mua bàn Oak 120 nhưng nhận hàng bị trầy xước. Tôi muốn đổi sản phẩm và cần nhân viên hỗ trợ.", "damaged_product"),
    ("Ghế vừa giao bị nứt chân, tôi muốn đổi cái khác", "damaged_product"),
    ("Hàng nhận về bị móp méo hết, giao thiếu ốc vít nữa", "damaged_product"),
    ("Đèn không hoạt động ngay lần đầu cắm điện", "damaged_product"),
    ("Cốc sứ bị vỡ khi mở thùng", "damaged_product"),
    ("Sản phẩm lỗi sản xuất, mong shop xử lý", "damaged_product"),
    ("Shop giao nhầm màu, tôi đặt màu trắng", "damaged_product"),
    ("The table arrived scratched and the leg is cracked", "damaged_product"),
    ("My lamp stopped working after two days", "damaged_product"),
    ("Đơn hàng #A12 nhận về bị trầy, nhờ nhân viên kiểm tra", "damaged_product"),      # quotes an order id: still a defect claim
    # exchange / return / warranty without a defect
    ("Tôi muốn đổi sang màu khác được không", "return_policy"),
    ("Mình không ưng, xin đổi hàng trong 7 ngày", "return_policy"),
    ("Cho tôi trả lại sản phẩm và hoàn tiền", "return_policy"),
    ("Bảo hành đèn bàn bao lâu và cần giấy tờ gì", "return_policy"),
    ("Can I exchange it for a bigger size? I would like a replacement", "return_policy"),
    # order data
    ("Cho tôi kiểm tra đơn hàng ngày hôm qua", "privacy_order"),
    ("Gửi mình số điện thoại của khách đã mua", "privacy_order"),
    ("Please provide my order status and my customer address", "privacy_order"),
    # shipping and plain product questions
    ("Phí vận chuyển về tỉnh là bao nhiêu", "shipping_question"),
    ("Bàn Oak 120 kích thước bao nhiêu", "product_question"),
    ("Giá ghế văn phòng là bao nhiêu", "product_question"),
    ("Chất liệu của sản phẩm này là gì", "product_question"),
    ("What sizes does the hoodie come in?", "product_question"),
    # no cue: manual review, whatever product is named
    ("Tôi quan tâm bàn Oak 120", "unknown"),
    ("quasar zyzzyva neutrino quantum teleport", "unknown"),
])
def test_requests_are_routed_by_kind_not_by_product(message, intent):
    assert route(message)[0] == intent, message


@pytest.mark.parametrize("message,not_intent", [
    ("Tôi thích ghế màu hồng, giá bao nhiêu", "damaged_product"),          # "hồng" (pink) is not "hỏng" (broken)
    ("Nút bấm của đèn ở đâu trên thân đèn", "damaged_product"),             # "nút" (button) is not "nứt" (cracked)
    ("Tôi đang đợi hàng từ hôm qua", "return_policy"),                      # "đợi" (wait) is not "đổi" (exchange)
])
def test_everyday_words_that_fold_to_defect_or_exchange_words_do_not_misroute(message, not_intent):
    assert route(message)[0] != not_intent


def test_the_priority_of_a_defect_claim_is_high_and_it_goes_to_claims():
    assert route("Hàng bị trầy xước, tôi muốn đổi")[1:] == ("high", "Customer support / claims")


def test_a_defect_claim_still_needs_a_human_and_promises_nothing():
    client = TestClient(create_app())
    body = client.post("/api/support/triage", json={
        "message": "Tôi mua bàn Oak 120 nhưng nhận hàng bị trầy xước. Tôi muốn đổi sản phẩm và cần nhân viên hỗ trợ."}).json()
    assert body["intent"] == "damaged_product" and body["priority"] == "high"
    assert body["status"] == "DRAFT_REQUIRES_HUMAN_REVIEW" and body["autonomous_action"] is False
    assert body["evidence"] and all(e["category"] == "policy" for e in body["evidence"])
    reply = body["draft_reply"].lower()
    assert "nhân viên" in reply and not any(w in reply for w in ("đã đổi", "sẽ đổi", "đã hoàn", "sẽ hoàn", "được hoàn tiền"))
