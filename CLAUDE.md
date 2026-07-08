# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# setup
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# run the bot
python3 bot.py

# tests
pytest
```

Test config is in `pytest.ini` (`pythonpath = .`, `asyncio_mode = auto`, `testpaths = tests`).

## Architecture

Flat module layout, mirrors the sibling `turist-bot` project:

- `config.py` — `RSS_FEEDS` / `TELEGRAM_CHANNELS` lists, must be filled in before collectors do anything
- `db.py` — SQLite (`radar.db`), single `items` table (source, text, url, published_at)
- `collector_rss.py` / `collector_telegram.py` — pull raw posts into `items`. Not implemented yet — deliberately, no point writing parsing logic against feeds/channels that aren't chosen yet
- `analysis.py` — Phase 1 (no paid LLM): TF-IDF keyword extraction + regex pain-point markers ("не хватает", "нужен сервис для", ...) + week-over-week frequency. Optional Phase 2: local LLM via Ollama for actual summarization, once Phase 1 pipeline is proven on real data
- `bot.py` — aiogram entry point, sends the digest

Full plan and time estimates: `tmp/plans/radar-potrebnostey.md` in the Teach repo, mirrored in the Obsidian vault (`Проекты/Радар потребностей (портфолио 2)/План.md`).

**No paid Claude/Anthropic API** — same constraint as `turist-bot`'s content generation. Keep `analysis.py` free/local (regex + TF-IDF, or a local Ollama model), never call a paid API without explicit sign-off.
