import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import pandas as pd
import matplotlib.pyplot as plt
import re
from matplotlib.backends.backend_pdf import PdfPages

from car_profile import MANUAL, CarProfileError, list_car_profiles, load_car_profile

# ==========================================
# ФУНКЦИИ АНАЛИЗА (Встроены из скрипта)
# ==========================================

def make_legend_interactive(fig, ax):
    leg = ax.legend(loc='best')
    lined = {}
    for legline, origline in zip(leg.get_lines(), ax.get_lines()):
        legline.set_picker(5)
        lined[legline] = origline

    def on_pick(event):
        legline = event.artist
        if legline not in lined: return
        origline = lined[legline]
        visible = not origline.get_visible()
        origline.set_visible(visible)
        if visible: legline.set_alpha(1.0)
        else: legline.set_alpha(0.2)
        fig.canvas.draw_idle()

    fig.canvas.mpl_connect('pick_event', on_pick)

def fmt_time(t):
    if pd.isna(t) or t < 0: return "Н/Д (неполный круг)"
    minutes = int(t // 60)
    seconds = t % 60
    if minutes > 0: return f"{minutes}:{seconds:06.3f}"
    else: return f"{seconds:.3f} сек"

def analyze_telemetry(file_path, selected_laps_str, mass, cd_a, crr, r_wheel, efficiency, gear_ratio, driver, track, weather, smooth_time, car_name=None):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Файл '{file_path}' не найден.")

    # Парсинг кругов
    selected_laps = None
    if selected_laps_str.strip():
        try:
            selected_laps = [int(x.strip()) for x in selected_laps_str.split(',') if x.strip()]
        except ValueError:
            raise ValueError("Неверный формат кругов. Введите через запятую, например: 2, 3")

    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()

    header_line = ""
    skip_rows = 0
    for i, line in enumerate(lines):
        if 'timestamp' in line and 'fragment_id' in line:
            header_line = line.strip()
            skip_rows = i + 3
            break

    if skip_rows == 0:
        raise ValueError("Не удалось найти строку заголовка в файле.")

    raw_cols = re.split(r'[,\|;\t]+', header_line)
    raw_cols = [c.strip() for c in raw_cols if c.strip()]
    cols, seen = [], {}
    for c in raw_cols:
        if c in seen:
            seen[c] += 1
            cols.append(f"{c}_{seen[c]}")
        else:
            seen[c] = 0
            cols.append(c)

    df = pd.read_csv(file_path, sep=None, engine='python', skiprows=skip_rows, header=None)
    
    if len(df.columns) > len(cols):
        cols = cols + [f'extra_{i}' for i in range(len(df.columns) - len(cols))]
    elif len(df.columns) < len(cols):
        cols = cols[:len(df.columns)]
    df.columns = cols

    for col in df.columns:
        if df[col].dtype == object: df[col] = df[col].str.strip()

    numeric_cols = ['elapsed_time', 'distance_traveled', 'speed', 'lateral_acc', 'longitudinal_acc', 'timestamp']
    for col in numeric_cols:
        if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce')

    lap_col = 'lap_number'
    if lap_col not in df.columns:
        raise ValueError("В файле нет колонки 'lap_number'.")

    all_laps_in_df = sorted(df[lap_col].dropna().unique())
    lap_starts = df.groupby(lap_col)['elapsed_time'].min()
    lap_times = {}
    for i, lap in enumerate(all_laps_in_df):
        if i + 1 < len(all_laps_in_df):
            lap_times[lap] = lap_starts[all_laps_in_df[i+1]] - lap_starts[lap]
        else:
            lap_times[lap] = df[df[lap_col] == lap]['elapsed_time'].max() - lap_starts[lap]

    if selected_laps:
        laps = [lap for lap in all_laps_in_df if int(lap) in selected_laps]
        if not laps: raise ValueError(f"Круги {selected_laps} не найдены. Доступны: {all_laps_in_df}")
    else:
        laps = all_laps_in_df

    # Пиковые показатели
    max_speed_kmh = df['speed'].max() * 3.6
    min_speed_kmh = df['speed'].min() * 3.6
    max_long_g = df['longitudinal_acc'].max()
    min_long_g = df['longitudinal_acc'].min()
    max_lat_g = df['lateral_acc'].max()
    min_lat_g = df['lateral_acc'].min()

    laps_str = "\n".join([f"  Круг {int(lap)}: {fmt_time(lap_times.get(lap, float('nan')))}" for lap in laps])

    df['lap_distance'] = float('nan')
    for lap in laps:
        lap_mask = df[lap_col] == lap
        if lap_mask.any():
            min_dist = df.loc[lap_mask, 'distance_traveled'].min()
            df.loc[lap_mask, 'lap_distance'] = df.loc[lap_mask, 'distance_traveled'] - min_dist

    # Физика
    g, rho = 9.81, 1.225 
    avg_dt = df['timestamp'].diff().mean()
    if pd.isna(avg_dt) or avg_dt <= 0: avg_dt = 0.01 
    freq_hz = 1.0 / avg_dt
    
    smooth_window = int(smooth_time / avg_dt)
    if smooth_window < 3: smooth_window = 3
    if smooth_window % 2 == 0: smooth_window += 1 
    median_window = 7

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

    # Графики
    figs = []
    
    fig1, ax1 = plt.subplots(figsize=(12, 6)); figs.append(fig1)
    for lap in laps:
        lap_data = df[df[lap_col] == lap]
        ax1.plot(lap_data['lap_distance'], lap_data['speed'] * 3.6, label=f'Круг {int(lap)}')
    ax1.set_title('Скорость от дистанции круга'); ax1.set_xlabel('Дистанция, м'); ax1.set_ylabel('Скорость, км/ч')
    ax1.grid(True, which='both', linestyle='--', linewidth=0.5, alpha=0.7); ax1.minorticks_on()
    make_legend_interactive(fig1, ax1); fig1.tight_layout(pad=2.0)

    fig2, ax2 = plt.subplots(figsize=(12, 6)); figs.append(fig2)
    for lap in laps:
        lap_data = df[df[lap_col] == lap]
        ax2.plot(lap_data['lap_distance'], lap_data['longitudinal_acc'], label=f'Продольное (Круг {int(lap)})', linestyle='--')
        ax2.plot(lap_data['lap_distance'], lap_data['lateral_acc'], label=f'Поперечное (Круг {int(lap)})', linestyle='-')
    ax2.set_title('Ускорения (G)'); ax2.set_xlabel('Дистанция, м'); ax2.set_ylabel('Ускорение, G')
    ax2.axhline(0, color='black', linewidth=1)
    ax2.grid(True, which='both', linestyle='--', linewidth=0.5, alpha=0.7); ax2.minorticks_on()
    make_legend_interactive(fig2, ax2); fig2.tight_layout(pad=2.0)

    fig3, ax3 = plt.subplots(figsize=(8, 8)); figs.append(fig3)
    for lap in laps:
        lap_data = df[df[lap_col] == lap]
        ax3.plot(lap_data['lateral_acc'], lap_data['longitudinal_acc'], marker='o', linestyle='', markersize=3, alpha=0.3, label=f'Круг {int(lap)}')
    ax3.set_title('Диаграмма G-G'); ax3.set_xlabel('Поперечное G (Влево/Вправо)'); ax3.set_ylabel('Продольное G (Тормож/Разгон)')
    ax3.axhline(0, color='black', linewidth=1); ax3.axvline(0, color='black', linewidth=1)
    ax3.set_aspect('equal', adjustable='box')
    ax3.grid(True, which='both', linestyle='--', linewidth=0.5, alpha=0.7); ax3.minorticks_on()
    make_legend_interactive(fig3, ax3); fig3.tight_layout(pad=2.0)

    fig4, ax4 = plt.subplots(figsize=(12, 6)); figs.append(fig4)
    for lap in laps:
        lap_data = df[df[lap_col] == lap]
        ax4.plot(lap_data['lap_distance'], lap_data['power_engine_hp'].clip(lower=0, upper=400), label=f'Круг {int(lap)}')
    ax4.set_title(f'Мощность ДВИГАТЕЛЯ (Масса: {mass} кг, КПД: {efficiency*100}%)'); ax4.set_xlabel('Дистанция, м'); ax4.set_ylabel('Мощность, л.с.')
    ax4.grid(True, which='both', linestyle='--', linewidth=0.5, alpha=0.7); ax4.minorticks_on()
    make_legend_interactive(fig4, ax4); fig4.tight_layout(pad=2.0)

    if gear_ratio > 0:
        fig5, ax5 = plt.subplots(figsize=(12, 6)); figs.append(fig5)
        for lap in laps:
            lap_data = df[df[lap_col] == lap]
            ax5.plot(lap_data['lap_distance'], lap_data['torque_engine_nm'].clip(lower=-100, upper=400), label=f'Круг {int(lap)}')
        ax5.set_title(f'Момент ДВИГАТЕЛЯ (Gear Ratio: {gear_ratio})'); ax5.set_xlabel('Дистанция, м'); ax5.set_ylabel('Момент, Нм')
        ax5.grid(True, which='both', linestyle='--', linewidth=0.5, alpha=0.7); ax5.minorticks_on()
        make_legend_interactive(fig5, ax5); fig5.tight_layout(pad=2.0)

    # PDF Отчет
    report_filename = f"Отчет_{os.path.basename(file_path).replace('.csv', '')}.pdf"
    with PdfPages(report_filename) as pdf:
        fig_text, ax_text = plt.subplots(figsize=(8.27, 11.69))
        ax_text.axis('off')
        report_text = (
            "ОТЧЕТ ПО ТЕЛЕМЕТРИИ\n==================================================\n\n"
            f"Исходный файл: {os.path.basename(file_path)}\nДата анализа: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            "--- ИНФОРМАЦИЯ О ЗАЕЗДЕ ---\n"
            f"Трасса: {track}\nПилот: {driver}\nПогодные условия: {weather}\n\n"
            "--- ПИКОВЫЕ ПОКАЗАТЕЛИ ---\n"
            f"Макс. скорость:     {max_speed_kmh:.1f} км/ч\n"
            f"Макс. продольное G: {max_long_g:.2f} G (Разгон)\n"
            f"Мин. продольное G:  {min_long_g:.2f} G (Торможение)\n"
            f"Макс. поперечное G: {max_lat_g:.2f} G (Вправо)\n"
            f"Мин. поперечное G:  {min_lat_g:.2f} G (Влево)\n\n"
            "--- ВРЕМЕНА КРУГОВ ---\n"
            f"{laps_str}\n\n"
            "--- ВХОДНЫЕ ПАРАМЕТРЫ ---\n"
            f"Профиль автомобиля: {car_name if car_name else 'вручную (без профиля)'}\n"
            f"Частота датчиков: ~{freq_hz:.1f} Гц\n"
            f"Масса автомобиля: {mass} кг\nАэродинамика (Cd*A): {cd_a}\nКоэфф. качения (Crr): {crr}\n"
            f"Радиус колеса: {r_wheel} м\nКПД трансмиссии: {efficiency * 100} %\n"
            f"Передаточное число: {gear_ratio if gear_ratio > 0 else 'Не указано'}\n"
            f"Окно сглаживания: {smooth_time} сек (~{smooth_window} точек)\n\n"
            "--- ВНИМАНИЕ ---\n"
            "Графики МОЩНОСТИ и МОМЕНТА двигателя корректны ТОЛЬКО\nна участках, где автомобиль двигался на передаче,\nуказанной в 'Передаточное число'.\n\n"
            "--- МЕТОДОЛОГИЯ ---\n"
            "Учитываются силы: инерции, аэродинамики, качения\n"
            "Мощность = (F_ин + F_аэро + F_кач) * V / КПД\n"
            "Момент = (F_ин + F_аэро + F_кач) * R / (GearRatio * КПД)\n"
        )
        ax_text.text(0.05, 0.95, report_text, va='top', ha='left', family='monospace', fontsize=11, wrap=True)
        pdf.savefig(fig_text, bbox_inches='tight')
        plt.close(fig_text)
        for fig in figs:
            pdf.savefig(fig, bbox_inches='tight')
            
    return report_filename, laps_str

# ==========================================
# ГРАФИЧЕСКИЙ ИНТЕРФЕЙС (Tkinter)
# ==========================================

class TelemetryApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Анализатор телеметрии RaceChrono")
        self.root.geometry("1024x900")
        self.root.resizable(True, True)

        # Переменные
        self.filepath = tk.StringVar()
        self.laps = tk.StringVar()
        self.mass = tk.DoubleVar(value=1250)
        self.cd_a = tk.DoubleVar(value=0.65)
        self.crr = tk.DoubleVar(value=0.012)
        self.r_wheel = tk.DoubleVar(value=0.288)
        self.efficiency = tk.DoubleVar(value=0.90)
        self.gear_ratio = tk.DoubleVar(value=0)
        self.smooth_time = tk.DoubleVar(value=0.8)
        self.driver = tk.StringVar()
        self.track = tk.StringVar(value="Автодром Санкт-Петербург")
        self.weather = tk.StringVar(value="Сухо")

        # Профиль автомобиля (выпадающий список)
        self.car_var = tk.StringVar(value=MANUAL)
        self._profile_map = {}          # отображаемое имя -> путь к .ini
        self._loading_profile = False   # защита от срабатывания trace при загрузке профиля

        self.build_ui()

        # Ручное редактирование поля сбрасывает выбранный профиль на 'вручную'
        for var in (self.mass, self.cd_a, self.crr, self.r_wheel, self.efficiency, self.gear_ratio):
            var.trace_add("write", self._on_field_edited)

    def build_ui(self):
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Выбор файла
        file_frame = ttk.LabelFrame(main_frame, text="Файл лога RaceChrono", padding=10)
        file_frame.pack(fill=tk.X, pady=5)
        ttk.Entry(file_frame, textvariable=self.filepath, width=45).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(file_frame, text="Обзор...", command=self.browse_file).pack(side=tk.LEFT)

        # Параметры заезда
        session_frame = ttk.LabelFrame(main_frame, text="Параметры заезда", padding=10)
        session_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(session_frame, text="Круги (через запятую, пусто = все):").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Entry(session_frame, textvariable=self.laps, width=30).grid(row=0, column=1, pady=2)
        
        ttk.Label(session_frame, text="Пилот:").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Entry(session_frame, textvariable=self.driver, width=30).grid(row=1, column=1, pady=2)
        
        ttk.Label(session_frame, text="Трасса:").grid(row=2, column=0, sticky=tk.W, pady=2)
        ttk.Entry(session_frame, textvariable=self.track, width=30).grid(row=2, column=1, pady=2)
        
        ttk.Label(session_frame, text="Погода:").grid(row=3, column=0, sticky=tk.W, pady=2)
        ttk.Entry(session_frame, textvariable=self.weather, width=30).grid(row=3, column=1, pady=2)

        # Параметры авто
        car_frame = ttk.LabelFrame(main_frame, text="Параметры автомобиля", padding=10)
        car_frame.pack(fill=tk.X, pady=5)

        ttk.Label(car_frame, text="Профиль:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.car_combo = ttk.Combobox(car_frame, textvariable=self.car_var, state="readonly", width=42)
        self.car_combo.grid(row=0, column=1, columnspan=2, sticky=tk.W, pady=2)
        self.car_combo.bind("<<ComboboxSelected>>", self.on_car_selected)
        ttk.Button(car_frame, text="Обновить список", command=self.refresh_car_profiles).grid(row=0, column=3, padx=5)
        self.refresh_car_profiles()

        fields = [
            ("Масса (кг):", self.mass), ("Aэродинамика (Cd*A):", self.cd_a),
            ("Коэфф. качения (Crr):", self.crr), ("Радиус колеса (м):", self.r_wheel),
            ("КПД трансмиссии (0-1):", self.efficiency), ("Передат. число (0=нет):", self.gear_ratio),
            ("Сглаживание (сек):", self.smooth_time)
        ]
        
        for i, (label, var) in enumerate(fields, start=1):
            ttk.Label(car_frame, text=label).grid(row=i, column=0, sticky=tk.W, pady=2)
            ttk.Entry(car_frame, textvariable=var, width=15).grid(row=i, column=1, sticky=tk.W, pady=2)

        # Кнопка запуска
        run_btn = ttk.Button(main_frame, text="Анализировать и построить графики", command=self.run_analysis)
        run_btn.pack(pady=20)

        # Статус
        self.status_label = ttk.Label(main_frame, text="Готово к работе", font=("Arial", 10, "italic"))
        self.status_label.pack()

    def refresh_car_profiles(self):
        """Перечитывает папку cars/ и обновляет выпадающий список профилей."""
        self._profile_map = {name: path for path, name in list_car_profiles()}
        names = [MANUAL] + sorted(self._profile_map)
        current = self.car_var.get()
        self.car_combo["values"] = names
        # Не сбрасывать текущий выбор, если профиль все еще существует
        if current not in names:
            self.car_var.set(MANUAL)

    def on_car_selected(self, event=None):
        """Загружает выбранный профиль в поля параметров."""
        sel = self.car_var.get()
        if sel == MANUAL or sel not in self._profile_map:
            return
        try:
            prof = load_car_profile(self._profile_map[sel])
        except CarProfileError as e:
            messagebox.showerror("Ошибка профиля автомобиля", str(e))
            self.car_var.set(MANUAL)
            return

        self._loading_profile = True
        try:
            self.mass.set(prof["mass"])
            self.cd_a.set(prof["cd_a"])
            self.crr.set(prof["crr"])
            self.r_wheel.set(prof["r_wheel"])
            self.efficiency.set(prof["efficiency"])
            self.gear_ratio.set(prof["gear_ratio"])
            self.status_label.config(text=f"Профиль загружен: {prof['name']}")
        except tk.TclError as e:
            messagebox.showerror("Ошибка профиля", f"Не удалось применить профиль: {e}")
            self.car_var.set(MANUAL)
        finally:
            # after_idle: trace не должен увидеть программное изменение полей
            self.root.after_idle(setattr, self, "_loading_profile", False)

    def _on_field_edited(self, *_):
        """Ручное редактирование поля сбрасывает выбор профиля на 'вручную'."""
        if not self._loading_profile and self.car_var.get() != MANUAL:
            self.car_var.set(MANUAL)

    def _get_float(self, var, label):
        """Читает числовое поле с русским сообщением об ошибке."""
        try:
            return var.get()
        except tk.TclError:
            raise ValueError(f"Некорректное число в поле '{label}'.")

    def browse_file(self):
        filename = filedialog.askopenfilename(
            title="Выберите файл телеметрии",
            filetypes=[("CSV файлы", "*.csv"), ("Все файлы", "*.*")]
        )
        if filename:
            self.filepath.set(filename)

    def run_analysis(self):
        filepath = self.filepath.get()
        if not filepath:
            messagebox.showwarning("Ошибка", "Пожалуйста, выберите файл лога.")
            return

        self.status_label.config(text="Анализирую данные... Это может занять несколько секунд.")
        self.root.update()

        try:
            sel = self.car_var.get()
            car_name = sel if sel != MANUAL and sel in self._profile_map else None
            report_file, laps_info = analyze_telemetry(
                file_path=filepath,
                selected_laps_str=self.laps.get(),
                mass=self._get_float(self.mass, "Масса (кг)"),
                cd_a=self._get_float(self.cd_a, "Аэродинамика (Cd*A)"),
                crr=self._get_float(self.crr, "Коэфф. качения (Crr)"),
                r_wheel=self._get_float(self.r_wheel, "Радиус колеса (м)"),
                efficiency=self._get_float(self.efficiency, "КПД трансмиссии (0-1)"),
                gear_ratio=self._get_float(self.gear_ratio, "Передат. число (0=нет)"),
                driver=self.driver.get(),
                track=self.track.get(),
                weather=self.weather.get(),
                smooth_time=self._get_float(self.smooth_time, "Сглаживание (сек)"),
                car_name=car_name
            )
            self.status_label.config(text=f"Готово! Отчет сохранен: {report_file}")
            messagebox.showinfo("Успех", f"Анализ завершен!\nОтчет сохранен в файл:\n{report_file}\n\nВремена кругов:\n{laps_info}")
        except Exception as e:
            self.status_label.config(text="Ошибка!")
            messagebox.showerror("Ошибка анализа", str(e))

if __name__ == "__main__":
    root = tk.Tk()
    app = TelemetryApp(root)
    root.mainloop()