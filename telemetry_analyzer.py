import pandas as pd
import matplotlib.pyplot as plt
import argparse
import sys
import os
import re
from matplotlib.backends.backend_pdf import PdfPages

def make_legend_interactive(fig, ax):
    leg = ax.legend(loc='best')
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

    fig.canvas.mpl_connect('pick_event', on_pick)

def fmt_time(t):
    if pd.isna(t) or t < 0: 
        return "Н/Д (неполный круг)"
    minutes = int(t // 60)
    seconds = t % 60
    if minutes > 0:
        return f"{minutes}:{seconds:06.3f}"
    else:
        return f"{seconds:.3f} сек"

def analyze_telemetry(file_path, selected_laps=None, mass=1250, cd_a=0.65, crr=0.012, r_wheel=0.288, efficiency=0.90, gear_ratio=0, driver="Не указан", track="Автодром Санкт-Петербург", weather="Сухо", smooth_time=0.8, car_name=None):
    if not os.path.exists(file_path):
        print(f"❌ Ошибка: Файл '{file_path}' не найден.")
        sys.exit(1)

    print(f"📊 Анализируем файл: {file_path}...")

    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"❌ Ошибка при чтении файла: {e}")
        sys.exit(1)

    header_line = ""
    skip_rows = 0
    for i, line in enumerate(lines):
        if 'timestamp' in line and 'fragment_id' in line:
            header_line = line.strip()
            skip_rows = i + 3
            break

    if skip_rows == 0:
        print("❌ Ошибка: Не удалось найти строку заголовка.")
        sys.exit(1)

    raw_cols = re.split(r'[,\|;\t]+', header_line)
    raw_cols = [c.strip() for c in raw_cols if c.strip()]
    
    cols = []
    seen = {}
    for c in raw_cols:
        if c in seen:
            seen[c] += 1
            cols.append(f"{c}_{seen[c]}")
        else:
            seen[c] = 0
            cols.append(c)

    try:
        df = pd.read_csv(file_path, sep=None, engine='python', skiprows=skip_rows, header=None)
    except Exception as e:
        print(f"❌ Ошибка при разборе CSV: {e}")
        sys.exit(1)

    if len(df.columns) != len(cols):
        if len(df.columns) > len(cols):
            cols = cols + [f'extra_{i}' for i in range(len(df.columns) - len(cols))]
        else:
            cols = cols[:len(df.columns)]

    df.columns = cols

    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].str.strip()

    numeric_cols = ['elapsed_time', 'distance_traveled', 'speed', 'lateral_acc', 'longitudinal_acc', 'timestamp']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    lap_col = 'lap_number'
    if lap_col not in df.columns:
        print("⚠️ Не найдена колонка 'lap_number'.")
        sys.exit(1)

    all_laps_in_df = sorted(df[lap_col].dropna().unique())
    lap_starts = df.groupby(lap_col)['elapsed_time'].min()
    lap_times = {}
    
    for i, lap in enumerate(all_laps_in_df):
        if i + 1 < len(all_laps_in_df):
            next_lap = all_laps_in_df[i+1]
            lap_times[lap] = lap_starts[next_lap] - lap_starts[lap]
        else:
            max_time = df[df[lap_col] == lap]['elapsed_time'].max()
            lap_times[lap] = max_time - lap_starts[lap]

    if selected_laps:
        laps = [lap for lap in all_laps_in_df if int(lap) in selected_laps]
        if not laps:
            print(f"⚠️ Указанные круги {selected_laps} не найдены. Доступные круги: {all_laps_in_df}")
            sys.exit(0)
    else:
        laps = all_laps_in_df

    # ==========================================
    # РАСЧЕТ ПИКОВЫХ ПОКАЗАТЕЛЕЙ
    # ==========================================
    max_speed_kmh = df['speed'].max() * 3.6
    min_speed_kmh = df['speed'].min() * 3.6
    max_long_g = df['longitudinal_acc'].max()
    min_long_g = df['longitudinal_acc'].min()
    max_lat_g = df['lateral_acc'].max()
    min_lat_g = df['lateral_acc'].min()

    print(f"✅ Отображаем круги: {laps}")
    
    laps_str = "\n".join([f"  Круг {int(lap)}: {fmt_time(lap_times.get(lap, float('nan')))}" for lap in laps])
    print("⏱ Времена кругов:")
    print(laps_str)
    print(f"🏁 Трасса: {track} | Пилот: {driver} | Погода: {weather}")
    print(f"📈 Пиковые показатели: V_max={max_speed_kmh:.1f} км/ч | G_long=[{min_long_g:.2f} ... {max_long_g:.2f}] | G_lat=[{min_lat_g:.2f} ... {max_lat_g:.2f}]")
    if car_name:
        print(f"🚗 Профиль автомобиля: {car_name}")
    print(f"⚙️ Расчет: Масса={mass} кг | КПД={efficiency*100}% | Gear Ratio={gear_ratio if gear_ratio > 0 else 'Не указан'}")

    df['lap_distance'] = float('nan')
    for lap in laps:
        lap_mask = df[lap_col] == lap
        if lap_mask.any():
            min_dist = df.loc[lap_mask, 'distance_traveled'].min()
            df.loc[lap_mask, 'lap_distance'] = df.loc[lap_mask, 'distance_traveled'] - min_dist

    # ==========================================
    # РАСЧЕТЫ ФИЗИКИ (С АВТОКАЛИБРОВКОЙ ОКНА)
    # ==========================================
    g = 9.81
    rho = 1.225 
    
    avg_dt = df['timestamp'].diff().mean()
    
    if pd.isna(avg_dt) or avg_dt <= 0:
        avg_dt = 0.01 
        
    freq_hz = 1.0 / avg_dt
    
    smooth_window = int(smooth_time / avg_dt)
    if smooth_window < 3: smooth_window = 3
    if smooth_window % 2 == 0: smooth_window += 1 
    
    median_window = 7
    
    print(f"⏱ Частота данных: ~{freq_hz:.1f} Гц (Δt={avg_dt:.3f} сек). Окно фильтра: {smooth_window} точек ({smooth_time} сек).")

    df['accel_ms2'] = df['longitudinal_acc'] * g
    df['speed_ms'] = df['speed']

    df['accel_ms2'] = df['accel_ms2'].rolling(window=median_window, center=True, min_periods=1).median()
    df['accel_ms2'] = df['accel_ms2'].rolling(window=smooth_window, center=True, min_periods=1).mean().bfill().ffill()
    df['speed_ms'] = df['speed_ms'].rolling(window=smooth_window, center=True, min_periods=1).mean().bfill().ffill()

    df['f_inertia'] = mass * df['accel_ms2']
    df['f_aero'] = 0.5 * rho * cd_a * (df['speed_ms']**2)
    df['f_roll'] = crr * mass * g
    df['f_total'] = df['f_inertia'] + df['f_aero'] + df['f_roll']
    
    df['power_wheel_hp'] = (df['f_total'] * df['speed_ms']) / 1000.0 * 1.35962
    df['power_engine_hp'] = df['power_wheel_hp'] / efficiency
    df['torque_wheel_nm'] = df['f_total'] * r_wheel
    if gear_ratio > 0:
        df['torque_engine_nm'] = df['torque_wheel_nm'] / (gear_ratio * efficiency)

    # ==========================================
    # ПОСТРОЕНИЕ ГРАФИКОВ
    # ==========================================
    figs = []

    # График 1: Скорость
    fig1, ax1 = plt.subplots(figsize=(12, 6))
    figs.append(fig1)
    for lap in laps:
        lap_data = df[df[lap_col] == lap]
        ax1.plot(lap_data['lap_distance'], lap_data['speed'] * 3.6, label=f'Круг {int(lap)}')
    ax1.set_title('Скорость от дистанции круга')
    ax1.set_xlabel('Дистанция от старта круга, м')
    ax1.set_ylabel('Скорость, км/ч')
    ax1.grid(True, which='both', linestyle='--', linewidth=0.5, alpha=0.7)
    ax1.minorticks_on()
    make_legend_interactive(fig1, ax1)
    fig1.tight_layout(pad=2.0)

    # График 2: Ускорения
    fig2, ax2 = plt.subplots(figsize=(12, 6))
    figs.append(fig2)
    for lap in laps:
        lap_data = df[df[lap_col] == lap]
        ax2.plot(lap_data['lap_distance'], lap_data['longitudinal_acc'], label=f'Продольное (Круг {int(lap)})', linestyle='--')
        ax2.plot(lap_data['lap_distance'], lap_data['lateral_acc'], label=f'Поперечное (Круг {int(lap)})', linestyle='-')
    ax2.set_title('Ускорения (G) от дистанции круга')
    ax2.set_xlabel('Дистанция от старта круга, м')
    ax2.set_ylabel('Ускорение, G')
    ax2.axhline(0, color='black', linewidth=1)
    ax2.grid(True, which='both', linestyle='--', linewidth=0.5, alpha=0.7)
    ax2.minorticks_on()
    make_legend_interactive(fig2, ax2)
    fig2.tight_layout(pad=2.0)

    # График 3: Диаграмма G-G
    fig3, ax3 = plt.subplots(figsize=(8, 8))
    figs.append(fig3)
    for lap in laps:
        lap_data = df[df[lap_col] == lap]
        ax3.plot(lap_data['lateral_acc'], lap_data['longitudinal_acc'], marker='o', linestyle='', markersize=3, alpha=0.3, label=f'Круг {int(lap)}')
    ax3.set_title('Диаграмма G-G (Тяговый круг)')
    ax3.set_xlabel('Поперечное ускорение, G (Влево / Вправо)')
    ax3.set_ylabel('Продольное ускорение, G (Торможение / Разгон)')
    ax3.axhline(0, color='black', linewidth=1)
    ax3.axvline(0, color='black', linewidth=1)
    ax3.set_aspect('equal', adjustable='box')
    ax3.grid(True, which='both', linestyle='--', linewidth=0.5, alpha=0.7)
    ax3.minorticks_on()
    make_legend_interactive(fig3, ax3)
    fig3.tight_layout(pad=2.0)

    # График 4: Мощность ДВИГАТЕЛЯ
    fig4, ax4 = plt.subplots(figsize=(12, 6))
    figs.append(fig4)
    for lap in laps:
        lap_data = df[df[lap_col] == lap]
        ax4.plot(lap_data['lap_distance'], lap_data['power_engine_hp'].clip(lower=0, upper=400), label=f'Круг {int(lap)}')
    ax4.set_title(f'Расчетная мощность ДВИГАТЕЛЯ (Масса: {mass} кг, КПД: {efficiency*100}%)')
    ax4.set_xlabel('Дистанция от старта круга, м')
    ax4.set_ylabel('Мощность, л.с.')
    ax4.grid(True, which='both', linestyle='--', linewidth=0.5, alpha=0.7)
    ax4.minorticks_on()
    make_legend_interactive(fig4, ax4)
    fig4.tight_layout(pad=2.0)

    # График 5: Момент ДВИГАТЕЛЯ
    if gear_ratio > 0:
        fig5, ax5 = plt.subplots(figsize=(12, 6))
        figs.append(fig5)
        for lap in laps:
            lap_data = df[df[lap_col] == lap]
            ax5.plot(lap_data['lap_distance'], lap_data['torque_engine_nm'].clip(lower=-100, upper=400), label=f'Круг {int(lap)}')
        ax5.set_title(f'Расчетный момент ДВИГАТЕЛЯ (Gear Ratio: {gear_ratio})')
        ax5.set_xlabel('Дистанция от старта круга, м')
        ax5.set_ylabel('Момент двигателя, Нм')
        ax5.grid(True, which='both', linestyle='--', linewidth=0.5, alpha=0.7)
        ax5.minorticks_on()
        make_legend_interactive(fig5, ax5)
        fig5.tight_layout(pad=2.0)

    # ==========================================
    # СОХРАНЕНИЕ PDF ОТЧЕТА
    # ==========================================
    report_filename = f"Отчет_{os.path.basename(file_path).replace('.csv', '')}.pdf"
    print(f"📄 Генерация PDF-отчета: {report_filename}...")
    
    with PdfPages(report_filename) as pdf:
        fig_text, ax_text = plt.subplots(figsize=(8.27, 11.69))
        ax_text.axis('off')
        
        report_text = (
            "ОТЧЕТ ПО ТЕЛЕМЕТРИИ\n"
            "==================================================\n\n"
            f"Исходный файл: {os.path.basename(file_path)}\n"
            f"Дата анализа: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            "--- ИНФОРМАЦИЯ О ЗАЕЗДЕ ---\n"
            f"Трасса: {track}\n"
            f"Пилот: {driver}\n"
            f"Погодные условия: {weather}\n\n"
            "--- ПИКОВЫЕ ПОКАЗАТЕЛИ ---\n"
            f"Макс. скорость:     {max_speed_kmh:.1f} км/ч\n"
            f"Макс. продольное G: {max_long_g:.2f} G (Разгон)\n"
            f"Мин. продольное G:  {min_long_g:.2f} G (Торможение)\n"
            f"Макс. поперечное G: {max_lat_g:.2f} G (Вправо)\n"
            f"Мин. поперечное G:  {min_lat_g:.2f} G (Влево)\n\n"
            "--- ВРЕМЕНА КРУГОВ ---\n"
            f"{laps_str}\n\n"
            "--- ВХОДНЫЕ ПАРАМЕТРЫ ---\n"
            f"Профиль автомобиля: {car_name if car_name else 'по умолчанию (встроенные параметры VW Polo Sedan 1.6)'}\n"
            f"Частота датчиков: ~{freq_hz:.1f} Гц\n"
            f"Масса автомобиля: {mass} кг\n"
            f"Аэродинамика (Cd*A): {cd_a}\n"
            f"Коэфф. качения (Crr): {crr}\n"
            f"Радиус колеса: {r_wheel} м\n"
            f"КПД трансмиссии: {efficiency * 100} %\n"
            f"Передаточное число: {gear_ratio if gear_ratio > 0 else 'Не указано'}\n"
            f"Окно сглаживания: {smooth_time} сек (~{smooth_window} точек)\n\n"
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
        ax_text.text(0.05, 0.95, report_text, va='top', ha='left', 
                     family='monospace', fontsize=11, wrap=True)
        pdf.savefig(fig_text, bbox_inches='tight')
        plt.close(fig_text)
        
        for fig in figs:
            pdf.savefig(fig, bbox_inches='tight')
            
    print(f"✅ Отчет успешно сохранен в файл: {report_filename}")

    plt.show()

if __name__ == "__main__":
    from car_profile import CarProfileError, resolve_car_params

    parser = argparse.ArgumentParser(description="Анализ телеметрии RaceChrono (по умолчанию для VW Polo Sedan 1.6 2017)")
    parser.add_argument("filepath", help="Путь к файлу лога RaceChrono")
    parser.add_argument("--car", type=str, default=None, help="Путь к файлу профиля автомобиля (.ini), например cars/vw_polo_sedan_16.ini")
    parser.add_argument("--laps", type=int, nargs='*', help="Какие круги отображать (например: --laps 2 3)")
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

    args = parser.parse_args()

    try:
        car = resolve_car_params(args.car, explicit={
            "mass": args.mass,
            "cd_a": args.cd_a,
            "crr": args.crr,
            "r_wheel": args.r_wheel,
            "efficiency": args.efficiency,
            "gear_ratio": args.gear_ratio,
        })
    except CarProfileError as e:
        print(f"❌ Ошибка: {e}")
        sys.exit(1)

    analyze_telemetry(
        args.filepath,
        selected_laps=args.laps,
        mass=car["mass"],
        cd_a=car["cd_a"],
        crr=car["crr"],
        r_wheel=car["r_wheel"],
        efficiency=car["efficiency"],
        gear_ratio=car["gear_ratio"],
        car_name=car["name"],
        driver=args.driver,
        track=args.track,
        weather=args.weather,
        smooth_time=args.smooth_time
    )