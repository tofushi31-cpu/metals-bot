# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# setup — строго python3.12: pandas-ta тянет numba, который не работает на 3.14
python3.12 -m venv venv && source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# run the bot
python3 bot.py

# tests
pytest
```

Test config is in `pytest.ini` (`pythonpath = .`, `asyncio_mode = auto`, `testpaths = tests`).

## Architecture

Telegram-бот с графиками металлов (золото GC=F, серебро SI=F, медь HG=F, алюминий ALI=F):

- `signals.py` — `METALS`, `fetch_prices` (yfinance, с ретраями, пустой ответ = ошибка), `compute_fib_zones` (уровни Фибоначчи по свингу 60 дней), `FIB_LABELS`
- `chart.py` — `render_chart(df, zones, name, path)`: свечи + уровни Фибоначчи + панель RSI → PNG (mplfinance). Данные принимает готовыми — сам ничего не скачивает
- `captions.py` — тексты подписей и алертов (отдельно от bot.py, чтобы тестировать без токена)
- `history.py` — SQLite `metals.db` (путь переопределяется env `METALS_DB`): дедупликация алертов (один на металл+уровень в день) и история для будущей статистики
- `bot.py` — aiogram, только для `ADMIN_IDS`; меню (строится динамически из `METALS`), ежедневный дайджест в `DIGEST_HOUR` по `DIGEST_TZ` (zoneinfo), алерт-цикл раз в `ALERT_INTERVAL_MIN` минут при входе цены в зону

Секреты и настройки — `.env` (`BOT_TOKEN`, `ADMIN_IDS`, `DIGEST_HOUR`, `DIGEST_TZ`, `ALERT_INTERVAL_MIN`).

Автозапуск на macOS: LaunchAgent `deploy/com.roger.metals-bot.plist` (KeepAlive).

## Constraints

- **Без платных API** — данные yfinance (бесплатно), индикаторы локально; никогда не подключать платный API без явного согласия.
- Без TradingView-данных: их ToS запрещает прямой сбор; в подписи бота даются лишь подсказки, как найти инструмент в терминале (`TERMINAL_SEARCH` в `bot.py`).
- Прошлая концепция «радар потребностей» заморожена и живёт в `../radar-idey/ПЛАН.md` — не восстанавливать её код здесь.
