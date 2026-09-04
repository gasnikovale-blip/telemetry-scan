"""Физико-динамические расчеты: сглаживание, силы, мощность, момент."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .config import AnalysisConfig

G = 9.81          # ускорение свободного падения, м/с²
RHO = 1.225       # плотность воздуха, кг/м³
MEDIAN_WINDOW = 7 # окно медианного фильтра (вырезает выбросы от кочек), точек

HP_PER_KW = 1.35962


@dataclass
class SmoothingInfo:
    """Параметры сглаживания, вычисленные из частоты данных."""

    freq_hz: float
    avg_dt: float
    smooth_window: int   # нечетное, >= 3


def compute_smoothing(df: pd.DataFrame, smooth_time: float) -> SmoothingInfo:
    """Вычисляет частоту данных по временным меткам и размер окна фильтра в точках,
    чтобы сглаживание всегда занимало заданное время в секундах.
    """
    avg_dt = df["timestamp"].diff().mean()

    if pd.isna(avg_dt) or avg_dt <= 0:
        avg_dt = 0.01

    smooth_window = int(smooth_time / avg_dt)
    if smooth_window < 3:
        smooth_window = 3
    if smooth_window % 2 == 0:
        smooth_window += 1

    return SmoothingInfo(freq_hz=1.0 / avg_dt, avg_dt=avg_dt, smooth_window=smooth_window)


def add_physics_columns(df: pd.DataFrame, cfg: AnalysisConfig) -> None:
    """Добавляет колонки: сглаженные ускорение/скорость, силы, мощность и момент.

    Двойная фильтрация: медианный фильтр (вырезает выбросы) + скользящее среднее.
    torque_engine_nm добавляется только при gear_ratio > 0.
    """
    df["accel_ms2"] = df["longitudinal_acc"] * G
    df["speed_ms"] = df["speed"]

    smooth_window = compute_smoothing(df, cfg.smooth_time).smooth_window

    df["accel_ms2"] = df["accel_ms2"].rolling(window=MEDIAN_WINDOW, center=True, min_periods=1).median()
    df["accel_ms2"] = df["accel_ms2"].rolling(window=smooth_window, center=True, min_periods=1).mean().bfill().ffill()
    df["speed_ms"] = df["speed_ms"].rolling(window=smooth_window, center=True, min_periods=1).mean().bfill().ffill()

    df["f_inertia"] = cfg.mass * df["accel_ms2"]
    df["f_aero"] = 0.5 * RHO * cfg.cd_a * (df["speed_ms"] ** 2)
    df["f_roll"] = cfg.crr * cfg.mass * G
    df["f_total"] = df["f_inertia"] + df["f_aero"] + df["f_roll"]

    df["power_wheel_hp"] = (df["f_total"] * df["speed_ms"]) / 1000.0 * HP_PER_KW
    df["power_engine_hp"] = df["power_wheel_hp"] / cfg.efficiency
    df["torque_wheel_nm"] = df["f_total"] * cfg.r_wheel
    if cfg.gear_ratio > 0:
        df["torque_engine_nm"] = df["torque_wheel_nm"] / (cfg.gear_ratio * cfg.efficiency)
