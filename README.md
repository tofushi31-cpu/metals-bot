# Бот металлов — зоны Фибоначчи

Личный Telegram-бот: свечные графики золота, серебра, меди и алюминия с уровнями коррекции Фибоначчи и RSI(14). По кнопке или ежедневным дайджестом присылает PNG-график и текстовую сводку уровней с пометкой ближайшего и «в зоне» (цена ближе 1% к уровню).

Не финансовый совет — сырые уровни цены, решение принимает человек. Отвечает только админам (`ADMIN_IDS`).

```
yfinance (Yahoo, бесплатно)
        |
   signals.py ── fetch_prices + compute_fib_zones
        |
   chart.py ──── свечи + Фибоначчи + RSI → PNG (mplfinance)
        |
   bot.py ────── aiogram: меню, /start, дайджест в DIGEST_HOUR (DIGEST_TZ)
```

## Запуск

```bash
python3.12 -m venv venv && source venv/bin/activate   # именно 3.12: pandas-ta/numba не работают на 3.14
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env   # заполнить BOT_TOKEN, ADMIN_IDS
python3 bot.py
```

Тесты: `pytest`.

Автозапуск на macOS — LaunchAgent `com.roger.metals-bot.plist` (см. `deploy/`), поднимает бота после перезагрузки и падений. Лог — `~/Library/Logs/metals-bot.log` (в папку Desktop launchd писать не может из-за TCC-защиты macOS).

## Ограничения

- Без платных API: данные yfinance, индикаторы локально (pandas-ta), без TradingView (их ToS запрещает прямой сбор данных).
- История проекта: репозиторий начинался как «радар потребностей» (сбор болей из RSS/Telegram) — идея заморожена и вынесена в `../radar-idey/ПЛАН.md`.
