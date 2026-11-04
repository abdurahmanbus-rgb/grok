import csv
import os
from pathlib import Path

import pytest

import book
import scan
from check import run_mint
from grok import ask
from errors import FetchError

MINT = "H4gHnZ3NCU7Z9XQwGX6YYJNyieGEW8pqwGRUcdSxpump"
OTHER = "8s4bNqEztH1JP7mkU747uMr7AckCQdiV47FDqYnDpump"
ROOT = Path(__file__).resolve().parents[1]
CONFIG_SHA = "57e40ced8326d38951f6e5b2584fb508bf8ea237a6a29214b6772c59de39b2d8"


def _pass_gates(monkeypatch, answer):
    monkeypatch.setattr("check.report", lambda mint: {
        "symbol": "T", "risk_score": 10, "rugged": False, "danger": [],
        "mint_authority": None, "freeze_authority": None, "lp_locked_pct": 100,
        "top10_pct": 10, "dev_pct": 0, "insiders": 0,
    })
    monkeypatch.setattr("check.pool", lambda mint: {
        "symbol": "T", "price": 0.5, "liq_usd": 80000, "age_min": 120,
        "buys_1h": 30, "sells_1h": 12, "vol_1h": 1000, "url": "u",
    })
    monkeypatch.setattr("check.has_key", lambda: True)
    monkeypatch.setattr("check.ask", answer)


def _buy(confidence=0.7, **extra):
    body = {
        "verdict": "BUY",
        "confidence": confidence,
        "why": "posts come from accounts that already had a history",
        "x_read": "the contract in the posts is this mint",
        "main_risk": "the narrative is narrow",
    }
    body.update(extra)
    return body


