# funnel.py
# counts and percentages. fetch errors stay out of the security-kill tally.
# the evening report still prints its original lines; this section is added after them.
import csv
import json
import os
from collections import Counter
from config import LOG

DISCOVERY_PATH = "discovery.json"

_FETCH_PREFIXES = ("error:", "rugcheck failed", "dexscreener failed", "grok failed")


def is_fetch_error(reason: str) -> bool:
    text = (reason or "").lower()
    return any(text.startswith(prefix) for prefix in _FETCH_PREFIXES)


def error_kind(reason: str) -> str:
    text = reason or ""
    low = text.lower()
    if low.startswith("error:"):
        parts = text.split(":")
        if len(parts) >= 3:
            return parts[2]
    if "429" in text or "rate" in low:
        return "rate_limit"
    if "timeout" in low or "timed out" in low:
        return "timeout"
    if " 5" in text and any(code in text for code in ("500", "502", "503", "504")):
        return "5xx"
    if "400" in text or "422" in text:
        return "rejection"
    if "404" in text:
        return "missing"
    return "unclassified"


def split_row(row: dict) -> dict:
    verdict = (row.get("verdict") or "").upper()
    stage = row.get("stage") or ""
    reason = row.get("reason") or ""
    if verdict == "BUY":
        bucket = "buy"
    elif reason == "live_trading_disabled":
        bucket = "safety_lock"
    elif reason == "already_checked":
        bucket = "duplicate"
    elif is_fetch_error(reason):
        bucket = "fetch_error"
    elif verdict == "HOLD":
        bucket = "hold"
    elif stage == "limits":
        bucket = "limits"
    elif stage == "grok":
        bucket = "grok"
    elif stage in ("facts", "pool"):
        bucket = "security"
    else:
        bucket = "other"
    return {"bucket": bucket, "stage": stage, "verdict": verdict, "reason": reason}


def load_checks(path: str = LOG) -> list[dict]:
    if not path or not os.path.exists(path):
        return []
    with open(path, newline="") as handle:
        return list(csv.DictReader(handle))


def load_discovery(path: str = DISCOVERY_PATH) -> dict:
    if not path or not os.path.exists(path):
        return {}
    try:
        data = json.load(open(path))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {mint: row for mint, row in data.items() if isinstance(row, dict)}


def _pct(count: int, whole: int) -> str:
    if not whole:
        return "0.0%"
    return f"{(100.0 * count / whole):.1f}%"


def _source_of(mint: str, discovery: dict) -> str:
    row = discovery.get(mint) or {}
    return row.get("first_source") or "unattributed"


def snapshot(rows: list[dict], discovery: dict, discovered_mints: set[str] | None = None) -> dict:
    """One window of check rows.

    `discovery` is the full store, used to attribute a mint to its sources.
    `discovered_mints` is the set that counts as discovered in this window.
    A mint seen from several sources counts once in `discovered` and once per
    source in `by_source`. Check rows are attributed to `first_source` only,
    so those columns sum to the number of rows.
    """
    buckets = Counter()
    stages = Counter()
    kinds = Counter()
    security_reasons = Counter()
    by_source = {}

    def source_row(name: str) -> dict:
        return by_source.setdefault(name, {
            "discovered": 0, "check_rows": 0, "security": 0, "fetch_error": 0,
            "grok": 0, "buy": 0, "hold": 0, "limits": 0,
        })

    seen_mints = set()
    for row in rows:
        info = split_row(row)
        buckets[info["bucket"]] += 1
        stages[info["stage"]] += 1
        mint = row.get("mint") or ""
        if mint:
            seen_mints.add(mint)
        source = _source_of(mint, discovery)
        slot = source_row(source)
        slot["check_rows"] += 1
        if info["bucket"] in slot:
            slot[info["bucket"]] += 1
        if info["bucket"] == "fetch_error":
            kinds[error_kind(info["reason"])] += 1
        elif info["bucket"] == "security":
            security_reasons[info["reason"]] += 1

    if discovered_mints is None:
        discovered_mints = set(discovery) | seen_mints
    for mint in discovered_mints:
        sources = (discovery.get(mint) or {}).get("sources")
        if not sources:
            sources = [_source_of(mint, discovery)]
        for source in sources:
            source_row(source)["discovered"] += 1

    rows_n = len(rows)
    return {
        "check_rows": rows_n,
        "unique_checked": len(seen_mints),
        "discovered": len(discovered_mints),
        "buckets": dict(buckets),
        "stages": dict(stages),
        "error_kinds": dict(kinds),
        "security_reasons": security_reasons.most_common(),
        "by_source": by_source,
        "buy": buckets["buy"],
        "security": buckets["security"],
        "fetch_error": buckets["fetch_error"],
    }


