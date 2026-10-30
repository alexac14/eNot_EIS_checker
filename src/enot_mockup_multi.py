"""
Варианты главного экрана для НЕСКОЛЬКИХ граждан (болванка без проверок).
Исходный макет на одного человека остаётся в enot_mockup.py без изменений.

Запуск:  python enot_mockup_multi.py 1     (1, 2, 3 или 4)

  1 — Вкладки-«чипы»     окно 640×~560, размер не меняется
  2 — Карточки-аккордеон окно 640 шириной, растёт по высоте при добавлении
  3 — Боковая панель     окно шире (900), высота небольшая и постоянная
  4 — Таблица            окно широкое (1100), растёт по высоте на строку

Ничего никуда не отправляется, всё работает локально.
"""
import sys
import tkinter as tk

import customtkinter as ctk

from enot_mockup import (
    BG, WHITE, TEXT, MUTED, ACCENT, ACCENT_SOFT, BORDER_IDLE, BORDER_HOVER,
    TRACK, TRACK_HOVER, GREEN, GREEN_SOFT, F, animate, lerp_color,
    pointer_inside, pick_family, fmt_date, fmt_passport, fmt_snils, fmt_fio,
    Field, Segmented, KeyCard, PrimaryButton,
)

MAX_PERSONS = 4
DOT_EMPTY = "#C3CCDA"

# (ключ, подпись, подсказка, обязательное, мелкая подпись, формат при вводе, формат при уходе)
SPEC = [
    ("fio", "Фамилия Имя Отчество", "Иванов Иван Иванович", True, None, None, fmt_fio),
    ("dob", "Дата рождения", "дд.мм.гггг", True, None, fmt_date, None),
    ("passport", "Серия и номер паспорта", "00 00 000000", True, None, fmt_passport, None),
    ("issued", "Дата выдачи паспорта", "дд.мм.гггг", True, None, fmt_date, None),
    ("snils", "СНИЛС", "000-000-000 00", False, "Для запроса данных о дееспособности", fmt_snils, None),
]


def make_field(parent, key, compact=False):
    for k, label, ph, req, cap, live, blur in SPEC:
        if k == key:
            return Field(parent, None if compact else label, ph, required=req,
                         caption=None if compact else cap, live_format=live,
                         on_blur_format=blur, height=38 if compact else 40)


def short_name(fio):
    parts = fio.split()
    if not parts:
        return ""
    ini = "".join(p[0].upper() + "." for p in parts[1:3])
    return (parts[0] + " " + ini).strip()


def chip_label(form, i, limit=10):
    parts = form.values()["fio"].split()
    if not parts:
        return f"Гражданин {i + 1}"
    fam = parts[0]
    ini = [p[0].upper() + "." for p in parts[1:3]]
    for cand in ((fam + " " + "".join(ini)).strip(), (fam + " " + "".join(ini[:1])).strip()):
        if len(cand) <= limit:
            return cand
    return ellipsize(fam, limit)


def ellipsize(s, n):
    return s if len(s) <= n else s[:n - 1] + "…"


def tween(widget, attr, target, dur, paint):
    """Плавно меняет число widget.<attr> до target и каждый кадр вызывает paint()."""
    start = getattr(widget, attr)

    def upd(e):
        setattr(widget, attr, start + (target - start) * e)
        paint()
    animate(widget, attr, dur, upd)


class FieldsMixin:
    def values(self):
        return {k: f.get().strip() for k, f in self.fields.items()}

    def complete(self):
        v = self.values()
        return all(v[k] for k, _, _, req, _, _, _ in SPEC if req)

    def short(self):
        return short_name(self.values()["fio"])


class PersonForm(ctk.CTkFrame, FieldsMixin):
    """Форма одного гражданина (5 полей), та же раскладка, что в исходном макете."""

    def __init__(self, master, on_change=None):
        super().__init__(master, fg_color="transparent")
        self.on_change = on_change
        self.grid_columnconfigure(0, weight=5, uniform="c")
        self.grid_columnconfigure(1, weight=7, uniform="c")
        self.fields = {k: make_field(self, k) for k, *_ in SPEC}
        f = self.fields
        f["fio"].grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 9))
        f["dob"].grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(0, 9))
        f["passport"].grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(0, 9))
        f["issued"].grid(row=2, column=0, sticky="ew", padx=(0, 8))
        f["snils"].grid(row=2, column=1, sticky="ew", padx=(8, 0))
        chain_fields(list(f.values()), self._chg)

    def _chg(self, *_):
        if self.on_change:
            self.on_change()

    def focus_first(self):
        self.fields["fio"].entry.focus_set()


def chain_fields(fields, on_change):
    for a, b in zip(fields, fields[1:]):
        a.entry.bind("<Return>", lambda e, b=b: b.entry.focus_set())
    for fld in fields:
        fld.entry.bind("<KeyRelease>", lambda e: on_change())
        fld.entry.bind("<FocusOut>", lambda e, fld=fld: fld.after(30, on_change))


# ───────────────────────── общие элементы ─────────────────────────
class AddButton(ctk.CTkButton):
    """Кнопка «+ Добавить» с плавной подсветкой."""

    def __init__(self, master, text, command, width=120, height=36):
        super().__init__(master, text=text, width=width, height=height, corner_radius=10,
                         font=F(13, "bold"), fg_color=BG, hover=False, border_width=2,
                         border_color="#B7C6E6", text_color=ACCENT, command=command)
        self.h = 0.0
        self.bind("<Enter>", lambda e: self.after(15, self._refresh))
        self.bind("<Leave>", lambda e: self.after(15, self._refresh))

    def _refresh(self):
        tween(self, "h", 1.0 if pointer_inside(self) else 0.0, 0.15, self._paint)

    def _paint(self):
        self.configure(fg_color=lerp_color(BG, ACCENT_SOFT, self.h),
                       border_color=lerp_color("#B7C6E6", ACCENT, self.h))


