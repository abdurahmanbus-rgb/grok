# shadow.py
# research watch for tokens the desk already rejected.
# it records price and liquidity. it does not reopen a token and it does not open a position.
import csv
import json
import os
import time
from config import EXIT, LOG
from errors import FetchError
from market import pool as read_pool

SHADOW_PATH = "shadow.json"
# per run, not a schedule. routines are unchanged; an operator runs this by hand.
SHADOW_BATCH = 15
SHADOW_INTERVAL_SEC = 3600
SHADOW_PAUSE_SEC = 0.4


def _load(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        data = json.load(open(path))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(path: str, state: dict):
    tmp = path + ".tmp"
    with open(tmp, "w") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(tmp, path)


def rejected_mints(log_path: str = LOG) -> list[dict]:
    """Last verdict per mint. BUY is not a rejected candidate. order is oldest check first."""
    if not os.path.exists(log_path):
        return []
    with open(log_path, newline="") as handle:
        rows = list(csv.DictReader(handle))
    last = {}
    order = []
    for row in rows:
        mint = row.get("mint") or ""
        if not mint:
            continue
        if mint not in last:
            order.append(mint)
        last[mint] = row
    rejected = []
    for mint in order:
        row = last[mint]
        if (row.get("verdict") or "").upper() == "BUY":
            continue
        rejected.append({
            "mint": mint,
            "symbol": row.get("symbol") or "",
            "stage": row.get("stage") or "",
            "verdict": row.get("verdict") or "",
            "reason": row.get("reason") or "",
            "time": row.get("time") or "",
        })
    return rejected


def _signals(first: dict, price, liq) -> list[str]:
    found = []
    base_price = first.get("price")
    base_liq = first.get("liq_usd")
    if isinstance(price, (int, float)) and isinstance(base_price, (int, float)) and base_price > 0:
        drop = (base_price - price) / base_price * 100
        if drop >= abs(EXIT["stop_pct"]):
            found.append("price_drop")
    if isinstance(liq, (int, float)) and isinstance(base_liq, (int, float)) and base_liq > 0:
        drop = (base_liq - liq) / base_liq * 100
        if drop >= EXIT["liq_drop_pct"]:
            found.append("liquidity_drop")
    return found


def _sample_one(record: dict, market, now: float) -> dict:
    samples = record.setdefault("samples", [])
    had_market = any(sample.get("status") == "watching" for sample in samples)
    if market is None:
        status = "delisted" if had_market else "missing"
        sample = {"t": now, "status": status, "price": None, "liq_usd": None, "signals": [status]}
    else:
        price = market.get("price")
        liq = market.get("liq_usd")
        if not price or price <= 0:
            status = "missing"
            sample = {"t": now, "status": status, "price": price, "liq_usd": liq, "signals": ["no_price"]}
        else:
            first = next((item for item in samples if item.get("status") == "watching"), None)
            signals = _signals(first, price, liq) if first else []
            status = "watching"
            sample = {"t": now, "status": status, "price": price, "liq_usd": liq, "signals": signals}
    samples.append(sample)
    record["samples"] = samples[-48:]
    record["status"] = sample["status"]
    record["signals"] = sample["signals"]
    record["next_due"] = now + SHADOW_INTERVAL_SEC
    return sample


def shadow_once(now: float | None = None, log_path: str = LOG, path: str = SHADOW_PATH,
                pool_fn=read_pool, limit: int = SHADOW_BATCH, sleep=time.sleep,
                pause: float = SHADOW_PAUSE_SEC) -> dict:
    """Sample due rejects. missing and delisted stay in the file. positions are not touched."""
    now = time.time() if now is None else now
    state = _load(path)
    due = []
    for meta in rejected_mints(log_path):
        record = state.get(meta["mint"])
        if record is None:
            record = {
                "mint": meta["mint"],
                "symbol": meta["symbol"],
                "rejected_stage": meta["stage"],
                "rejected_verdict": meta["verdict"],
                "rejected_reason": meta["reason"],
                "rejected_time": meta["time"],
                "samples": [],
                "status": "unsampled",
                "next_due": 0,
            }
            state[meta["mint"]] = record
        else:
            # refresh the rejection note. do not delete the record if a later read fails.
            record["rejected_reason"] = meta["reason"]
            record["rejected_verdict"] = meta["verdict"]
        if now >= float(record.get("next_due") or 0):
            due.append(record)
    sampled = []
    errors = []
    for index, record in enumerate(due[:limit]):
        mint = record["mint"]
        try:
            market = pool_fn(mint)
        except FetchError as exc:
            sample = {
                "t": now, "status": exc.kind, "price": None, "liq_usd": None,
                "signals": [exc.kind], "detail": exc.detail,
            }
            record.setdefault("samples", []).append(sample)
            record["samples"] = record["samples"][-48:]
            record["status"] = exc.kind
            record["signals"] = [exc.kind]
            record["next_due"] = now + SHADOW_INTERVAL_SEC
            errors.append({"mint": mint, "kind": exc.kind})
            sampled.append({"mint": mint, "symbol": record.get("symbol"), **sample})
        except Exception as exc:
            sample = {
                "t": now, "status": "network", "price": None, "liq_usd": None,
                "signals": ["network"], "detail": exc.__class__.__name__,
            }
            record.setdefault("samples", []).append(sample)
            record["samples"] = record["samples"][-48:]
            record["status"] = "network"
            record["signals"] = ["network"]
            record["next_due"] = now + SHADOW_INTERVAL_SEC
            errors.append({"mint": mint, "kind": "network"})
            sampled.append({"mint": mint, "symbol": record.get("symbol"), **sample})
        else:
            sample = _sample_one(record, market, now)
            sampled.append({"mint": mint, "symbol": record.get("symbol"), **sample})
        if pause and index + 1 < min(len(due), limit):
            sleep(pause)
    # never drop a mint that has gone missing. the record stays.
    _save(path, state)
    parked = [
        {"mint": mint, "symbol": row.get("symbol"), "status": row.get("status"),
         "signals": row.get("signals") or []}
        for mint, row in sorted(state.items())
        if row.get("status") in ("missing", "delisted")
    ]
    return {
        "sampled": sampled,
        "errors": errors,
        "parked_missing_or_delisted": parked,
        "tracked": len(state),
        "due_left": max(0, len(due) - limit),
    }


def format_report(result: dict) -> str:
    lines = ["SHADOW research-only. rejected tokens are not reopened and no position is created."]
    if not result["sampled"]:
        lines.append("sampled: 0")
    for row in result["sampled"]:
        signals = ",".join(row.get("signals") or []) or "-"
        lines.append(
            f"{row.get('symbol') or row['mint']}: {row.get('status')} "
            f"price={row.get('price')} liq={row.get('liq_usd')} signals={signals}"
        )
    lines.append(f"tracked: {result['tracked']} | still due after this run: {result['due_left']}")
    lines.append(f"missing_or_delisted: {len(result['parked_missing_or_delisted'])}")
    for row in result["parked_missing_or_delisted"]:
        lines.append(f"  {row.get('symbol') or row['mint']}: {row['status']}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(format_report(shadow_once()))
