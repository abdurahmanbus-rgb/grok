# watch.py
# every open position, every 10 minutes. prints nothing when nothing changed.
import time
from config import EXIT, PAPER
from market import pool
import book


def watch() -> list[str]:
    events = []
    for mint, p in list(book.load().items()):
        try:
            m = pool(mint)
        except Exception as e:
            events.append(f"{p['symbol']}: price feed down ({e}), holding, will retry")
            continue
        if not m or m["price"] <= 0:
            events.append(f"{p['symbol']}: pool gone. treat as rugged, sell what you can")
            book.sell(mint, 1.0, 0.0, "pool_gone")
            continue

        price = m["price"]
        b = book.load(); s = b[mint]
        s["peak"] = max(s["peak"], price); book.save(b)
        pct = (price / s["entry"] - 1) * 100
        hours = (time.time() - s["opened"]) / 3600

        def out(frac, why):
            pnl = book.sell(mint, frac, price, why)
            verb = "sold" if PAPER else "LIVE SELL DISABLED (paper only); local book marked"
            size = "the rest" if frac >= 1 else f"{int(frac * 100)}%"
            events.append(f"{s['symbol']}: {verb} {size} at {pct:+.0f}% ({why}), pnl ${pnl:+.2f}")

        if m["liq_usd"] < s["liq0"] * (1 - EXIT["liq_drop_pct"] / 100):
            out(1.0, "liquidity_pulled"); continue
        if pct <= EXIT["stop_pct"]:
            out(1.0, "stop"); continue
        ladder = EXIT["ladder"]
        if s["steps"] < len(ladder) and pct >= ladder[s["steps"]][0]:
            out(ladder[s["steps"]][1], f"take_profit_{ladder[s['steps']][0]}")
            b = book.load()
            if mint in b:
                b[mint]["steps"] += 1; book.save(b)
            continue
        if s["steps"] > 0 and price <= s["peak"] * (1 - EXIT["trail_pct"] / 100):
            out(1.0, "trailing_stop"); continue
        if hours >= EXIT["time_stop_hours"] and pct < EXIT["time_stop_min_pct"]:
            out(1.0, "time_stop")
    return events


if __name__ == "__main__":
    for e in watch():
        print(e)