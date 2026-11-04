# discover.py
# one queue from several public feeds. a feed is not a quality signal and not a pass.
import json
import os
import time
from pathlib import Path

from config import LOG
from errors import FetchError, fetch_json
from mints import is_valid_mint
from scout import load_scout

# operational cap. not a risk threshold, and it does not live in config.py.
# one run stays inside the public rate limits:
#   DexScreener list endpoints are 60 requests/minute (official reference)
#   GeckoTerminal's public API is about 10 calls/minute (official swagger)
# each mint that is actually checked then costs one RugCheck GET and, only if
# the rug filter passes, one DexScreener token GET.
MAX_CHECKS_PER_RUN = 20
SOURCE_PAUSE_SEC = 0.35

# paid profile / boost / takeover lists. chainId + tokenAddress. not a ranking we trust.
DS = "https://api.dexscreener.com"
DS_LISTS = (
    ("dexscreener_profiles", f"{DS}/token-profiles/latest/v1"),
    ("dexscreener_profile_updates", f"{DS}/token-profiles/recent-updates/v1"),
    ("dexscreener_boosts_latest", f"{DS}/token-boosts/latest/v1"),
    ("dexscreener_boosts_top", f"{DS}/token-boosts/top/v1"),
    ("dexscreener_cto", f"{DS}/community-takeovers/latest/v1"),
)

# pair discovery. base token address comes back only with include=base_token.
# page 1 only: paging would multiply the 10/minute GeckoTerminal budget.
GT = "https://api.geckoterminal.com/api/v2"
GT_LISTS = (
    ("geckoterminal_new_pools",
     f"{GT}/networks/solana/new_pools?include=base_token&page=1"),
    ("geckoterminal_trending_pools",
     f"{GT}/networks/solana/trending_pools?include=base_token&page=1&duration=1h"),
)

SOURCE_ORDER = (
    "scout",
    "dexscreener_profiles",
    "dexscreener_profile_updates",
    "dexscreener_boosts_latest",
    "dexscreener_boosts_top",
    "dexscreener_cto",
    "geckoterminal_new_pools",
    "geckoterminal_trending_pools",
)

# canonical majors. skipping them saves a batch slot. check.py still runs every
# gate if one of these is handed to it directly.
MAJORS = {
    "So11111111111111111111111111111111111111112",
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
}

DISCOVERY_PATH = "discovery.json"
GT_HEADERS = {"Accept": "application/json;version=20230203"}


def utc_now(when: float | None = None) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() if when is None else when))


def default_leads_dirs() -> list[Path]:
    env = os.environ.get("DESK_LEADS_DIR")
    if env:
        return [Path(env)]
    here = Path(__file__).resolve().parent
    dirs = []
    for candidate in (here / "leads", here.parent / "leads"):
        if candidate.is_dir():
            dirs.append(candidate)
    return dirs


def checked_mints(path: str = LOG) -> set[str]:
    import csv
    if not path or not os.path.exists(path):
        return set()
    with open(path, newline="") as handle:
        return {row.get("mint", "") for row in csv.DictReader(handle) if row.get("mint")}


