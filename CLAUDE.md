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

Telegram-бот с графиками сырьевых инструментов (золото GC=F, серебро SI=F, медь HG=F, алюминий ALI=F, нефть Brent BZ=F; словарь исторически называется `METALS`):

- `signals.py` — `METALS`, `fetch_prices` (yfinance, с ретраями, пустой ответ = ошибка; кэш в памяти на `CACHE_TTL_MINUTES` минут по инструменту), `compute_fib_zones` (уровни Фибоначчи по свингу 60 дней), `compute_indicators` (RSI/ATR для контекста алерта), `close_price_after` (цена через N дней — для дозаписи результатов), `ALGO_VERSION`, `FIB_LABELS`
- `chart.py` — `render_chart(df, zones, name, path)`: свечи + уровни Фибоначчи + панель RSI → PNG (mplfinance). Данные принимает готовыми — сам ничего не скачивает
- `captions.py` — тексты подписей и алертов (отдельно от bot.py, чтобы тестировать без токена)
- `history.py` — SQLite `metals.db` (путь переопределяется env `METALS_DB`): дедупликация алертов (один на инструмент+уровень в день), история алертов с контекстом (RSI, ATR, algo_version) и результатами через 1/3/7 дней (`alerts_missing_outcomes`/`record_outcome`, дозаписывает `outcome_backfill_loop` в bot.py), `level_stats` для `/stats`, подписчики (user_id, expires_at), подарочные коды (`create_gift`/`redeem_gift`, одноразовые, админская команда `/gift [дней]` выдаёт ссылку t.me/...?start=gift_<код>); новые колонки добавляются к старым базам автоматически в `_conn`
- `sheets.py` — опциональная выгрузка алертов в Google-таблицу (gspread + сервисный аккаунт; выключено, пока не заданы `GSHEET_CREDS`/`GSHEET_ID`)
- `bot.py` — aiogram; доступ у `ADMIN_IDS` и активных подписчиков (оплата Telegram Stars, currency XTR, без платёжного провайдера); меню (строится динамически из `METALS`), ежедневный дайджест в `DIGEST_HOUR` по `DIGEST_TZ` (zoneinfo), алерт-цикл раз в `ALERT_INTERVAL_MIN` минут при входе цены в зону

Секреты и настройки — `.env` (`BOT_TOKEN`, `ADMIN_IDS`, `DIGEST_HOUR`, `DIGEST_TZ`, `ALERT_INTERVAL_MIN`, `CACHE_TTL_MINUTES`, `STARS_PRICE`, `SUB_DAYS`, `GSHEET_CREDS`, `GSHEET_ID`).

Автозапуск на macOS: LaunchAgent `deploy/com.roger.metals-bot.plist` (KeepAlive).

## Constraints

- **Без платных API** — данные yfinance (бесплатно), индикаторы локально; никогда не подключать платный API без явного согласия.
- Без TradingView-данных: их ToS запрещает прямой сбор; в подписи бота даются лишь подсказки, как найти инструмент в терминале (`TERMINAL_SEARCH` в `bot.py`).
- Прошлая концепция «радар потребностей» заморожена и живёт в `../radar-idey/ПЛАН.md` — не восстанавливать её код здесь.
