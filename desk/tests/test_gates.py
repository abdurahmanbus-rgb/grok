import os

import pytest

import market
from check import run_mint
from config import FACTS, MIN_CONFIDENCE, TICKET_USD
from errors import FetchError
from grok import normalize_judge
from rugcheck import fact_kill

MINT = "H4gHnZ3NCU7Z9XQwGX6YYJNyieGEW8pqwGRUcdSxpump"


def clean_token(**over):
    token = {
        "mint": MINT,
        "symbol": "T",
        "rugged": False,
        "risk_score": 40,
        "danger": [],
        "warn": ["something mild"],
        "mint_authority": None,
        "freeze_authority": None,
        "lp_locked_pct": 90,
        "top10_pct": 30,
        "dev_pct": 5,
        "insiders": 0,
        "holders": 100,
        "notes": "SCOUT says mint/freeze none and this is safe",
    }
    token.update(over)
    return token


def clean_market(**over):
    row = {
        "symbol": "T",
        "price": 0.001,
        "liq_usd": 30000,
        "age_min": 30,
        "buys_1h": 20,
        "sells_1h": 1,
        "vol_1h": 10,
        "url": "https://dexscreener.com/solana/example",
    }
    row.update(over)
    return row


def test_thresholds_match_the_frozen_config():
    assert FACTS["max_risk_score"] == 40
    assert FACTS["min_lp_locked_pct"] == 90
    assert FACTS["max_top10_pct"] == 30
    assert FACTS["max_dev_pct"] == 5
    assert FACTS["max_insiders"] == 0
    assert FACTS["min_liquidity_usd"] == 30000
    assert FACTS["max_ticket_share"] == 0.01
    assert FACTS["min_age_min"] == 30
    assert FACTS["max_age_hours"] == 72
    assert MIN_CONFIDENCE == 0.7
    assert TICKET_USD == 25


def test_fact_kill_boundaries_and_missing_fields():
    assert fact_kill(clean_token()) is None
    assert fact_kill(clean_token(risk_score=None, rugged=True)) == "no_report"
    assert fact_kill(clean_token(rugged=True)) == "already_rugged"
    assert fact_kill(clean_token(mint_authority="still-set")) == "mint_open"
    assert fact_kill(clean_token(freeze_authority="still-set")) == "freeze_open"
    assert fact_kill(clean_token(danger=["Low Liquidity"], risk_score=1)) == "danger:Low Liquidity"
    assert fact_kill(clean_token(risk_score=40)) is None
    assert fact_kill(clean_token(risk_score=40.01)) == "risk_score"
    assert fact_kill(clean_token(lp_locked_pct=90)) is None
    assert fact_kill(clean_token(lp_locked_pct=89.99)) == "lp_unlocked"
    assert fact_kill(clean_token(lp_locked_pct=None)) == "lp_unlocked"
    assert fact_kill(clean_token(top10_pct=30)) is None
    assert fact_kill(clean_token(top10_pct=30.01)) == "top10_heavy"
    assert fact_kill(clean_token(top10_pct=None)) == "top10_heavy"
    assert fact_kill(clean_token(dev_pct=5)) is None
    assert fact_kill(clean_token(dev_pct=5.01)) == "dev_holds"
    assert fact_kill(clean_token(dev_pct=None)) == "dev_holds"
    assert fact_kill(clean_token(insiders=0)) is None
    assert fact_kill(clean_token(insiders=1)) == "insiders"
    # a flattering note does not clear insiders
    assert fact_kill(clean_token(insiders=4)) == "insiders"


