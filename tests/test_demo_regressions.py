"""Demo-visible defects found in the audit (offline, no model)."""
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.agent import execute_tool
from app.config import Settings
from app.main import create_app
from app.storage import Store


def api(tmp_path):
    return TestClient(create_app(settings=replace(
        Settings(), data_path=tmp_path / 'demo.db', llm_provider='off', embedding_provider='off')))


def test_extractive_answer_keeps_the_exclusion_at_the_end_of_the_policy(tmp_path):
    answer = api(tmp_path).post('/api/chat', json={'question': 'Đổi trả trong 7 ngày được không?'}).json()['answer']
    assert 'không nằm trong diện đổi trả miễn phí' in answer  # used to be cut after 215 characters
    assert answer.rstrip().endswith(('.', '…'))


@pytest.mark.parametrize('sku', ['POD-201', 'POD-202', 'PRD-103', 'PRD-104'])
def test_campaign_template_has_no_internal_notes_or_prices(tmp_path, sku):
    body = api(tmp_path).post('/api/campaign', json={'sku': sku, 'audience': 'khách hàng'}).json()['body']
    for leaked in ('Do not claim', 'No inventory', 'Price:', 'SKU', 'Synthetic', 'niêm yết', '390.000', '2.350.000'):
        assert leaked.lower() not in body.lower(), (sku, leaked, body)
    assert len(body) > 40


def test_search_policy_tool_is_not_starved_by_product_hits(tmp_path):
    store = Store(tmp_path / 'tool.db')
    settings = replace(Settings(), embedding_provider='off')
    result = execute_tool(store, settings, 'search_policy', {'query': 'Ghế Flex bảo hành mấy tháng'})
    assert 'POL-003' in [d['source'] for d in result['documents']]