class CloseMark(ctk.CTkLabel):
    """Крестик удаления: проявляется только когда это уместно."""

    def __init__(self, master, bg, command):
        super().__init__(master, text="×", font=F(18, "bold"), text_color=bg, fg_color=bg, width=22)
        self.vis = 0.0
        self.bg = bg
        self.command = command
        self.bind("<Button-1>", lambda e: self.command())

    def paint(self, bg, vis):
        self.bg = bg
        self.configure(fg_color=bg, text_color=lerp_color(bg, MUTED, vis))


class MultiResult(ctk.CTkToplevel):
    def __init__(self, master, blocks, shared):
        super().__init__(master, fg_color=BG)
        self.title("Макет: данные получены")
        self.geometry("560x620")
        self.transient(master)
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=14, pady=(14, 4))
        for title, rows in blocks + [("Общее для всех", shared)]:
            card = ctk.CTkFrame(scroll, fg_color=WHITE, corner_radius=14, border_width=2,
                                border_color=BORDER_IDLE)
            card.pack(fill="x", padx=6, pady=(0, 10))
            ctk.CTkLabel(card, text=title, font=F(15, "bold"), text_color=ACCENT).pack(
                anchor="w", padx=16, pady=(12, 4))
            for k, v in rows:
                r = ctk.CTkFrame(card, fg_color="transparent")
                r.pack(fill="x", padx=16, pady=1)
                ctk.CTkLabel(r, text=k, font=F(13), text_color=MUTED, width=170, anchor="w").pack(side="left")
                ctk.CTkLabel(r, text=v or "—", font=F(14, "bold"), text_color=TEXT, anchor="w").pack(side="left")
            ctk.CTkFrame(card, fg_color="transparent", height=8).pack()
        ctk.CTkLabel(self, text="Это макет: проверки не выполняются, данные никуда не отправляются.",
                     font=F(12), text_color=MUTED).pack(pady=(0, 6))
        PrimaryButton(self, "Закрыть", self.destroy).pack(fill="x", padx=20, pady=(0, 16))
        self.after(50, self.lift)


class Base(ctk.CTk):
    def __init__(self, width, height):
        super().__init__(fg_color=BG)
        pick_family()
        self.W, self.H = width, height
        self.title("Проверки еНот")
        self.resizable(False, False)
        self._center(width, height)
        try:
            self.attributes("-alpha", 0.0)
        except Exception:
            pass
        self.forms_getter = lambda: []

    def scale(self):
        try:
            return self._get_window_scaling()
        except Exception:
            return 1.0

    def _center(self, w, h):
        s = self.scale()
        x = int((self.winfo_screenwidth() - w * s) / 2)
        y = int((self.winfo_screenheight() - h * s) / 2.3)
        self.geometry(f"{w}x{h}+{max(x, 0)}+{max(y, 0)}")

    def fit(self):
        """Подгоняет высоту окна под содержимое (для вариантов, где окно растёт)."""
        self.update_idletasks()
        h = round(self.winfo_reqheight() / self.scale())
        self.geometry(f"{self.W}x{h}")

    def fade_in(self):
        animate(self, "fade", 0.35, lambda e: self.attributes("-alpha", e))

    def title_row(self, parent, text, legend=True):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        ctk.CTkFrame(row, fg_color=ACCENT, width=6, height=24, corner_radius=3).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(row, text=text, font=F(22, "bold"), text_color=TEXT).pack(side="left")
        if legend:
            ctk.CTkLabel(row, text="* — обязательные поля", font=F(12), text_color=MUTED).pack(
                side="right", anchor="s", pady=(0, 3))
        return row

    def note_for_all(self, who):
        """Подпись «общий для всех граждан» у переключателя; проявляется при 2+ гражданах."""
        self.note = ctk.CTkLabel(who.head, text="общий для всех граждан", font=F(12), text_color=BG)
        self.note.pack(side="right")
        self.note_v = 0.0

    def update_count(self, n):
        if hasattr(self, "note"):
            tween(self, "note_v", 1.0 if n > 1 else 0.0, 0.25,
                  lambda: self.note.configure(text_color=lerp_color(BG, MUTED, self.note_v)))
        if hasattr(self, "go"):
            self.go.label.configure(text="Начать проверки" if n == 1 else f"Начать проверки ({n})")

    def start(self):
        blocks = []
        for i, form in enumerate(self.forms_getter()):
            v = form.values()
            parts = v["fio"].split()
            fam, name, otch = (parts + ["", "", ""])[:3]
            blocks.append((f"Гражданин {i + 1}", [
                ("ФИО", v["fio"]), ("Фамилия", fam), ("Имя", name), ("Отчество", otch),
                ("Дата рождения", v["dob"]), ("Паспорт", v["passport"]),
                ("Дата выдачи паспорта", v["issued"]), ("СНИЛС", v["snils"])]))
        shared = [("Исполняет обязанности", self.who.value or ""),
                  ("Ключ вставлен", "да" if self.key.confirmed else "нет")]
        MultiResult(self, blocks, shared)


