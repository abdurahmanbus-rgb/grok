# scan.py
# one queue, then the normal check. a paid profile, boost, or trend is not a pass.
# one bad mint is logged and the run continues. a second scan does not start while one is in progress.
import json
import os
import time
from discover import MAX_CHECKS_PER_RUN, collect
from check import log, run_mint

LOCK = "scan.lock"
# pause between mints so a full batch stays polite to RugCheck and DexScreener.
# this is not a risk threshold.
CHECK_INTERVAL_SEC = 1.25


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    else:
        return True


def acquire_lock(path: str = LOCK) -> bool:
    """False when another live scan owns the lock. a dead pid does not block the next run."""
    if os.path.exists(path):
        try:
            pid = int(open(path).read().strip() or "0")
        except ValueError:
            pid = 0
        if _alive(pid):
            return False
    with open(path, "w") as handle:
        handle.write(str(os.getpid()))
    return True


def release_lock(path: str = LOCK):
    try:
        if os.path.exists(path):
            owner = int(open(path).read().strip() or "0")
            if owner == os.getpid():
                os.remove(path)
    except (OSError, ValueError):
        pass


def run(limit: int = MAX_CHECKS_PER_RUN, interval: float = CHECK_INTERVAL_SEC,
        sleep=time.sleep, check_fn=run_mint, collect_fn=collect) -> dict:
    """Check up to `limit` new mints. limit cannot exceed the operational cap."""
    limit = max(0, min(int(limit), MAX_CHECKS_PER_RUN))
    collection = collect_fn()
    outcomes = []
    queued = list(collection.get("queue") or [])[:limit]
    for index, cand in enumerate(queued):
        mint = cand["mint"] if isinstance(cand, dict) else cand.mint
        source = cand.get("first_source") if isinstance(cand, dict) else getattr(cand, "first_source", "")
        try:
            verdict = check_fn(mint)
        except Exception as exc:
            verdict = {
                "stage": "scan",
                "verdict": "SKIP",
                "reason": f"error:scan:isolated:{exc.__class__.__name__}",
                "error_class": "network",
                "symbol": None,
            }
            try:
                log({"time": time.strftime("%Y-%m-%d %H:%M"), "mint": mint, **verdict})
            except Exception:
                pass
        if isinstance(verdict, dict):
            verdict["mint"] = mint
            verdict["source"] = source
        outcomes.append(verdict)
        if interval and index + 1 < len(queued):
            sleep(interval)
    return {"collection": collection, "outcomes": outcomes, "locked": True}


def main(argv=None) -> int:
    argv = list(argv if argv is not None else [])
    limit = MAX_CHECKS_PER_RUN
    if "--limit" in argv:
        try:
            asked = int(argv[argv.index("--limit") + 1])
        except (IndexError, ValueError):
            print("usage: python3 scan.py [--limit N]")
            return 2
        limit = max(0, min(asked, MAX_CHECKS_PER_RUN))
    if not acquire_lock():
        print("scan already running; this run does nothing")
        return 0
    try:
        result = run(limit=limit)
    finally:
        release_lock()
    stats = (result.get("collection") or {}).get("stats") or {}
    print(json.dumps({
        "unique": stats.get("unique"),
        "queued": stats.get("queued"),
        "checked": len(result["outcomes"]),
        "source_errors": stats.get("source_errors"),
        "verdicts": [
            {"mint": item.get("mint"), "stage": item.get("stage"),
             "verdict": item.get("verdict"), "reason": item.get("reason"),
             "source": item.get("source")}
            for item in result["outcomes"] if isinstance(item, dict)
        ],
    }, indent=2, default=str))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