def _discovered_on(rows: list[dict], discovery: dict, day: str | None) -> set[str]:
    if not day:
        found = set(discovery)
        found |= {row.get("mint") for row in rows if row.get("mint")}
        return found
    found = {
        mint for mint, row in discovery.items()
        if str(row.get("first_seen") or "").startswith(day)
    }
    for row in rows:
        mint = row.get("mint")
        if mint and (row.get("time") or "").startswith(day) and mint not in discovery:
            found.add(mint)
    return found


def _lines(title: str, snap: dict) -> list[str]:
    rows_n = snap["check_rows"]
    discovered = snap["discovered"]
    buckets = snap["buckets"]
    lines = [
        title,
        f"discovered: {discovered}",
        f"check_rows: {rows_n} ({_pct(rows_n, discovered)} of discovered) | "
        f"unique_mints: {snap['unique_checked']}",
        f"security_kills: {snap['security']} ({_pct(snap['security'], rows_n)} of rows, "
        f"{_pct(snap['security'], discovered)} of discovered)",
        f"fetch_errors: {snap['fetch_error']} ({_pct(snap['fetch_error'], rows_n)} of rows) "
        f"[kept out of the security tally]",
        f"grok_skips: {buckets.get('grok', 0)} ({_pct(buckets.get('grok', 0), rows_n)} of rows)",
        f"buys: {snap['buy']} ({_pct(snap['buy'], rows_n)} of rows)",
        f"holds: {buckets.get('hold', 0)} | limits: {buckets.get('limits', 0)} | "
        f"safety_lock: {buckets.get('safety_lock', 0)} | other: {buckets.get('other', 0)}",
    ]
    if snap["error_kinds"]:
        kinds = ", ".join(f"{name} {count}" for name, count in sorted(snap["error_kinds"].items()))
        lines.append(f"fetch_error_kinds: {kinds}")
    if snap["by_source"]:
        lines.append("by_source (check rows use first source; discovered counts each source the mint was seen on):")
        for name in sorted(snap["by_source"]):
            slot = snap["by_source"][name]
            if not any(slot.values()):
                continue
            lines.append(
                f"  {name}: discovered {slot['discovered']} | rows {slot['check_rows']} | "
                f"security {slot['security']} | fetch_error {slot['fetch_error']} | "
                f"grok {slot['grok']} | buy {slot['buy']} | hold {slot['hold']}"
            )
    return lines


def format_funnel(day: str | None = None, log_path: str = LOG,
                  discovery_path: str = DISCOVERY_PATH) -> str:
    rows = load_checks(log_path)
    discovery = load_discovery(discovery_path)
    if day:
        daily_rows = [row for row in rows if (row.get("time") or "").startswith(day)]
        parts = _lines(
            f"FUNNEL daily {day}",
            snapshot(daily_rows, discovery, _discovered_on(rows, discovery, day)),
        )
        parts.append("")
        parts.extend(_lines(
            "FUNNEL cumulative",
            snapshot(rows, discovery, _discovered_on(rows, discovery, None)),
        ))
        return "\n".join(parts)
    return "\n".join(_lines(
        "FUNNEL cumulative",
        snapshot(rows, discovery, _discovered_on(rows, discovery, None)),
    ))


def print_funnel(day: str | None = None, log_path: str = LOG,
                 discovery_path: str = DISCOVERY_PATH):
    text = format_funnel(day, log_path, discovery_path)
    if text:
        print(text)


if __name__ == "__main__":
    import time
    print_funnel(time.strftime("%Y-%m-%d"))
