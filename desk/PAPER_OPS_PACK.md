# RUG DESK — Paper Ops Pack

Generated 2026-11-03 ~16:20 EAT (Africa/Mogadishu, UTC+3). Factual dump for ops analysis. No opinions on tokens; kill reasons only.
All `checks.csv` timestamps are box-local = EAT (written by `time.strftime` in `check.py`).

**Desk hard rules:** PAPER only · never edit `config.py` · never buy/sell/sign/move funds · never lower filters · never guess missing numbers.

---

## 0. Executive index
1. Files & what they do (`/workspace/desk`, `/workspace/trading-desk`, `/workspace/grokdesk`)
2. `config.py` values (quoted, unchanged)
3. Pipeline: scan → check (limits → Rugcheck facts → DexScreener pool → Grok) → book → watch → report
4. `checks.csv` stats: 65 rows, 62 SKIP / 3 HOLD / **0 BUY**, kill-reason frequency, full table
5. Routine status
6. Paper session results (Mon Nov 2 evening, Tue Nov 3 15:55)
7. Floor bots / roster
8. How to re-run
9. Missing sources & data caveats

---

## 1. Files

### `/workspace/desk` (RUG DESK paper filter)
| File | Lines | Role (from code header / body) |
|---|---|---|
| `config.py` | 37 | "every number on the desk lives here". PAPER flag, sizing, limits, FACTS filter thresholds, EXIT rules, file names. |
| `scan.py` | 14 | Optional lead source. GETs `https://api.dexscreener.com/token-profiles/latest/v1`, keeps `chainId == solana` mints not already in `checks.csv`, runs `check.py` on the first **5** per run. |
| `check.py` | 63 | One mint in → one verdict out. Order: `book.guard` (limits) → `rugcheck.report`+`fact_kill` → `market.pool`+`market_kill` → `grok.ask` (only paid step). Logs every verdict to `checks.csv`. On BUY with PAPER=True → `book.open_position` (paper fill). |
| `rugcheck.py` | 60 | GET `https://api.rugcheck.xyz/v1/tokens/<mint>/report`; trims to facts (risk_score, rugged, authorities, danger/warn risks, LP locked %, top10 % excluding AMM/LOCKER accounts, dev %, insiders, holders). `fact_kill` = ordered plain comparisons, first failure wins. |
| `market.py` | 41 | GET `https://api.dexscreener.com/tokens/v1/solana/<mint>`; deepest pair → price, liq_usd, age_min, buys/sells 1h, vol_1h, url. `market_kill` = pool checks. |
| `grok.py` | 47 | Only file that reads `XAI_API_KEY` (env or `.env`). POST `https://api.x.ai/v1/responses`, model from config, `x_search` tool from last 3 days, `max_turns: 2`, timeout 180 s. Non-JSON answer raises → SKIP upstream. |
| `prompts.py` | 28 | `JUDGE_PROMPT`: Grok searches X for ticker + CA (72 h), judges only what code can't see (stacked warns, first posters, organic vs bought, CA mismatch/copycat, prior rug ties). Returns JSON `verdict/confidence/why/x_read/main_risk`. Hard rules: zero X posts → SKIP; other CA under same ticker → SKIP; never BUY on null field. |
| `book.py` | 80 | Positions (`positions.json`) + trades (`trades.csv`) + `guard()` limits (halt on daily loss, already_open, max_open, max_entries_today, cooldown). CLI `add`/`close` for live-mode manual bookkeeping. |
| `watch.py` | 53 | Every open position: re-reads pool; exits on pool_gone, liquidity_pulled, stop, take_profit ladder, trailing_stop, time_stop. Prints nothing if no positions. |
| `report.py` | 30 | Evening report for today from `checks.csv` + `trades.csv`: checked count, kills by stage (facts/pool/grok/limits), buys, open, realized PnL, most common facts/pool kill. |
| `ARTICLE.md` | 140 | Source write-up the desk was built from (funnel design, 14 checks, routines, paper-week guidance). Code blocks are not embedded in this copy (blank sections). |
| `READY.md` | 18 | Readiness note (2026-11-02) + schedule-freeze note (2026-11-03 ~01:08 EAT). |
| `checks.csv` | 66 (65 rows + header) | Verdict log. Columns: `time,mint,symbol,stage,verdict,confidence,reason`. |
| `.env` | — | chmod 600. **Keys present:** `XAI_API_KEY` (present), `HELIUS_API_KEY` (present). Values not reproduced. |
| `python` | symlink | → `/usr/bin/python3`. |
| `.env.example` | **MISSING** | Not present in `/workspace/desk` (a `env.example` exists in `/workspace/grokdesk`). |
| `positions.json` | **MISSING** | Not yet created = no position ever opened. |
| `trades.csv` | **MISSING** | Not yet created = no paper trade ever recorded. |