# ═════════════════════════ ВАРИАНТ 1: вкладки-чипы ═════════════════════════
class Chip(ctk.CTkFrame):
    W = 138

    def __init__(self, master, on_select, on_close):
        super().__init__(master, fg_color=TRACK, corner_radius=10, border_width=2,
                         border_color=TRACK, height=36, width=40)
        self.pack_propagate(False)
        self.sel = self.hov = self.comp = self.closable = 0.0
        self.dot = ctk.CTkFrame(self, width=10, height=10, corner_radius=5, fg_color=DOT_EMPTY)
        self.dot.pack(side="left", padx=(11, 7))
        self.name = ctk.CTkLabel(self, text="", font=F(13, "bold"), text_color=TEXT,
                                 fg_color=TRACK, anchor="w")
        self.name.pack(side="left", fill="x", expand=True)
        self.close = CloseMark(self, TRACK, on_close)
        self.close.place(relx=1.0, x=-6, rely=0.5, anchor="e")
        for w in (self, self.name, self.dot):
            w.bind("<Button-1>", lambda e: on_select())
        for w in (self, self.name, self.dot, self.close):
            w.bind("<Enter>", lambda e: self.after(15, self._hover))
            w.bind("<Leave>", lambda e: self.after(15, self._hover))
        animate(self, "w", 0.28, lambda e: self.configure(width=round(40 + (self.W - 40) * e)))

    def _hover(self):
        tween(self, "hov", 1.0 if pointer_inside(self) else 0.0, 0.15, self.paint)

    def set_selected(self, on):
        tween(self, "sel", 1.0 if on else 0.0, 0.22, self.paint)

    def set_complete(self, on):
        tween(self, "comp", 1.0 if on else 0.0, 0.25, self.paint)

    def set_closable(self, on):
        self.closable = 1.0 if on else 0.0
        self.paint()

    def set_label(self, text):
        self.name.configure(text=text)

    def paint(self):
        base = lerp_color(TRACK, TRACK_HOVER, self.hov)
        fg = lerp_color(base, WHITE, self.sel)
        self.configure(fg_color=fg, border_color=lerp_color(base, ACCENT, self.sel))
        self.name.configure(fg_color=fg, text_color=lerp_color(TEXT, ACCENT, self.sel))
        self.dot.configure(fg_color=lerp_color(DOT_EMPTY, GREEN, self.comp))
        self.close.paint(fg, max(self.hov, self.sel) * self.closable)

    def shrink(self, done):
        animate(self, "w", 0.2, lambda e: self.configure(width=round(self.W - (self.W - 8) * e)))
        self.after(230, done)


class ChipsApp(Base):
    def __init__(self):
        super().__init__(640, 560)
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=32, pady=(14, 14))
        self.title_row(body, "Введите данные граждан").pack(fill="x", pady=(0, 8))

        self.row = ctk.CTkFrame(body, fg_color="transparent")
        self.row.pack(fill="x", pady=(0, 10))
        self.add_btn = AddButton(self.row, "+  Добавить", self.add_person)
        self.add_btn.pack(side="left")

        self.holder = ctk.CTkFrame(body, fg_color="transparent", height=10)
        self.holder.pack(fill="x")
        self.who = Segmented(body, "Кто сегодня исполняет обязанности", ["Нотариус", "ВРИО"])
        self.who.pack(fill="x", pady=(9, 0))
        self.note_for_all(self.who)
        self.key = KeyCard(body)
        self.key.pack(fill="x", pady=(8, 0))
        self.go = PrimaryButton(body, "Начать проверки", self.start)
        self.go.pack(fill="x", pady=(10, 0))

        self.persons = []      # [{"form":..., "chip":...}]
        self.active = None
        self.forms_getter = lambda: [p["form"] for p in self.persons]
        self.add_person(first=True)
        first = self.persons[0]["form"]
        first.update_idletasks()
        self.holder.configure(height=round(first.winfo_reqheight() / self.scale()))
        self.after(30, first.focus_first)
        self.after(60, self.fade_in)

    def add_person(self, first=False):
        if len(self.persons) >= MAX_PERSONS:
            return
        form = PersonForm(self.holder, on_change=self.relabel)
        chip = Chip(self.row, on_select=lambda: self.select_chip(chip), on_close=lambda: self.remove(chip))
        chip.pack(side="left", padx=(0, 8), before=self.add_btn)
        self.persons.append({"form": form, "chip": chip})
        if len(self.persons) >= MAX_PERSONS:
            self.add_btn.pack_forget()
        self.select(len(self.persons) - 1, focus=not first)
        self.relabel()

    def index_of(self, chip):
        return next(i for i, p in enumerate(self.persons) if p["chip"] is chip)

    def select_chip(self, chip):
        self.select(self.index_of(chip), focus=True)

    def select(self, i, focus=False):
        old = self.active
        self.active = i
        new = self.persons[i]["form"]
        for j, p in enumerate(self.persons):
            p["chip"].set_selected(j == i)
            if p["form"] is not new:
                p["form"].place_forget()
        dx = 0 if old is None or old == i else (32 if i > old else -32)

        def pos(e):
            new.place(x=round(dx * (1 - e)), y=0, relwidth=1, relheight=1)
        animate(new, "slide", 0.24, pos)
        if focus:
            self.after(40, new.focus_first)

    def remove(self, chip):
        if len(self.persons) <= 1:
            return
        i = self.index_of(chip)
        p = self.persons.pop(i)
        was_active = (i == self.active)
        p["form"].destroy()
        if was_active:
            self.active = None
        elif self.active is not None and self.active > i:
            self.active -= 1
        chip.shrink(chip.destroy)
        if len(self.persons) < MAX_PERSONS:
            self.add_btn.pack(side="left")
        if was_active:
            self.select(min(i, len(self.persons) - 1), focus=True)
        self.relabel()

    def relabel(self):
        n = len(self.persons)
        for i, p in enumerate(self.persons):
            p["chip"].set_label(chip_label(p["form"], i))
            p["chip"].set_closable(n > 1)
            p["chip"].set_complete(p["form"].complete())
        self.update_count(n)


