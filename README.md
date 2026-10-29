# CDL Training Hub — Discord bot

A Python bot that creates a structured competitive Call of Duty study server and routes X/Reddit links into map-specific Discord forum threads **only after manual approval**.

## Features
- Non-destructive, repeatable `/setup preview` and `/setup apply` (existing channels are never moved/deleted)
- Text channels for fundamentals, S&D, Hardpoint, Hijack, practice and review
- Discord Forum libraries with topic tags for each mode
- Confirmed map allowlists in `maps.json` via `/map-add`
- `/submit` link intake, de-duplication, conservative classifier, `/pending`, `/approve`, `/reject`, `/find`
- Optional Reddit OAuth and X recent-search discovery via `/discover` or periodic checks (default disabled)
- SQLite persistence

## Install / invite bot
1. Open https://discord.com/developers/applications and create a new application/bot. Copy the bot token from **Bot**. **Never paste that token in a chat**.
2. In **Installation**, enable **Guild Install**, add scopes `bot` and `applications.commands`, and grant **Manage Channels**, **View Channels**, **Send Messages**, **Send Messages in Threads**, **Create Public Threads**, **Read Message History**, and **Manage Threads** if relevant. Prefer narrowly scoped permissions; no Administrator permission required.
3. Generate an install link under the app's Installation settings, open it, and choose your Discord server.
4. Enable Developer Mode in Discord → right-click your server → **Copy Server ID**.
5. Install Python 3.11+ on a computer/server that stays online.
6. Run:

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate
pip install -r requirements.txt
```

7. Copy `.env.example` to `.env`. Fill **DISCORD_TOKEN** and **DISCORD_GUILD_ID**. Start the bot with `python bot.py`.
8. In Discord, as someone with Manage Server permission, run `/setup action:preview` then `/setup action:apply`.
9. Add maps when officially verified: `/map-add mode:hardpoint name:MAP_NAME` (repeat per mode/map).
10. Submit a source: `/submit url:https://x.com/... title:...`; admins can then use `/pending` and `/approve clip_id:1 mode:hardpoint map_name:MAP_NAME topic:spawns lesson:...`.

**Important:** the bot does not automatically infer map assignments for ambiguous sources and does not publish unreviewed links. `/approve` requires manually selected mode, map, topic and lesson. That keeps the library reliable.

## Optional source discovery
- **Reddit:** register an approved API client and add `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, and your unique `REDDIT_USER_AGENT`. Reddit's API policies and approval conditions apply.
- **X:** provide `X_BEARER_TOKEN` with access to recent search endpoint. Access, price, rate limits, and availability are controlled by X.
- Run `/discover` manually first. Set `DISCOVERY_ENABLED=true` to poll hourly while the bot is running. Discovery only **queues** links; it never approves them.
- Automatic discovery searches are conservative defaults in `sources.py`. Extend queries as needed.
- If no API credentials are set, manual `/submit` remains fully functional.

## Safety / maintenance
- Back up `cdl_training.sqlite3` and `maps.json`.
- Keep `.env` secret; never commit it. Token leaks: regenerate in the Discord Developer Portal.
- Source posts can be deleted or edited; re-review important material periodically and honor platform data retention/deletion rules. This bot stores only a link and excerpt/title, not media downloads.
- Forum thread names are created lazily when clips are approved, not during initial setup.
- The bot is initially **not installed** on your server and will not run while your PC/server is off.
- To test: `pytest -q`.

## Future upgrades
A webhook endpoint or admin UI, X account allowlists, scheduled patch-aware reviews, interactive approval buttons, clip transcription and AI-assisted summaries. These are *not* included in this initial implementation.
