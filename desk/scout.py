# scout.py
# SCOUT leads are a discovery feed. they are not a security authority.
import json
import re
from pathlib import Path
from mints import is_valid_mint

_TS = re.compile(r"(20\d{2}-\d{2}-\d{2}T)(\d{4}|\d{6})Z")
_NOTE_KEYS = ("symbol", "name", "dex", "liq", "note")


def stamp_from_name(name: str) -> str | None:
    """Pull a UTC stamp out of a lead filename. returns None when the name has none."""
    match = _TS.search(name)
    if not match:
        return None
    hm = match.group(2)
    if len(hm) == 4:
        hm += "00"
    return f"{match.group(1)}{hm[:2]}:{hm[2:4]}:{hm[4:6]}Z"


def _mtime_stamp(path: Path) -> str:
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(path.stat().st_mtime))


def load_reported(dirs: list[Path]) -> set[str]:
    """reported_mints.txt is SCOUT's identity ledger, not a clearance list."""
    found: set[str] = set()
    for directory in dirs:
        path = directory / "reported_mints.txt"
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            mint = line.strip()
            if is_valid_mint(mint):
                found.add(mint)
    return found


def _hit(mint: str, note: str, path: Path, kind: str) -> dict:
    return {
        "mint": mint,
        "source": "scout",
        "seen": stamp_from_name(path.name) or _mtime_stamp(path),
        "note": note[:300],
        "provenance": {"source": "scout", "file": path.name, "kind": kind},
    }


def parse_markdown(text: str, path: Path) -> tuple[list[dict], int]:
    """First field of a line, when it is a full mint. URLs later on the line are not mints."""
    hits = []
    dropped = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        token = line.split()[0]
        if not is_valid_mint(token):
            dropped += 1
            continue
        note = line[len(token):].strip()
        hits.append(_hit(token, note, path, "md"))
    return hits, dropped


def _walk_json(node, path: Path, hits: list[dict], dropped: list[int]):
    if isinstance(node, dict):
        mint = node.get("mint")
        if isinstance(mint, str):
            mint = mint.strip()
            if is_valid_mint(mint):
                bits = []
                for key in _NOTE_KEYS:
                    value = node.get(key)
                    if isinstance(value, (str, int, float)) and value != "":
                        bits.append(f"{key}={value}")
                hits.append(_hit(mint, " ".join(bits), path, "json"))
            else:
                dropped[0] += 1
        for key, value in node.items():
            # wallet addresses are traders, not token mints. do not read them as leads.
            if key == "wallet":
                continue
            _walk_json(value, path, hits, dropped)
    elif isinstance(node, list):
        for value in node:
            _walk_json(value, path, hits, dropped)


def parse_json(text: str, path: Path) -> tuple[list[dict], int]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return [], 1
    hits: list[dict] = []
    dropped = [0]
    _walk_json(data, path, hits, dropped)
    return hits, dropped[0]


def load_scout(dirs: list[Path]) -> tuple[list[dict], set[str], dict]:
    """Read every lead file. reported_mints.txt is returned separately, not as a feed."""
    hits: list[dict] = []
    dropped = 0
    files = 0
    for directory in dirs:
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            if not path.is_file():
                continue
            if path.name == "reported_mints.txt":
                continue
            suffix = path.suffix.lower()
            text = path.read_text(encoding="utf-8", errors="replace")
            if suffix == ".md":
                found, skip = parse_markdown(text, path)
            elif suffix == ".json":
                found, skip = parse_json(text, path)
            elif suffix == ".txt":
                found, skip = parse_markdown(text, path)
            else:
                continue
            files += 1
            hits.extend(found)
            dropped += skip
    reported = load_reported(dirs)
    stats = {"files": files, "hits": len(hits), "dropped_lines": dropped, "reported": len(reported)}
    return hits, reported, stats
