"""Анализ телеметрии RaceChrono — графический интерфейс (Tkinter).

Логика анализа — в пакете lib/. Здесь только ввод параметров и отображение результата.
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from car_profile import MANUAL, CarProfileError, list_car_profiles, load_car_profile
from lib import AnalysisConfig, run_analysis
from lib.telemetry_io import compute_lap_times, format_lap_time, read_telemetry


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

        # Таблица кругов (заполняется после выбора файла)
        self._lap_vars = {}    # номер круга -> tk.BooleanVar (чекбокс)

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
        path_entry = ttk.Entry(file_frame, textvariable=self.filepath, width=45)
        path_entry.pack(side=tk.LEFT, padx=(0, 5))
        path_entry.bind("<FocusOut>", lambda e: self.refresh_laps_table())
        path_entry.bind("<Return>", lambda e: self.refresh_laps_table())
        ttk.Button(file_frame, text="Обзор...", command=self.browse_file).pack(side=tk.LEFT)

        # Параметры заезда
        session_frame = ttk.LabelFrame(main_frame, text="Параметры заезда", padding=10)
        session_frame.pack(fill=tk.X, pady=5)

        ttk.Label(session_frame, text="Пилот:").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Entry(session_frame, textvariable=self.driver, width=30).grid(row=1, column=1, pady=2)

        ttk.Label(session_frame, text="Трасса:").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Entry(session_frame, textvariable=self.track, width=30).grid(row=1, column=1, pady=2)

        ttk.Label(session_frame, text="Погода:").grid(row=2, column=0, sticky=tk.W, pady=2)
        ttk.Entry(session_frame, textvariable=self.weather, width=30).grid(row=2, column=1, pady=2)

        # Таблица кругов (появляется после выбора файла)
        laps_frame = ttk.LabelFrame(main_frame, text="Круги в файле (отметьте нужные)", padding=10)
        laps_frame.pack(fill=tk.X, pady=5)

        self.laps_hint = ttk.Label(laps_frame, text="Файл не выбран — круги появятся после выбора CSV.",
                                   foreground="grey")
        self.laps_hint.pack(anchor=tk.W)

        self.laps_table = ttk.Frame(laps_frame)
        self.laps_table.pack(fill=tk.X, anchor=tk.W)
        # Кнопки «Все/Снять» создаются при заполнении таблицы
        self.laps_buttons = ttk.Frame(laps_frame)
        self.laps_buttons.pack(anchor=tk.W, pady=(5, 0))

        ttk.Button(self.laps_buttons, text="Отметить все", command=self.check_all_laps).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(self.laps_buttons, text="Снять все", command=self.uncheck_all_laps).pack(side=tk.LEFT)

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
            ttk.Entry(car_frame, textvariable=var, width=15).grid(row=i, column=1, pady=2)

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
            self.refresh_laps_table()

    def refresh_laps_table(self):
        """Сканирует выбранный файл и строит таблицу кругов с чекбоксами и временами."""
        for w in self.laps_table.winfo_children():
            w.destroy()
        self._lap_vars = {}

        filepath = self.filepath.get().strip()
        if not filepath:
            self.laps_hint.config(text="Файл не выбран — круги появятся после выбора CSV.")
            return

        self.laps_hint.config(text=f"Читаю круги из {filepath}...")
        self.root.update()

        try:
            df = read_telemetry(filepath)
            all_laps, lap_times = compute_lap_times(df)
        except (FileNotFoundError, ValueError) as e:
            self.laps_hint.config(text=f"Не удалось прочитать файл: {e}", foreground="red")
            self.laps_buttons.pack_forget()
            return

        self.laps_hint.config(
            text=f"Найдено кругов: {len(all_laps)}. Отметьте интересные — неотмеченные будут скрыты на графиках.",
            foreground="grey"
        )
        self.laps_buttons.pack(anchor=tk.W, pady=(5, 0))

        # Таблица: строки по кругам, до 8 колонок с переносом
        for i, lap in enumerate(all_laps):
            var = tk.BooleanVar(value=True)   # по умолчанию все отмечены (= текущее поведение «все круги»)
            self._lap_vars[int(lap)] = var
            row, col = divmod(i, 8)
            cell = ttk.Frame(self.laps_table)
            cell.grid(row=row, column=col, sticky=tk.W, padx=(0, 15), pady=2)
            ttk.Checkbutton(cell, text=f"Круг {int(lap)}", variable=var).pack(side=tk.LEFT)
            ttk.Label(cell, text=format_lap_time(lap_times.get(lap, float("nan"))),
                      foreground="grey").pack(side=tk.LEFT, padx=(4, 0))

    def check_all_laps(self):
        for var in self._lap_vars.values():
            var.set(True)

    def uncheck_all_laps(self):
        for var in self._lap_vars.values():
            var.set(False)

    def selected_laps(self):
        """Список отмеченных кругов; None = таблица еще не построена (файл не выбран)."""
        if not self._lap_vars:
            return None
        return [lap for lap, var in self._lap_vars.items() if var.get()]

    def run_analysis(self):
        filepath = self.filepath.get()
        if not filepath:
            messagebox.showwarning("Ошибка", "Пожалуйста, выберите файл лога.")
            return

        self.status_label.config(text="Анализирую данные... Это может занять несколько секунд.")
        self.root.update()

        sel = self.car_var.get()
        laps = self.selected_laps()
        if laps == []:
            messagebox.showwarning("Ошибка", "Отметьте хотя бы один круг в таблице кругов.")
            return
        try:
            cfg = AnalysisConfig(
                file_path=filepath,
                laps=laps,
                mass=self._get_float(self.mass, "Масса (кг)"),
                cd_a=self._get_float(self.cd_a, "Аэродинамика (Cd*A)"),
                crr=self._get_float(self.crr, "Коэфф. качения (Crr)"),
                r_wheel=self._get_float(self.r_wheel, "Радиус колеса (м)"),
                efficiency=self._get_float(self.efficiency, "КПД трансмиссии (0-1)"),
                gear_ratio=self._get_float(self.gear_ratio, "Передат. число (0=нет)"),
                smooth_time=self._get_float(self.smooth_time, "Сглаживание (сек)"),
                driver=self.driver.get(),
                track=self.track.get(),
                weather=self.weather.get(),
                car_label=sel if sel != MANUAL and sel in self._profile_map else "вручную (без профиля)",
            )
            result = run_analysis(cfg)   # progress не передаем: GUI молчит
            self.status_label.config(text=f"Готово! Отчет сохранен: {result.report_path}")
            messagebox.showinfo(
                "Успех",
                f"Анализ завершен!\nОтчет сохранен в файл:\n{result.report_path}\n\nВремена кругов:\n{result.laps_summary}"
            )
        except (ValueError, FileNotFoundError, CarProfileError) as e:
            self.status_label.config(text="Ошибка!")
            messagebox.showerror("Ошибка анализа", str(e))


if __name__ == "__main__":
    root = tk.Tk()
    app = TelemetryApp(root)
    root.mainloop()
