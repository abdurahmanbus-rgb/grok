# book.py
# positions, trades, limits. the desk's memory lives in two files you can open yourself.
import csv, json, os, sys, time
from config import (POSITIONS, TRADES, TICKET_USD, MAX_OPEN, MAX_ENTRIES_PER_DAY,
                    DAILY_LOSS_HALT_USD, COOLDOWN_HOURS)


def load() -> dict:
    return json.load(open(POSITIONS)) if os.path.exists(POSITIONS) else {}


def save(book: dict):
    json.dump(book, open(POSITIONS, "w"), indent=2)


def trades() -> list[dict]:
    return list(csv.DictReader(open(TRADES))) if os.path.exists(TRADES) else []


def record(mint, symbol, action, usd, pnl, reason):
    new = not os.path.exists(TRADES)
    with open(TRADES, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["time", "mint", "symbol", "action", "usd", "pnl", "reason"])
        if new:
            w.writeheader()
        w.writerow({"time": time.strftime("%Y-%m-%d %H:%M"), "mint": mint, "symbol": symbol,
                    "action": action, "usd": round(usd, 2), "pnl": round(pnl, 2), "reason": reason})


def today_pnl() -> float:
    day = time.strftime("%Y-%m-%d")
    return sum(float(t["pnl"]) for t in trades() if t["time"].startswith(day))


def guard(mint: str) -> str | None:
    """Limits run before any network call. A blocked entry costs nothing."""
    day = time.strftime("%Y-%m-%d")
    book = load()
    if today_pnl() <= -DAILY_LOSS_HALT_USD:                      return "halted_daily_loss"
    if mint in book:                                             return "already_open"
    if len(book) >= MAX_OPEN:                                    return "max_open"
    opens = [t for t in trades() if t["action"] == "open" and t["time"].startswith(day)]
    if len(opens) >= MAX_ENTRIES_PER_DAY:                        return "max_entries_today"
    cutoff = time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time() - COOLDOWN_HOURS * 3600))
    if any(t["mint"] == mint and t["action"] == "close" and t["time"] >= cutoff for t in trades()):
        return "cooldown"
    return None


def open_position(mint, symbol, price, liq_usd, usd=TICKET_USD):
    """Paper book only. a second open of the same mint does nothing and returns False."""
    book = load()
    if mint in book:
        return False
    if price is None or float(price) <= 0:
        raise ValueError("paper open requires a price")
    price = float(price)
    book[mint] = {"symbol": symbol, "entry": price, "qty0": usd / price, "qty": usd / price,
                  "peak": price, "liq0": liq_usd, "opened": time.time(), "steps": 0}
    save(book)
    record(mint, symbol, "open", usd, 0, "entry")
    return True


def sell(mint, frac_of_original, price, reason) -> float:
    """Sells a fraction of the ORIGINAL size (1.0 = everything left). Returns realized pnl."""
    book = load()
    p = book[mint]
    q = min(p["qty"], p["qty0"] * frac_of_original)
    pnl = q * (price - p["entry"])
    p["qty"] -= q
    action = "close" if p["qty"] <= p["qty0"] * 1e-6 else "partial"
    record(mint, p["symbol"], action, q * price, pnl, reason)
    if action == "close":
        del book[mint]
    save(book)
    return pnl


if __name__ == "__main__":
    # local paper book only. this command does not submit a transaction.
    # python book.py add <mint> <usd> <price> <liq_usd>
    # python book.py close <mint> <price>
    from config import PAPER
    if not PAPER:
        print("LIVE TRADING DISABLED. book.py does not write a live position.")
        sys.exit(2)
    cmd = sys.argv[1]
    if cmd == "add":
        mint, usd, price, liq = sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5])
        open_position(mint, mint[:6], price, liq, usd)
    elif cmd == "close":
        print(round(sell(sys.argv[2], 1.0, float(sys.argv[3]), "manual"), 2))