# ═════════════════════════ ВАРИАНТ 2: аккордеон ═════════════════════════
class AccCard(ctk.CTkFrame, FieldsMixin):
    def __init__(self, master, app):
        super().__init__(master, fg_color=WHITE, corner_radius=12, border_width=2, border_color=BORDER_IDLE)
        self.app = app
        self.expanded = False
        self.exp = self.hov = self.comp = 0.0
        self.closable = 0.0
        self.num = 1

        self.head = ctk.CTkFrame(self, fg_color=WHITE, height=48, corner_radius=10)
        self.head.pack(fill="x", padx=2, pady=2)
        self.head.pack_propagate(False)
        self.badge = ctk.CTkLabel(self.head, text="1", width=28, height=28, corner_radius=14,
                                  fg_color=ACCENT_SOFT, text_color=ACCENT, font=F(13, "bold"))
        self.badge.pack(side="left", padx=(12, 10))
        self.title = ctk.CTkLabel(self.head, text="Новый гражданин", font=F(14, "bold"),
                                  text_color=TEXT, fg_color=WHITE)
        self.title.pack(side="left")
        self.sub = ctk.CTkLabel(self.head, text="", font=F(13), text_color=MUTED, fg_color=WHITE)
        self.sub.pack(side="left", padx=(8, 0))
        self.chev = ctk.CTkLabel(self.head, text="▾", font=F(15, "bold"), text_color=MUTED,
                                 fg_color=WHITE, width=22)
        self.chev.pack(side="right", padx=(0, 12))
        self.close = CloseMark(self.head, WHITE, lambda: app.remove(self))
        self.close.pack(side="right")

        self.body = ctk.CTkFrame(self, fg_color=WHITE, height=1, corner_radius=0)
        self.body.pack_propagate(False)
        self.form = PersonForm(self.body, on_change=app.relabel)
        self.form.pack(fill="x", padx=14, pady=(2, 0))
        self.fields = self.form.fields

        for w in (self.head, self.badge, self.title, self.sub, self.chev):
            w.bind("<Button-1>", lambda e: app.toggle(self))
        for w in (self, self.head, self.badge, self.title, self.sub, self.chev, self.close):
            w.bind("<Enter>", lambda e: self.after(15, self._hover))
            w.bind("<Leave>", lambda e: self.after(15, self._hover))

    def _hover(self):
        tween(self, "hov", 1.0 if pointer_inside(self) else 0.0, 0.15, self.paint)

    def paint(self):
        border = lerp_color(lerp_color(BORDER_IDLE, BORDER_HOVER, self.hov), ACCENT, self.exp)
        self.configure(border_color=border)
        # значок: синий когда раскрыто, зелёный когда заполнено, иначе бледный
        idle = lerp_color(ACCENT_SOFT, GREEN_SOFT, self.comp)
        idle_t = lerp_color(ACCENT, GREEN, self.comp)
        self.badge.configure(fg_color=lerp_color(idle, ACCENT, self.exp),
                             text_color=lerp_color(idle_t, "#FFFFFF", self.exp))
        self.close.paint(WHITE, max(self.hov, self.exp) * self.closable)

    def set_summary(self, n, title, sub, complete):
        self.num = n
        self.badge.configure(text=str(n))
        self.title.configure(text=title)
        self.sub.configure(text=sub)
        tween(self, "comp", 1.0 if complete else 0.0, 0.25, self.paint)

    def body_height(self):
        self.form.update_idletasks()
        return round(self.form.winfo_reqheight() / self.app.scale()) + 14

    def expand(self):
        self.expanded = True
        self.chev.configure(text="▴")
        self.badge.configure(text=str(self.num))
        H = self.body_height()
        self.body.pack(fill="x", padx=14, pady=(0, 2))

        def upd(e):
            self.body.configure(height=max(1, round(H * e)))
            self.exp = e
            self.paint()
            self.app.fit()
        animate(self, "acc", 0.3, upd)
        self.after(60, self.form.focus_first)

    def collapse(self):
        self.expanded = False
        self.chev.configure(text="▾")
        h0 = int(self.body.cget("height"))

        def upd(e):
            self.body.configure(height=max(1, round(h0 * (1 - e))))
            self.exp = 1 - e
            self.paint()
            self.app.fit()
        animate(self, "acc", 0.25, upd)
        self.after(280, lambda: (self.body.pack_forget() if not self.expanded else None, self.app.fit()))


class AccordionApp(Base):
    def __init__(self):
        super().__init__(640, 520)
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=32, pady=(14, 14))
        self.title_row(body, "Введите данные граждан").pack(fill="x", pady=(0, 10))
        self.list = ctk.CTkFrame(body, fg_color="transparent")
        self.list.pack(fill="x")
        self.add_btn = AddButton(body, "+  Добавить гражданина", self.add_person, width=200, height=40)
        self.add_btn.pack(fill="x", pady=(2, 0))
        self.who = Segmented(body, "Кто сегодня исполняет обязанности", ["Нотариус", "ВРИО"])
        self.who.pack(fill="x", pady=(12, 0))
        self.note_for_all(self.who)
        self.key = KeyCard(body)
        self.key.pack(fill="x", pady=(8, 0))
        self.go = PrimaryButton(body, "Начать проверки", self.start)
        self.go.pack(fill="x", pady=(10, 0))
        self.cards = []
        self.forms_getter = lambda: self.cards
        self.add_person()
        self.after(60, self.fade_in)

    def add_person(self):
        if len(self.cards) >= MAX_PERSONS:
            return
        card = AccCard(self.list, self)
        card.pack(fill="x", pady=(0, 8))
        self.cards.append(card)
        if len(self.cards) >= MAX_PERSONS:
            self.add_btn.pack_forget()
        for c in self.cards:
            if c is not card and c.expanded:
                c.collapse()
        card.expand()
        self.relabel()

    def toggle(self, card):
        if card.expanded:
            card.collapse()
        else:
            for c in self.cards:
                if c.expanded:
                    c.collapse()
            card.expand()

    def remove(self, card):
        if len(self.cards) <= 1:
            return
        self.cards.remove(card)
        card.destroy()
        if not any(c.expanded for c in self.cards):
            self.cards[-1].expand()
        if len(self.cards) < MAX_PERSONS:
            self.add_btn.pack(fill="x", pady=(2, 0), after=self.list)
        self.relabel()
        self.after(20, self.fit)

    def relabel(self):
        n = len(self.cards)
        for i, c in enumerate(self.cards):
            v = c.values()
            name = c.short() or "Новый гражданин"
            sub = v["dob"] if v["dob"] else ""
            c.closable = 1.0 if n > 1 else 0.0
            c.set_summary(i + 1, name, sub, c.complete())
        self.update_count(n)


