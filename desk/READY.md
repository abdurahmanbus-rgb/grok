# RUG DESK — ready for paper week

Status as of 2026-11-02 (Africa/Mogadishu):
- PAPER=True in config.py (do not flip without the user)
- XAI_API_KEY in .env (chmod 600), proven once
- Free APIs OK: Rugcheck + DexScreener
- Book empty: 0 positions, 0 trades, 0 checks
- Routines paused until paper week starts: desk-watch, desk-scan, desk-evening-report
- Use `python3` on this computer (symlink also at ~/.local/bin/python)

Tomorrow with the user:
1. Confirm Auto-review Ask-first rules (wallet / config.py)
2. Resume the three routines
3. First paper run: either hand a CA to `python3 check.py <mint>` or resume scan


## Schedule freeze
User order 2026-11-03 ~01:08 Africa/Mogadishu: ALL bot scheduled tasks / routines paused until further notice.
