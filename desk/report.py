# report.py
# the evening report. everything in it comes from checks.csv and trades.csv, nothing from memory.
# the original lines are unchanged. the funnel section is printed after them.
import csv, os, time
from collections import Counter
from config import LOG, PAPER
import book
from funnel import print_funnel


def evening(day: str | None = None, log_path: str | None = None):
    day = day or time.strftime("%Y-%m-%d")
    log_path = log_path or LOG
    checks = [r for r in csv.DictReader(open(log_path))] if os.path.exists(log_path) else []
    checks = [r for r in checks if r["time"].startswith(day)]
    done = [t for t in book.trades() if t["time"].startswith(day) and t["action"] != "open"]

    by_stage = Counter(r["stage"] for r in checks if r["verdict"] == "SKIP")
    buys = [r for r in checks if r["verdict"] == "BUY"]
    wins = [t for t in done if float(t["pnl"]) > 0]
    reasons = Counter(r["reason"] for r in checks if r["stage"] in ("facts", "pool"))

    print(f"EVENING REPORT {day} {'(PAPER)' if PAPER else '(LIVE)'}")
    print(f"checked: {len(checks)}")
    print(f"killed by rug filter: {by_stage['facts']} | by pool: {by_stage['pool']} | "
          f"by Grok: {by_stage['grok']} | by limits: {by_stage['limits']}")
    print(f"bought: {len(buys)} | open now: {len(book.load())}")
    print(f"realized pnl today: ${book.today_pnl():+.2f}")
    if done:
        print(f"green exits: {len(wins)}/{len(done)}")
        best = max(done, key=lambda t: float(t["pnl"]))
        worst = min(done, key=lambda t: float(t["pnl"]))
        print(f"best: {best['symbol']} ${float(best['pnl']):+.2f} | worst: {worst['symbol']} ${float(worst['pnl']):+.2f}")
    if reasons:
        top, n = reasons.most_common(1)[0]
        print(f"most common kill: {top} ({n}x)")
    return day


if __name__ == "__main__":
    day = evening()
    print()
    print_funnel(day)