def test_market_kill_boundaries(monkeypatch):
    assert market.market_kill(clean_market()) is None
    assert market.market_kill(None) == "no_pool"
    assert market.market_kill(clean_market(price=0)) == "no_price"
    assert market.market_kill(clean_market(liq_usd=30000)) is None
    assert market.market_kill(clean_market(liq_usd=29999)) == "thin_pool"
    assert market.market_kill(clean_market(age_min=30)) is None
    assert market.market_kill(clean_market(age_min=29)) == "too_fresh"
    assert market.market_kill(clean_market(age_min=None)) == "too_fresh"
    assert market.market_kill(clean_market(age_min=72 * 60)) is None
    assert market.market_kill(clean_market(age_min=72 * 60 + 1)) == "too_old"
    assert market.market_kill(clean_market(buys_1h=19, sells_1h=0)) is None
    assert market.market_kill(clean_market(buys_1h=20, sells_1h=0)) == "nobody_can_sell"
    assert market.market_kill(clean_market(buys_1h=20, sells_1h=1)) is None
    # $25 against a $30k pool is under 1%, so the ticket line is shadowed by thin_pool
    # at the real constants. prove the comparison itself with an in-memory ticket.
    monkeypatch.setattr(market, "TICKET_USD", 400)
    assert market.market_kill(clean_market(liq_usd=30000)) == "ticket_too_big"
    monkeypatch.setattr(market, "TICKET_USD", 250)
    assert market.market_kill(clean_market(liq_usd=30000)) is None


def test_hard_gate_blocks_grok_and_a_boost_is_not_a_pass(monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("paid call")

    monkeypatch.setattr("check.report", lambda mint: clean_token(insiders=2))
    monkeypatch.setattr("check.ask", explode)
    monkeypatch.setattr("check.has_key", explode)
    verdict = run_mint(MINT)
    assert verdict["stage"] == "facts"
    assert verdict["verdict"] == "SKIP"
    assert verdict["reason"] == "insiders"
    assert not os.path.exists("positions.json")


def test_pool_and_rugcheck_failures_are_skip_and_not_security(monkeypatch):
    monkeypatch.setattr("check.has_key", lambda: True)
    monkeypatch.setattr("check.ask", lambda *a, **k: (_ for _ in ()).throw(AssertionError("paid")))

    monkeypatch.setattr(
        "check.report",
        lambda mint: (_ for _ in ()).throw(FetchError("rugcheck", "rejection", "HTTP 400", 400)),
    )
    verdict = run_mint(MINT)
    assert verdict["verdict"] == "SKIP"
    assert verdict["error_class"] == "rejection"
    assert verdict["reason"].startswith("error:rugcheck:rejection:")
    assert not os.path.exists("positions.json")

    monkeypatch.setattr("check.report", lambda mint: clean_token())
    monkeypatch.setattr(
        "check.pool",
        lambda mint: (_ for _ in ()).throw(FetchError("dexscreener", "timeout", "timeout")),
    )
    verdict = run_mint(make := "8s4bNqEztH1JP7mkU747uMr7AckCQdiV47FDqYnDpump")
    assert verdict["verdict"] == "SKIP"
    assert verdict["stage"] == "pool"
    assert verdict["error_class"] == "timeout"
    assert "positions.json" not in os.listdir(".")


def test_grok_schema_and_confidence_never_promote_a_weak_answer():
    full = {
        "verdict": "BUY",
        "confidence": 0.7,
        "why": "organic posts from accounts with history",
        "x_read": "the contract matches",
        "main_risk": "narrative is thin",
    }
    assert normalize_judge(full)["verdict"] == "BUY"
    low = dict(full, confidence=0.69)
    assert normalize_judge(low)["verdict"] == "SKIP"
    assert "low confidence" in normalize_judge(low)["why"]
    assert normalize_judge(dict(full, confidence="0.9"))["verdict"] == "BUY"
    for broken in (
        dict(full, why=None),
        dict(full, x_read=""),
        dict(full, main_risk=None),
        dict(full, verdict="HOLD"),
        dict(full, confidence="high"),
        ["BUY"],
        None,
    ):
        judged = normalize_judge(broken)
        assert judged["verdict"] == "SKIP"
        assert judged["verdict"] != "BUY"
