"""Формирование PDF-отчета по телеметрии."""
from __future__ import annotations

from pathlib import Path
from typing import List

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages

from .config import AnalysisConfig, AnalysisResult
from .paths import report_path_for

PAGE_SIZE = (8.27, 11.69)   # A4, титульный лист


def build_report_text(result: AnalysisResult, cfg: AnalysisConfig) -> str:
    """Текст титульного листа отчета."""
    max_speed_kmh = result.max_speed_kmh
    min_long_g, max_long_g = result.g_long_range
    min_lat_g, max_lat_g = result.g_lat_range
    return (
        "ОТЧЕТ ПО ТЕЛЕМЕТРИИ\n"
        "==================================================\n\n"
        f"Исходный файл: {Path(cfg.file_path).name}\n"
        f"Дата анализа: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        "--- ИНФОРМАЦИЯ О ЗАЕЗДЕ ---\n"
        f"Трасса: {cfg.track}\n"
        f"Пилот: {cfg.driver}\n"
        f"Погодные условия: {cfg.weather}\n\n"
        "--- ПИКОВЫЕ ПОКАЗАТЕЛИ ---\n"
        f"Макс. скорость:     {max_speed_kmh:.1f} км/ч\n"
        f"Макс. продольное G: {max_long_g:.2f} G (Разгон)\n"
        f"Мин. продольное G:  {min_long_g:.2f} G (Торможение)\n"
        f"Макс. поперечное G: {max_lat_g:.2f} G (Вправо)\n"
        f"Мин. поперечное G:  {min_lat_g:.2f} G (Влево)\n\n"
        "--- ВРЕМЕНА КРУГОВ ---\n"
        f"{result.laps_summary}\n\n"
        "--- ВХОДНЫЕ ПАРАМЕТРЫ ---\n"
        f"Профиль автомобиля: {cfg.car_label}\n"
        f"Частота датчиков: ~{result.freq_hz:.1f} Гц\n"
        f"Масса автомобиля: {cfg.mass} кг\n"
        f"Аэродинамика (Cd*A): {cfg.cd_a}\n"
        f"Коэфф. качения (Crr): {cfg.crr}\n"
        f"Радиус колеса: {cfg.r_wheel} м\n"
        f"КПД трансмиссии: {cfg.efficiency * 100} %\n"
        f"Передаточное число: {cfg.gear_ratio if cfg.gear_ratio > 0 else 'Не указано'}\n"
        f"Окно сглаживания: {cfg.smooth_time} сек (~{result.smooth_window} точек)\n\n"
        "--- ВНИМАНИЕ ---\n"
        "Графики МОЩНОСТИ и МОМЕНТА двигателя\n"
        "корректны ТОЛЬКО на участках, где\n"
        "автомобиль двигался на передаче,\n"
        "указанной в 'Передаточное число'.\n"
        "При переключении передач или движении\n"
        "накатом графики могут выдавать\n"
        "некорректные пиковые значения.\n\n"
        "--- МЕТОДОЛОГИЯ ---\n"
        "Силы и ускорения очищены медианным фильтром\n"
        "и скользящим средним.\n"
        "Учитываются силы: инерции, аэродинамики, качения\n"
        "Мощность = (F_ин + F_аэро + F_кач) * V / КПД\n"
        "Момент = (F_ин + F_аэро + F_кач) * R /\n"
        "         (GearRatio * КПД)\n"
    )


def save_pdf_report(figs: List, result: AnalysisResult, cfg: AnalysisConfig) -> Path:
    """Собирает PDF: титульный лист + все графики. Возвращает путь к файлу."""
    path = report_path_for(cfg.file_path)

    with PdfPages(path) as pdf:
        fig_text, ax_text = plt.subplots(figsize=PAGE_SIZE)
        ax_text.axis("off")
        ax_text.text(0.05, 0.95, build_report_text(result, cfg), va="top", ha="left",
                     family="monospace", fontsize=11, wrap=True)
        pdf.savefig(fig_text, bbox_inches="tight")
        plt.close(fig_text)

        for fig in figs:
            pdf.savefig(fig, bbox_inches="tight")

    return path