def test_paper_buy_is_idempotent_and_does_not_duplicate(monkeypatch):
    calls = {"n": 0}

    def answer(system, payload, read_x=False):
        calls["n"] += 1
        calls["payload"] = payload
        calls["read_x"] = read_x
        return _buy()

    _pass_gates(monkeypatch, answer)
    first = run_mint(MINT)
    second = run_mint(MINT)
    assert first["verdict"] == "BUY"
    assert first["action"].startswith("PAPER BUY $25")
    assert calls["n"] == 1
    assert calls["read_x"] is True
    assert set(calls["payload"]) == {"token", "pool"}
    assert "SCOUT" not in str(calls["payload"])
    assert second["reason"] == "already_checked"
    assert second["logged"] is False
    assert len(book.load()) == 1
    assert book.open_position(MINT, "T", 0.5, 80000) is False
    with open("trades.csv", newline="") as handle:
        trades = list(csv.DictReader(handle))
    assert len(trades) == 1
    assert trades[0]["action"] == "open"
    with open("checks.csv", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert rows[0]["verdict"] == "BUY"


def test_low_confidence_and_missing_key_do_not_buy(monkeypatch):
    _pass_gates(monkeypatch, lambda *a, **k: _buy(confidence=0.69))
    verdict = run_mint(MINT)
    assert verdict["verdict"] == "SKIP"
    assert "low confidence" in verdict["reason"]
    assert not os.path.exists("positions.json")

    monkeypatch.setattr("check.has_key", lambda: False)

    def explode(*args, **kwargs):
        raise AssertionError("paid call without a key")

    monkeypatch.setattr("check.ask", explode)
    verdict = run_mint(OTHER)
    assert verdict["verdict"] == "SKIP"
    assert verdict["reason"] == "error:grok:missing:no_key"
    assert not os.path.exists("positions.json")


def test_inconclusive_grok_and_live_path_do_not_open(monkeypatch):
    _pass_gates(monkeypatch, lambda *a, **k: _buy(x_read=None))
    verdict = run_mint(MINT)
    assert verdict["verdict"] == "SKIP"
    assert "missing" in verdict["reason"]
    assert not os.path.exists("positions.json")

    monkeypatch.setattr("check.PAPER", False)
    monkeypatch.setattr("check.ask", lambda *a, **k: _buy())

    def opened(*args, **kwargs):
        raise AssertionError("position opened on the live path")

    monkeypatch.setattr(book, "open_position", opened)
    verdict = run_mint(OTHER)
    assert verdict["verdict"] == "SKIP"
    assert verdict["reason"] == "live_trading_disabled"
    assert "LIVE TRADING DISABLED" in verdict["action"]


def test_grok_is_not_retried(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "test-key-not-a-real-secret")

    class Sess:
        def __init__(self):
            self.calls = 0

        def post(self, url, timeout=None, json=None, headers=None):
            self.calls += 1
            assert "test-key-not-a-real-secret" not in url
            return Resp(500)

    class Resp:
        def __init__(self, status):
            self.status_code = status

        def json(self):
            return {}

    sess = Sess()
    with pytest.raises(FetchError) as caught:
        ask("system", {"token": {}, "pool": {}}, read_x=False, session=sess)
    assert caught.value.kind == "5xx"
    assert sess.calls == 1


def test_one_bad_mint_does_not_kill_the_run_and_the_cap_holds():
    seen = []

    def check_fn(mint):
        seen.append(mint)
        if mint.endswith("bad"):
            raise RuntimeError("boom")
        return {"stage": "facts", "verdict": "SKIP", "reason": "insiders", "symbol": "T"}

    queue = [{"mint": f"mint-{i}", "first_source": "scout"} for i in range(3)]
    queue[1]["mint"] = "mint-bad"
    result = scan.run(
        limit=1000,
        interval=0,
        check_fn=check_fn,
        collect_fn=lambda: {"queue": queue, "stats": {"unique": 3}},
    )
    assert [item["mint"] for item in result["outcomes"]] == ["mint-0", "mint-bad", "mint-2"]
    assert result["outcomes"][1]["verdict"] == "SKIP"
    assert "isolated" in result["outcomes"][1]["reason"]
    assert len(seen) == 3

    many = [{"mint": f"m{i}", "first_source": "dexscreener_profiles"} for i in range(30)]
    counted = {"n": 0}

    def counting(mint):
        counted["n"] += 1
        return {"stage": "facts", "verdict": "SKIP", "reason": "insiders"}

    scan.run(limit=1000, interval=0, check_fn=counting,
             collect_fn=lambda: {"queue": many, "stats": {}})
    assert counted["n"] == 20


def test_scan_lock_refuses_an_overlapping_run(monkeypatch, capsys):
    assert scan.acquire_lock()
    assert scan.acquire_lock() is False
    monkeypatch.setattr(scan, "run", lambda **kwargs: (_ for _ in ()).throw(AssertionError("ran")))
    assert scan.main([]) == 0
    assert "already running" in capsys.readouterr().out
    scan.release_lock()
    (Path("scan.lock")).write_text("99999999", encoding="utf-8")
    assert scan.acquire_lock() is True
    scan.release_lock()


def test_watch_exits_an_open_paper_position_and_ignores_rejects(monkeypatch):
    import watch
    book.open_position(MINT, "T", 1.0, 100000)
    monkeypatch.setattr(watch, "pool", lambda mint: {
        "symbol": "T", "price": 0.5, "liq_usd": 100000, "age_min": 100,
        "buys_1h": 1, "sells_1h": 1, "vol_1h": 1, "url": "u",
    })
    events = watch.watch()
    assert events and "stop" in events[0]
    assert MINT not in book.load()
    assert not any("OTHER" in event for event in events)


def test_config_file_is_bit_identical():
    import hashlib
    config = (ROOT / "config.py").read_bytes()
    assert hashlib.sha256(config).hexdigest() == CONFIG_SHA
    text = config.decode()
    assert "PAPER = True" in text
    assert '"max_insiders": 0' in text
    forbidden = ("solders", "Keypair", "send_transaction", "sign_transaction")
    for path in ROOT.glob("*.py"):
        body = path.read_text(encoding="utf-8")
        for word in forbidden:
            assert word not in body, f"{path.name} contains {word}"