# ═════════════════════════ ВАРИАНТ 3: боковая панель ═════════════════════════
class SideRow(ctk.CTkFrame):
    def __init__(self, master, on_select, on_close):
        super().__init__(master, fg_color=WHITE, corner_radius=10, height=1, border_width=2, border_color=WHITE)
        self.pack_propagate(False)
        self.sel = self.hov = self.comp = self.closable = 0.0
        self.num = 1
        self.badge = ctk.CTkLabel(self, text="1", width=28, height=28, corner_radius=14,
                                  fg_color=ACCENT_SOFT, text_color=ACCENT, font=F(13, "bold"))
        self.badge.pack(side="left", padx=(10, 10))
        box = ctk.CTkFrame(self, fg_color="transparent")
        box.pack(side="left", fill="both", expand=True, pady=6)
        self.name = ctk.CTkLabel(box, text="", font=F(13, "bold"), text_color=TEXT, fg_color=WHITE, anchor="w")
        self.name.pack(anchor="w")
        self.sub = ctk.CTkLabel(box, text="", font=F(12), text_color=MUTED, fg_color=WHITE, anchor="w")
        self.sub.pack(anchor="w")
        self.close = CloseMark(self, WHITE, on_close)
        self.close.place(relx=1.0, x=-6, rely=0.5, anchor="e")
        for w in (self, self.badge, self.name, self.sub, box):
            w.bind("<Button-1>", lambda e: on_select())
        for w in (self, self.badge, self.name, self.sub, self.close, box):
            w.bind("<Enter>", lambda e: self.after(15, self._hover))
            w.bind("<Leave>", lambda e: self.after(15, self._hover))
        animate(self, "h", 0.28, lambda e: self.configure(height=max(1, round(52 * e))))

    def _hover(self):
        tween(self, "hov", 1.0 if pointer_inside(self) else 0.0, 0.15, self.paint)

    def set_selected(self, on):
        tween(self, "sel", 1.0 if on else 0.0, 0.22, self.paint)

    def set_info(self, n, title, sub, complete, closable):
        self.num = n
        self.name.configure(text=title)
        self.sub.configure(text=sub, )
        self.closable = 1.0 if closable else 0.0
        self.complete_target = complete
        self.sub_color = GREEN if complete else MUTED
        tween(self, "comp", 1.0 if complete else 0.0, 0.25, self.paint)

    def paint(self):
        base = lerp_color(WHITE, BG, self.hov)
        fg = lerp_color(base, ACCENT_SOFT, self.sel)
        self.configure(fg_color=fg, border_color=lerp_color(fg, ACCENT, self.sel))
        idle = lerp_color(ACCENT_SOFT, GREEN_SOFT, self.comp)
        idle_t = lerp_color(ACCENT, GREEN, self.comp)
        self.badge.configure(fg_color=lerp_color(idle, ACCENT, self.sel),
                             text_color=lerp_color(idle_t, "#FFFFFF", self.sel))
        self.name.configure(fg_color=fg, text_color=lerp_color(TEXT, ACCENT, self.sel * 0.7))
        self.sub.configure(fg_color=fg, text_color=lerp_color(MUTED, GREEN, self.comp))
        self.close.paint(fg, max(self.hov, self.sel) * self.closable)


