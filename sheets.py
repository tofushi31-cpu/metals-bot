"""Выгрузка алертов в Google-таблицу — вся аналитика отработки уровней ведётся там.

Опционально: работает только если в .env заданы GSHEET_CREDS (путь к JSON
сервисного аккаунта Google) и GSHEET_ID (id таблицы из её URL). Без них бот
просто пишет алерты в SQLite и пропускает выгрузку.

Настройка (один раз):
1. console.cloud.google.com → создать проект → включить Google Sheets API
2. Создать сервисный аккаунт → скачать JSON-ключ
3. Создать таблицу и дать доступ "Редактор" на email сервисного аккаунта
4. В .env: GSHEET_CREDS=/путь/к/ключу.json, GSHEET_ID=<id из URL таблицы>
"""

import logging
import os
from datetime import datetime

log = logging.getLogger(__name__)

GSHEET_CREDS = os.getenv("GSHEET_CREDS")
GSHEET_ID = os.getenv("GSHEET_ID")

HEADER = ["Дата и время", "Инструмент", "Уровень Фибоначчи", "Цена уровня", "Цена входа в зону", "Отработал (вручную)"]

_worksheet = None


def _get_worksheet():
    global _worksheet
    if _worksheet is None:
        import gspread

        client = gspread.service_account(filename=GSHEET_CREDS)
        sheet = client.open_by_key(GSHEET_ID).sheet1
        if not sheet.row_values(1):
            sheet.append_row(HEADER)
        _worksheet = sheet
    return _worksheet


def enabled() -> bool:
    return bool(GSHEET_CREDS and GSHEET_ID)


def export_alert(metal: str, fib_label: str, level: float, price: float):
    """Добавляет строку алерта в таблицу. Ошибки сети/доступа не роняют бота."""
    if not enabled():
        return
    try:
        _get_worksheet().append_row(
            [datetime.now().isoformat(timespec="seconds"), metal, fib_label, level, price, ""]
        )
    except Exception:
        log.exception("Не удалось выгрузить алерт в Google-таблицу")
