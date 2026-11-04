# errors.py
# RugCheck and DexScreener failures, named. a failure is never a pass.
import time
import requests

# the classes the desk records. they are not security kills.
KINDS = (
    "rejection",
    "missing",
    "invalid",
    "rate_limit",
    "timeout",
    "5xx",
    "malformed",
    "network",
)

# only these are worth a second try. a 400 will not become a 200 if we hit it again immediately.
TRANSIENT = {"rate_limit", "timeout", "5xx", "network"}


class FetchError(Exception):
    """The call did not return usable JSON. Callers turn this into SKIP, never BUY."""

    def __init__(self, provider: str, kind: str, detail: str, status: int | None = None):
        if kind not in KINDS:
            raise ValueError(f"unknown error kind {kind}")
        self.provider = provider
        self.kind = kind
        self.detail = detail
        self.status = status
        super().__init__(f"{provider}:{kind}:{detail}")


def classify_status(code: int) -> str:
    """Map an HTTP status. 400/422 on a locally valid mint is a rejection, not a pass."""
    if code == 404:
        return "missing"
    if code == 429:
        return "rate_limit"
    if 500 <= code <= 599:
        return "5xx"
    if 400 <= code < 500:
        return "rejection"
    return "malformed"


def classify_exception(exc: BaseException) -> str:
    if isinstance(exc, requests.Timeout):
        return "timeout"
    if isinstance(exc, requests.RequestException):
        return "network"
    return "network"


def _retry_after(resp, cap: float) -> float | None:
    headers = getattr(resp, "headers", None) or {}
    try:
        raw = headers.get("Retry-After")
    except Exception:
        return None
    if raw is None:
        return None
    try:
        return min(cap, max(0.0, float(raw)))
    except (TypeError, ValueError):
        return None


def fetch_json(url: str, *, provider: str, timeout: float = 15, attempts: int = 3,
               sleep=time.sleep, session=None, headers=None, retry_cap: float = 2.0):
    """GET JSON. Retries only transient failures, and only a few times.

    A raised FetchError is the only failure signal. This function never fills in
    a token report, a pool, or a BUY.
    """
    sess = session or requests
    last: FetchError | None = None
    hdrs = {"User-Agent": "rug-desk-paper/1.0", "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    for attempt in range(max(1, attempts)):
        try:
            resp = sess.get(url, timeout=timeout, headers=hdrs)
        except requests.Timeout as exc:
            last = FetchError(provider, "timeout", str(exc) or "timeout")
        except requests.RequestException as exc:
            last = FetchError(provider, "network", exc.__class__.__name__)
        else:
            status = getattr(resp, "status_code", None) or 0
            if status == 200:
                try:
                    data = resp.json()
                except ValueError as exc:
                    raise FetchError(provider, "malformed", f"json decode: {exc}", 200)
                if not isinstance(data, (dict, list)):
                    raise FetchError(provider, "malformed",
                                     f"unexpected json type {type(data).__name__}", 200)
                return data
            kind = classify_status(status)
            last = FetchError(provider, kind, f"HTTP {status}", status)
            if kind not in TRANSIENT:
                raise last
            if attempt + 1 >= attempts:
                raise last
            wait = _retry_after(resp, retry_cap)
            sleep(wait if wait is not None else min(retry_cap, 0.4 * (2 ** attempt)))
            continue
        if last.kind not in TRANSIENT or attempt + 1 >= attempts:
            raise last
        sleep(min(retry_cap, 0.4 * (2 ** attempt)))
    raise last or FetchError(provider, "network", "no attempt")