class SidebarApp(Base):
    def __init__(self):
        super().__init__(940, 470)
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=32, pady=(14, 14))
        self.title_row(body, "Введите данные граждан").pack(fill="x", pady=(0, 10))

        mid = ctk.CTkFrame(body, fg_color="transparent")
        mid.pack(fill="x")
        side = ctk.CTkFrame(mid, fg_color=WHITE, corner_radius=14, border_width=2,
                            border_color=BORDER_IDLE, width=240, height=300)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        hr = ctk.CTkFrame(side, fg_color="transparent")
        hr.pack(fill="x", padx=14, pady=(12, 6))
        ctk.CTkLabel(hr, text="Граждане", font=F(14, "bold"), text_color=TEXT).pack(side="left")
        self.count = ctk.CTkLabel(hr, text="1 из 4", font=F(12), text_color=MUTED)
        self.count.pack(side="right")
        self.list = ctk.CTkFrame(side, fg_color="transparent")
        self.list.pack(fill="x", padx=8)
        self.add_btn = AddButton(side, "+  Добавить гражданина", self.add_person, width=200, height=38)
        self.add_btn.pack(side="bottom", fill="x", padx=12, pady=(0, 12))

        right = ctk.CTkFrame(mid, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True, padx=(18, 0))
        self.holder = ctk.CTkFrame(right, fg_color="transparent", height=10)
        self.holder.pack(fill="x")
        self.who = Segmented(right, "Кто сегодня исполняет обязанности", ["Нотариус", "ВРИО"])
        self.who.pack(fill="x", pady=(14, 0))
        self.note_for_all(self.who)

        bottom = ctk.CTkFrame(body, fg_color="transparent")
        bottom.pack(fill="x", pady=(14, 0))
        self.go = PrimaryButton(bottom, "Начать проверки", self.start)
        self.go.configure(width=290)
        self.go.pack(side="right")
        self.key = KeyCard(bottom)
        self.key.pack(side="left", fill="x", expand=True, padx=(0, 14))

        self.rows = []     # [{"form","row"}]
        self.active_form = None
        self.forms_getter = lambda: [r["form"] for r in self.rows]
        self.add_person(first=True)
        f = self.rows[0]["form"]
        f.update_idletasks()
        self.holder.configure(height=round(f.winfo_reqheight() / self.scale()))
        self.after(30, f.focus_first)
        self.after(60, self.fade_in)

    def add_person(self, first=False):
        if len(self.rows) >= MAX_PERSONS:
            return
        form = PersonForm(self.holder, on_change=self.relabel)
        row = SideRow(self.list, on_select=lambda: self.select(self.index_of(row), True),
                      on_close=lambda: self.remove(row))
        row.pack(fill="x", pady=(0, 4))
        self.rows.append({"form": form, "row": row})
        if len(self.rows) >= MAX_PERSONS:
            self.add_btn.pack_forget()
        self.select(len(self.rows) - 1, focus=not first)
        self.relabel()

    def index_of(self, row):
        return next(i for i, r in enumerate(self.rows) if r["row"] is row)

    def select(self, i, focus=False):
        old = self.active_form
        new = self.rows[i]["form"]
        self.active_form = new
        for j, r in enumerate(self.rows):
            r["row"].set_selected(j == i)
            if r["form"] is not new:
                r["form"].place_forget()
        dx = 0 if old is None or old is new else 32

        def pos(e):
            new.place(x=round(dx * (1 - e)), y=0, relwidth=1, relheight=1)
        animate(new, "slide", 0.24, pos)
        if focus:
            self.after(40, new.focus_first)

    def remove(self, row):
        if len(self.rows) <= 1:
            return
        i = self.index_of(row)
        r = self.rows.pop(i)
        was_active = r["form"] is self.active_form
        r["form"].destroy()
        row.destroy()
        if was_active:
            self.active_form = None
            self.select(min(i, len(self.rows) - 1), focus=True)
        if len(self.rows) < MAX_PERSONS:
            self.add_btn.pack(side="bottom", fill="x", padx=12, pady=(0, 12))
        self.relabel()

    def relabel(self):
        n = len(self.rows)
        for i, r in enumerate(self.rows):
            f = r["form"]
            if f.complete():
                sub = "Готов к проверке"
            elif any(f.values().values()):
                sub = "Не все поля заполнены"
            else:
                sub = "Новый гражданин"
            r["row"].set_info(i + 1, ellipsize(f.short() or f"Гражданин {i + 1}", 17), sub, f.complete(), n > 1)
            r["row"].badge.configure(text=str(i + 1))
        self.count.configure(text=f"{n} из {MAX_PERSONS}")
        self.update_count(n)


# ═════════════════════════ ВАРИАНТ 4: таблица (с прокруткой) ═════════════════════════
ROW_H = 44
MAX_VISIBLE = 5                      # сколько строк видно без прокрутки
COL_RATIO = [40, 300, 124, 182, 166, 168, 34]   # №, ФИО, дата рожд., паспорт, дата выдачи, СНИЛС, ×


def make_cols(card_width):
    """Ширины колонок так, чтобы таблица заполняла карточку (одинаково для шапки и строк)."""
    total = card_width - 4 - 28 - 22           # рамка, внутренние отступы, полоса прокрутки
    k = total / sum(COL_RATIO)
    cols = [round(r * k) for r in COL_RATIO]
    cols[1] += total - sum(cols)
    return cols


def setup_cols(frame, cols):
    # Tk grid.minsize измеряется в физических пикселях; размеры CTk —
    # в логических. Без пересчёта при 125/150% заголовок и строки расходятся.
    scale = frame._get_widget_scaling()
    for i, w in enumerate(cols):
        frame.grid_columnconfigure(i, minsize=round(w * scale), weight=0)


def cancel_callbacks(widget):
    """Отменяет after именно удаляемого поддерева, включая анимации полей.

    Tk удаляет Python-команды при destroy, но таймеры сам не отменяет.
    Поэтому быстрая смена сделки иначе оставляет invalid command name tick.
    """
    owners = {}

    def collect(node):
        for command in getattr(node, '_tclCommands', None) or ():
            owners[command] = node
        for child in node.winfo_children():
            collect(child)
        getattr(node, '_anim_jobs', {}).clear()

    collect(widget)
    for job in widget.tk.splitlist(widget.tk.call('after', 'info')):
        try:
            script, _kind = widget.tk.call('after', 'info', job)
            command = widget.tk.splitlist(script)[0]
            owner = owners.get(command)
            if owner is not None:
                owner.after_cancel(job)
        except (tk.TclError, IndexError):
            pass


class SafeDestroy:
    def destroy(self):
        if self.winfo_exists():
            cancel_callbacks(self)
        super().destroy()


