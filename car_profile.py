"""Профили автомобилей (папка cars/*.ini). Общий модуль для CLI и GUI.

Единственный источник значений по умолчанию — CAR_DEFAULTS (VW Polo Sedan 1.6).
Приоритет параметров: явный флаг командной строки > профиль --car > CAR_DEFAULTS.
"""
import configparser
from pathlib import Path

CARS_DIR = Path(__file__).resolve().parent / "cars"

# Встроенные значения по умолчанию (VW Polo Sedan 1.6, 2017, МКПП)
CAR_DEFAULTS = {
    "mass": 1250,
    "cd_a": 0.65,
    "crr": 0.012,
    "r_wheel": 0.288,
    "efficiency": 0.90,
    "gear_ratio": 0.0,
}

REQUIRED_KEYS = ("mass", "cd_a", "crr", "r_wheel", "efficiency")  # name и gear_ratio — опциональны

# Запись для ручного ввода в выпадающем списке GUI
MANUAL = "вручную (свои значения)"

# Диапазоны допустимых значений: (мин, макс, мин_включительно, макс_включительно)
BOUNDS = {
    "mass":       (100, 10000, True,  True),
    "cd_a":       (0.0, 10.0,  False, True),
    "crr":        (0.0, 0.1,   False, True),
    "r_wheel":    (0.10, 1.0,  True,  True),
    "efficiency": (0.0, 1.0,   False, True),   # КПД задается долей: 0.90 = 90%
    "gear_ratio": (0.0, 20.0,  True,  True),   # 0 разрешен = момент двигателя не рассчитывается
}

KEY_LABELS = {
    "mass": "Масса (кг)",
    "cd_a": "Аэродинамика Cd*A",
    "crr": "Коэфф. качения Crr",
    "r_wheel": "Радиус колеса (м)",
    "efficiency": "КПД трансмиссии",
    "gear_ratio": "Передаточное число",
}


class CarProfileError(Exception):
    """Ошибка загрузки профиля или значения параметров.

    str(e) — готовое русское сообщение без префикса '❌ Ошибка: ' (его добавляет вызывающий код).
    """


def validate_car_values(values, where):
    """Проверяет числовые параметры автомобиля по диапазонам BOUNDS.

    values — dict с ключами из CAR_DEFAULTS.
    where — контекст для сообщения, например "профиль 'cars/bmw.ini'"
    или "аргументы командной строки".
    Выбрасывает CarProfileError с русским сообщением при некорректном значении.
    """
    for key, (lo, hi, lo_inc, hi_inc) in BOUNDS.items():
        v = values[key]
        ok_lo = (v >= lo) if lo_inc else (v > lo)
        ok_hi = (v <= hi) if hi_inc else (v < hi)
        if not (ok_lo and ok_hi):
            msg = f"В {where}: {KEY_LABELS[key]} = {v} вне допустимого диапазона {lo}..{hi}."
            if key == "efficiency":
                msg += " КПД задается долей: 0.90 = 90%."
            raise CarProfileError(msg)


def _new_parser():
    # inline_comment_prefixes обязателен: иначе 'gear_ratio = 5.0 ; комментарий'
    # распарсится вместе с комментарием и float() упадет.
    return configparser.ConfigParser(inline_comment_prefixes=(";", "#"))


def _read_ini(path):
    cfg = _new_parser()
    try:
        # utf-8-sig: обычный UTF-8 читается так же, но BOM (файл из Блокнота) не ломает заголовок секции
        with open(path, "r", encoding="utf-8-sig") as f:
            cfg.read_file(f)
    except (OSError, UnicodeDecodeError, configparser.Error) as e:
        raise CarProfileError(f"Не удалось прочитать профиль '{path}': {e}")
    return cfg


def _parse_value(key, raw, where):
    """Строка из ini -> число. mass округляется до целого."""
    try:
        v = float(raw)
    except (TypeError, ValueError):
        raise CarProfileError(
            f"В {where} ключ '{key}' имеет некорректное значение '{raw}' (ожидается число)."
        )
    if key == "mass":
        return int(round(v))
    return v


