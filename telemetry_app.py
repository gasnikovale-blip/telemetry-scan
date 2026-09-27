"""Анализ телеметрии RaceChrono — графический интерфейс (Tkinter).

Логика анализа — в пакете lib/. Здесь только ввод параметров и отображение результата.
Внешний вид: встроенная тема 'clam' с ручной настройкой стилей (без сторонних пакетов).
"""
import math
import statistics
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

from car_profile import MANUAL, CarProfileError, list_car_profiles, load_car_profile
from lib import AnalysisConfig, run_analysis
from lib.telemetry_io import compute_lap_times, format_lap_time_fixed, read_telemetry


# ==========================================
# ПАЛИТРА И ШРИФТЫ (единый вид всех виджетов)
# ==========================================

BG = "#f4f5f7"           # фон окна
CARD = "#ffffff"         # фон карточек (LabelFrame)
BORDER = "#d9dce3"       # рамки полей ввода и карточек
ACCENT = "#2563eb"       # основной синий (кнопка "Анализировать", фокус полей)
ACCENT_HOVER = "#3b82f6"
ACCENT_ACTIVE = "#1d4ed8"
TEXT = "#1f2937"         # основной текст
MUTED = "#6b7280"        # вторичный текст (подсказки, статус)
SUCCESS = "#15803d"      # успешный статус и лучший круг
ERROR = "#dc2626"        # ошибки
ZEBRA = "#eef1f6"        # полоска нечетных строк таблицы кругов
BUTTON_BG = "#e4e7ec"    # обычная кнопка
BUTTON_ACTIVE = "#d3d7df"

GLYPH_ON, GLYPH_OFF = "☑", "☐"   # отметка круга в таблице


class TelemetryApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Анализатор телеметрии RaceChrono")
        self.root.geometry("1440x1000")
        # Минимум подбирается так, чтобы ничего не обрезалось: ниже по ширине —
        # колонка 'К лучшему', ниже по высоте — поля левой колонки
        self.root.minsize(1250, 990)
        self.root.resizable(True, True)
        self._setup_style()

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
        self._lap_checked = {}   # номер круга -> отмечен ли
        self._lap_rows = {}      # номер круга -> iid строки в Treeview
        self._lap_times = {}     # номер круга -> время в секундах
        self._lap_best = None    # номер лучшего круга (None = нет полных кругов)
        self._sort_col = "lap"   # текущая сортировка таблицы
        self._sort_desc = False

        # Профиль автомобиля (выпадающий список)
        self.car_var = tk.StringVar(value=MANUAL)
        self._profile_map = {}          # отображаемое имя -> путь к .ini
        self._loading_profile = False   # защита от срабатывания trace при загрузке профиля

        self.build_ui()

        # Ручное редактирование поля сбрасывает выбранный профиль на 'вручную'
        for var in (self.mass, self.cd_a, self.crr, self.r_wheel, self.efficiency, self.gear_ratio):
            var.trace_add("write", self._on_field_edited)

    # ------------------------------------------
    # Стиль
    # ------------------------------------------

    def _setup_style(self):
        """Тема 'clam' + единая палитра: плоские кнопки, карточки, таблица без рамок.

        Размер шрифта не задаем: системный шрифт по умолчанию уже согласован
        с масштабом экрана (важно для HiDPI), у него берутся только жирные варианты.
        """
        base = tkfont.nametofont("TkDefaultFont")
        self.font_bold = base.copy()
        self.font_bold.configure(weight="bold")
        self.font_big = base.copy()
        self.font_big.configure(weight="bold", size=base.cget("size") + 2)
        # Моноширинный шрифт таблицы кругов: цифры одной ширины, разделители
        # времени (мин:сек.доли) выстроены по вертикали
        self.font_mono = tkfont.nametofont("TkFixedFont").copy()
        self.font_mono.configure(size=base.cget("size"))
        self.font_mono_bold = self.font_mono.copy()
        self.font_mono_bold.configure(weight="bold")

        style = ttk.Style(self.root)
        style.theme_use("clam")

        style.configure(".", background=BG, foreground=TEXT, borderwidth=0, focusthickness=0)
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD)
        # Внутри карточек фон белый, снаружи (статус, низ окна) — серый
        style.configure("TLabel", background=CARD, foreground=TEXT)
        style.configure("Muted.TLabel", background=CARD, foreground=MUTED)
        style.configure("Status.TLabel", background=BG, foreground=MUTED)

        style.configure(
            "TLabelframe", background=CARD, bordercolor=BORDER,
            relief="solid", borderwidth=1,
        )
        style.configure(
            "TLabelframe.Label", background=CARD, foreground=ACCENT,
            font=self.font_bold,
        )

        entry_colors = {"fieldbackground": CARD, "background": CARD, "bordercolor": BORDER,
                        "lightcolor": BORDER, "darkcolor": BORDER, "insertcolor": TEXT,
                        "padding": (6, 2)}
        style.configure("TEntry", **entry_colors)
        style.map("TEntry",
                  bordercolor=[("focus", ACCENT)],
                  lightcolor=[("focus", ACCENT)],
                  darkcolor=[("focus", ACCENT)])
        style.configure("TCombobox", arrowsize=14, **entry_colors)
        style.map("TCombobox",
                  bordercolor=[("focus", ACCENT)],
                  lightcolor=[("focus", ACCENT)],
                  darkcolor=[("focus", ACCENT)],
                  fieldbackground=[("readonly", CARD)],
                  foreground=[("readonly", TEXT)])
        # Выпадающий список комбобокса рисуется вне темы — задается через option_add
        self.root.option_add("*TCombobox*Listbox.background", CARD)
        self.root.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.root.option_add("*TCombobox*Listbox.selectForeground", CARD)
        self.root.option_add("*TCombobox*Listbox.font", base)

        style.configure("TButton", padding=(12, 6), background=BUTTON_BG, foreground=TEXT)
        style.map("TButton",
                  background=[("pressed", BUTTON_ACTIVE), ("active", BUTTON_ACTIVE)],
                  bordercolor=[("pressed", BUTTON_ACTIVE)])
        style.configure(
            "Accent.TButton", background=ACCENT, foreground=CARD,
            font=self.font_big, padding=(22, 9),
        )
        style.map("Accent.TButton",
                  background=[("disabled", "#93b4f5"), ("pressed", ACCENT_ACTIVE),
                              ("active", ACCENT_HOVER)],
                  foreground=[("disabled", "#e8edf7")])

        # Высота строки таблицы — от реальной метрики системного шрифта
        row_height = max(base.metrics("linespace"),
                         self.font_mono.metrics("linespace")) + 8
        style.configure("Treeview", background=CARD, fieldbackground=CARD,
                        foreground=TEXT, rowheight=row_height, borderwidth=0,
                        font=self.font_mono)
        style.configure("Treeview.Heading", background=CARD, foreground=MUTED,
                        font=self.font_bold, padding=(6, 6), relief="flat")
        style.map("Treeview.Heading", background=[("active", CARD)])
        style.map("Treeview",
                  background=[("selected", ACCENT)],
                  foreground=[("selected", CARD)])

    # ------------------------------------------
    # Компоновка
    # ------------------------------------------

    def build_ui(self):
        main_frame = ttk.Frame(self.root, padding=12)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Выбор файла
        file_frame = ttk.LabelFrame(main_frame, text="Файл лога RaceChrono", padding=10)
        file_frame.pack(fill=tk.X)
        file_frame.columnconfigure(0, weight=1)
        path_entry = ttk.Entry(file_frame, textvariable=self.filepath)
        path_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        path_entry.bind("<Return>", lambda e: self.refresh_laps_table())
        ttk.Button(file_frame, text="Обзор...", command=self.browse_file).grid(row=0, column=1)

        # Две колонки: слева параметры, справа таблица кругов (забирает все свободное место)
        columns = ttk.Frame(main_frame)
        columns.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

        # Ширина левой колонки — естественная (по подписям полей), зависит от системного шрифта
        left_col = ttk.Frame(columns)
        left_col.pack(side=tk.LEFT, fill=tk.Y)

        self._build_session_group(left_col)
        self._build_profile_group(left_col)
        self._build_car_group(left_col)
        self._build_laps_group(columns)

        # Нижняя панель: главная кнопка + статус всегда на виду
        bottom = ttk.Frame(main_frame)
        bottom.pack(fill=tk.X, pady=(12, 0))
        run_btn = ttk.Button(bottom, text="Анализировать и построить графики",
                             style="Accent.TButton", command=self.run_analysis)
        run_btn.pack()
        self.status_label = ttk.Label(bottom, text="Готово к работе", style="Status.TLabel")
        self.status_label.pack(pady=(6, 0))

    def _build_session_group(self, parent):
        session_frame = ttk.LabelFrame(parent, text="Параметры заезда", padding=10)
        session_frame.pack(fill=tk.X)
        session_frame.columnconfigure(1, weight=1)

        for row, (label, var) in enumerate(
                (("Пилот:", self.driver), ("Трасса:", self.track), ("Погода:", self.weather))):
            ttk.Label(session_frame, text=label).grid(row=row, column=0, sticky=tk.W, pady=3, padx=(0, 8))
            ttk.Entry(session_frame, textvariable=var, width=14).grid(row=row, column=1, sticky="ew", pady=3)

    def _build_profile_group(self, parent):
        """Отдельная группа для выбора профиля: имя автомобиля длинное и занимает всю ширину."""
        profile_frame = ttk.LabelFrame(parent, text="Профиль автомобиля", padding=10)
        profile_frame.pack(fill=tk.X, pady=(10, 0))
        profile_frame.columnconfigure(0, weight=1)

        self.car_combo = ttk.Combobox(profile_frame, textvariable=self.car_var,
                                      state="readonly", width=14)
        self.car_combo.grid(row=0, column=0, sticky="ew")
        self.car_combo.bind("<<ComboboxSelected>>", self.on_car_selected)
        ttk.Button(profile_frame, text="Обновить список профилей",
                   command=self.refresh_car_profiles).grid(row=1, column=0, sticky=tk.W, pady=(6, 0))
        self.refresh_car_profiles()

    def _build_car_group(self, parent):
        car_frame = ttk.LabelFrame(parent, text="Параметры автомобиля", padding=10)
        car_frame.pack(fill=tk.X, pady=(10, 0))
        car_frame.columnconfigure(1, weight=1, minsize=140)

        fields = [
            ("Масса, кг:", self.mass),
            ("Cd·A (аэродинамика):", self.cd_a),
            ("Crr (качение):", self.crr),
            ("Радиус колеса, м:", self.r_wheel),
            ("КПД трансмиссии (0–1):", self.efficiency),
            ("Передат. число (0=нет):", self.gear_ratio),
            ("Сглаживание, с:", self.smooth_time),
        ]
        for row, (label, var) in enumerate(fields):
            ttk.Label(car_frame, text=label).grid(row=row, column=0, sticky=tk.W, pady=3, padx=(0, 8))
            ttk.Entry(car_frame, textvariable=var, width=10).grid(row=row, column=1, sticky="ew", pady=3)

    def _build_laps_group(self, parent):
        laps_frame = ttk.LabelFrame(parent, text="Круги в файле (отметьте нужные)", padding=10)
        laps_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0))

        self.laps_hint = ttk.Label(laps_frame, text="Файл не выбран — круги появятся после выбора CSV.",
                                   style="Muted.TLabel")
        self.laps_hint.pack(anchor=tk.W, fill=tk.X)
        # Перенос текста — по фактической ширине метки: подсказка перестраивается
        # при любом размере окна, а не по жестко заданной длине строки
        self.laps_hint.bind("<Configure>", self._on_hint_resize)

        table_row = ttk.Frame(laps_frame, style="Card.TFrame")
        table_row.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self.laps_tree = ttk.Treeview(
            table_row, columns=("on", "lap", "time", "delta"), show="headings",
            selectmode="none", height=10,
        )
        scrollbar = ttk.Scrollbar(table_row, orient=tk.VERTICAL, command=self.laps_tree.yview)
        self.laps_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.laps_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Время круга: моноширинный формат 'M:SS.mmm' (единицы — в заголовке),
        # выравнивание вправо, чтобы разделители строк шли по одной вертикали
        headings = {"on": "", "lap": "Круг", "time": "Время (мин:сек)", "delta": "К лучшему"}
        anchors = {"on": tk.CENTER, "lap": tk.CENTER, "time": tk.E, "delta": tk.E}
        widths = {"on": 44, "lap": 90, "time": 170, "delta": 110}
        # Ширина колонок — не уже их заголовков (двухстрочный заголовок ttk обрезает
        # по высоте, поэтому заголовки пишем в одну строку и даем колонке место)
        for col, text in headings.items():
            if text:
                widths[col] = max(widths[col], self.font_bold.measure(text) + 18)
        # и не уже данных: 'Круг 00' в моноширинном шрифте шире, чем в обычном
        widths["lap"] = max(widths["lap"], self.font_mono.measure("Круг 00") + 16)
        for col, text in headings.items():
            self.laps_tree.heading(col, text=text,
                                   command=(lambda c=col: self._sort_by(c)) if col != "on" else "")
            # minwidth: при нехватке ширины колонки не должны сжиматься до нечитаемых
            self.laps_tree.column(col, width=widths[col], minwidth=widths[col],
                                  anchor=anchors[col], stretch=(col != "on"))

        # Клик по строке переключает отметку, колесо прокручивает таблицу
        self.laps_tree.bind("<Button-1>", self._on_lap_click)
        self.laps_tree.bind("<space>", self._on_lap_space)
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.laps_tree.bind(seq, self._on_laps_wheel)
        # odd — полоска нечетных строк; best — лучший круг; dim — неотмеченные строки бледнее
        self.laps_tree.tag_configure("odd", background=ZEBRA)
        self.laps_tree.tag_configure("best", foreground=SUCCESS, font=self.font_mono_bold)
        self.laps_tree.tag_configure("dim", foreground=MUTED)

        buttons_row = ttk.Frame(laps_frame, style="Card.TFrame")
        buttons_row.pack(anchor=tk.W, pady=(6, 0))
        ttk.Button(buttons_row, text="Отметить все", command=self.check_all_laps).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(buttons_row, text="Снять все", command=self.uncheck_all_laps).pack(side=tk.LEFT)
        self.laps_counter = ttk.Label(buttons_row, style="Muted.TLabel")
        self.laps_counter.pack(side=tk.LEFT, padx=(10, 0))

    # ------------------------------------------
    # Таблица кругов
    # ------------------------------------------

    def _on_laps_wheel(self, event):
        if event.num == 4 or event.delta > 0:
            self.laps_tree.yview_scroll(-1, "units")
        elif event.num == 5 or event.delta < 0:
            self.laps_tree.yview_scroll(1, "units")

    def _on_hint_resize(self, event):
        """Задает перенос строк подсказки по текущей ширине метки."""
        if event.width > 1:   # 1 — размер до первой раскладки, переносить по нему нельзя
            self.laps_hint.configure(wraplength=event.width - 4)

    def _row_tags(self, lap, pos):
        """Порядок тегов задает приоритет: неотмеченность важнее цвета лучшего круга."""
        tags = []
        if not self._lap_checked[lap]:
            tags.append("dim")
        if lap == self._lap_best:
            tags.append("best")
        if pos % 2:
            tags.append("odd")
        return tuple(tags)

    def _delta_value(self, lap):
        """Отставание от лучшего круга числом; None — неполный круг или обрывок быстрее лучшего."""
        t = self._lap_times.get(lap)
        if t is None or math.isnan(t) or t < 0 or self._lap_best is None:
            return None
        if lap == self._lap_best:
            return 0.0
        d = t - self._lap_times[self._lap_best]
        return None if d < 0 else d

    def _delta_text(self, lap):
        """Отставание от лучшего круга: 'лучший', '+0.879' или '—' если не сравнивается."""
        d = self._delta_value(lap)
        if d is None:
            return "—"
        if lap == self._lap_best:
            return "лучший"
        return f"+{d:.3f}"

    def _lap_sort_value(self, lap, col):
        """Число для сортировки; неполные круги уходят в конец списка."""
        if col == "lap":
            return lap
        if col == "time":
            t = self._lap_times.get(lap)
            return math.inf if (t is None or math.isnan(t) or t < 0) else t
        d = self._delta_value(lap)
        return math.inf if d is None else d

    def _sorted_laps(self):
        return sorted(self._lap_checked,
                      key=lambda lap: self._lap_sort_value(lap, self._sort_col),
                      reverse=self._sort_desc)

    def _sort_by(self, col):
        """Клик по заголовку: повторный клик меняет направление."""
        if self._sort_col == col:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_col, self._sort_desc = col, False
        self._render_rows()

    def _render_rows(self):
        """Перестраивает строки таблицы в текущем порядке сортировки."""
        self.laps_tree.delete(*self.laps_tree.get_children())
        self._lap_rows = {}
        for pos, lap in enumerate(self._sorted_laps()):
            values = (GLYPH_ON if self._lap_checked[lap] else GLYPH_OFF,
                      f"Круг {lap}", format_lap_time_fixed(self._lap_times.get(lap, float("nan"))),
                      self._delta_text(lap))
            iid = str(lap)
            self.laps_tree.insert("", tk.END, iid=iid, values=values, tags=self._row_tags(lap, pos))
            self._lap_rows[lap] = iid
        self._update_headings()
        self._update_lap_counter()

    def _update_headings(self):
        base = {"lap": "Круг", "time": "Время (мин:сек)", "delta": "К лучшему"}
        for col, text in base.items():
            arrow = ""
            if col == self._sort_col:
                arrow = " ▼" if self._sort_desc else " ▲"
            self.laps_tree.heading(col, text=text + arrow)

    def _set_lap_checked(self, lap, checked):
        self._lap_checked[lap] = checked
        iid = self._lap_rows[lap]
        pos = list(self._lap_rows).index(lap)
        self.laps_tree.set(iid, "on", GLYPH_ON if checked else GLYPH_OFF)
        self.laps_tree.item(iid, tags=self._row_tags(lap, pos))
        self._update_lap_counter()

    def _update_lap_counter(self):
        if not self._lap_checked:
            self.laps_counter.config(text="")
            return
        checked = sum(self._lap_checked.values())
        # Короткий формат: длинный не влезает в строку с кнопками при крупных шрифтах
        self.laps_counter.config(text=f"Отмечено: {checked}/{len(self._lap_checked)}")

    def _on_lap_click(self, event):
        if self.laps_tree.identify_region(event.x, event.y) != "cell":
            return
        iid = self.laps_tree.identify_row(event.y)
        if iid:
            self.laps_tree.focus(iid)
            self._set_lap_checked(int(iid), not self._lap_checked[int(iid)])

    def _on_lap_space(self, _event):
        iid = self.laps_tree.focus()
        if iid:
            self._set_lap_checked(int(iid), not self._lap_checked[int(iid)])

    # ------------------------------------------
    # Профили автомобиля
    # ------------------------------------------

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
            self.set_status(f"Профиль загружен: {prof['name']}", "success")
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

    # ------------------------------------------
    # Запуск анализа
    # ------------------------------------------

    def set_status(self, text, kind="info"):
        """Строка состояния внизу окна: info (серый), success (зеленый), error (красный)."""
        colors = {"info": MUTED, "success": SUCCESS, "error": ERROR}
        self.status_label.config(text=text, foreground=colors.get(kind, MUTED))

    def _get_float(self, var, label):
        """Читает числовое поле с русским сообщением об ошибке."""
        try:
            return var.get()
        except tk.TclError:
            raise ValueError(f"Некорректное число в поле '{label}'.")

    def browse_file(self):
        # Стартуем из папки текущего файла, а без него — из data/ проекта
        current = self.filepath.get().strip()
        if current:
            initialdir = str(Path(current).parent)
        else:
            data_dir = Path(__file__).resolve().parent / "data"
            initialdir = str(data_dir) if data_dir.is_dir() else None
        filename = filedialog.askopenfilename(
            title="Выберите файл телеметрии",
            filetypes=[("CSV файлы", "*.csv"), ("Все файлы", "*.*")],
            parent=self.root,
            initialdir=initialdir,
        )
        if filename:
            self.filepath.set(filename)
            self.refresh_laps_table()

    def refresh_laps_table(self):
        """Сканирует выбранный файл и заполняет таблицу кругов с временами."""
        self._lap_checked = {}
        self._lap_rows = {}
        self._lap_times = {}
        self._lap_best = None
        self._sort_col, self._sort_desc = "lap", False

        filepath = self.filepath.get().strip()
        if not filepath:
            self.laps_hint.config(text="Файл не выбран — круги появятся после выбора CSV.",
                                  foreground=MUTED)
            self._update_lap_counter()
            return

        self.laps_hint.config(text=f"Читаю круги из {filepath}...", foreground=MUTED)
        self.root.update()

        try:
            df = read_telemetry(filepath)
            all_laps, lap_times = compute_lap_times(df)
        except (FileNotFoundError, ValueError) as e:
            self.laps_hint.config(text=f"Не удалось прочитать файл: {e}", foreground=ERROR)
            self._render_rows()
            return

        self._lap_times = {int(lap): lap_times[lap] for lap in all_laps}
        self._lap_checked = {lap: True for lap in self._lap_times}
        # Лучший круг — самый быстрый из полных (у неполных время NaN или отрицательное).
        # Первый/последний обрывки кругов (в- и выезды) дают фальшивые времена в пару секунд,
        # поэтому на звание лучшего не претендуют: отсекаются те, что короче половины медианы.
        full = {lap: t for lap, t in self._lap_times.items() if not math.isnan(t) and t >= 0}
        if full:
            median_t = statistics.median(full.values())
            candidates = {lap: t for lap, t in full.items() if t >= median_t / 2}
            pool = candidates or full
            self._lap_best = min(pool, key=pool.get)

        self.laps_hint.config(
            text=f"Найдено кругов: {len(all_laps)}. Отметьте интересные — неотмеченные будут скрыты на графиках.",
            foreground=MUTED
        )
        self._render_rows()

    def check_all_laps(self):
        for lap in self._lap_checked:
            self._set_lap_checked(lap, True)

    def uncheck_all_laps(self):
        for lap in self._lap_checked:
            self._set_lap_checked(lap, False)

    def selected_laps(self):
        """Список отмеченных кругов; None = таблица еще не построена (файл не выбран)."""
        if not self._lap_checked:
            return None
        return [lap for lap, checked in self._lap_checked.items() if checked]

    def run_analysis(self):
        filepath = self.filepath.get()
        if not filepath:
            messagebox.showwarning("Ошибка", "Пожалуйста, выберите файл лога.")
            return

        self.set_status("Анализирую данные... Это может занять несколько секунд.")
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
            self.set_status(f"Готово! Отчет сохранен: {result.report_path}", "success")
            messagebox.showinfo(
                "Успех",
                f"Анализ завершен!\nОтчет сохранен в файл:\n{result.report_path}"
            )
        except (ValueError, FileNotFoundError, CarProfileError) as e:
            self.set_status(f"Ошибка: {e}", "error")
            messagebox.showerror("Ошибка анализа", str(e))


if __name__ == "__main__":
    root = tk.Tk()
    app = TelemetryApp(root)
    root.mainloop()
