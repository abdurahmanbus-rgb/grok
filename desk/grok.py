# grok.py
# the only file that holds the key and the only place the desk talks to xAI.
# one call. no retry. a bad answer is a SKIP upstream, never a BUY.
import os, json, datetime, requests
from config import MODEL, MIN_CONFIDENCE
from errors import FetchError, classify_status

URL = "https://api.x.ai/v1/responses"
_REQUIRED = ("verdict", "confidence", "why", "x_read", "main_risk")


def _key() -> str:
    k = os.environ.get("XAI_API_KEY")
    if not k and os.path.exists(".env"):
        for line in open(".env"):
            if line.startswith("XAI_API_KEY="):
                k = line.split("=", 1)[1].strip().strip('"')
    if not k:
        raise RuntimeError("no XAI_API_KEY in the environment or in .env")
    return k


def has_key() -> bool:
    """True when a key is configured. the key itself is never returned."""
    try:
        return bool(_key())
    except RuntimeError:
        return False


def _text(resp: dict) -> str:
    if isinstance(resp.get("output_text"), str):
        return resp["output_text"]
    parts = []
    for item in resp.get("output") or []:
        if item.get("type") == "message":
            for c in item.get("content") or []:
                if c.get("type") in ("output_text", "text"):
                    parts.append(c.get("text") or "")
    return "\n".join(parts)


def _skip(why: str, confidence=0) -> dict:
    return {
        "verdict": "SKIP",
        "confidence": confidence if isinstance(confidence, (int, float)) else 0,
        "why": why,
        "x_read": None,
        "main_risk": None,
        "inconclusive": True,
    }


def normalize_judge(ans) -> dict:
    """Structured JSON only. missing, null, or off-schema evidence is SKIP, not BUY."""
    if not isinstance(ans, dict):
        return _skip("inconclusive: response was not an object")
    for field in _REQUIRED:
        value = ans.get(field)
        if value is None:
            return _skip(f"inconclusive: missing {field}")
        if isinstance(value, str) and not value.strip():
            return _skip(f"inconclusive: missing {field}")
    verdict = ans.get("verdict")
    if verdict not in ("BUY", "SKIP"):
        return _skip(f"inconclusive: verdict {verdict!r}")
    try:
        confidence = float(ans["confidence"])
    except (TypeError, ValueError):
        return _skip("inconclusive: confidence not a number")
    if verdict == "BUY" and confidence < MIN_CONFIDENCE:
        return {
            "verdict": "SKIP",
            "confidence": confidence,
            "why": f"low confidence {confidence}",
            "x_read": ans.get("x_read"),
            "main_risk": ans.get("main_risk"),
        }
    return {
        "verdict": verdict,
        "confidence": confidence,
        "why": ans.get("why"),
        "x_read": ans.get("x_read"),
        "main_risk": ans.get("main_risk"),
    }


def ask(system: str, payload: dict, read_x: bool = False, session=None) -> dict:
    """One call, JSON in, JSON out. Transport and parse failures raise FetchError.

    There is no retry. a second call would spend the same budget on the same token.
    """
    body = {"model": MODEL,
            "input": [{"role": "system", "content": system},
                      {"role": "user", "content": json.dumps(payload)}]}
    if read_x:
        since = (datetime.date.today() - datetime.timedelta(days=3)).isoformat()
        body["tools"] = [{"type": "x_search", "from_date": since}]
        body["max_turns"] = 2          # two rounds of searching, then it has to answer
    sess = session or requests
    try:
        response = sess.post(URL, timeout=180, json=body,
                             headers={"Authorization": f"Bearer {_key()}"})
    except requests.Timeout:
        raise FetchError("grok", "timeout", "timeout")
    except requests.RequestException as exc:
        raise FetchError("grok", "network", exc.__class__.__name__)
    status = getattr(response, "status_code", 0) or 0
    if status != 200:
        raise FetchError("grok", classify_status(status), f"HTTP {status}", status)
    try:
        payload_json = response.json()
    except ValueError as exc:
        raise FetchError("grok", "malformed", f"json decode: {exc}", 200)
    if not isinstance(payload_json, dict):
        raise FetchError("grok", "malformed", "response was not an object", 200)
    text = _text(payload_json)
    start, end = text.find("{"), text.rfind("}")
    if start == -1:
        raise FetchError("grok", "malformed", "no json in answer", 200)
    try:
        parsed = json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise FetchError("grok", "malformed", f"json decode: {exc}", 200)
    if not isinstance(parsed, dict):
        raise FetchError("grok", "malformed", "judge json was not an object", 200)
    return parsed
