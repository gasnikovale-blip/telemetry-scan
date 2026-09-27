"""Конфигурация анализа: входные параметры и итоговые результаты."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple


@dataclass
class AnalysisConfig:
    """Входные параметры одного анализа (собираются CLI или GUI).

    Числовые параметры автомобиля по умолчанию соответствуют встроенным
    значениям VW Polo Sedan 1.6 (см. car_profile.CAR_DEFAULTS).
    """

    file_path: Path
    laps: Optional[List[int]] = None      # None = все круги
    mass: int = 1250
    cd_a: float = 0.65
    crr: float = 0.012
    r_wheel: float = 0.288
    efficiency: float = 0.90
    gear_ratio: float = 0.0               # 0 = момент двигателя не рассчитывается
    smooth_time: float = 0.8
    driver: str = "Не указан"
    track: str = "Автодром Санкт-Петербург"
    weather: str = "Сухо"
    car_label: str = "вручную (без профиля)"   # готовая строка для PDF и консоли
    report_name: str = ""                       # имя PDF-отчета; пусто = автоимя со штампом времени
    show_plots: bool = False                    # показывать окна графиков после анализа
    plot_show_block: bool = True                # True = ждать закрытия окон (CLI), False = не блокировать (GUI)

    def __post_init__(self):
        if self.mass <= 0:
            raise ValueError("Масса автомобиля должна быть положительной.")
        if self.cd_a <= 0:
            raise ValueError("Аэродинамическое сопротивление (Cd*A) должно быть положительным.")
        if self.crr <= 0:
            raise ValueError("Коэффициент сопротивления качению должен быть положительным.")
        if self.r_wheel <= 0:
            raise ValueError("Радиус колеса должен быть положительным.")
        if not 0 < self.efficiency <= 1:
            raise ValueError("КПД трансмиссии задается долей: 0.90 = 90%.")
        if self.gear_ratio < 0:
            raise ValueError("Передаточное число не может быть отрицательным.")
        if self.smooth_time <= 0:
            raise ValueError("Окно сглаживания должно быть положительным.")


@dataclass
class AnalysisResult:
    """Итоги анализа для вывода в консоль/GUI."""

    report_path: Path
    laps: List
    lap_times: Dict
    laps_summary: str                     # многострочный список времен кругов
    max_speed_kmh: float
    g_long_range: Tuple[float, float]     # (мин, макс)
    g_lat_range: Tuple[float, float]
    freq_hz: float
    smooth_window: int


def parse_laps_spec(text: str) -> Optional[List[int]]:
    """Строка с номерами кругов -> список. Пустая строка или пробелы -> None (все круги).

    Пример: "2, 3" -> [2, 3]
    """
    text = (text or "").strip()
    if not text:
        return None
    try:
        return [int(x.strip()) for x in text.split(",") if x.strip()]
    except ValueError:
        raise ValueError("Неверный формат кругов. Введите через запятую, например: 2, 3")
