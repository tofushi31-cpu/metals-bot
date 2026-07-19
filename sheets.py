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

HEADER = ["Дата и время", "Инструмент", "Уровень Фибоначчи", "Цена уровня", "Цена входа в зону", "Отработал (вручную)"]
SUBS_SHEET = "Подписчики"
SUBS_HEADER = ["Дата и время", "Событие", "Пользователь", "Дней", "Действует до"]

_worksheet = None
_subs_worksheet = None


def _book():
    # env читается в момент вызова, а не при импорте: load_dotenv в bot.py
    # срабатывает уже после импорта sheets
    import gspread

    client = gspread.service_account(filename=os.getenv("GSHEET_CREDS"))
    return client.open_by_key(os.getenv("GSHEET_ID"))


def _get_worksheet():
    global _worksheet
    if _worksheet is None:
        sheet = _book().sheet1
        if not sheet.row_values(1):
            sheet.append_row(HEADER)
        _worksheet = sheet
    return _worksheet


def _get_subs_worksheet():
    global _subs_worksheet
    if _subs_worksheet is None:
        import gspread

        book = _book()
        try:
            sheet = book.worksheet(SUBS_SHEET)
        except gspread.WorksheetNotFound:
            sheet = book.add_worksheet(SUBS_SHEET, rows=1000, cols=len(SUBS_HEADER))
            sheet.append_row(SUBS_HEADER)
        _subs_worksheet = sheet
    return _subs_worksheet


def enabled() -> bool:
    return bool(os.getenv("GSHEET_CREDS") and os.getenv("GSHEET_ID"))


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


def export_subscription(event: str, user: str, days: int, expires: str):
    """Строка о новой подписке (оплата или подарок) на лист «Подписчики»."""
    if not enabled():
        return
    try:
        _get_subs_worksheet().append_row(
            [datetime.now().isoformat(timespec="seconds"), event, user, days, expires]
        )
    except Exception:
        log.exception("Не удалось выгрузить подписку в Google-таблицу")
