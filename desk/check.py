# check.py
# one contract address in, one verdict out. limits, facts, pool, then Grok.
# a fetch failure is a SKIP. it is never evidence that the token is safe.
import csv, json, os, sys, time
from config import LOG, PAPER, TICKET_USD
from rugcheck import report, fact_kill
from market import pool, market_kill
from grok import ask, has_key, normalize_judge
from prompts import JUDGE_PROMPT
from errors import FetchError
from mints import is_valid_mint
import book

FIELDS = ["time", "mint", "symbol", "stage", "verdict", "confidence", "reason"]


def log(row: dict):
    new = not os.path.exists(LOG)
    with open(LOG, "a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        if new:
            writer.writeheader()
        writer.writerow({key: row.get(key) for key in FIELDS})


def prior_rows(mint: str) -> list[dict]:
    if not os.path.exists(LOG):
        return []
    with open(LOG, newline="") as handle:
        return [row for row in csv.DictReader(handle) if row.get("mint") == mint]


def _error(stage: str, provider: str, kind: str, detail: str, symbol=None) -> dict:
    return {
        "stage": stage,
        "verdict": "SKIP",
        "reason": f"error:{provider}:{kind}:{detail}",
        "error_class": kind,
        "symbol": symbol,
    }


def check(mint: str, *, force: bool = False) -> dict:
    mint = (mint or "").strip()
    if not is_valid_mint(mint):
        return _error("facts", "desk", "invalid", "mint failed local validation")

    if not force:
        earlier = prior_rows(mint)
        if earlier:
            prev = earlier[-1]
            return {
                "stage": prev.get("stage") or "limits",
                "verdict": "SKIP",
                "reason": "already_checked",
                "symbol": prev.get("symbol"),
                "idempotent": True,
                "prior_verdict": prev.get("verdict"),
            }

    if (blocked := book.guard(mint)):
        return {"stage": "limits", "verdict": "SKIP", "reason": blocked}

    try:
        token = report(mint)
    except FetchError as exc:
        return _error("facts", "rugcheck", exc.kind, exc.detail)
    except Exception as exc:
        return _error("facts", "rugcheck", "network", exc.__class__.__name__)
    if (killed := fact_kill(token)):
        return {"stage": "facts", "verdict": "SKIP", "reason": killed, "symbol": token.get("symbol")}

    try:
        market = pool(mint)
    except FetchError as exc:
        return _error("pool", "dexscreener", exc.kind, exc.detail, token.get("symbol"))
    except Exception as exc:
        return _error("pool", "dexscreener", "network", exc.__class__.__name__, token.get("symbol"))
    if (killed := market_kill(market)):
        return {"stage": "pool", "verdict": "SKIP", "reason": killed, "symbol": token.get("symbol")}

    # hard gates have passed. this is the only place a paid call is allowed.
    symbol = market.get("symbol") or token.get("symbol")
    base = {"symbol": symbol, "price": market.get("price"), "liq_usd": market.get("liq_usd"),
            "url": market.get("url")}
    if not has_key():
        return {**base, "stage": "grok", "verdict": "SKIP",
                "reason": "error:grok:missing:no_key", "error_class": "missing"}
    try:
        raw = ask(JUDGE_PROMPT, {"token": token, "pool": market}, read_x=True)
    except FetchError as exc:
        return {**base, **_error("grok", "grok", exc.kind, exc.detail, symbol)}
    except Exception as exc:
        return {**base, **_error("grok", "grok", "network", exc.__class__.__name__, symbol)}

    judged = normalize_judge(raw)
    return {**base, **judged, "stage": "grok", "verdict": judged["verdict"], "reason": judged.get("why"),
            "confidence": judged.get("confidence")}


def apply_paper(mint: str, verdict: dict) -> dict:
    """Paper fill only. the live branch does not sign, send, or open a position."""
    if verdict.get("verdict") != "BUY":
        return verdict
    if not PAPER:
        verdict["verdict"] = "SKIP"
        verdict["reason"] = "live_trading_disabled"
        verdict["action"] = "LIVE TRADING DISABLED. Paper only. No wallet, no signature, no order."
        return verdict
    price = verdict.get("price")
    if not price or float(price) <= 0:
        verdict["verdict"] = "SKIP"
        verdict["reason"] = "error:desk:invalid:no_price_for_paper_fill"
        verdict["action"] = "paper fill refused without a price"
        return verdict
    opened = book.open_position(mint, verdict.get("symbol"), float(price), verdict.get("liq_usd"))
    if opened:
        verdict["action"] = f"PAPER BUY ${TICKET_USD} at {price}"
    else:
        verdict["action"] = "already open; no duplicate paper position"
        verdict["duplicate_position"] = True
    return verdict


def run_mint(mint: str, *, force: bool = False) -> dict:
    verdict = check(mint, force=force)
    if verdict.get("idempotent"):
        verdict["logged"] = False
        return verdict
    verdict = apply_paper(mint.strip(), verdict)
    log({"time": time.strftime("%Y-%m-%d %H:%M"), "mint": mint.strip(), **verdict})
    verdict["logged"] = True
    return verdict


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python3 check.py <mint>")
        sys.exit(2)
    print(json.dumps(run_mint(sys.argv[1].strip()), indent=2, default=str))
