"""Оркестратор анализа: полный цикл от чтения файла до PDF-отчета."""
from __future__ import annotations

from typing import Callable, Optional

import matplotlib.pyplot as plt

from .config import AnalysisConfig, AnalysisResult
from .paths import report_path_for
from .physics import add_physics_columns, compute_smoothing
from .plots import build_figures
from .report import save_pdf_report
from .telemetry_io import (LAP_COL, compute_lap_times, format_lap_time,
                           normalize_lap_distances, peak_stats, read_telemetry,
                           select_laps)


def run_analysis(cfg: AnalysisConfig,
                 progress: Optional[Callable[[str], None]] = None) -> AnalysisResult:
    """Полный цикл анализа: чтение -> круги -> физика -> графики -> PDF-отчет.

    progress — необязательный callback для сообщений о ходе выполнения
    (CLI передает print, GUI — обновление статус-бара).
    Показ окон графиков управляется cfg.show_plots; при блокирующем показе
    (cfg.plot_show_block, CLI) фигуры закрываются после закрытия окон,
    при неблокирующем (GUI) остаются открытыми.
    """
    def say(msg: str):
        if progress:
            progress(msg)

    say(f"📊 Анализируем файл: {cfg.file_path}...")

    # Чтение и круги
    df = read_telemetry(cfg.file_path)
    all_laps, lap_times = compute_lap_times(df)
    laps = select_laps(all_laps, cfg.laps)
    max_speed_kmh, max_long_g, min_long_g, max_lat_g, min_lat_g = peak_stats(df)

    say(f"✅ Отображаем круги: {laps}")

    laps_summary = "\n".join(
        f"  Круг {int(lap)}: {format_lap_time(lap_times.get(lap, float('nan')))}" for lap in laps
    )
    say("⏱ Времена кругов:")
    say(laps_summary)
    say(f"🏁 Трасса: {cfg.track} | Пилот: {cfg.driver} | Погода: {cfg.weather}")
    say(f"📈 Пиковые показатели: V_max={max_speed_kmh:.1f} км/ч | "
        f"G_long=[{min_long_g:.2f} ... {max_long_g:.2f}] | "
        f"G_lat=[{min_lat_g:.2f} ... {max_lat_g:.2f}]")
    if cfg.car_label:
        say(f"🚗 Профиль автомобиля: {cfg.car_label}")
    say(f"⚙️ Расчет: Масса={cfg.mass} кг | КПД={cfg.efficiency * 100}% | "
        f"Gear Ratio={cfg.gear_ratio if cfg.gear_ratio > 0 else 'Не указан'}")

    # Физика
    normalize_lap_distances(df, laps)
    smoothing = compute_smoothing(df, cfg.smooth_time)
    say(f"⏱ Частота данных: ~{smoothing.freq_hz:.1f} Гц (Δt={smoothing.avg_dt:.3f} сек). "
        f"Окно фильтра: {smoothing.smooth_window} точек ({cfg.smooth_time} сек).")
    add_physics_columns(df, cfg)

    result = AnalysisResult(
        report_path=report_path_for(cfg.file_path, cfg.report_name),
        laps=laps,
        lap_times=lap_times,
        laps_summary=laps_summary,
        max_speed_kmh=max_speed_kmh,
        g_long_range=(min_long_g, max_long_g),
        g_lat_range=(min_lat_g, max_lat_g),
        freq_hz=smoothing.freq_hz,
        smooth_window=smoothing.smooth_window,
    )

    # Графики и PDF; при блокирующем показе (CLI) фигуры закрываются сами,
    # при неблокирующем (GUI) окна остаются открытыми до закрытия пользователем
    say(f"📄 Генерация PDF-отчета: {result.report_path}...")
    figs = build_figures(df, laps, cfg)
    try:
        save_pdf_report(figs, result, cfg)
        say(f"✅ Отчет успешно сохранен в файл: {result.report_path}")
        if cfg.show_plots:
            plt.show(block=cfg.plot_show_block)
    finally:
        if not cfg.show_plots or cfg.plot_show_block:
            for fig in figs:
                plt.close(fig)

    return result