Also: `/workspace/desk-source/` holds the original copies (`article.md`, all .py files, `prove-key.sh`, `setup.sh`).

### `/workspace/trading-desk` (shared eight-seat floor state)
| Path | Content |
|---|---|
| `ROSTER.md` | Seat table + group rooms (see §7). |
| `desk.md` | Engagement: research; throwaway wallet not connected; daily loss limit 5%; halt off; "Schedules: ALL PAUSED until further notice (user order 2026-11-03 ~01:08 EAT)" — **stale**, see §5. RPC: helius-or-public. |
| `risk-limits.md` | Status: interview pending; Max ticket USD TBD; Max concurrent TBD; Max slippage 100 bps; Top-10 kill 25%; Daily loss halt 5%. |
| `leads/` | SCOUT sweeps (`sweep-2026-11-02T1907Z/2012Z/2101Z/2206Z.md`), FOMO json snapshots, `reported_mints.txt` (32 mints). Labelled "research only, not risk-cleared". |
| `briefs/ incidents/ journal/ positions/ proposals/ research/ watch/` | All empty. |

### `/workspace/grokdesk` (GrokDesk plugin pack)
`AGENTS.md`, `GAMEPLAN.md` (approval phrase `APPROVE SOL-YYYYMMDD-NNN mint=<MINT> size=<SIZE> slippage=<BPS>`; overnight: SCOUT + RUG + journal only), `agents/` (`_constitution.md`, chief, exit, risk, rug, scout, shill, sniper, whale), `skills/`, `commands/`, `rules/`, `scripts/`, `tools/`, `env.example`, `.env` (only `HELIUS_API_KEY` present; no XAI key there).

---

## 2. `config.py` (quoted verbatim, not modified)
```python
MODEL = "grok-4.7"
PAPER = True
TICKET_USD = 25
MAX_OPEN = 4
MAX_ENTRIES_PER_DAY = 6
DAILY_LOSS_HALT_USD = 50
COOLDOWN_HOURS = 24
FACTS = {
    "max_risk_score": 40,
    "min_lp_locked_pct": 90,
    "max_top10_pct": 30,
    "max_dev_pct": 5,
    "max_insiders": 0,
    "min_liquidity_usd": 30000,
    "max_ticket_share": 0.01,
    "min_age_min": 30,
    "max_age_hours": 72,
}
MIN_CONFIDENCE = 0.7
EXIT = {
    "stop_pct": -35,
    "ladder": [(100, 0.50), (200, 0.25)],
    "trail_pct": 30,
    "time_stop_hours": 6,
    "time_stop_min_pct": 20,
    "liq_drop_pct": 40,
}
LOG = "checks.csv"; POSITIONS = "positions.json"; TRADES = "trades.csv"
```
Batch size: `scan.py` hard-codes `fresh[:5]` (5 mints/run) — not in config.
Note: `/workspace/trading-desk/risk-limits.md` lists a different top-10 kill (25%) and 5% daily-loss halt; `config.py` uses 30% and $50. The desk code uses `config.py`.

---

