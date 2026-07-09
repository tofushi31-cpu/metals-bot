# Бот металлов — зоны Фибоначчи

Telegram-бот: свечные графики золота, серебра, меди, алюминия и нефти Brent с уровнями коррекции Фибоначчи и RSI(14). По кнопке или ежедневным дайджестом присылает PNG-график и текстовую сводку уровней с пометкой ближайшего и «в зоне» (цена ближе 1% к уровню).

Не финансовый совет — сырые уровни цены, решение принимает человек. Полный доступ — у админов (`ADMIN_IDS`) и подписчиков: оплата через Telegram Stars (`STARS_PRICE` за `SUB_DAYS` дней, платёжный провайдер не нужен).

![Пример графика](docs/chart-example.png)

Плюс алерты в реальном времени: раз в `ALERT_INTERVAL_MIN` минут (по умолчанию 30) бот проверяет цены и присылает сообщение, когда цена входит в зону Фибоначчи (ближе 1% к уровню). Один алерт на инструмент+уровень в день, история — в SQLite `metals.db`, и опционально каждая строка выгружается в Google-таблицу (`sheets.py`) — там ведётся аналитика, сколько раз уровни отработали.

```
yfinance (Yahoo, бесплатно)
        |
   signals.py ── fetch_prices (ретраи) + compute_fib_zones
        |
   chart.py ──── свечи + Фибоначчи + RSI → PNG (mplfinance)
   captions.py ─ текст подписей и алертов
        |
   bot.py ────── aiogram: меню, дайджест (DIGEST_HOUR, DIGEST_TZ),
        |         алерт-цикл (ALERT_INTERVAL_MIN)
   history.py ── SQLite metals.db: дедупликация и история алертов
```

## Запуск

```bash
python3.12 -m venv venv && source venv/bin/activate   # именно 3.12: pandas-ta/numba не работают на 3.14
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env   # заполнить BOT_TOKEN, ADMIN_IDS
python3 bot.py
```

Тесты: `pytest`.

Docker (для сервера): `docker compose up -d --build` — рестарт автоматический, база алертов в `./data/`.

Автозапуск на macOS — LaunchAgent `com.roger.metals-bot.plist` (см. `deploy/`), поднимает бота после перезагрузки и падений. Лог — `~/Library/Logs/metals-bot.log` (в папку Desktop launchd писать не может из-за TCC-защиты macOS).

## Ограничения

- Без платных API: данные yfinance, индикаторы локально (pandas-ta), без TradingView (их ToS запрещает прямой сбор данных).
- История проекта: репозиторий начинался как «радар потребностей» (сбор болей из RSS/Telegram) — идея заморожена и вынесена в `../radar-idey/ПЛАН.md`.
