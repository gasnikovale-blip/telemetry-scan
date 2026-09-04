"""Чтение лога RaceChrono и расчеты по кругам."""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

import pandas as pd

NUMERIC_COLS = ["elapsed_time", "distance_traveled", "speed",
                "lateral_acc", "longitudinal_acc", "timestamp"]
LAP_COL = "lap_number"


def read_telemetry(file_path) -> pd.DataFrame:
    """Читает специфический текстовый формат RaceChrono (разделители | и многоуровневый заголовок).

    Автоматически находит строку заголовка, устраняет дубликаты имен колонок
    (суффикс _N), приводит нужные колонки к числам.
    """
    file_path = str(file_path)
    if not pd.io.common.file_exists(file_path):
        raise FileNotFoundError(f"Файл '{file_path}' не найден.")

    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except OSError as e:
        raise FileNotFoundError(f"Ошибка при чтении файла: {e}")

    header_line = ""
    skip_rows = 0
    for i, line in enumerate(lines):
        if "timestamp" in line and "fragment_id" in line:
            header_line = line.strip()
            skip_rows = i + 3
            break

    if skip_rows == 0:
        raise ValueError("Не удалось найти строку заголовка в файле.")

    raw_cols = re.split(r"[,\|;\t]+", header_line)
    raw_cols = [c.strip() for c in raw_cols if c.strip()]

    # Дубликаты имен колонок получают суффикс _N (в логах RaceChrono колонки повторяются)
    cols = []
    seen = {}
    for c in raw_cols:
        if c in seen:
            seen[c] += 1
            cols.append(f"{c}_{seen[c]}")
        else:
            seen[c] = 0
            cols.append(c)

    df = pd.read_csv(file_path, sep=None, engine="python", skiprows=skip_rows, header=None)

    # Число колонок данных может отличаться от заголовка — выравниваем
    if len(df.columns) > len(cols):
        cols = cols + [f"extra_{i}" for i in range(len(df.columns) - len(cols))]
    elif len(df.columns) < len(cols):
        cols = cols[:len(df.columns)]
    df.columns = cols

    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].str.strip()

    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if LAP_COL not in df.columns:
        raise ValueError("В файле нет колонки 'lap_number'.")
    return df


def compute_lap_times(df: pd.DataFrame) -> Tuple[List, Dict]:
    """Все круги в логе и времена каждого (разница elapsed_time между стартами кругов).

    Возвращает (отсортированный список кругов, dict круг -> время в секундах).
    """
    all_laps = sorted(df[LAP_COL].dropna().unique())
    lap_starts = df.groupby(LAP_COL)["elapsed_time"].min()

    lap_times = {}
    for i, lap in enumerate(all_laps):
        if i + 1 < len(all_laps):
            lap_times[lap] = lap_starts[all_laps[i + 1]] - lap_starts[lap]
        else:
            max_time = df[df[LAP_COL] == lap]["elapsed_time"].max()
            lap_times[lap] = max_time - lap_starts[lap]
    return all_laps, lap_times


def select_laps(all_laps: List, selected: List[int]) -> List:
    """Отфильтровывает круги по выбранным номерам. None/пусто = все круги."""
    if not selected:
        return list(all_laps)
    laps = [lap for lap in all_laps if int(lap) in selected]
    if not laps:
        raise ValueError(f"Круги {selected} не найдены. Доступны: {all_laps}")
    return laps


def peak_stats(df: pd.DataFrame) -> Tuple[float, float, float, float, float]:
    """Пиковые показатели: (макс. скорость км/ч, макс/мин продольное G, макс/мин поперечное G)."""
    return (
        df["speed"].max() * 3.6,
        df["longitudinal_acc"].max(),
        df["longitudinal_acc"].min(),
        df["lateral_acc"].max(),
        df["lateral_acc"].min(),
    )


def normalize_lap_distances(df: pd.DataFrame, laps: List) -> None:
    """Добавляет колонку lap_distance — дистанция от начала круга (для наложения кругов)."""
    df["lap_distance"] = float("nan")
    for lap in laps:
        lap_mask = df[LAP_COL] == lap
        if lap_mask.any():
            min_dist = df.loc[lap_mask, "distance_traveled"].min()
            df.loc[lap_mask, "lap_distance"] = df.loc[lap_mask, "distance_traveled"] - min_dist


def format_lap_time(t) -> str:
    """Время круга в читаемом виде: '1:23.456' / '23.456 сек' / 'Н/Д (неполный круг)'."""
    if pd.isna(t) or t < 0:
        return "Н/Д (неполный круг)"
    minutes = int(t // 60)
    seconds = t % 60
    if minutes > 0:
        return f"{minutes}:{seconds:06.3f}"
    return f"{seconds:.3f} сек"