## 3. Pipeline (from code)
```
scan.py  — DexScreener latest token profiles (solana, unseen in checks.csv) → first 5
  └─ check.py <mint>
       1. limits  (book.guard, free): halted_daily_loss / already_open / max_open / max_entries_today / cooldown
       2. facts   (rugcheck.py, free), first failure wins, in order:
          no_report → already_rugged → mint_open → freeze_open → danger:<first danger risk>
          → risk_score>40 → lp_unlocked(<90%) → top10_heavy(>30%) → dev_holds(>5%) → insiders(>0)
          (fetch error → "rugcheck failed: ...")
       3. pool    (market.py, free), in order:
          no_pool → no_price → thin_pool(<$30k) → ticket_too_big($25/liq>1%) → too_fresh(<30 min)
          → too_old(>72 h) → nobody_can_sell(buys_1h≥20 & sells_1h==0)
          (fetch error → "dexscreener failed: ...")
       4. grok    (grok.py + prompts.JUDGE_PROMPT, PAID, x_search 3 days, 2 turns)
          BUY with confidence < 0.7 → SKIP "low confidence"
       → append row to checks.csv
       → if BUY and PAPER: book.open_position (paper fill at DexScreener price, $25)
watch.py — every open position: liquidity −40% → out; −35% → stop; +100% sell 50%; +200% sell 25%;
           after first take, −30% from peak → trail out; ≥6 h and < +20% → time_stop; pool gone → close at 0
report.py — today's counts by stage, buys, open, realized PnL, most common facts/pool kill
```
Cost: only step 4 calls xAI; steps 1–3 are free public APIs (`check.py` comments; ARTICLE.md "the bill").

---

## 4. `checks.csv` analysis
- Source: `/workspace/desk/checks.csv`
- Date range: **2026-11-02 21:40 → 2026-11-03 15:55 EAT**
- Rows: **65** (60 on Nov 2, 5 on Nov 3); unique mints: **55**
- Verdicts: **SKIP 62 · HOLD 3 · BUY 0**
- `trades.csv` / `positions.json`: absent → 0 paper fills, 0 PnL.

| Stage | SKIP | HOLD |
|---|---|---|
| facts (Rugcheck) | 39 | 0 |
| pool (DexScreener) | 21 | 3 |
| grok | 2 | 0 |
| limits | 0 | 0 |

### Kill reason frequency (SKIP rows)
| Reason | Count |
|---|---|
| insiders | 18 |
| thin_pool | 17 |
| danger:Low Liquidity | 5 |
| danger:Creator history of rugged tokens | 4 |
| danger:Large Amount of LP Unlocked | 3 |
| rugcheck failed: 400 Bad Request | 3 |
| lp_unlocked | 3 |
| top10_heavy | 2 |
| Grok judge SKIP (free text) | 2 |
| no_price | 2 |
| danger:Top 10 holders high ownership | 1 |
| no_pool | 1 |
| too_fresh | 1 |

### Grok kills (both confidence 0.93, both copycat/same-ticker + coordinated-posting reasons)
- 2026-11-02 22:15 — ANAKIN `8s4bNqEztH1JP7mkU747uMr7AckCQdiV47FDqYnDpump`
- 2026-11-02 22:46 — Slingoor `H4gHnZ3NCU7Z9XQwGX6YYJNyieGEW8pqwGRUcdSxpump`

### HOLD rows (data caveat)
3 rows at 2026-11-02 23:14 have verdict `HOLD`, reason "passed facts+pool; Grok deferred (paper week not started)" (豆助, Slingoor, ANAKIN). `check.py` only emits SKIP/BUY, so these were logged outside the normal `check.py` path. Two of those mints already had Grok SKIPs earlier the same evening.

