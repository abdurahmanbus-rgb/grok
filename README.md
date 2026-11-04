# grok

abdurahman’s RUG DESK: a paper-first Solana memecoin desk.

The code in `desk/` is PAPER only (`PAPER = True` in `desk/config.py`). Every mint goes through `desk/check.py`. The desk never buys, sells, signs, or moves live funds.

Copy `desk/.env.example` to a local `desk/.env` if you want the optional Grok judge. Do not commit `.env` or any API key.
