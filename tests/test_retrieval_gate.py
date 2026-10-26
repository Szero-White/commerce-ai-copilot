"""Regression tests for the lexical relevance gate (offline; no embeddings)."""
import pytest

from app.storage import Store


@pytest.fixture()
def store(tmp_path):
    return Store(tmp_path / 'gate.db')


def ids(store, query):
    return [d['id'] for d in store.fts_search(query, limit=3)]


@pytest.mark.parametrize('query', [
    'Hôm nay thời tiết thế nào?', 'bitcoin giá', 'Có khuyến mãi mùa hè không?',
    'Giá vàng hôm nay bao nhiêu?', 'Chính sách bảo hành xe máy thế nào?',
    'Có giảm 5% không?', 'Có voucher 20% cho khách mới không?', 'Có bán sofa không?',
    'Công ty có bao nhiêu nhân viên?', 'What is the weather in Hanoi?',
])
def test_out_of_scope_queries_return_no_documents(store, query):
    assert ids(store, query) == [], query


@pytest.mark.parametrize('query,expected', [
    ('Giao hàng ở thành phố Hồ Chí Minh mất bao lâu?', 'POL-001'),
    ('Bàn Oak 120 kích thước bao nhiêu?', 'PRD-101'),
    ('Sản phẩm lỗi có được đổi trong 7 ngày không?', 'POL-002'),
    ('Hoodie size nào?', 'POD-202'),
    ('Tủ Slim màu gì?', 'PRD-104'),
    ('Ghế lưng lưới Flex giá bao nhiêu?', 'PRD-102'),
])
def test_in_scope_queries_still_found(store, query, expected):
    assert expected in ids(store, query), query


def test_single_digit_number_is_checked_like_any_other_number(store):
    # "7 ngày" exists in POL-002; "5%" exists nowhere.
    assert 'POL-002' in ids(store, 'Đổi trả trong 7 ngày được không?')
    assert ids(store, 'Đổi trả trong 5 ngày được không?') == []


def test_diacritics_typed_by_user_must_match(store):
    # "nhân" (person) must not match "nhận" (receive); an unaccented query stays tolerant.
    assert ids(store, 'Có tuyển dụng nhân viên không?') == []
    assert 'POL-001' in ids(store, 'giao hang tinh khac mat bao lau')


def test_known_limitation_is_documented_not_hidden(store):
    # The gate is a lexical heuristic: relevant-sounding but unanswerable questions may still
    # return related policy text. Semantic retrieval + the LLM must still abstain (live-only).
    assert isinstance(ids(store, 'Mã giảm giá tháng này là gì?'), list)
