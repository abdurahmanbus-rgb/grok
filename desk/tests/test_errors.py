import requests

import pytest

from errors import FetchError, classify_status, fetch_json
from market import market_kill, pool
from mints import is_valid_mint
from rugcheck import report

MINT = "H4gHnZ3NCU7Z9XQwGX6YYJNyieGEW8pqwGRUcdSxpump"


class Resp:
    def __init__(self, status, body, headers=None):
        self.status_code = status
        self._body = body
        self.headers = headers or {}

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class Sess:
    def __init__(self, items):
        self.items = list(items)
        self.calls = 0

    def get(self, url, timeout=None, headers=None):
        self.calls += 1
        item = self.items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_status_classes():
    assert classify_status(404) == "missing"
    assert classify_status(429) == "rate_limit"
    assert classify_status(400) == "rejection"
    assert classify_status(422) == "rejection"
    assert classify_status(403) == "rejection"
    assert classify_status(500) == "5xx"
    assert classify_status(503) == "5xx"
    assert classify_status(200) == "malformed"


def test_invalid_mint_never_calls_the_network():
    sess = Sess([])
    with pytest.raises(FetchError) as caught:
        report("not-a-mint", fetch=lambda *a, **k: sess.get(*a, **k))
    assert caught.value.kind == "invalid"
    assert sess.calls == 0
    assert is_valid_mint(MINT)
    assert not is_valid_mint("0" * 32)  # zero is not base58
    assert not is_valid_mint(MINT[:20])
    assert not is_valid_mint(" " + MINT)


def test_rejection_missing_and_malformed_are_not_retried():
    for status, kind in ((400, "rejection"), (404, "missing"), (403, "rejection")):
        sess = Sess([Resp(status, {"error": True})])
        slept = []
        with pytest.raises(FetchError) as caught:
            fetch_json("https://example.test/x", provider="rugcheck", session=sess,
                       sleep=slept.append, attempts=3)
        assert caught.value.kind == kind
        assert sess.calls == 1
        assert slept == []

    sess = Sess([Resp(200, ValueError("bad"))])
    with pytest.raises(FetchError) as caught:
        fetch_json("https://example.test/x", provider="dexscreener", session=sess, attempts=3)
    assert caught.value.kind == "malformed"
    assert sess.calls == 1

    sess = Sess([Resp(200, "nope")])
    with pytest.raises(FetchError) as caught:
        fetch_json("https://example.test/x", provider="dexscreener", session=sess, attempts=3)
    assert caught.value.kind == "malformed"


def test_transient_retries_then_succeeds_or_stays_an_error():
    slept = []
    sess = Sess([
        Resp(429, {}, {"Retry-After": "0"}),
        Resp(200, [{"ok": 1}]),
    ])
    data = fetch_json("https://example.test/x", provider="dexscreener", session=sess,
                      sleep=slept.append, attempts=3)
    assert data == [{"ok": 1}]
    assert sess.calls == 2
    assert slept == [0.0]

    sess = Sess([requests.Timeout("slow"), Resp(200, {"score_normalised": 1})])
    data = fetch_json("https://example.test/x", provider="rugcheck", session=sess,
                      sleep=lambda s: None, attempts=3)
    assert data["score_normalised"] == 1
    assert sess.calls == 2

    sess = Sess([Resp(502, {}), Resp(503, {}), Resp(500, {})])
    with pytest.raises(FetchError) as caught:
        fetch_json("https://example.test/x", provider="rugcheck", session=sess,
                   sleep=lambda s: None, attempts=3)
    assert caught.value.kind == "5xx"
    assert sess.calls == 3

    sess = Sess([requests.ConnectionError("down")] * 3)
    with pytest.raises(FetchError) as caught:
        fetch_json("https://example.test/x", provider="dexscreener", session=sess,
                   sleep=lambda s: None, attempts=3)
    assert caught.value.kind == "network"
    assert sess.calls == 3


def test_empty_pool_is_no_pool_not_a_pass_or_a_fetch_error():
    assert pool(MINT, fetch=lambda *a, **k: []) is None
    assert market_kill(None) == "no_pool"

    def fetch(*args, **kwargs):
        raise FetchError("dexscreener", "timeout", "timeout")

    with pytest.raises(FetchError) as caught:
        pool(MINT, fetch=fetch)
    assert caught.value.kind == "timeout"


def test_rugcheck_non_object_is_malformed():
    with pytest.raises(FetchError) as caught:
        report(MINT, fetch=lambda *a, **k: [1, 2])
    assert caught.value.kind == "malformed"