class TableRow(SafeDestroy, ctk.CTkFrame, FieldsMixin):
    def __init__(self, master, board, values=None, animated=True):
        super().__init__(master, fg_color="transparent", height=ROW_H)
        self.board = board
        self.pack_propagate(False)
        inner = self.inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.pack(fill="x", anchor="n")
        setup_cols(inner, board.cols)
        self.badge = ctk.CTkLabel(inner, text="1", width=28, height=28, corner_radius=14,
                                  fg_color=ACCENT_SOFT, text_color=ACCENT, font=F(13, "bold"))
        self.badge.grid(row=0, column=0, sticky="w", padx=(2, 0))
        self.fields = {k: make_field(inner, k, compact=True) for k, *_ in SPEC}
        for col, k in enumerate(("fio", "dob", "passport", "issued", "snils"), start=1):
            # Малая запрошенная ширина: фактическую ширину задаёт общая сетка.
            self.fields[k].configure(width=1)
            self.fields[k].entry.configure(width=1)
            self.fields[k].grid(row=0, column=col, sticky="ew", padx=(0, 8), pady=3)
        self.close = CloseMark(inner, WHITE, lambda: board.remove(self))
        self.close.grid(row=0, column=6, sticky="w")
        for k, v in (values or {}).items():
            if v and k in self.fields:
                self.fields[k].entry.insert(0, v)
        self.focus_v = 0.0
        self.comp = 0.0
        self.closable = 0.0
        chain_fields(list(self.fields.values()), board.changed)
        for f in self.fields.values():
            f.entry.bind("<FocusIn>", lambda e: self._on_focus())
            f.entry.bind("<FocusOut>", lambda e: self.after(40, self._focus))
        # Геометрию строк не анимируем: фокус и цвета остаются плавными.

    def _on_focus(self):
        self.after(10, self._focus)
        self.board.ensure_visible(self)

    def has_focus(self):
        return any(f.focused for f in self.fields.values())

    def _focus(self):
        tween(self, "focus_v", 1.0 if self.has_focus() else 0.0, 0.18, self.paint)

    def set_state(self, n, complete, closable):
        self.badge.configure(text=str(n))
        self.closable = 1.0 if closable else 0.0
        tween(self, "comp", 1.0 if complete else 0.0, 0.25, self.paint)

    def paint(self):
        idle = lerp_color(ACCENT_SOFT, GREEN_SOFT, self.comp)
        idle_t = lerp_color(ACCENT, GREEN, self.comp)
        self.badge.configure(fg_color=lerp_color(idle, ACCENT, self.focus_v),
                             text_color=lerp_color(idle_t, "#FFFFFF", self.focus_v))
        self.close.paint(WHITE, self.closable * 0.8)