def _scan_dir(cars_dir=CARS_DIR):
    """Список .ini файлов в папке профилей (шаблоны с '_' и скрытые — пропускаются)."""
    if not cars_dir.is_dir():
        return []
    return sorted(
        p for p in cars_dir.glob("*.ini")
        if not p.name.startswith(("_", "."))
    )


def _available_profiles_hint(cars_dir):
    profiles = _scan_dir(cars_dir)
    if not profiles:
        return "Папка 'cars/' не найдена или пуста."
    return "Профили в папке cars/: " + ", ".join(f"cars/{p.name}" for p in profiles) + "."


def resolve_profile_path(spec, cars_dir=CARS_DIR):
    """Превращает --car в путь к файлу профиля.

    spec — путь к .ini файлу (абсолютный или относительный от текущей папки).
    Имена без пути не разрешаются: в CLI передается путь, GUI передает готовый Path
    из list_car_profiles().
    """
    if spec is None or not str(spec).strip():
        raise CarProfileError("Не указан путь к файлу профиля автомобиля.")

    # На входе может быть и строка (--car), и готовый Path (из списка GUI)
    path = Path(str(spec).strip())
    if not path.is_file():
        raise CarProfileError(
            f"Файл профиля '{path}' не найден. {_available_profiles_hint(cars_dir)}"
        )
    return path


def load_car_profile(spec, cars_dir=CARS_DIR):
    """Загружает профиль автомобиля. Возвращает dict:
    {"name", "path", mass, cd_a, crr, r_wheel, efficiency, gear_ratio}.
    """
    path = resolve_profile_path(spec, cars_dir)
    cfg = _read_ini(path)

    if not cfg.has_section("car"):
        raise CarProfileError(f"В профиле '{path}' нет секции [car].")

    section = cfg["car"]
    missing = [k for k in REQUIRED_KEYS if k not in section]
    if missing:
        raise CarProfileError(f"В профиле '{path}' не заполнены ключи: {', '.join(missing)}.")

    where = f"профиле '{path}'"
    profile = {"name": (section.get("name") or "").strip() or path.stem, "path": path}
    for key in CAR_DEFAULTS:
        raw = section.get(key)
        if raw is None:
            # gear_ratio и любые пропущенные ключи берутся из значений по умолчанию
            profile[key] = CAR_DEFAULTS[key]
        else:
            profile[key] = _parse_value(key, raw, where)

    unknown = [k for k in section if k not in CAR_DEFAULTS and k != "name"]
    if unknown:
        print(f"⚠️ Профиль '{profile['name']}': неизвестные ключи {unknown} проигнорированы.")

    validate_car_values(profile, where)
    return profile


def resolve_car_params(car_spec, explicit=None, cars_dir=CARS_DIR):
    """Итоговые параметры для CLI: явные флаги > профиль > CAR_DEFAULTS.

    explicit — dict значений флагов; None означает 'флаг не передавали'.
    Возвращает dict {"name", "path", **шесть числовых параметров}.
    """
    explicit = {k: v for k, v in (explicit or {}).items() if v is not None}

    profile = load_car_profile(car_spec, cars_dir) if car_spec else None

    params = dict(CAR_DEFAULTS)
    if profile:
        params.update({k: profile[k] for k in CAR_DEFAULTS})
    params.update(explicit)

    validate_car_values(params, "аргументах командной строки")

    return {
        "name": profile["name"] if profile else None,
        "path": profile["path"] if profile else None,
        **params,
    }


def list_car_profiles(cars_dir=CARS_DIR):
    """Список профилей для выпадающего списка GUI: [(путь, отображаемое_имя)].

    Файл, который не удается прочитать, не ломает список — помечается как 'ошибка чтения'.
    """
    result = []
    for path in _scan_dir(cars_dir):
        try:
            cfg = _read_ini(path)
            name = (cfg.get("car", "name", fallback="") or "").strip() or path.stem
        except CarProfileError:
            name = path.stem + " (ошибка чтения)"
        result.append((path, name))
    return result
