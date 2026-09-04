"""Анализ телеметрии RaceChrono — консольная точка входа.

Вся логика чтения, расчетов, графиков и PDF-отчета — в пакете lib/.
"""
import argparse
import sys
from pathlib import Path

from car_profile import CarProfileError, resolve_car_params
from lib import AnalysisConfig, run_analysis
from lib.paths import DATA_DIR

CAR_FLAGS = ("mass", "cd_a", "crr", "r_wheel", "efficiency", "gear_ratio")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Анализ телеметрии RaceChrono (по умолчанию для VW Polo Sedan 1.6 2017)")
    parser.add_argument("filepath", help="Путь к файлу лога RaceChrono (CSV-файлы лежат в папке data/)")
    parser.add_argument("--car", type=str, default=None, help="Путь к файлу профиля автомобиля (.ini), например cars/vw_polo_sedan_16.ini")
    parser.add_argument("--laps", type=int, nargs="*", help="Какие круги отображать (например: --laps 2 3)")
    parser.add_argument("--mass", type=int, default=None, help="Масса автомобиля в кг (по умолчанию: из профиля --car, иначе 1250)")
    parser.add_argument("--cd_a", type=float, default=None, help="Аэродинамическое сопротивление Cd*A (по умолчанию: из профиля --car, иначе 0.65)")
    parser.add_argument("--crr", type=float, default=None, help="Коэффициент сопротивления качению (по умолчанию: из профиля --car, иначе 0.012)")
    parser.add_argument("--r_wheel", type=float, default=None, help="Радиус колеса в метрах (по умолчанию: из профиля --car, иначе 0.288)")
    parser.add_argument("--efficiency", type=float, default=None, help="КПД трансмиссии (0.90 = 90%; по умолчанию: из профиля --car, иначе 0.90)")
    parser.add_argument("--gear_ratio", type=float, default=None, help="Передаточное число КПП * Главная пара (для расчета момента двигателя; по умолчанию: из профиля --car, иначе 0)")
    parser.add_argument("--smooth_time", type=float, default=0.8, help="Окно сглаживания в СЕКУНДАХ (по умолчанию 0.8 сек)")
    parser.add_argument("--driver", type=str, default="Не указан", help="Имя пилота")
    parser.add_argument("--track", type=str, default="Автодром Санкт-Петербург", help="Название трассы")
    parser.add_argument("--weather", type=str, default="Сухо", help="Погодные условия")
    return parser


def compose_car_label(car: dict, args) -> str:
    """Строка о происхождении параметров автомобиля для консоли и PDF."""
    explicit_flags = [f for f in CAR_FLAGS if getattr(args, f) is not None]
    if car["name"]:
        return car["name"]
    if explicit_flags:
        return "вручную (флаги командной строки)"
    return "по умолчанию (встроенные параметры VW Polo Sedan 1.6)"


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    try:
        car = resolve_car_params(args.car, explicit={f: getattr(args, f) for f in CAR_FLAGS})
    except CarProfileError as e:
        print(f"❌ Ошибка: {e}")
        return 1

    try:
        cfg = AnalysisConfig(
            file_path=args.filepath,
            laps=args.laps,
            mass=car["mass"],
            cd_a=car["cd_a"],
            crr=car["crr"],
            r_wheel=car["r_wheel"],
            efficiency=car["efficiency"],
            gear_ratio=car["gear_ratio"],
            smooth_time=args.smooth_time,
            driver=args.driver,
            track=args.track,
            weather=args.weather,
            car_label=compose_car_label(car, args),
            show_plots=True,
        )
        run_analysis(cfg, progress=print)
    except FileNotFoundError as e:
        print(f"❌ Ошибка: {e}")
        hint = DATA_DIR / Path(args.filepath).name
        if hint.is_file():
            print(f"💡 Возможно, файл лежит в папке data/? Попробуйте: {hint}")
        return 1
    except (ValueError, CarProfileError) as e:
        print(f"❌ Ошибка: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