def _rows_of(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("data", "pairs", "tokens"):
            if isinstance(data.get(key), list):
                return data[key]
    raise FetchError("dexscreener", "malformed", "list body expected")


def parse_dexscreener_list(data, source: str, seen: str) -> list[dict]:
    hits = []
    for row in _rows_of(data):
        if not isinstance(row, dict):
            continue
        if row.get("chainId") != "solana":
            continue
        mint = row.get("tokenAddress")
        if not isinstance(mint, str) or not is_valid_mint(mint):
            continue
        if mint in MAJORS:
            continue
        hits.append({
            "mint": mint,
            "source": source,
            "seen": seen,
            "note": "",
            "provenance": {"source": source, "file": source, "kind": "api"},
        })
    return hits


def parse_geckoterminal(data, source: str, seen: str) -> list[dict]:
    if not isinstance(data, dict):
        raise FetchError("geckoterminal", "malformed", "body was not an object")
    included = {}
    for item in data.get("included") or []:
        if isinstance(item, dict) and item.get("id"):
            included[item["id"]] = item
    hits = []
    pools = data.get("data")
    if not isinstance(pools, list):
        raise FetchError("geckoterminal", "malformed", "missing data list")
    for pool in pools:
        if not isinstance(pool, dict):
            continue
        rel = ((pool.get("relationships") or {}).get("base_token") or {}).get("data") or {}
        token_id = rel.get("id") if isinstance(rel, dict) else None
        addr = None
        extra = included.get(token_id) if token_id else None
        if isinstance(extra, dict):
            addr = (extra.get("attributes") or {}).get("address")
        if not addr and isinstance(token_id, str) and token_id.startswith("solana_"):
            addr = token_id.split("_", 1)[1]
        if not isinstance(addr, str) or not is_valid_mint(addr) or addr in MAJORS:
            continue
        name = (pool.get("attributes") or {}).get("name") or ""
        hits.append({
            "mint": addr,
            "source": source,
            "seen": seen,
            "note": str(name)[:300],
            "provenance": {"source": source, "file": source, "kind": "api", "pool": name},
        })
    return hits


def _rank(source: str) -> int:
    try:
        return SOURCE_ORDER.index(source)
    except ValueError:
        return len(SOURCE_ORDER)


def _load_store(path: str) -> dict:
    if not path or not os.path.exists(path):
        return {}
    try:
        data = json.load(open(path))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_store(path: str, store: dict):
    if not path:
        return
    tmp = path + ".tmp"
    with open(tmp, "w") as handle:
        json.dump(store, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(tmp, path)


def merge_hits(hits: list[dict], existing: dict, checked: set[str], reported: set[str]) -> list[dict]:
    """One record per full mint. earliest first_seen wins. sources are a union."""
    grouped: dict[str, list[dict]] = {}
    for hit in hits:
        mint = hit["mint"]
        if not is_valid_mint(mint):
            continue
        grouped.setdefault(mint, []).append(hit)

    merged = []
    for mint in existing:
        if mint not in grouped and is_valid_mint(mint):
            prev = existing[mint]
            merged.append({
                "mint": mint,
                "sources": list(prev.get("sources") or []),
                "first_seen": prev.get("first_seen") or "",
                "first_source": prev.get("first_source") or "",
                "notes": list(prev.get("notes") or []),
                "provenance": list(prev.get("provenance") or []),
                "in_reported": bool(prev.get("in_reported")),
                "already_checked": mint in checked,
            })

    for mint, group in grouped.items():
        group.sort(key=lambda hit: (hit["seen"], _rank(hit["source"]), hit["source"]))
        prev = existing.get(mint) or {}
        sources: list[str] = []
        notes: list[str] = []
        provenance: list[dict] = []
        for hit in group:
            if hit["source"] not in sources:
                sources.append(hit["source"])
            if hit.get("note") and hit["note"] not in notes:
                notes.append(hit["note"])
            provenance.append(hit["provenance"])
        for source in prev.get("sources") or []:
            if source not in sources:
                sources.append(source)
        for note in prev.get("notes") or []:
            if note not in notes:
                notes.append(note)
        seen_values = [group[0]["seen"]]
        if prev.get("first_seen"):
            seen_values.append(prev["first_seen"])
        first_seen = min(seen_values)
        if prev.get("first_seen") == first_seen and prev.get("first_source"):
            first_source = prev["first_source"]
        else:
            first_source = group[0]["source"]
        merged.append({
            "mint": mint,
            "sources": sources,
            "first_seen": first_seen,
            "first_source": first_source,
            "notes": notes[:8],
            "provenance": (list(prev.get("provenance") or []) + provenance)[:12],
            "in_reported": mint in reported or bool(prev.get("in_reported")),
            "already_checked": mint in checked,
        })
    merged.sort(key=lambda row: (row["first_seen"], row["mint"]))
    return merged


def build_queue(merged: list[dict], limit: int) -> list[dict]:
    """Round-robin by first source so one noisy feed cannot fill the whole run.

    Order inside a feed is the feed's own order. that is not a score.
    """
    pending = [row for row in merged if not row["already_checked"]]
    buckets = {source: [] for source in SOURCE_ORDER}
    extra = []
    for row in pending:
        source = row["first_source"]
        if source in buckets:
            buckets[source].append(row)
        else:
            extra.append(row)
    queue = []
    while len(queue) < limit and any(buckets.values()):
        for source in SOURCE_ORDER:
            if not buckets[source]:
                continue
            queue.append(buckets[source].pop(0))
            if len(queue) >= limit:
                break
    while len(queue) < limit and extra:
        queue.append(extra.pop(0))
    return queue


def _fetch_lists(fetch, seen: str, sleep, source_errors: list[dict]) -> list[dict]:
    hits = []
    specs = list(DS_LISTS) + list(GT_LISTS)
    for index, (source, url) in enumerate(specs):
        if index:
            sleep(SOURCE_PAUSE_SEC)
        headers = GT_HEADERS if source.startswith("geckoterminal") else None
        provider = "geckoterminal" if source.startswith("geckoterminal") else "dexscreener"
        try:
            data = fetch(url, provider=provider, timeout=20, headers=headers)
            if source.startswith("geckoterminal"):
                hits.extend(parse_geckoterminal(data, source, seen))
            else:
                hits.extend(parse_dexscreener_list(data, source, seen))
        except FetchError as exc:
            source_errors.append({"source": source, "kind": exc.kind, "detail": exc.detail})
        except Exception as exc:
            source_errors.append({"source": source, "kind": "network", "detail": exc.__class__.__name__})
    return hits


def collect(now: str | None = None, sleep=time.sleep, fetch=fetch_json,
            leads_dirs: list[Path] | None = None, discovery_path: str = DISCOVERY_PATH,
            checks_path: str = LOG, limit: int = MAX_CHECKS_PER_RUN) -> dict:
    """Collect, dedupe, persist, and return the queue. does not call check.py or Grok."""
    seen = now or utc_now()
    source_errors: list[dict] = []
    hits = _fetch_lists(fetch, seen, sleep, source_errors)

    dirs = leads_dirs if leads_dirs is not None else default_leads_dirs()
    try:
        scout_hits, reported, scout_stats = load_scout(dirs)
    except Exception as exc:
        scout_hits, reported, scout_stats = [], set(), {"error": exc.__class__.__name__}
        source_errors.append({"source": "scout", "kind": "malformed", "detail": exc.__class__.__name__})
    hits.extend(scout_hits)

    checked = checked_mints(checks_path)
    existing = _load_store(discovery_path)
    merged = merge_hits(hits, existing, checked, reported)
    queue = build_queue(merged, limit)

    store = {}
    for row in merged:
        store[row["mint"]] = {
            "mint": row["mint"],
            "sources": row["sources"],
            "first_seen": row["first_seen"],
            "first_source": row["first_source"],
            "notes": row["notes"],
            "provenance": row["provenance"],
            "in_reported": row["in_reported"],
        }
    _save_store(discovery_path, store)

    by_source = {source: 0 for source in SOURCE_ORDER}
    for row in merged:
        for source in row["sources"]:
            by_source[source] = by_source.get(source, 0) + 1
    stats = {
        "raw_hits": len(hits),
        "unique": len(merged),
        "queued": len(queue),
        "already_checked": sum(1 for row in merged if row["already_checked"]),
        "in_reported": sum(1 for row in merged if row["in_reported"]),
        "unchecked_in_reported": sum(
            1 for row in merged if row["in_reported"] and not row["already_checked"]
        ),
        "by_source": by_source,
        "source_errors": source_errors,
        "scout": scout_stats,
        "limit": limit,
        "collected_at": seen,
    }
    return {
        "candidates": merged,
        "queue": queue,
        "source_errors": source_errors,
        "stats": stats,
    }


if __name__ == "__main__":
    # discovery only. no RugCheck, no Grok, no paper fill.
    result = collect()
    print(json.dumps(result["stats"], indent=2))
    print(f"queue {len(result['queue'])} unique {len(result['candidates'])}")
