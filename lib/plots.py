"""Построение графиков телеметрии (5 фигур matplotlib)."""
from __future__ import annotations

from typing import List

import matplotlib.pyplot as plt
import pandas as pd

from .config import AnalysisConfig
from .telemetry_io import LAP_COL

# Единый источник подписей и заголовков графиков
XLAP = "Дистанция от старта круга, м"
T_SPEED = "Скорость от дистанции круга"
T_ACC = "Ускорения (G) от дистанции круга"
T_GG = "Диаграмма G-G (Тяговый круг)"
XL_GG = "Поперечное ускорение, G (Влево / Вправо)"
YL_GG = "Продольное ускорение, G (Торможение / Разгон)"
YL_SPEED = "Скорость, км/ч"
YL_ACC = "Ускорение, G"
YL_POWER_HP = "Мощность, л.с."
YL_TORQUE_NM = "Момент двигателя, Нм"

POWER_CLIP = (0, 400)      # л.с., защита от выбросов при переключении передач
TORQUE_CLIP = (-100, 400)  # Нм

GRID_KWARGS = dict(which="both", linestyle="--", linewidth=0.5, alpha=0.7)


def make_legend_interactive(fig, ax) -> None:
    """Легенда, позволяющая скрывать/показывать линии кликом (для интерактивных окон)."""
    leg = ax.legend(loc="best")
    lined = {}

    for legline, origline in zip(leg.get_lines(), ax.get_lines()):
        legline.set_picker(5)
        lined[legline] = origline

    def on_pick(event):
        legline = event.artist
        if legline not in lined:
            return
        origline = lined[legline]
        visible = not origline.get_visible()
        origline.set_visible(visible)
        if visible:
            legline.set_alpha(1.0)
        else:
            legline.set_alpha(0.2)
        fig.canvas.draw_idle()

    fig.canvas.mpl_connect("pick_event", on_pick)


def _finish(fig, ax) -> None:
    """Общее оформление фигуры: сетка, минорные деления, интерактивная легенда, компоновка."""
    ax.grid(True, **GRID_KWARGS)
    ax.minorticks_on()
    make_legend_interactive(fig, ax)
    fig.tight_layout(pad=2.0)


def build_figures(df: pd.DataFrame, laps: List, cfg: AnalysisConfig) -> List:
    """Строит 4 фигуры (скорость, ускорения, G-G, мощность) + момент при gear_ratio > 0."""
    figs = []

    def lap_rows(lap):
        return df[df[LAP_COL] == lap]

    # График 1: Скорость
    fig, ax = plt.subplots(figsize=(12, 6))
    figs.append(fig)
    for lap in laps:
        lap_data = lap_rows(lap)
        ax.plot(lap_data["lap_distance"], lap_data["speed"] * 3.6, label=f"Круг {int(lap)}")
    ax.set_title(T_SPEED)
    ax.set_xlabel(XLAP)
    ax.set_ylabel(YL_SPEED)
    _finish(fig, ax)

    # График 2: Ускорения
    fig, ax = plt.subplots(figsize=(12, 6))
    figs.append(fig)
    for lap in laps:
        lap_data = lap_rows(lap)
        ax.plot(lap_data["lap_distance"], lap_data["longitudinal_acc"],
                label=f"Продольное (Круг {int(lap)})", linestyle="--")
        ax.plot(lap_data["lap_distance"], lap_data["lateral_acc"],
                label=f"Поперечное (Круг {int(lap)})", linestyle="-")
    ax.set_title(T_ACC)
    ax.set_xlabel(XLAP)
    ax.set_ylabel(YL_ACC)
    ax.axhline(0, color="black", linewidth=1)
    _finish(fig, ax)

    # График 3: Диаграмма G-G
    fig, ax = plt.subplots(figsize=(8, 8))
    figs.append(fig)
    for lap in laps:
        lap_data = lap_rows(lap)
        ax.plot(lap_data["lateral_acc"], lap_data["longitudinal_acc"],
                marker="o", linestyle="", markersize=3, alpha=0.3, label=f"Круг {int(lap)}")
    ax.set_title(T_GG)
    ax.set_xlabel(XL_GG)
    ax.set_ylabel(YL_GG)
    ax.axhline(0, color="black", linewidth=1)
    ax.axvline(0, color="black", linewidth=1)
    ax.set_aspect("equal", adjustable="box")
    _finish(fig, ax)

    # График 4: Мощность двигателя
    fig, ax = plt.subplots(figsize=(12, 6))
    figs.append(fig)
    for lap in laps:
        lap_data = lap_rows(lap)
        ax.plot(lap_data["lap_distance"], lap_data["power_engine_hp"].clip(*POWER_CLIP),
                label=f"Круг {int(lap)}")
    ax.set_title(f"Расчетная мощность ДВИГАТЕЛЯ (Масса: {cfg.mass} кг, КПД: {cfg.efficiency * 100}%)")
    ax.set_xlabel(XLAP)
    ax.set_ylabel(YL_POWER_HP)
    _finish(fig, ax)

    # График 5: Момент двигателя (только если известно передаточное число)
    if cfg.gear_ratio > 0:
        fig, ax = plt.subplots(figsize=(12, 6))
        figs.append(fig)
        for lap in laps:
            lap_data = lap_rows(lap)
            ax.plot(lap_data["lap_distance"], lap_data["torque_engine_nm"].clip(*TORQUE_CLIP),
                    label=f"Круг {int(lap)}")
        ax.set_title(f"Расчетный момент ДВИГАТЕЛЯ (Gear Ratio: {cfg.gear_ratio})")
        ax.set_xlabel(XLAP)
        ax.set_ylabel(YL_TORQUE_NM)
        _finish(fig, ax)

    return figs
