# market.py
# the pool itself: depth, age, price, and whether anyone can actually sell.
import time
from config import FACTS, TICKET_USD
from errors import FetchError, fetch_json
from mints import is_valid_mint

DS = "https://api.dexscreener.com/tokens/v1/solana"


def pool(mint: str, fetch=fetch_json) -> dict | None:
    if not is_valid_mint(mint):
        raise FetchError("dexscreener", "invalid", "mint failed local validation")
    data = fetch(f"{DS}/{mint}", provider="dexscreener", timeout=15)
    # a list, or {"pairs": [...]} . an empty list is a real "no pool", not a fetch error.
    if isinstance(data, list):
        pairs = data
    elif isinstance(data, dict):
        pairs = data.get("pairs") or []
    else:
        raise FetchError("dexscreener", "malformed", "pool body was not a list or object")
    pairs = [p for p in pairs if isinstance(p, dict) and (p.get("baseToken") or {}).get("address") == mint]
    if not pairs:
        return None
    p = max(pairs, key=lambda x: (x.get("liquidity") or {}).get("usd") or 0)
    h1 = (p.get("txns") or {}).get("h1") or {}
    born = p.get("pairCreatedAt")
    return {
        "symbol": (p.get("baseToken") or {}).get("symbol"),
        "price": float(p.get("priceUsd") or 0),
        "liq_usd": (p.get("liquidity") or {}).get("usd") or 0,
        "age_min": round((time.time() * 1000 - born) / 60000) if born else None,
        "buys_1h": h1.get("buys", 0),
        "sells_1h": h1.get("sells", 0),
        "vol_1h": (p.get("volume") or {}).get("h1"),
        "url": p.get("url"),
    }


def market_kill(m: dict | None) -> str | None:
    if not m:                                                    return "no_pool"
    if m["price"] <= 0:                                          return "no_price"
    if m["liq_usd"] < FACTS["min_liquidity_usd"]:                return "thin_pool"
    if TICKET_USD / m["liq_usd"] > FACTS["max_ticket_share"]:    return "ticket_too_big"
    if m["age_min"] is None or m["age_min"] < FACTS["min_age_min"]:
        return "too_fresh"
    if m["age_min"] > FACTS["max_age_hours"] * 60:               return "too_old"
    if m["buys_1h"] >= 20 and m["sells_1h"] == 0:                return "nobody_can_sell"
    return None