class TableBoard(ctk.CTkFrame):
    """Таблица участников: шапка + прокручиваемый список строк + кнопка «Добавить»."""

    def __init__(self, master, width, on_change=None, on_resize=None):
        super().__init__(master, fg_color=WHITE, corner_radius=14, border_width=2, border_color=BORDER_IDLE)
        self.cols = make_cols(width)
        self.on_change, self.on_resize = on_change, on_resize
        self.rows = []
        self._focus_job = self._layout_job = None
        self._loading = False
        self._column_width = None
        self.stable = False
        self.h_cur = ROW_H + 2
        pad = ctk.CTkFrame(self, fg_color="transparent")
        pad.pack(fill="both", expand=True, padx=14, pady=12)

        head = self.head = ctk.CTkFrame(pad, fg_color="transparent", height=56)
        head.pack(fill="x", pady=(0, 4))
        head.pack_propagate(False)
        head.grid_propagate(False)
        setup_cols(head, self.cols)
        self.head_cells = {}
        self.head_labels = {}
        heads = [(1, "Фамилия Имя Отчество", True, None), (2, "Дата рождения", True, None),
                 (3, "Серия и номер паспорта", True, None), (4, "Дата выдачи паспорта", True, None),
                 (5, "СНИЛС", False, "Для запроса данных о дееспособности")]
        hf = F(13, "bold")
        for col, text, req, cap in heads:
            if hf.measure(text + " *") > self.cols[col] - 6:      # не помещается в одну строку — переносим
                text = text.replace("номер паспорта", "номер\nпаспорта").replace("выдачи паспорта", "выдачи\nпаспорта")
            # ячейка шапки имеет фиксированную ширину колонки: даже длинный текст не сдвинет соседей
            cell = ctk.CTkFrame(head, fg_color="transparent", width=max(1, self.cols[col]-8), height=56)
            cell.pack_propagate(False)
            cell.grid(row=0, column=col, sticky="nw", padx=(2, 0))
            self.head_cells[col] = cell
            line = ctk.CTkFrame(cell, fg_color="transparent")
            line.pack(anchor="w")
            label = ctk.CTkLabel(line, text=text, font=F(13, "bold"), text_color=TEXT, justify="left")
            label.pack(side="left")
            self.head_labels[col] = (label, text.replace('\n', ' '))
            if req:
                ctk.CTkLabel(line, text=" *", font=F(13, "bold"), text_color=ACCENT).pack(side="left", anchor="s")
            if cap:
                ctk.CTkLabel(cell, text=cap, font=F(12), text_color=MUTED,
                             wraplength=self.cols[5] - 14, justify="left").pack(anchor="w")

        # Собственный viewport без изменения внутренних размеров CTkScrollableFrame.
        # Место под scrollbar зарезервировано всегда: колонки не прыгают.
        self.viewport = ctk.CTkFrame(pad, fg_color=WHITE, corner_radius=0, height=ROW_H+2)
        self.viewport.pack(fill="both", expand=True)
        self.viewport.pack_propagate(False)
        self.bar = ctk.CTkScrollbar(self.viewport, width=16, fg_color=WHITE,
                                    button_color="#C9D2E0", button_hover_color=BORDER_HOVER)
        self.bar.pack(side="right", fill="y")
        self.canvas = tk.Canvas(self.viewport, bg=WHITE, bd=0, highlightthickness=0,
                                height=ROW_H+2, yscrollincrement=1)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scroll = ctk.CTkFrame(self.canvas, fg_color=WHITE, corner_radius=0)
        self.window_id = self.canvas.create_window(0, 0, window=self.scroll, anchor="nw")
        self.canvas.configure(yscrollcommand=self._scrollbar_set)
        self.bar.configure(command=self.canvas.yview)
        self.canvas.bind('<Configure>', self._viewport_changed)
        self.scroll.bind('<Configure>', self._content_changed)
        self.canvas.bind('<MouseWheel>', self._wheel)
        self.scroll.bind('<MouseWheel>', self._wheel)
        self.add_btn = AddButton(pad, "+  Добавить гражданина", self.add_row, width=200, height=40)
        self.add_btn.pack(fill="x", pady=(6, 0))

    # ── строки ──
    def add_row(self, values=None, focus=True, animated=True):
        row = TableRow(self.scroll, self, values, animated)
        row.pack(fill="x")
        self.rows.append(row)
        for fld in row.fields.values():
            fld.entry.bind('<MouseWheel>', self._wheel)
        row.badge.bind('<MouseWheel>', self._wheel)
        row.close.bind('<MouseWheel>', self._wheel)
        if not self._loading:
            self._resize(False)
        if focus:
            self._cancel_focus()
            self._focus_job = self.after_idle(lambda: self._focus_row(row))
        if not self._loading:
            self.changed()
        return row

    def _cancel_focus(self):
        if self._focus_job is not None:
            self.after_cancel(self._focus_job)
            self._focus_job = None

    def _focus_row(self, row):
        self._focus_job = None
        if row in self.rows and row.winfo_exists():
            row.fields['fio'].entry.focus_set()
            self.ensure_visible(row)

    def remove(self, row):
        if len(self.rows) <= 1:
            return
        if row not in self.rows:
            return
        self._cancel_focus()
        self.rows.remove(row)
        row.destroy()
        self._resize(True)
        self.changed()

    def clear(self):
        self._cancel_focus()
        for r in self.rows:
            r.destroy()
        self.rows = []

    def load(self, people):
        # Замена модели — одна операция, без промежуточных размеров и событий.
        self._loading = True
        try:
            self.clear()
            for p in (people or [{}]):
                self.add_row(p, focus=False, animated=False)
        finally:
            self._loading = False
        self._resize(False)
        self.changed()
        self.canvas.yview_moveto(0)

    def changed(self):
        n = len(self.rows)
        for i, r in enumerate(self.rows):
            r.set_state(i + 1, r.complete(), n > 1)
        if self.on_change:
            self.on_change()

    # ── размер и прокрутка ──
    def _resize(self, animated=True):
        target = min(len(self.rows), MAX_VISIBLE) * ROW_H + 2
        self.h_cur = target
        if not self.stable:
            self.viewport.configure(height=target)
        self._schedule_layout()
        if not self.stable and self.on_resize:
            self.on_resize()

    def _scrollbar_set(self, first, last):
        self.bar.set(float(first), float(last))

    def _wheel(self, event):
        if self.scroll.winfo_height() > self.canvas.winfo_height():
            delta = -round(event.delta / 120 * ROW_H * self._get_widget_scaling())
            self.canvas.yview_scroll(delta, 'units')
        return 'break'

    def _viewport_changed(self, event):
        self.canvas.itemconfigure(self.window_id, width=event.width)
        self._schedule_layout()

    def _content_changed(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    def _schedule_layout(self):
        if self._layout_job is None:
            self._layout_job = self.after_idle(self._layout_columns)

    def _layout_columns(self):
        self._layout_job = None
        physical = self.canvas.winfo_width()
        if physical <= 1:
            return
        total = round(physical / self._get_widget_scaling())
        # Минимальная ширина элементов не может превысить ширину колонки.
        # Круглый CTkLabel запрашивает дополнительный отступ для двух цифр.
        # Фиксированный запас не даёт номерам 10+ раздвигать первую колонку.
        ratios = [300, 146, 180, 164, 164]
        available = max(1, total - 48 - 26)
        cols = [48] + [round(available * r / sum(ratios)) for r in ratios] + [26]
        cols[1] += total - sum(cols)
        self.cols = cols
        setup_cols(self.head, cols)
        for col, cell in self.head_cells.items():
            cell.configure(width=max(1, cols[col]-8))
            label, original = self.head_labels[col]
            label.configure(wraplength=max(1, cols[col]-22), text=original)
        for row in self.rows:
            setup_cols(row.inner, cols)
        self._content_changed()

    def scroll_to_end(self):
        self.update_idletasks()
        self.canvas.yview_moveto(1.0)

    def ensure_visible(self, row):
        if row not in self.rows or not row.winfo_exists():
            return
        c = self.canvas
        self.update_idletasks()
        total = max(1, self.scroll.winfo_height())
        view = c.winfo_height()
        top = c.canvasy(0)
        y, h = row.winfo_y(), row.winfo_height()
        if total <= view:
            return
        if y < top:
            c.yview_moveto(y / total)
        elif y + h > top + view:
            c.yview_moveto((y + h - view) / total)


class TableApp(Base):
    W4 = 1180

    def __init__(self):
        super().__init__(self.W4, 480)
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=32, pady=(14, 14))
        self.title_row(body, "Введите данные граждан").pack(fill="x", pady=(0, 10))
        self.board = TableBoard(body, width=self.W4 - 64, on_change=self._chg,
                                on_resize=lambda: self.after_idle(self.fit))
        self.board.pack(fill="x")

        low = ctk.CTkFrame(body, fg_color="transparent")
        low.pack(fill="x", pady=(14, 0))
        low.grid_columnconfigure(0, weight=3, uniform="l")
        low.grid_columnconfigure(1, weight=7, uniform="l")
        self.who = Segmented(low, "Кто сегодня исполняет обязанности", ["Нотариус", "ВРИО"])
        self.who.grid(row=0, column=0, sticky="sew", padx=(0, 14))
        self.key = KeyCard(low)
        self.key.grid(row=0, column=1, sticky="sew")
        self.go = PrimaryButton(body, "Начать проверки", self.start)
        self.go.pack(fill="x", pady=(12, 0))

        self.forms_getter = lambda: self.board.rows
        self.board.add_row(focus=False, animated=False)
        self.after(60, lambda: self.board.rows[0].fields["fio"].entry.focus_set())
        self.after(60, self.fade_in)

    def add_person(self):          # для тестов/единообразия
        self.board.add_row()

    def _chg(self):
        self.update_count(len(self.board.rows))


VARIANTS = {"1": ChipsApp, "2": AccordionApp, "3": SidebarApp, "4": TableApp}

