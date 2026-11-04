import csv
import json
from pathlib import Path

import shadow
from funnel import error_kind, format_funnel, is_fetch_error, load_checks, snapshot, split_row
from report import evening

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "tests" / "fixtures" / "checks_baseline.csv"
MINT = "H4gHnZ3NCU7Z9XQwGX6YYJNyieGEW8pqwGRUcdSxpump"
OTHER = "8s4bNqEztH1JP7mkU747uMr7AckCQdiV47FDqYnDpump"


def _log(*rows):
    with open("checks.csv", "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["time", "mint", "symbol", "stage", "verdict", "confidence", "reason"])
        writer.writeheader()
        writer.writerows(rows)


def _row(mint, reason="insiders", stage="facts", verdict="SKIP", when="2026-11-02 22:00", symbol="T"):
    return {"time": when, "mint": mint, "symbol": symbol, "stage": stage,
            "verdict": verdict, "confidence": "", "reason": reason}


def test_shadow_records_drops_delist_and_never_reopens(tmp_path):
    source = Path(shadow.__file__).read_text(encoding="utf-8")
    assert "import book" not in source
    assert "open_position" not in source
    _log(_row(MINT, symbol="SLING"))
    Path("positions.json").write_text('{"sentinel": true}', encoding="utf-8")
    before = Path("checks.csv").read_text(encoding="utf-8")
    calls = {"n": 0}

    def pool_fn(mint):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"price": 1.0, "liq_usd": 100000}
        return None

    first = shadow.shadow_once(now=1_000, pool_fn=pool_fn, pause=0)
    assert first["sampled"][0]["status"] == "watching"
    assert Path("positions.json").read_text(encoding="utf-8") == '{"sentinel": true}'
    assert Path("checks.csv").read_text(encoding="utf-8") == before

    second = shadow.shadow_once(now=1_001, pool_fn=pool_fn, pause=0)
    assert second["sampled"] == []
    assert calls["n"] == 1

    third = shadow.shadow_once(now=1_000 + shadow.SHADOW_INTERVAL_SEC, pool_fn=pool_fn, pause=0)
    assert third["sampled"][0]["status"] == "delisted"
    assert any(row["status"] == "delisted" for row in third["parked_missing_or_delisted"])
    state = json.loads(Path("shadow.json").read_text(encoding="utf-8"))
    assert MINT in state
    assert "not reopened" in shadow.format_report(third)
    assert Path("positions.json").read_text(encoding="utf-8") == '{"sentinel": true}'


def test_shadow_keeps_a_token_that_was_missing_from_the_first_look():
    _log(_row(OTHER, symbol="GONE"))

    def pool_fn(mint):
        return None

    first = shadow.shadow_once(now=50, pool_fn=pool_fn, pause=0)
    assert first["sampled"][0]["status"] == "missing"
    assert first["parked_missing_or_delisted"]
    Path("checks.csv").write_text("time,mint,symbol,stage,verdict,confidence,reason\n", encoding="utf-8")
    shadow.shadow_once(now=50 + shadow.SHADOW_INTERVAL_SEC, pool_fn=pool_fn, pause=0)
    state = json.loads(Path("shadow.json").read_text(encoding="utf-8"))
    assert OTHER in state
    assert state[OTHER]["status"] == "missing"
    assert not Path("positions.json").exists()


def test_shadow_flags_price_and_liquidity_drops_without_a_position():
    _log(_row(MINT))
    samples = [{"price": 1.0, "liq_usd": 100000}, {"price": 0.5, "liq_usd": 50000}]

    def pool_fn(mint):
        return samples.pop(0)

    shadow.shadow_once(now=10, pool_fn=pool_fn, pause=0)
    later = shadow.shadow_once(now=10 + shadow.SHADOW_INTERVAL_SEC, pool_fn=pool_fn, pause=0)
    signals = later["sampled"][0]["signals"]
    assert "price_drop" in signals
    assert "liquidity_drop" in signals
    assert not Path("positions.json").exists()


def test_fetch_errors_stay_out_of_the_security_tally():
    rows = [
        _row("a", "insiders"),
        _row("b", "error:rugcheck:rejection:HTTP 400"),
        _row("c", "rugcheck failed: 400 Client Error", when="2026-11-03 15:55"),
        _row("d", "thin_pool", stage="pool"),
        _row("e", "passed facts+pool; Grok deferred", stage="pool", verdict="HOLD"),
        _row("f", "copycat", stage="grok"),
    ]
    discovery = {
        "a": {"first_source": "scout", "sources": ["scout", "dexscreener_boosts_top"],
              "first_seen": "2026-11-02T19:07:00Z"},
    }
    snap = snapshot(rows, discovery, {"a", "b", "c", "d", "e", "f"})
    assert snap["security"] == 2
    assert snap["fetch_error"] == 2
    assert snap["buy"] == 0
    assert snap["buckets"]["hold"] == 1
    assert snap["buckets"]["grok"] == 1
    assert "insiders" in dict(snap["security_reasons"])
    assert all(not is_fetch_error(reason) for reason, _count in snap["security_reasons"])
    assert snap["by_source"]["scout"]["check_rows"] == 1
    assert snap["by_source"]["scout"]["discovered"] == 1
    assert snap["by_source"]["dexscreener_boosts_top"]["discovered"] == 1
    assert snap["by_source"]["dexscreener_boosts_top"]["check_rows"] == 0
    assert error_kind("rugcheck failed: 400 Client Error") == "rejection"
    assert split_row(rows[2])["bucket"] == "fetch_error"


def test_historical_funnel_and_legacy_evening_report(capsys):
    checks = BASELINE
    rows = load_checks(str(checks))
    snap = snapshot(rows, {})
    assert snap["check_rows"] == 65
    assert snap["unique_checked"] == 55
    assert snap["buy"] == 0
    assert snap["fetch_error"] == 3
    assert snap["security"] == 57
    assert snap["buckets"]["grok"] == 2
    assert snap["buckets"]["hold"] == 3
    assert snap["error_kinds"]["rejection"] == 3

    text = format_funnel("2026-11-03", log_path=str(checks), discovery_path="missing.json")
    assert "FUNNEL daily 2026-11-03" in text
    assert "FUNNEL cumulative" in text
    assert "fetch_errors: 3" in text
    assert "buys: 0" in text
    assert "security_kills: 57" in text

    evening("2026-11-02", log_path=str(checks))
    printed = capsys.readouterr().out
    assert printed.startswith("EVENING REPORT 2026-11-02 (PAPER)\n")
    assert "checked: 60\n" in printed
    assert "bought: 0 |" in printed
    assert "killed by rug filter:" in printed
    assert "by Grok:" in printed
    nov2 = [row for row in rows if row["time"].startswith("2026-11-02") and row["verdict"] == "SKIP"]
    facts = sum(1 for row in nov2 if row["stage"] == "facts")
    pool = sum(1 for row in nov2 if row["stage"] == "pool")
    grok = sum(1 for row in nov2 if row["stage"] == "grok")
    assert f"killed by rug filter: {facts} | by pool: {pool} | by Grok: {grok} | by limits: 0" in printed
