import json
from pathlib import Path

from discover import (
    DS_LISTS,
    GT_LISTS,
    MAJORS,
    MAX_CHECKS_PER_RUN,
    SOURCE_ORDER,
    build_queue,
    collect,
    parse_dexscreener_list,
    parse_geckoterminal,
)
from errors import FetchError
from mints import is_valid_mint
from scout import load_scout

ROOT = Path(__file__).resolve().parents[2]
LEADS = ROOT / "leads"
ALPH = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
WALLET = "8CQsNv856jzmDKKGue5GcrX3zrMjhfbwfMNZTjm5b9ZF"
WSOL = "So11111111111111111111111111111111111111112"


def make_mint(n: int) -> str:
    chars = []
    x = n + 97
    for _ in range(32):
        chars.append(ALPH[x % len(ALPH)])
        x = (x // len(ALPH)) + n + 3
    mint = "".join(chars)
    assert is_valid_mint(mint), mint
    return mint


def test_make_mint_unique():
    found = {make_mint(n) for n in range(40)}
    assert len(found) == 40


def test_list_parsers_drop_other_chains_invalid_and_majors():
    mint = make_mint(1)
    rows = [
        {"chainId": "solana", "tokenAddress": mint},
        {"chainId": "ethereum", "tokenAddress": mint},
        {"chainId": "solana", "tokenAddress": "not-a-mint"},
        {"chainId": "solana", "tokenAddress": WSOL},
        {"chainId": "solana"},
    ]
    hits = parse_dexscreener_list(rows, "dexscreener_boosts_top", "2026-11-03T00:00:00Z")
    assert [hit["mint"] for hit in hits] == [mint]
    assert WSOL in MAJORS

    payload = {
        "data": [
            {"attributes": {"name": "MEME / SOL"},
             "relationships": {"base_token": {"data": {"id": f"solana_{mint}", "type": "token"}}}},
            {"attributes": {"name": "SOL / USDC"},
             "relationships": {"base_token": {"data": {"id": f"solana_{WSOL}", "type": "token"}}}},
        ],
        "included": [
            {"id": f"solana_{mint}", "type": "token", "attributes": {"address": mint}},
            {"id": f"solana_{WSOL}", "type": "token", "attributes": {"address": WSOL}},
        ],
    }
    gt = parse_geckoterminal(payload, "geckoterminal_trending_pools", "2026-11-03T00:00:00Z")
    assert [hit["mint"] for hit in gt] == [mint]
    assert gt[0]["note"] == "MEME / SOL"
    assert "verdict" not in gt[0]


def test_round_robin_does_not_let_one_feed_fill_the_batch():
    rows = []
    for source, count in (("dexscreener_profiles", 10), ("dexscreener_boosts_top", 10)):
        for n in range(count):
            rows.append({
                "mint": make_mint(n + (0 if source.endswith("profiles") else 100)),
                "first_source": source,
                "first_seen": "2026-11-03T00:00:00Z",
                "already_checked": False,
                "sources": [source],
            })
    queue = build_queue(rows, 4)
    assert [row["first_source"] for row in queue] == [
        "dexscreener_profiles",
        "dexscreener_boosts_top",
        "dexscreener_profiles",
        "dexscreener_boosts_top",
    ]
    assert MAX_CHECKS_PER_RUN == 20
    assert "scout" in SOURCE_ORDER


def _routes(mapping):
    def fetch(url, provider=None, timeout=None, headers=None, **kwargs):
        if url not in mapping:
            raise AssertionError(url)
        value = mapping[url]
        if isinstance(value, Exception):
            raise value
        return value
    return fetch


def test_collect_dedupes_records_provenance_and_survives_one_dead_source(tmp_path):
    kept = make_mint(3)
    other = make_mint(4)
    leads = tmp_path / "leads"
    leads.mkdir()
    (leads / "reported_mints.txt").write_text(kept + "\n", encoding="utf-8")
    (leads / "sweep-2026-11-02T1907Z.md").write_text(
        f"# SCOUT sweep research only\n{kept} CAPY pumpswap liq 67k note-from-scout\n"
        "this line is not a mint\n",
        encoding="utf-8",
    )
    (leads / "fomo-2026-11-02T2012Z.json").write_text(json.dumps({
        "traders": [{"wallet": WALLET, "handle": "macenare"}],
        "overlaps": [{"mint": other, "symbol": "NEW", "note": "wallet overlap"}],
    }), encoding="utf-8")

    profiles = DS_LISTS[0][1]
    updates = DS_LISTS[1][1]
    boosts = DS_LISTS[2][1]
    top = DS_LISTS[3][1]
    cto = DS_LISTS[4][1]
    new_pools = GT_LISTS[0][1]
    trending = GT_LISTS[1][1]
    mapping = {
        profiles: [
            {"chainId": "solana", "tokenAddress": kept},
            {"chainId": "ethereum", "tokenAddress": "0xabc"},
        ],
        updates: [],
        boosts: [{"chainId": "solana", "tokenAddress": kept}],
        top: FetchError("dexscreener", "rate_limit", "HTTP 429", 429),
        cto: [],
        new_pools: {"data": [], "included": []},
        trending: {
            "data": [{
                "attributes": {"name": "OTHER / SOL"},
                "relationships": {"base_token": {"data": {"id": f"solana_{other}"}}},
            }],
            "included": [{"id": f"solana_{other}", "type": "token",
                          "attributes": {"address": other}}],
        },
    }
    slept = []
    result = collect(
        now="2026-11-03T12:00:00Z",
        sleep=slept.append,
        fetch=_routes(mapping),
        leads_dirs=[leads],
        discovery_path=str(tmp_path / "discovery.json"),
        checks_path=str(tmp_path / "checks.csv"),
        limit=20,
    )
    by_mint = {row["mint"]: row for row in result["candidates"]}
    assert WALLET not in by_mint
    assert set(by_mint) == {kept, other}
    assert by_mint[kept]["first_seen"] == "2026-11-02T19:07:00Z"
    assert by_mint[kept]["first_source"] == "scout"
    assert "dexscreener_profiles" in by_mint[kept]["sources"]
    assert "dexscreener_boosts_latest" in by_mint[kept]["sources"]
    assert by_mint[kept]["in_reported"] is True
    assert by_mint[kept]["already_checked"] is False
    assert any("note-from-scout" in note for note in by_mint[kept]["notes"])
    assert by_mint[other]["first_source"] == "scout"
    assert "geckoterminal_trending_pools" in by_mint[other]["sources"]
    assert {row["mint"] for row in result["queue"]} == {kept, other}
    assert any(err["source"] == "dexscreener_boosts_top" and err["kind"] == "rate_limit"
               for err in result["source_errors"])
    assert slept  # pauses between the public list calls

    again = collect(
        now="2026-11-04T00:00:00Z",
        sleep=lambda s: None,
        fetch=_routes({**mapping, top: []}),
        leads_dirs=[leads],
        discovery_path=str(tmp_path / "discovery.json"),
        checks_path=str(tmp_path / "checks.csv"),
    )
    again_kept = next(row for row in again["candidates"] if row["mint"] == kept)
    assert again_kept["first_seen"] == "2026-11-02T19:07:00Z"
    assert "verdict" not in again_kept


def test_checks_and_reported_dedupe_without_treating_reported_as_clearance(tmp_path):
    checked = make_mint(5)
    reported_only = make_mint(6)
    fresh = make_mint(7)
    leads = tmp_path / "leads"
    leads.mkdir()
    (leads / "reported_mints.txt").write_text(f"{checked}\n{reported_only}\n", encoding="utf-8")
    (leads / "sweep-2026-11-02T2012Z.md").write_text(
        f"{checked} already judged\n{reported_only} scout saw it, desk has not\n{fresh} brand new\n",
        encoding="utf-8",
    )
    log = tmp_path / "checks.csv"
    log.write_text(
        "time,mint,symbol,stage,verdict,confidence,reason\n"
        f"2026-11-02 22:00,{checked},OLD,facts,SKIP,,insiders\n",
        encoding="utf-8",
    )
    result = collect(
        now="2026-11-03T12:00:00Z",
        sleep=lambda s: None,
        fetch=lambda *a, **k: [],
        leads_dirs=[leads],
        discovery_path=str(tmp_path / "discovery.json"),
        checks_path=str(log),
    )
    queued = [row["mint"] for row in result["queue"]]
    assert checked not in queued
    assert reported_only in queued
    assert fresh in queued
    assert queued.count(reported_only) == 1
    row = next(item for item in result["candidates"] if item["mint"] == reported_only)
    assert row["in_reported"] is True
    assert row["already_checked"] is False
    assert any("desk has not" in note for note in row["notes"])


def test_real_scout_leads_keep_mints_and_drop_wallets_and_pair_urls():
    hits, reported, stats = load_scout([LEADS])
    mints = {hit["mint"] for hit in hits}
    assert WALLET not in mints
    assert "ishesmywetrsksuafp9xc16zy1w3ujv3idwacsnyric" not in {mint.lower() for mint in mints}
    assert "H4gHnZ3NCU7Z9XQwGX6YYJNyieGEW8pqwGRUcdSxpump" in mints
    assert "4xsNJzPvTu2anxUfDcn7wPgmBTygjmJu7mKoT1kHuLgZ" in mints
    assert "xRtT8q7g7NsAnbTgvCtim8jtxKVVc5epoLoAYmqpump" in reported
    sling = next(hit for hit in hits if hit["mint"] == "H4gHnZ3NCU7Z9XQwGX6YYJNyieGEW8pqwGRUcdSxpump")
    assert "Slingoor" in sling["note"]
    assert stats["files"] >= 6
    assert all(is_valid_mint(mint) for mint in mints)
