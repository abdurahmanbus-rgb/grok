# RUG DESK engineering report

Date of this run: 2026-11-03. Paper only. No live order was sent, no wallet was created, and no paper position was opened.

`config.py` was not edited. SHA-256 before and after this work:

```
57e40ced8326d38951f6e5b2584fb508bf8ea237a6a29214b6772c59de39b2d8  desk/config.py
```

`PAPER = True`. The non-paper branch in `check.py` now refuses instead of printing a buy instruction: verdict becomes `SKIP` / `live_trading_disabled`, and `book.open_position` is not called. `book.py add` exits if `PAPER` is off. No module imports a signer (`solders`, `Keypair`, `send_transaction`, `sign_transaction` are absent). A test locks the hash above.

The historical verdict log was not appended to. Its snapshot is `desk/tests/fixtures/checks_baseline.csv` (same bytes as `desk/checks.csv` at the end of this change: `db6968730c29b58f785d3cb6a32f43334aaf66c07e20d5685763265c45d85976`). There is no `positions.json` and no `trades.csv`.

## 1. What was audited

The desk is ten small modules plus `checks.csv` (65 data rows, 2026-11-02 21:40 through 2026-11-03 15:55, box-local timestamps).

| Piece | What it did |
|---|---|
| `scan.py` | One GET, `token-profiles/latest/v1`. Solana mints not already in `checks.csv`. First **5** passed to `check.py`. |
| `check.py` | `book.guard` → RugCheck `fact_kill` → DexScreener `market_kill` → Grok. First failure wins. `PAPER` opens a local fill. |
| `rugcheck.py` | `GET /v1/tokens/{mint}/report`. Ordered kills from `no_report` through `insiders`. |
| `market.py` | Deepest pair. Kills: `no_pool`, `no_price`, `thin_pool`, `ticket_too_big`, `too_fresh`, `too_old`, `nobody_can_sell`. |
| `grok.py` / `prompts.py` | One xAI call, X search, JSON object. Confidence below 0.70 forces SKIP. |
| `book.py` | Local positions and the free limit checks. |
| `watch.py` | Exits for open positions only. |
| `report.py` | Today's counts from the two CSVs. |
| `config.py` | Every risk number. Left byte-for-byte. |

SCOUT material is in `leads/`: four sweep markdown files, two FOMO JSON files, and `reported_mints.txt` (32 mints). The JSON leaderboard is wallets. The overlap file is mints. The sweeps put the mint in column one and a pair address, when present, only inside a URL.

`PAPER_OPS_PACK.md` matches that code and that log: 65 rows, 62 SKIP, 3 HOLD, **0 BUY**, no positions. The three HOLD rows are not produced by `check.py`; they were written beside it ("Grok deferred"). Two of those mints already had a Grok SKIP earlier the same night.

## 2. Why so few opportunities

The "5 profiles per run" hypothesis is real, and it is not the whole story.

**Discovery was a single list with a hard cap of 5.** `scan.py` ignored boosts, community takeovers, profile updates, pool lists, and the SCOUT files. Of the 32 mints in `reported_mints.txt`, **16 were never passed to `check.py`.** Those 16 are still in the lead files. The desk was not starved of names it had already been handed; it never read them.

**The names that were checked died at the hard gates.** Recomputed from the baseline log by `funnel.split_row` (this is the same file the ops pack tabulated):

| Bucket | Rows | Share of 65 |
|---|---|---|
| Security kill (facts or pool) | 57 | 87.7% |
| RugCheck fetch error (HTTP 400), previously mixed into the facts stage | 3 | 4.6% |
| Grok SKIP | 2 | 3.1% |
| HOLD (manual, not `check.py`) | 3 | 4.6% |
| BUY | 0 | 0% |

Security reasons, fetch errors removed: insiders 18, thin_pool 17, danger:Low Liquidity 5, danger:Creator history of rugged tokens 4, danger:Large Amount of LP Unlocked 3, lp_unlocked 3, top10_heavy 2, no_price 2, danger:Top 10 holders high ownership 1, no_pool 1, too_fresh 1.

Only 2 of 65 rows reached Grok. Both were SKIP at confidence 0.93 (copycat / coordinated posts). The filter did not fail open. Widening discovery increases how many tokens get examined. It does not raise the pass rate, and this change does not claim a BUY.

With the frozen constants, `ticket_too_big` cannot fire on its own: a pool under $2,500 fails `thin_pool` ($30k) first, and $25 / $30,000 is 0.083%, under the 1% share. The comparison is still there and is tested with an in-memory ticket so the operator is not weakened. It was not reordered.