### Mints checked more than once (scan dedupe skips mints already in checks.csv; repeats came from manual/other runs)
| Mint | Symbol | Times | Sequence |
|---|---|---|---|
| `9nutvj678qvbouYKqHkSJu3n5cQUEZw42wtPdjekpump` | horse | 2 | facts/SKIP:danger:Large Amount of LP Unlocked → facts/SKIP:danger:Large Amount of LP Unlocked |
| `6qnAerbLSGbhS3i6Xyh8AcsLTrutS1Rb7kuHsfwZpump` | ADCY | 2 | facts/SKIP:insiders → facts/SKIP:insiders |
| `7uwr9Zoz8WW9UyRVC22nmmAXRbPoFTUpVjsN8q7kids` | KIDS | 2 | pool/SKIP:thin_pool → pool/SKIP:thin_pool |
| `GnY6RSduqXgJ3nas2CKTDkNbrm2FXYExFxP7BXYEpump` | PAUL | 2 | facts/SKIP:insiders → facts/SKIP:insiders |
| `8s4bNqEztH1JP7mkU747uMr7AckCQdiV47FDqYnDpump` | ANAKIN | 2 | grok/SKIP:Grok judge SKIP (free text) → pool/HOLD:passed facts+pool; Grok deferred (paper  |
| `DBPTU2oKLDHXQjAEJ3rZi8bUGmt2uxUbipgg6xmXoMqr` | CAPY | 2 | pool/SKIP:no_pool → facts/SKIP:insiders |
| `5DnWmSL9t3YqK5MeYq8ozJpna46VcdePWzHvyN8avg2g` | CAPY | 2 | facts/SKIP:insiders → facts/SKIP:insiders |
| `6kKETm8xPeZ2z1DBYjXmxMTFAJudvGHJvRHu5Wt8uGtf` | COLLECTOR | 2 | facts/SKIP:top10_heavy → facts/SKIP:lp_unlocked |
| `Ei19qkvBM3amMyrveNLqKSPB1ESMEUQ6MrqDYwZVpump` | 豆助 | 2 | pool/SKIP:too_fresh → pool/HOLD:passed facts+pool; Grok deferred (paper  |
| `H4gHnZ3NCU7Z9XQwGX6YYJNyieGEW8pqwGRUcdSxpump` | Slingoor | 2 | grok/SKIP:Grok judge SKIP (free text) → pool/HOLD:passed facts+pool; Grok deferred (paper  |

### Full check log
| # | Time (EAT) | Mint | Symbol | Stage | Verdict | Conf | Reason |
|---|---|---|---|---|---|---|---|
| 1 | 2026-11-02 21:40 | `FMmmuDrCwe9ZzsVz7enjGqgrjBFp8a283nZ7jbTrpump` | Boba | pool | SKIP |  | thin_pool |
| 2 | 2026-11-02 21:40 | `5nubwW2MN5KESGnqqcuXBn8NpcPFF3VuFW8j3AWEpump` | YELU | pool | SKIP |  | thin_pool |
| 3 | 2026-11-02 21:40 | `9nutvj678qvbouYKqHkSJu3n5cQUEZw42wtPdjekpump` | horse | facts | SKIP |  | danger:Large Amount of LP Unlocked |
| 4 | 2026-11-02 21:40 | `CAoAQvqA8qQXrBFgVXwcasueKRdHJ8Cim7ixMTZSpump` | SHORT | facts | SKIP |  | top10_heavy |
| 5 | 2026-11-02 21:40 | `6Ng4MHjMbNAUySLKXQDsRpCrvKdCeTUb2cePRXCSpump` | Alouatta | pool | SKIP |  | thin_pool |
| 6 | 2026-11-02 21:55 | `ALTRgkReDWGmhisjTXwqHvbZRUcVoJicj54bQzVCpump` | PizzaGate | pool | SKIP |  | thin_pool |
| 7 | 2026-11-02 21:55 | `HcUWHmM5QgpPMDekGTKYWTGEFzAndG4t9ZUrYBm6pump` | OPTIC | pool | SKIP |  | thin_pool |
| 8 | 2026-11-02 21:55 | `5q3qz1ajtbS8aBvcCMU63sK3YKWs7c5kqtrkeZLBpump` | YELU | facts | SKIP |  | rugcheck failed: 400 Client Error: Bad Request for url: https://api.rugcheck.xyz/v1/tokens/5q3qz1ajtbS8aBvcCMU63sK3YKWs7c5kqtrkeZLBpump/report |
| 9 | 2026-11-02 21:55 | `9nutvj678qvbouYKqHkSJu3n5cQUEZw42wtPdjekpump` | horse | facts | SKIP |  | danger:Large Amount of LP Unlocked |
| 10 | 2026-11-02 21:55 | `DtspS4D5sX9rZqi5oeWnd8YFQsCsqkrwmuR4NvAYpump` | SELFBET | facts | SKIP |  | danger:Top 10 holders high ownership |
| 11 | 2026-11-02 21:56 | `AWRPD8jjvTHTnUXWMEfUCg8hKaev2rjjZ2QDCcfjpump` | Mamesuke | pool | SKIP |  | thin_pool |
| 12 | 2026-11-02 21:56 | `6qnAerbLSGbhS3i6Xyh8AcsLTrutS1Rb7kuHsfwZpump` | ADCY | facts | SKIP |  | insiders |
| 13 | 2026-11-02 21:56 | `9QXux7boKcnA5eoHvXTUhGCEQQRr6F1AKrmBd3gRpump` | Mutant | pool | SKIP |  | thin_pool |
| 14 | 2026-11-02 21:56 | `8SymmzsWdQBweqCK1p35MGNCwgw8FgPRdL4KPckdata` | DATALOOM | facts | SKIP |  | danger:Low Liquidity |
| 15 | 2026-11-02 21:56 | `Gdzu2f4SCNFGCgGLjDrpsQyqxvEzYddcW33UN54Qpump` | Uma | pool | SKIP |  | thin_pool |
| 16 | 2026-11-02 22:02 | `7uwr9Zoz8WW9UyRVC22nmmAXRbPoFTUpVjsN8q7kids` | KIDS | pool | SKIP |  | thin_pool |
| 17 | 2026-11-02 22:02 | `8nDq2s5pmGn7jGRkawHe2d4eYcr7G1DetbYTWovspump` | SCROOGE | pool | SKIP |  | thin_pool |
| 18 | 2026-11-02 22:02 | `GnY6RSduqXgJ3nas2CKTDkNbrm2FXYExFxP7BXYEpump` | PAUL | facts | SKIP |  | insiders |
| 19 | 2026-11-02 22:02 | `4MnM6aAuayLRhejDSuiaEm2QGyR4ye4Sxhdywt37pump` | SLINGOOR | facts | SKIP |  | danger:Low Liquidity |
| 20 | 2026-11-02 22:02 | `7LzPdsBxMoR9FrjgizvxNRvDtjGSP423quJ4M7Jqpump` | Slingoor | facts | SKIP |  | danger:Low Liquidity |
| 21 | 2026-11-02 22:09 | `xRtT8q7g7NsAnbTgvCtim8jtxKVVc5epoLoAYmqpump` | CAPYTISTAS | facts | SKIP |  | insiders |
| 22 | 2026-11-02 22:09 | `6qnAerbLSGbhS3i6Xyh8AcsLTrutS1Rb7kuHsfwZpump` | ADCY | facts | SKIP |  | insiders |
| 23 | 2026-11-02 22:09 | `7uwr9Zoz8WW9UyRVC22nmmAXRbPoFTUpVjsN8q7kids` | KIDS | pool | SKIP |  | thin_pool |
| 24 | 2026-11-02 22:09 | `8kuQg3WivDtL85VEdw2jEmSXjYt6EEeYBATJ4DtQpump` | RICO | facts | SKIP |  | danger:Creator history of rugged tokens |
| 25 | 2026-11-02 22:09 | `GnY6RSduqXgJ3nas2CKTDkNbrm2FXYExFxP7BXYEpump` | PAUL | facts | SKIP |  | insiders |
| 26 | 2026-11-02 22:15 | `8s4bNqEztH1JP7mkU747uMr7AckCQdiV47FDqYnDpump` | ANAKIN | grok | SKIP | 0.93 | Same ticker is already tied to a different Solana mint on X, so this is copycat risk by rule. This mint's posts are a same-hour wave of identical Moonshot/pump vote bait from unrelated accounts, not a dev or a real community. |
| 27 | 2026-11-02 22:15 | `ExxzYBTt3jwU5MUxuw2F4toYbTLdFwThSjyaCn6Xpump` | Anakin | facts | SKIP |  | insiders |
| 28 | 2026-11-02 22:15 | `BngAfLZxaWN2QvpFhRbUHydYGr8zA7YTSA178G8Epump` | PEACE | facts | SKIP |  | insiders |
| 29 | 2026-11-02 22:15 | `5BDmaYCBL9oznREDgx93Vop614p3SradkMJLfzFhzaob` | (none) | facts | SKIP |  | rugcheck failed: 400 Client Error: Bad Request for url: https://api.rugcheck.xyz/v1/tokens/5BDmaYCBL9oznREDgx93Vop614p3SradkMJLfzFhzaob/report |
| 30 | 2026-11-02 22:15 | `GoDSW31bTxfkoup9yA1qcGGx9RMXdTEWgApv3xzBmoA` | STEALTH | facts | SKIP |  | insiders |
| 31 | 2026-11-02 22:15 | `CvRJ8MrnB1AwjrgX25uyeLJiXNSugTo2ZHh8UXDTpump` | ANSEM | facts | SKIP |  | insiders |
| 32 | 2026-11-02 22:15 | `wMHBD2B8KbDagvXUEapginhtJdrH4QSvSezBM8Tpump` | ANTS | facts | SKIP |  | danger:Large Amount of LP Unlocked |
| 33 | 2026-11-02 22:15 | `3jAHcV6ZwmA3pnrR9MrWwNSbN5gDiM7rSM1RJradQ8xK` | CHAD | facts | SKIP |  | danger:Low Liquidity |
| 34 | 2026-11-02 22:15 | `GexThZHgaswpAQ7Fi8QrHFubjPimUNSYhJiAA7XZpump` | WASTED | facts | SKIP |  | insiders |
| 35 | 2026-11-02 22:15 | `8s11PkgQt4ZzdZ7oo84hK5t9HG1EvdgAjcg4W7Lpump` | BLOB | facts | SKIP |  | lp_unlocked |
| 36 | 2026-11-02 22:15 | `6QUHcqYuiPRHxhnYZoygewXtNQr9kUrhc9Tmwgtbpump` | (none) | facts | SKIP |  | rugcheck failed: 400 Client Error: Bad Request for url: https://api.rugcheck.xyz/v1/tokens/6QUHcqYuiPRHxhnYZoygewXtNQr9kUrhc9Tmwgtbpump/report |
| 37 | 2026-11-02 22:20 | `DBPTU2oKLDHXQjAEJ3rZi8bUGmt2uxUbipgg6xmXoMqr` | CAPY | pool | SKIP |  | no_pool |
| 38 | 2026-11-02 22:20 | `5DnWmSL9t3YqK5MeYq8ozJpna46VcdePWzHvyN8avg2g` | CAPY | facts | SKIP |  | insiders |
| 39 | 2026-11-02 22:20 | `GnmsWg3igP5by5EYMKS4tVwM5ZjzDMgaayQTNT65HoLd` | OLDPUMP | facts | SKIP |  | danger:Low Liquidity |
| 40 | 2026-11-02 22:20 | `3R6C9YD2Mmmm96H4UbpwTTyC4emnBxY3QGAgVwxepump` | Escobahh | pool | SKIP |  | thin_pool |
| 41 | 2026-11-02 22:20 | `wLjTQSsKmoy9pjE7ZcdtU1Vf5HKhKPU2piR3vXGpump` | HACKCAT | pool | SKIP |  | thin_pool |
| 42 | 2026-11-02 22:32 | `mUakXVwjZYyCDqkrrzE8g6XW9FqianLunmNTGgipump` | SAMANTHA | pool | SKIP |  | no_price |
| 43 | 2026-11-02 22:32 | `6kKETm8xPeZ2z1DBYjXmxMTFAJudvGHJvRHu5Wt8uGtf` | COLLECTOR | facts | SKIP |  | top10_heavy |
| 44 | 2026-11-02 22:32 | `92jz5dgWVfN5y1fmev5xu1D3fPmD4td6pzQ3muBpump` | PEPPER | facts | SKIP |  | insiders |
| 45 | 2026-11-02 22:46 | `GsNVxDCFAoynYr1K1gVUD9aJUhLzvfZBFECyCzQBGAME` | WOOL | pool | SKIP |  | thin_pool |
| 46 | 2026-11-02 22:46 | `H2F3dSkiLxyRekj1uzyUyyRpKLSrc7aDEyNrADbcpump` | SPDR | pool | SKIP |  | no_price |
| 47 | 2026-11-02 22:46 | `Ei19qkvBM3amMyrveNLqKSPB1ESMEUQ6MrqDYwZVpump` | 豆助 | pool | SKIP |  | too_fresh |
| 48 | 2026-11-02 22:46 | `3svjF5QE5UcYSuajZr4MD9voX5WCDmPB7WbxniBTpump` | Grindset | facts | SKIP |  | danger:Creator history of rugged tokens |
| 49 | 2026-11-02 22:46 | `H4gHnZ3NCU7Z9XQwGX6YYJNyieGEW8pqwGRUcdSxpump` | Slingoor | grok | SKIP | 0.93 | Hard checks are clean, but X is a same-minute caller farm with copy-paste entries and fake multi-x posts. A second contract is being pushed under the same ticker. |
| 50 | 2026-11-02 23:14 | `5DnWmSL9t3YqK5MeYq8ozJpna46VcdePWzHvyN8avg2g` | CAPY | facts | SKIP |  | insiders |
| 51 | 2026-11-02 23:14 | `DBPTU2oKLDHXQjAEJ3rZi8bUGmt2uxUbipgg6xmXoMqr` | CAPY | facts | SKIP |  | insiders |
| 52 | 2026-11-02 23:14 | `Ei19qkvBM3amMyrveNLqKSPB1ESMEUQ6MrqDYwZVpump` | 豆助 | pool | HOLD |  | passed facts+pool; Grok deferred (paper week not started) |
| 53 | 2026-11-02 23:14 | `H4gHnZ3NCU7Z9XQwGX6YYJNyieGEW8pqwGRUcdSxpump` | Slingoor | pool | HOLD |  | passed facts+pool; Grok deferred (paper week not started) |
| 54 | 2026-11-02 23:14 | `6kKETm8xPeZ2z1DBYjXmxMTFAJudvGHJvRHu5Wt8uGtf` | COLLECTOR | facts | SKIP |  | lp_unlocked |
| 55 | 2026-11-02 23:14 | `SCGBBnSwnekytGFHgyeHHxPMiN7xDxsWFGg9JgFSTNK` | MAMESUKE | facts | SKIP |  | lp_unlocked |
| 56 | 2026-11-02 23:14 | `8s4bNqEztH1JP7mkU747uMr7AckCQdiV47FDqYnDpump` | ANAKIN | pool | HOLD |  | passed facts+pool; Grok deferred (paper week not started) |
| 57 | 2026-11-02 23:14 | `B1FxS86N8hEBTgKMpt29yPB9VzPxXUgNY7AzdjGZpump` | SLM | pool | SKIP |  | thin_pool |
| 58 | 2026-11-02 23:15 | `4DV2FsyBjowCbFtbhFdv9u3EuUFDZK2ZEMFVodE3pump` | XMOON | facts | SKIP |  | danger:Creator history of rugged tokens |
| 59 | 2026-11-02 23:15 | `8rMKmGTdLqx6xNvjLMARQxRQMXtvE4jnDY8ZqN2wpump` | TRENCHER | facts | SKIP |  | insiders |
| 60 | 2026-11-02 23:15 | `HsprHxBRgiVaQdRf3TnKNuZZtaX9JUSPgMFdAkk6pump` | GATO | facts | SKIP |  | insiders |
| 61 | 2026-11-03 15:55 | `FSfyGqKCMWi3UjQarU5QycGnBfNphX144zoeHdzWM9ZM` | CI | facts | SKIP |  | danger:Creator history of rugged tokens |
| 62 | 2026-11-03 15:55 | `ESqXTLxmuYeU2MeUzZfdxFP81EXpTPR5sgWkzmAVpump` | zkSnark | facts | SKIP |  | insiders |
| 63 | 2026-11-03 15:55 | `4up8RwmTFU6qVaZaS4pWa8R8qH8DE13NvAF6rRo2pump` | SATMINE | pool | SKIP |  | thin_pool |
| 64 | 2026-11-03 15:55 | `4yxnt3xAdyBFFbzMWJy9sjGEoiBNkjwdSQZ8ZyULpump` | MOGMAS | pool | SKIP |  | thin_pool |
| 65 | 2026-11-03 15:55 | `Hxqh7Fxsz11pyqDRdEkBgP8vP44BPLPnQDrxzPYZpump` | PUMP | facts | SKIP |  | insiders |

---

## 5. Routine status (as known by RUG DESK, 2026-11-03 ~16:20 EAT)
| Routine | Schedule | Status |
|---|---|---|
| Desk watch | every 10 min, weekdays 08:00–22:50 EAT | **ON** (resumed by user 2026-11-03 ~15:18 EAT) |
| Desk scan | hourly, weekdays 09:00–18:00 EAT | **ON** (resumed ~15:18 EAT) |
| Desk evening report | weekdays ~20:00 EAT | **ON** (resumed ~15:18 EAT) |
| Paper hour scans | Mon Nov 2 evening one-off window | **PAUSED** |

History: all routines paused by user order 2026-11-03 ~01:08 EAT (also relayed by CHIEF); user resumed the three above on Nov 3. `READY.md` and `trading-desk/desk.md` still say "ALL PAUSED" — files not updated since. `ROSTER.md` mentions an "8:47 AM ask-to-resume"; RUG DESK reported no such routine on its seat.
Cost (per code): watch/report make no xAI calls; scan only costs when a mint survives facts+pool and reaches Grok (≤5 mints/run).

---

## 6. Paper session results
**Mon 2026-11-02 evening paper hour (21:40–22:46 EAT, plus 23:14–23:15 re-checks):** 60 rows, 0 BUY. Final scan 22:46: WOOL thin_pool, SPDR no_price, 豆助 too_fresh, Grindset danger:Creator history of rugged tokens, Slingoor Grok SKIP 0.93. 22:32 scan: SAMANTHA no_price, COLLECTOR top10_heavy, PEPPER insiders.
Note: chat summary called Slingoor (22:46) the "first Grok kill tonight", but `checks.csv` also shows a Grok SKIP for ANAKIN at 22:15.

**Tue 2026-11-03 15:55 EAT desk scan:** 5 SKIP, 0 BUY — CI danger:Creator history of rugged tokens; zkSnark insiders; SATMINE thin_pool; MOGMAS thin_pool; PUMP insiders.

Cumulative: 0 paper buys, 0 positions, $0 realized PnL.

---

## 7. Floor bots (`/workspace/trading-desk/ROSTER.md`, created 2026-11-02, engagement: research, no live sends)
| Seat | Role |
|---|---|
| CHIEF | Orchestrator — never trades |
| SCOUT | Alpha / search |
| RISK | Safety gate |
| WHALE | Smart money |
| SNIPER | Buy prep — human APPROVE only |
| RUG | Post-entry alerts — never closes |
| EXIT | Position manager — human APPROVE sells |
| SHILL | Sentiment — never confirms alone |

Rooms: Trading Floor (CHIEF, SCOUT, RISK, WHALE, SNIPER, RUG); Floor Extras (RUG DESK, CHIEF, EXIT, SHILL). All seats research/paper. Handoffs idle unless asked. EXIT and SHILL confirmed zero routines (Nov 3 ~01:xx EAT). Only SCOUT has produced files (`trading-desk/leads/`).

---

## 8. How to re-run (working_directory `/workspace/desk`)
```bash
cd /workspace/desk
python3 scan.py              # up to 5 fresh DexScreener-profile Solana mints → check.py each (may call Grok = paid)
python3 check.py <MINT>      # one mint → JSON verdict, row appended to checks.csv (Grok only if facts+pool pass)
python3 watch.py             # open paper positions; prints nothing when book is empty
python3 report.py            # today's evening report from checks.csv / trades.csv
```
PAPER=True means a BUY becomes a paper fill only. Do not edit `config.py`.

---

## 9. Missing sources / caveats
- `/workspace/desk/.env.example` — missing.
- `/workspace/desk/positions.json`, `/workspace/desk/trades.csv` — missing (never created; no fills).
- `/workspace/trading-desk/{briefs,incidents,journal,positions,proposals,research,watch}` — empty.
- `ARTICLE.md` copy has code blocks stripped; the code itself is the source of truth.
- `READY.md` / `trading-desk/desk.md` routine status is stale vs. §5.
- Thresholds differ between `config.py` (code) and `trading-desk/risk-limits.md` (floor doc).
- `rugcheck failed: 400` rows (3) = Rugcheck API rejected the mint; logged as facts-stage SKIP.
