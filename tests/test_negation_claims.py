"""Negated policies and unsupported promises (offline; mock LLM only).

The guard is sentence-level pattern matching. It is NOT semantic verification and
does not prevent hallucination in general.
"""
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.evidence import safe_marketing_copy, unsupported_claims, valid_cited_answer
from app.main import create_app

PERSONALIZED = [{'id': 'POD-POL-201', 'title': 'Personalized item return policy', 'content':
                 'Personalized items are not eligible for return due to a change of mind after production '
                 'begins. If an item arrives damaged, contact customer support within 7 days with photos.'}]
PAYMENT = [{'id': 'POL-004', 'title': 'Thanh toán', 'content':
            'Demo Lab hỗ trợ chuyển khoản và COD. Việc thanh toán và hoàn tiền thật chưa được tích hợp.'}]
RETURNS = [{'id': 'POL-002', 'title': 'Đổi trả', 'content':
            'Khách hàng có thể gửi yêu cầu đổi trả trong 7 ngày đối với sản phẩm lỗi. '
            'Hàng hư hại do sử dụng sai không nằm trong diện đổi trả miễn phí.'}]


def client(tmp_path):
    config = replace(Settings(), data_path=tmp_path / 'neg.db', llm_provider='ollama', embedding_provider='off')
    return TestClient(create_app(settings=config))


# RAG answers --------------------------------------------------------------
def test_affirming_a_negated_policy_is_rejected():
    assert not valid_cited_answer('You can return a personalized item [POD-POL-201]', PERSONALIZED)
    assert not valid_cited_answer('Bạn sẽ được hoàn tiền ngay [POL-004]', PAYMENT)


def test_restating_the_negation_is_accepted():
    assert valid_cited_answer('Personalized items are not eligible for return [POD-POL-201]', PERSONALIZED)
    assert valid_cited_answer('Hoàn tiền thật chưa được tích hợp [POL-004]', PAYMENT)


def test_mixed_source_with_affirmative_sentence_still_answerable():
    assert valid_cited_answer('Có thể gửi yêu cầu đổi trả trong 7 ngày [POL-002]', RETURNS)


def test_promise_must_be_affirmed_by_cited_source():
    delivery = [{'id': 'POL-001', 'title': 'Giao hàng', 'content': 'Giao hàng trong 2 đến 4 ngày làm việc.'}]
    assert not valid_cited_answer('Miễn phí giao hàng toàn quốc [POL-001]', delivery)
    free = [{'id': 'POL-009', 'title': 'Giao hàng', 'content': 'Miễn phí giao hàng nội thành.'}]
    assert valid_cited_answer('Miễn phí giao hàng nội thành [POL-009]', free)


def test_unsupported_claims_reports_reasons():
    reasons = unsupported_claims('You can return a personalized item [POD-POL-201]', PERSONALIZED)
    assert reasons and 'return' in reasons[0]


def test_negated_policy_through_api_falls_back_to_sources(tmp_path, monkeypatch):
    from app import services
    monkeypatch.setattr(services, 'ollama_chat', lambda *a, **k: (
        'You can return a personalized item if you changed your mind [POD-POL-201]', 30, 12))
    result = client(tmp_path).post('/api/chat', json={
        'question': 'Can I return a personalized item because I changed my mind?'}).json()
    assert result['mode'] == 'llm_citation_rejected_extractive', result
    assert 'POD-POL-201' in [s['id'] for s in result['sources']]


# Campaign copy ------------------------------------------------------------
def test_negated_source_sentence_does_not_whitelist_a_promise():
    product = {'id': 'P', 'title': 'Chair', 'content': 'Không cam kết công thái học y tế hay tải trọng.'}
    assert not safe_marketing_copy({'headline': 'Chair', 'body': 'Cam kết công thái học', 'cta': 'Xem'}, product)
    assert safe_marketing_copy({'headline': 'Chair', 'body': 'Không cam kết công thái học', 'cta': 'Xem'}, product)


def test_copy_cannot_claim_what_the_source_says_is_missing():
    product = {'id': 'P', 'title': 'Lamp', 'content': 'Đèn LED ba mức sáng. Chưa có chứng nhận kiểm nghiệm ánh sáng.'}
    assert not safe_marketing_copy({'headline': 'Lamp', 'body': 'Đèn đã có chứng nhận kiểm nghiệm', 'cta': 'Xem'}, product)
    assert safe_marketing_copy({'headline': 'Lamp', 'body': 'Đèn LED ba mức sáng', 'cta': 'Xem'}, product)


@pytest.mark.parametrize('sku', ['PRD-101', 'PRD-102', 'PRD-103', 'PRD-104', 'POD-201', 'POD-202'])
def test_template_drafts_for_every_product_stay_valid(tmp_path, sku):
    result = TestClient(create_app(settings=replace(
        Settings(), data_path=tmp_path / 't.db', llm_provider='off', embedding_provider='off'))
    ).post('/api/campaign', json={'sku': sku, 'audience': 'nhân viên văn phòng'}).json()
    assert result['mode'] == 'template_preview', result
