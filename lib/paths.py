"""Пути проекта: папки data/ и reports/."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJECT_ROOT / "data"
REPORTS_DIR = PROJECT_ROOT / "reports"

# Символы, запрещенные в именах файлов Windows (проверяем всегда: отчеты
# часто копируют между Linux и Windows)
_UNSAFE_FILENAME = re.compile(r'[\\/:*?"<>|]+')


def ensure_reports_dir() -> Path:
    """Создает папку reports/ при необходимости и возвращает её."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    return REPORTS_DIR


def report_path_for(csv_path, report_name: str = "") -> Path:
    """Путь к PDF-отчету.

    report_name задан  -> reports/<report_name>.pdf; запрещенные для Windows
                          символы заменяются на '_', суффикс .pdf добавляется,
                          если его нет.
    report_name пуст   -> reports/Отчет_<имя csv>_<ГГГГММДД_ЧЧММСС>.pdf — штамп
                          времени, чтобы повторные анализы не перезаписывали
                          предыдущие отчеты.
    """
    name = (report_name or "").strip()
    if name:
        name = _UNSAFE_FILENAME.sub("_", name)
        if not name.lower().endswith(".pdf"):
            name += ".pdf"
        return ensure_reports_dir() / name
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return ensure_reports_dir() / f"Отчет_{Path(csv_path).stem}_{stamp}.pdf"
