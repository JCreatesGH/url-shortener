from app.shortcode import encode, decode
import pytest


def test_roundtrip():
    for n in [0, 1, 61, 62, 1000, 123456789]:
        assert decode(encode(n)) == n


def test_encode_is_compact_and_url_safe():
    code = encode(1_000_000)
    assert code.isalnum() and len(code) <= 4


def test_negative_rejected():
    with pytest.raises(ValueError):
        encode(-1)
