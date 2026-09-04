"""Пути проекта: папки data/ и reports/."""
from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJECT_ROOT / "data"
REPORTS_DIR = PROJECT_ROOT / "reports"


def ensure_reports_dir() -> Path:
    """Создает папку reports/ при необходимости и возвращает её."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    return REPORTS_DIR


def report_path_for(csv_path) -> Path:
    """Путь к PDF-отчету для данного файла телеметрии: reports/Отчет_<имя>.pdf."""
    return ensure_reports_dir() / f"Отчет_{Path(csv_path).stem}.pdf"