## 3. Acceptance

### 1. Paper only

`PAPER` stays True. A BUY under paper calls `book.open_position` once and writes a local JSON position. The same mint a second time hits `already_checked` before any network call and does not open again. `open_position` itself returns False if the mint is already in the book. The live branch does not open anything. Tests: `test_paper_buy_is_idempotent_and_does_not_duplicate`, `test_inconclusive_grok_and_live_path_do_not_open`, `test_config_file_is_bit_identical`.

### 2. Risk thresholds unchanged

`fact_kill` and `market_kill` use the same comparisons, in the same order, against `config.FACTS` and `MIN_CONFIDENCE`. Boundary tests: score 40 passes and 40.01 fails; LP 90 passes and 89.99 or None fails; top 10 at 30 passes and 30.01 or None fails; dev at 5 passes and 5.01 or None fails; insiders 0 passes and 1 fails; liquidity $30,000 passes and $29,999 fails; age 30 minutes and 72 hours pass, 29 minutes, missing age, and 72 hours + 1 minute fail. A missing RugCheck score is `no_report` even if another field looks fatal. None of those become BUY.

### 3. Multi-source discovery, verified before use

Official DexScreener reference: [https://docs.dexscreener.com/api/reference](https://docs.dexscreener.com/api/reference). List endpoints below are documented at 60 requests per minute. Each was GET once while building this, and again inside the smoke collect. All returned HTTP 200 and a JSON list of objects with `chainId` and `tokenAddress`.

| Source id | Endpoint | Used |
|---|---|---|
| `dexscreener_profiles` | `GET /token-profiles/latest/v1` | yes, the old feed |
| `dexscreener_profile_updates` | `GET /token-profiles/recent-updates/v1` | yes, same schema, verified 200 |
| `dexscreener_boosts_latest` | `GET /token-boosts/latest/v1` | yes. REST body is a list (the websocket doc shows a `{limit, data}` wrapper; the parser accepts both) |
| `dexscreener_boosts_top` | `GET /token-boosts/top/v1` | yes, same |
| `dexscreener_cto` | `GET /community-takeovers/latest/v1` | yes |

Not adopted, on purpose:

- `GET /ads/latest/v1` is a paid-ad list, not a pair or trending feed. Skipped.
- `GET /metas/trending/v1` returns narrative slugs, not mints. Resolving each slug is another call against the 60/minute budget. Skipped.
- `GET /latest/dex/search` is a fuzzy query, not a discovery feed. Skipped.
- Pump.fun `https://frontend-api-v3.pump.fun/coins/latest` and `https://frontend-api.pump.fun/coins?offset=0&limit=1` both returned **HTTP 403** on 2026-11-03. Not integrated. That matches the ops pack note that the pump feed was 403.

GeckoTerminal public API, swagger `https://api.geckoterminal.com/docs/v2/swagger.json` (base `https://api.geckoterminal.com/api/v2`, version header `Accept: application/json;version=20230203`). The swagger states the public API is about 10 calls per minute and that responses are cached for one minute. Page 1 only.

| Source id | Endpoint |
|---|---|
| `geckoterminal_new_pools` | `GET /networks/solana/new_pools?include=base_token&page=1` |
| `geckoterminal_trending_pools` | `GET /networks/solana/trending_pools?include=base_token&page=1&duration=1h` |

The mint is `included[].attributes.address` for the pool's `base_token`. Wrapped SOL, USDC, and USDT are dropped at collection so a SOL/USDC pool does not consume a batch slot. That denylist is not a risk bypass: `check.py` still runs every gate if one of those mints is passed in directly.

A profile, boost, takeover, or trending flag is stored as a source name. It is not a verdict. Tests assert the parsed record has no `verdict`, and that a mint arriving from a boost still dies on `insiders` with zero calls to Grok.

### 4. One queue, full mint, source, first-seen

Identity is the full mint string, case-sensitive, 32–44 base58 characters. Records live in `discovery.json` (gitignored runtime file). The earliest `first_seen` wins; later collects union `sources` and keep the old timestamp. `first_source` is the feed that saw it first, not a rank. The per-run queue is round-robin across first sources so one list cannot fill all 20 slots. Provider order inside a list is not treated as quality.

Operational cap, in `discover.py` / `scan.py`, **not** in `config.py`: `MAX_CHECKS_PER_RUN = 20`. `scan.py --limit` can only lower it. Pause between list calls is 0.35s. Pause between mints that actually enter `check.py` is 1.25s. One list call per source per run (7 calls: 5 DexScreener at a 60/minute budget, 2 GeckoTerminal at a ~10/minute budget).

### 5. SCOUT is discovery, not clearance

`scout.py` reads `leads/*.md`, `*.json`, and other `*.txt`. Markdown uses the first field only, so a DexScreener pair URL later on the line is not a second mint. JSON uses the key `mint` only. The key `wallet` is ignored. `reported_mints.txt` is the identity ledger: a mint listed there and also in a sweep is one candidate, with the sweep note kept on the record.

It is not a veto and not a pass. A mint already present in `checks.csv` is not queued again. A mint in `reported_mints.txt` that the desk has never judged **is** queued, once, into the normal `check.py` path. Notes are stored on the discovery record and are not passed to `fact_kill` or to the Grok payload (`{"token", "pool"}` only). A note that says the token is safe does not clear `insiders`.

Against the attached `leads/` directory the loader returns 38 mints from 6 files, drops 4 non-mint lines (the "FOMO board unchanged" lines), and does not return wallet `8CQsNv856jzmDKKGue5GcrX3zrMjhfbwfMNZTjm5b9ZF` or the pair address embedded in the 22:06Z URLs. `unchecked_in_reported` on the live collect is 16, the same 16 the audit diff found.

### 6. Fetch errors are classified, retried only when the retry can matter, and never treated as safe

`errors.py` kinds: `rejection` (HTTP 4xx other than 404/429, including 400 and 422), `missing` (404), `invalid` (mint failed the local base58 check; no HTTP), `rate_limit` (429), `timeout`, `5xx`, `malformed` (200 that is not a JSON object or list, or a RugCheck body that is not an object), `network`.

Retries: up to 3 attempts, and only for `rate_limit`, `timeout`, `5xx`, `network`. `Retry-After` is honored up to 2 seconds. Rejection, missing, invalid, and malformed are not retried. Grok is never retried (one paid call). After the attempts are spent, `check.py` logs `SKIP` with `error:<provider>:<kind>:<detail>`. An empty DexScreener pair list stays `no_pool`, which is a market outcome, not a fetch error.

### 7. Error stats are not security kills, and the old report still prints

`checks.csv` columns are unchanged: `time,mint,symbol,stage,verdict,confidence,reason`. Old rows that say `rugcheck failed: 400 ...` stay as they are. `funnel.py` classifies those, and the new `error:` reasons, as `fetch_error`. They are excluded from `security_kills`.

`report.py` still prints the original evening lines first (`EVENING REPORT`, `checked`, `killed by rug filter | by pool | by Grok | by limits`, `bought`, `realized pnl`, optional best/worst and most common kill). The funnel is appended after a blank line. A test builds the killed-by line from the baseline CSV independently and matches the printed line for 2026-11-02.

### 8. Funnel, daily and cumulative, by stage and by source

`python3 funnel.py` and the bottom of `python3 report.py`. Counts and percents of check rows, plus percent of discovered. Check rows attribute to `first_source`. Discovered counts a mint once per source it was actually seen on, so those columns can sum to more than the unique total. Mints with no discovery record are `unattributed` (the entire baseline, until a collect is stored beside the log).

Baseline output, run in `/workspace/desk` on 2026-11-03 against the untouched log:

```
FUNNEL daily 2026-11-03
discovered: 5
check_rows: 5 (100.0% of discovered) | unique_mints: 5
security_kills: 5 (100.0% of rows, 100.0% of discovered)
fetch_errors: 0 (0.0% of rows) [kept out of the security tally]
grok_skips: 0 (0.0% of rows)
buys: 0 (0.0% of rows)
holds: 0 | limits: 0 | safety_lock: 0 | other: 0
  unattributed: discovered 5 | rows 5 | security 5 | fetch_error 0 | grok 0 | buy 0 | hold 0

FUNNEL cumulative
discovered: 55
check_rows: 65 (118.2% of discovered) | unique_mints: 55
security_kills: 57 (87.7% of rows, 103.6% of discovered)
fetch_errors: 3 (4.6% of rows) [kept out of the security tally]
grok_skips: 2 (3.1% of rows)
buys: 0 (0.0% of rows)
holds: 3 | limits: 0 | safety_lock: 0 | other: 0
fetch_error_kinds: rejection 3
  unattributed: discovered 55 | rows 65 | security 57 | fetch_error 3 | grok 2 | buy 0 | hold 3
```

118.2% is 65 rows over 55 unique mints (the repeat checks in the ops pack). It is not a pass rate.

The evening header for the same day, same command:

```
EVENING REPORT 2026-11-03 (PAPER)
checked: 5
killed by rug filter: 3 | by pool: 2 | by Grok: 0 | by limits: 0
bought: 0 | open now: 0
realized pnl today: $+0.00
most common kill: insiders (2x)
```

### 9. Shadow monitor cannot reopen a reject

`shadow.py` reads the last verdict per mint and ignores BUY. It samples at most 15 due mints per invocation, then waits `SHADOW_INTERVAL_SEC` (3600) before sampling that mint again. Output is `shadow.json`. Statuses include `watching`, `missing` (no pool on the first look), and `delisted` (a pool that later disappears). A price drop of at least 35% from the first good sample, or a liquidity drop of at least 40%, is recorded as a research flag using the existing `EXIT` numbers as labels. The module does not import `book`, does not call `open_position`, does not rewrite `checks.csv`, and does not delete a mint that has gone missing. Tests cover the interval, the delist, the kept-missing record, the drop flags, and an untouched `positions.json`.

This is not a new routine. Schedules were not created or edited. Run it by hand with `python3 shadow.py` if you want the research log.

### 10. Grok stays downstream

`ask` runs only after `fact_kill` and `market_kill` both return None. No key: no HTTP, reason `error:grok:missing:no_key`. One POST, no retry. The judge must be a JSON object with `verdict`, `confidence`, `why`, `x_read`, and `main_risk`. Null, blank, non-numeric confidence, or a verdict other than BUY/SKIP becomes SKIP (`inconclusive`). BUY below 0.70 becomes SKIP (`low confidence`). The prompt now also says a boost, a trending rank, and a SCOUT note are not evidence. This environment has no `XAI_API_KEY`. The smoke collect did not call xAI. Tests stub the HTTP client and count calls.

### 11. One bad mint, no double fill, no overlapping scan

`scan.run` catches an exception per mint, logs `error:scan:isolated:<Type>`, and continues. The cap test asks for 1000 and gets 20. `scan.lock` holds the current pid; a second `scan.py` prints `scan already running; this run does nothing` and does not collect. A dead pid does not stick. A mint already in `checks.csv` is not checked again and is not logged again.

## 4. Before / after

Security outcomes were **not** re-run against live RugCheck or DexScreener in this change, so there is no new kill row and no invented pass rate. The after column is a discovery collect at `2026-11-03T13:42:58Z` (`python3` calling `discover.collect`, checks path = the real log, leads path = `leads/`, discovery file under `/tmp`, sleep between list calls). `source_errors` was `[]`. `check.py` was not invoked. Grok was not invoked.

| | Before | After this collect |
|---|---|---|
| Feeds in one run | 1 (latest profiles) | 8 (5 DexScreener lists, 2 GeckoTerminal lists, SCOUT) |
| Cap per run | 5 | 20, round-robin, cannot be raised from the CLI |
| Raw hits / unique mints | not recorded; the code kept 5 | 182 raw parsed hits, **134 unique** |
| Membership | — | scout 38, profiles 23, profile updates 23, boosts latest 25, boosts top 25, cto 7, new pools 19, trending pools 20 |
| Already in `checks.csv` | 55 unique judged | 23 of the 134 |
| Reported by SCOUT, never judged | 16, not queued | 16, queued by the normal path (3 of them fell inside this run's 20-slot round-robin; the rest wait for later runs) |
| Queue | 5 | 20. First sources this run: scout 3, profiles 3, profile updates 3, boosts latest 3, cto 3, new pools 3, trending 2. Boosts-top had no *first* source in the top 20 because those mints were already attributed to an earlier feed; the 25 memberships are in the candidate set |
| Check rows added | — | **0** |
| BUY | 0 | 0 |
| Paper positions / realized PnL | none / $0 | none / $0 |

The next real `python3 scan.py` will send up to 20 of that queue through RugCheck, then DexScreener only if the rug filter passes, then Grok only if both pass and a key exists. Expect the historical kill mix (insiders, thin pools, danger flags) to keep dominating. That is the filter working.

## 5. Tests

```
cd desk && python3 -m pytest tests -v
```

Final run in this environment (no network inside the suite; the live collect above was separate):

```
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.2.0, pluggy-1.7.0
collected 31 items

tests/test_discover.py::test_make_mint_unique PASSED
tests/test_discover.py::test_list_parsers_drop_other_chains_invalid_and_majors PASSED
tests/test_discover.py::test_round_robin_does_not_let_one_feed_fill_the_batch PASSED
tests/test_discover.py::test_collect_dedupes_records_provenance_and_survives_one_dead_source PASSED
tests/test_discover.py::test_checks_and_reported_dedupe_without_treating_reported_as_clearance PASSED
tests/test_discover.py::test_real_scout_leads_keep_mints_and_drop_wallets_and_pair_urls PASSED
tests/test_errors.py::test_status_classes PASSED
tests/test_errors.py::test_invalid_mint_never_calls_the_network PASSED
tests/test_errors.py::test_rejection_missing_and_malformed_are_not_retried PASSED
tests/test_errors.py::test_transient_retries_then_succeeds_or_stays_an_error PASSED
tests/test_errors.py::test_empty_pool_is_no_pool_not_a_pass_or_a_fetch_error PASSED
tests/test_errors.py::test_rugcheck_non_object_is_malformed PASSED
tests/test_gates.py::test_thresholds_match_the_frozen_config PASSED
tests/test_gates.py::test_fact_kill_boundaries_and_missing_fields PASSED
tests/test_gates.py::test_market_kill_boundaries PASSED
tests/test_gates.py::test_hard_gate_blocks_grok_and_a_boost_is_not_a_pass PASSED
tests/test_gates.py::test_pool_and_rugcheck_failures_are_skip_and_not_security PASSED
tests/test_gates.py::test_grok_schema_and_confidence_never_promote_a_weak_answer PASSED
tests/test_paper.py::test_paper_buy_is_idempotent_and_does_not_duplicate PASSED
tests/test_paper.py::test_low_confidence_and_missing_key_do_not_buy PASSED
tests/test_paper.py::test_inconclusive_grok_and_live_path_do_not_open PASSED
tests/test_paper.py::test_grok_is_not_retried PASSED
tests/test_paper.py::test_one_bad_mint_does_not_kill_the_run_and_the_cap_holds PASSED
tests/test_paper.py::test_scan_lock_refuses_an_overlapping_run PASSED
tests/test_paper.py::test_watch_exits_an_open_paper_position_and_ignores_rejects PASSED
tests/test_paper.py::test_config_file_is_bit_identical PASSED
tests/test_shadow_report.py::test_shadow_records_drops_delist_and_never_reopens PASSED
tests/test_shadow_report.py::test_shadow_keeps_a_token_that_was_missing_from_the_first_look PASSED
tests/test_shadow_report.py::test_shadow_flags_price_and_liquidity_drops_without_a_position PASSED
tests/test_shadow_report.py::test_fetch_errors_stay_out_of_the_security_tally PASSED
tests/test_shadow_report.py::test_historical_funnel_and_legacy_evening_report PASSED

============================== 31 passed in 0.11s ==============================
```

That is the run after the baseline fixture was split out from the live log. No test calls RugCheck, DexScreener, GeckoTerminal, or xAI.

## 6. Files

Added: `desk/errors.py`, `desk/mints.py`, `desk/scout.py`, `desk/discover.py`, `desk/funnel.py`, `desk/shadow.py`, `desk/tests/` (including `fixtures/checks_baseline.csv`), `desk/requirements.txt`, `desk/.env.example`, `desk/.gitignore`, `ENGINEERING_REPORT.md`, root `.gitignore`.

Edited, behavior only where noted: `desk/scan.py` (multi-source queue, cap 20, per-mint isolation, lock), `desk/check.py` (classified errors, idempotent log, paper-only fill), `desk/rugcheck.py` and `desk/market.py` (fetch wrapper; kill functions unchanged), `desk/grok.py` (schema check, no retry), `desk/prompts.py` (boost / trend / SCOUT note are not evidence), `desk/book.py` (second open is a no-op; CLI refuses when PAPER is off), `desk/report.py` (same evening lines, funnel after), `desk/watch.py` (the non-paper wording no longer says to sell from a wallet; paper exits unchanged).

Untouched: `desk/config.py`, `desk/checks.csv` bytes, `desk/ARTICLE.md`, `desk/READY.md`, `desk/PAPER_OPS_PACK.md`, `PAPER_OPS_PACK.md`, `leads/`.

Routines: still `python3 scan.py`, `python3 watch.py`, `python3 report.py`. Nothing in this repo starts, stops, or reschedules them. `READY.md` still records the earlier pause note; it was left as written.

## 7. Paper confirmation

This change set created no position, no trade, and no BUY. Discovery smoke wrote a JSON file under `/tmp` only. `XAI_API_KEY` was unset, and the collect path does not import `grok.py`. Live trading is refused in code even if `PAPER` were flipped later; flipping it would require editing `config.py`, which this work does not do.
