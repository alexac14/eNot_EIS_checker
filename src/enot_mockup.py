"""
Макет главного экрана «Проверки еНот» (болванка без проверок).

Что делает:
  * можно вводить данные, поля сами ставят точки/пробелы/дефисы;
  * плавные анимации при наведении и фокусе (поля, переключатель, кнопки);
  * кнопка «Начать проверки» просто показывает введённые данные в окне.

Ничего никуда не отправляется, программа работает полностью локально.

Запуск:   pip install customtkinter==5.2.2 pillow
          python enot_mockup.py
"""
import re
import time
import tkinter as tk
from tkinter import font as tkfont

import customtkinter as ctk
from PIL import Image, ImageDraw

# ───────────────────────── палитра ─────────────────────────
BG = "#F3F6FA"          # фон окна
WHITE = "#FFFFFF"
TEXT = "#18212F"        # основной текст
MUTED = "#677386"       # подписи, мелкий текст
PLACEHOLDER = "#9AA5B5"
ACCENT = "#2B5FD9"      # единственный акцентный цвет
ACCENT_HOVER = "#3C72EE"
ACCENT_PRESS = "#1F49B0"
ACCENT_SOFT = "#E7EEFF"
BORDER_IDLE = "#DDE3EC"
BORDER_HOVER = "#9DB5E8"
TRACK = "#E4E9F1"
TRACK_HOVER = "#D5DDEA"
GREEN = "#1E8E5A"
GREEN_SOFT = "#EDF8F2"

WIN_W, WIN_H = 640, 560


# ───────────────────────── утилиты анимации ─────────────────────────
def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def lerp_color(a, b, t):
    t = max(0.0, min(1.0, t))
    ra, rb = _rgb(a), _rgb(b)
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(ra, rb))


def ease_out(p):
    return 1 - (1 - p) ** 3


def animate(widget, key, duration, update, ease=ease_out):
    """Запускает анимацию; новая анимация с тем же key отменяет предыдущую."""
    jobs = widget.__dict__.setdefault("_anim_jobs", {})
    if key in jobs:
        try:
            widget.after_cancel(jobs[key])
        except Exception:
            pass
    t0 = time.perf_counter()

    def tick():
        p = min(1.0, (time.perf_counter() - t0) / duration)
        try:
            update(ease(p))
            if p < 1.0:
                jobs[key] = widget.after(12, tick)
            else:
                jobs.pop(key, None)
        except tk.TclError:      # виджет уже удалён во время анимации
            jobs.pop(key, None)

    tick()


def pointer_inside(widget):
    try:
        x, y = widget.winfo_pointerxy()
        x0, y0 = widget.winfo_rootx(), widget.winfo_rooty()
        return x0 <= x < x0 + widget.winfo_width() and y0 <= y < y0 + widget.winfo_height()
    except Exception:
        return False


_font_cache = {}
FAMILY = "Segoe UI"


def pick_family():
    global FAMILY
    have = set(tkfont.families())
    for name in ("Segoe UI", "Inter", "Noto Sans", "DejaVu Sans"):
        if name in have:
            FAMILY = name
            return


def F(size, weight="normal"):
    key = (size, weight)
    if key not in _font_cache:
        _font_cache[key] = ctk.CTkFont(family=FAMILY, size=size, weight=weight)
    return _font_cache[key]


# ───────────────────────── иконки (рисуем сами) ─────────────────────────
def make_icon(kind):
    S = 144
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if kind == "key":
        d.ellipse((0, 0, S - 1, S - 1), fill=ACCENT_SOFT)
        c = _rgb(ACCENT)
        d.ellipse((30, 30, 80, 80), outline=c, width=9)
        d.line((72, 72, 112, 112), fill=c, width=9)
        d.line((96, 96, 108, 84), fill=c, width=9)
        d.line((108, 108, 120, 96), fill=c, width=9)
        for p in ((72, 72), (112, 112), (108, 84), (120, 96)):
            d.ellipse((p[0] - 4, p[1] - 4, p[0] + 4, p[1] + 4), fill=c)
    else:
        d.ellipse((0, 0, S - 1, S - 1), fill=_rgb(GREEN))
        pts = [(40, 76), (64, 98), (106, 50)]
        d.line(pts, fill=(255, 255, 255), width=12, joint="curve")
        for p in (pts[0], pts[-1]):
            d.ellipse((p[0] - 6, p[1] - 6, p[0] + 6, p[1] + 6), fill=(255, 255, 255))
    return ctk.CTkImage(light_image=img, size=(36, 36))


# ───────────────────────── форматирование ввода ─────────────────────────
def digits(s):
    return re.sub(r"\D", "", s)


def fmt_date(s):
    d = digits(s)[:8]
    out = d[:2]
    if len(d) > 2:
        out += "." + d[2:4]
    if len(d) > 4:
        out += "." + d[4:8]
    return out


def fmt_passport(s):
    d = digits(s)[:10]
    return " ".join(p for p in (d[:2], d[2:4], d[4:]) if p)


def fmt_snils(s):
    d = digits(s)[:11]
    out = d[:3]
    if len(d) > 3:
        out += "-" + d[3:6]
    if len(d) > 6:
        out += "-" + d[6:9]
    if len(d) > 9:
        out += " " + d[9:11]
    return out


def fmt_fio(s):
    def cap(word):
        return "-".join(p[:1].upper() + p[1:].lower() for p in word.split("-"))
    return " ".join(cap(w) for w in s.split())


# ───────────────────────── поле ввода ─────────────────────────
class Field(ctk.CTkFrame):
    """Подпись + поле. Граница и подпись плавно меняют цвет при наведении и фокусе."""

    def __init__(self, master, label, placeholder, required=True, caption=None,
                 live_format=None, on_blur_format=None, height=40):
        super().__init__(master, fg_color="transparent")
        self.live_format, self.on_blur_format = live_format, on_blur_format
        self.p = 0.0          # 0 — покой, 1 — наведение, 2 — фокус
        self.focused = False
        self.lbl = None

        if label is not None:
            head = ctk.CTkFrame(self, fg_color="transparent")
            head.pack(fill="x")
            self.lbl = ctk.CTkLabel(head, text=label, font=F(14, "bold"), text_color=TEXT)
            self.lbl.pack(side="left")
            if required:
                ctk.CTkLabel(head, text=" *", font=F(14, "bold"), text_color=ACCENT).pack(side="left")
            if caption:
                ctk.CTkLabel(head, text=caption, font=F(12), text_color=MUTED).pack(side="right")

        self.entry = ctk.CTkEntry(
            self, height=height, corner_radius=10, border_width=2, fg_color=WHITE,
            border_color=BORDER_IDLE, text_color=TEXT, placeholder_text=placeholder,
            placeholder_text_color=PLACEHOLDER, font=F(16))
        self.entry.pack(fill="x", pady=(4 if label is not None else 0, 0))

        self.entry.bind("<Enter>", lambda e: self.after(15, self._refresh))
        self.entry.bind("<Leave>", lambda e: self.after(15, self._refresh))
        self.entry.bind("<FocusIn>", self._focus_in)
        self.entry.bind("<FocusOut>", self._focus_out)
        self.entry.bind("<KeyRelease>", self._key_release)

    def get(self):
        return self.entry.get()

    def _focus_in(self, _):
        self.focused = True
        self._refresh()

    def _focus_out(self, _):
        self.focused = False
        if self.on_blur_format:
            val = self.entry.get()
            new = self.on_blur_format(val)
            if new != val:
                self.entry.delete(0, "end")
                self.entry.insert(0, new)
        self._refresh()

    def _key_release(self, _):
        if not self.live_format:
            return
        val = self.entry.get()
        new = self.live_format(val)
        if new != val:
            self.entry.delete(0, "end")
            self.entry.insert(0, new)

    def _refresh(self):
        target = 2.0 if self.focused else (1.0 if pointer_inside(self.entry) else 0.0)
        start = self.p

        def upd(e):
            self.p = start + (target - start) * e
            if self.p <= 1:
                c = lerp_color(BORDER_IDLE, BORDER_HOVER, self.p)
            else:
                c = lerp_color(BORDER_HOVER, ACCENT, self.p - 1)
            self.entry.configure(border_color=c)
            if self.lbl is not None:
                self.lbl.configure(text_color=lerp_color(TEXT, ACCENT, max(0.0, self.p - 1)))

        animate(self, "p", 0.18, upd)


# ───────────────────────── переключатель «Нотариус / ВРИО» ─────────────────────────
class Segmented(ctk.CTkFrame):
    def __init__(self, master, label, options):
        super().__init__(master, fg_color="transparent")
        self.options = options
        self.value = None
        self.sel = [0.0] * len(options)   # степень «выбрано» для каждой кнопки
        self.hov = [0.0] * len(options)
        self.has_focus = False

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x")
        ctk.CTkLabel(head, text=label, font=F(14, "bold"), text_color=TEXT).pack(side="left")
        ctk.CTkLabel(head, text=" *", font=F(14, "bold"), text_color=ACCENT).pack(side="left")

        self.head = head
        self.track = ctk.CTkFrame(self, fg_color=TRACK, corner_radius=12, border_width=2,
                                  border_color=TRACK, height=42)
        self.track.pack(fill="x", pady=(4, 0))
        self.track.grid_propagate(False)
        tk.Frame.configure(self.track, takefocus=1)
        self.track.grid_rowconfigure(0, weight=1)

        self.btns = []
        for i, name in enumerate(options):
            self.track.grid_columnconfigure(i, weight=1, uniform="seg")
            b = ctk.CTkButton(self.track, text=name, font=F(15, "bold"), height=32,
                              corner_radius=9, fg_color=TRACK, hover=False,
                              text_color=TEXT, border_width=0,
                              command=lambda i=i: self.select(i))
            b.grid(row=0, column=i, sticky="nsew", padx=(3, 3 if i == len(options) - 1 else 0), pady=3)
            b.bind("<Enter>", lambda e, i=i: self.after(15, lambda: self._hover(i)))
            b.bind("<Leave>", lambda e, i=i: self.after(15, lambda: self._hover(i)))
            self.btns.append(b)

        tk.Frame.bind(self.track, "<FocusIn>", lambda e: self._focus(True))
        tk.Frame.bind(self.track, "<FocusOut>", lambda e: self._focus(False))
        tk.Frame.bind(self.track, "<Left>", lambda e: self._step(-1))
        tk.Frame.bind(self.track, "<Right>", lambda e: self._step(1))

    def _step(self, d):
        cur = -1 if self.value is None else self.options.index(self.value)
        self.select(max(0, min(len(self.options) - 1, cur + d if cur >= 0 else (0 if d > 0 else len(self.options) - 1))))

    def _focus(self, on):
        self.has_focus = on
        start = 0.0 if on else 1.0
        end = 1.0 if on else 0.0
        animate(self, "focus", 0.15,
                lambda e: self.track.configure(border_color=lerp_color(TRACK, ACCENT, start + (end - start) * e)))

    def select(self, i):
        self.value = self.options[i]
        self.track.focus_set()
        for j in range(len(self.options)):
            self._go(j, 1.0 if j == i else 0.0)

    def _hover(self, i):
        self._go(i, None)

    def _go(self, i, sel_target):
        if sel_target is not None:
            s0 = self.sel[i]

            def upd_sel(e):
                self.sel[i] = s0 + (sel_target - s0) * e
                self._paint(i)
            animate(self, ("sel", i), 0.22, upd_sel)
        h_target = 1.0 if pointer_inside(self.btns[i]) else 0.0
        h0 = self.hov[i]

        def upd_hov(e):
            self.hov[i] = h0 + (h_target - h0) * e
            self._paint(i)
        animate(self, ("hov", i), 0.15, upd_hov)

    def _paint(self, i):
        base = lerp_color(TRACK, TRACK_HOVER, self.hov[i])
        fg = lerp_color(base, ACCENT, self.sel[i])
        tc = lerp_color(TEXT, "#FFFFFF", self.sel[i])
        self.btns[i].configure(fg_color=fg, text_color=tc)


# ───────────────────────── карточка «Вставьте ключ» ─────────────────────────
class KeyCard(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color=WHITE, corner_radius=12, border_width=2,
                         border_color=BORDER_IDLE, height=56)
        self.pack_propagate(False)
        self.confirmed = False
        self.conf = 0.0      # 0 — не подтверждено, 1 — подтверждено
        self.hov = 0.0
        self.icon_key, self.icon_ok = make_icon("key"), make_icon("ok")

        self.icon = ctk.CTkLabel(self, text="", image=self.icon_key, fg_color=WHITE, width=36, height=36)
        self.icon.pack(side="left", padx=(14, 10))
        self.text = ctk.CTkLabel(
            self, text="Вставьте ключ электронной подписи в компьютер и нажмите «ОК» *",
            font=F(13), text_color=TEXT, fg_color=WHITE, wraplength=300, justify="left", anchor="w")
        self.text.pack(side="left", fill="x", expand=True)
        self.btn = ctk.CTkButton(self, text="ОК", width=168, height=38, corner_radius=10,
                                 font=F(14, "bold"), border_width=2, hover=False,
                                 fg_color=WHITE, border_color=ACCENT, text_color=ACCENT,
                                 command=self.toggle)
        self.btn.pack(side="right", padx=(10, 11))
        tk.Frame.configure(self.btn, takefocus=1)
        self.btn_hov = 0.0
        self.btn_focus = False
        self.btn.bind("<Enter>", lambda e: self.after(15, self._btn_refresh))
        self.btn.bind("<Leave>", lambda e: self.after(15, self._btn_refresh))
        tk.Frame.bind(self.btn, "<FocusIn>", lambda e: self._set_focus(True))
        tk.Frame.bind(self.btn, "<FocusOut>", lambda e: self._set_focus(False))
        tk.Frame.bind(self.btn, "<space>", lambda e: self.toggle())
        tk.Frame.bind(self.btn, "<Return>", lambda e: self.toggle())
        self.bind("<Enter>", lambda e: self.after(15, self._card_refresh))
        self.bind("<Leave>", lambda e: self.after(15, self._card_refresh))

    def _set_focus(self, on):
        self.btn_focus = on
        self._btn_refresh()

    def toggle(self):
        self.confirmed = not self.confirmed
        start, end = self.conf, 1.0 if self.confirmed else 0.0
        self.btn.configure(text="✓  ОК, ключ вставлен" if self.confirmed else "ОК")
        self.icon.configure(image=self.icon_ok if self.confirmed else self.icon_key)

        def upd(e):
            self.conf = start + (end - start) * e
            self._paint()
        animate(self, "conf", 0.28, upd)

    def _card_refresh(self):
        target = 1.0 if pointer_inside(self) else 0.0
        start = self.hov

        def upd(e):
            self.hov = start + (target - start) * e
            self._paint()
        animate(self, "hov", 0.18, upd)

    def _btn_refresh(self):
        target = 1.0 if (self.btn_focus or pointer_inside(self.btn)) else 0.0
        start = self.btn_hov

        def upd(e):
            self.btn_hov = start + (target - start) * e
            self._paint()
        animate(self, "bh", 0.15, upd)

    def _paint(self):
        card_bg = lerp_color(WHITE, GREEN_SOFT, self.conf)
        border = lerp_color(lerp_color(BORDER_IDLE, BORDER_HOVER, self.hov), GREEN, self.conf)
        self.configure(fg_color=card_bg, border_color=border)
        self.icon.configure(fg_color=card_bg)
        self.text.configure(fg_color=card_bg)
        # кнопка: белая с синим → при наведении светло-синяя → подтверждено: зелёная
        idle_fill = lerp_color(WHITE, ACCENT_SOFT, self.btn_hov)
        fill = lerp_color(idle_fill, GREEN, self.conf)
        bc = lerp_color(ACCENT, GREEN, self.conf)
        tc = lerp_color(ACCENT, "#FFFFFF", self.conf)
        self.btn.configure(fg_color=fill, border_color=bc, text_color=tc)


# ───────────────────────── главная кнопка ─────────────────────────
class PrimaryButton(ctk.CTkFrame):
    def __init__(self, master, text, command):
        super().__init__(master, fg_color=ACCENT, corner_radius=12, height=48, border_width=2,
                         border_color=ACCENT)
        self.command = command
        self.pack_propagate(False)
        self.hov = 0.0
        self.pressed = False
        self.focused = False
        tk.Frame.configure(self, takefocus=1)

        self.label = ctk.CTkLabel(self, text=text, font=F(16, "bold"), text_color="white", fg_color=ACCENT)
        self.label.place(relx=0.5, rely=0.5, anchor="center")
        self.arrow = ctk.CTkLabel(self, text="→", font=F(20, "bold"), text_color="white", fg_color=ACCENT)
        self._place_arrow(0)

        for w in (self, self.label, self.arrow):
            w.bind("<Enter>", lambda e: self.after(15, self._refresh))
            w.bind("<Leave>", lambda e: self.after(15, self._refresh))
            w.bind("<ButtonPress-1>", self._press)
            w.bind("<ButtonRelease-1>", self._release)
        tk.Frame.bind(self, "<FocusIn>", lambda e: self._focus(True))
        tk.Frame.bind(self, "<FocusOut>", lambda e: self._focus(False))
        tk.Frame.bind(self, "<Return>", lambda e: self.command())
        tk.Frame.bind(self, "<space>", lambda e: self.command())

    def _place_arrow(self, shift):
        self.arrow.place(relx=1.0, x=-52 + shift, rely=0.5, anchor="w")

    def _focus(self, on):
        self.focused = on
        self._refresh()

    def _press(self, _):
        self.pressed = True
        self.focus_set()
        self._paint()

    def _release(self, _):
        was = self.pressed
        self.pressed = False
        self._paint()
        if was and pointer_inside(self):
            self.command()

    def _refresh(self):
        target = 1.0 if (self.focused or pointer_inside(self)) else 0.0
        start = self.hov

        def upd(e):
            self.hov = start + (target - start) * e
            self._place_arrow(10 * self.hov)
            self._paint()
        animate(self, "hov", 0.2, upd)

    def _paint(self):
        c = lerp_color(ACCENT, ACCENT_HOVER, self.hov)
        if self.pressed:
            c = ACCENT_PRESS
        ring = lerp_color(c, "#0F2A66", 1.0 if self.focused else 0.0)
        self.configure(fg_color=c, border_color=ring)
        self.label.configure(fg_color=c)
        self.arrow.configure(fg_color=c)


# ───────────────────────── окно с результатом (для демонстрации) ─────────────────────────
class ResultWindow(ctk.CTkToplevel):
    def __init__(self, master, rows):
        super().__init__(master, fg_color=BG)
        self.title("Макет: данные получены")
        self.resizable(False, False)
        self.geometry("520x560")
        self.transient(master)
        card = ctk.CTkFrame(self, fg_color=WHITE, corner_radius=14, border_width=2, border_color=BORDER_IDLE)
        card.pack(fill="both", expand=True, padx=20, pady=(20, 10))
        ctk.CTkLabel(card, text="Так программа увидит введённые данные",
                     font=F(16, "bold"), text_color=TEXT).pack(anchor="w", padx=18, pady=(16, 8))
        for k, v in rows:
            r = ctk.CTkFrame(card, fg_color="transparent")
            r.pack(fill="x", padx=18, pady=2)
            ctk.CTkLabel(r, text=k, font=F(13), text_color=MUTED, width=170, anchor="w").pack(side="left")
            ctk.CTkLabel(r, text=v or "—", font=F(14, "bold"), text_color=TEXT, anchor="w").pack(side="left")
        ctk.CTkLabel(card, text="Это макет: проверки не выполняются, данные никуда не отправляются.",
                     font=F(12), text_color=MUTED, wraplength=440, justify="left").pack(anchor="w", padx=18, pady=(12, 8))
        PrimaryButton(self, "Закрыть", self.destroy).pack(fill="x", padx=20, pady=(0, 20))
        self.after(50, self.lift)


# ───────────────────────── приложение ─────────────────────────
class App(ctk.CTk):
    def __init__(self):
        super().__init__(fg_color=BG)
        pick_family()
        self.title("Проверки еНот")
        self.resizable(False, False)
        self._center()
        try:
            self.attributes("-alpha", 0.0)
        except Exception:
            pass

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=32, pady=(18, 16))
        body.grid_columnconfigure(0, weight=5, uniform="col")
        body.grid_columnconfigure(1, weight=7, uniform="col")

        title = ctk.CTkFrame(body, fg_color="transparent")
        title.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        ctk.CTkFrame(title, fg_color=ACCENT, width=6, height=24, corner_radius=3).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(title, text="Введите данные гражданина", font=F(22, "bold"),
                     text_color=TEXT).pack(side="left")

        self.fio = Field(body, "Фамилия Имя Отчество", "Иванов Иван Иванович", on_blur_format=fmt_fio)
        self.dob = Field(body, "Дата рождения", "дд.мм.гггг", live_format=fmt_date)
        self.passport = Field(body, "Серия и номер паспорта", "00 00 000000", live_format=fmt_passport)
        self.issued = Field(body, "Дата выдачи паспорта", "дд.мм.гггг", live_format=fmt_date)
        self.snils = Field(body, "СНИЛС", "000-000-000 00", required=False,
                           caption="Для запроса данных о дееспособности", live_format=fmt_snils)
        self.who = Segmented(body, "Кто сегодня исполняет обязанности", ["Нотариус", "ВРИО"])
        self.key = KeyCard(body)

        pad = dict(pady=(0, 9))
        self.fio.grid(row=1, column=0, columnspan=2, sticky="ew", **pad)
        self.dob.grid(row=2, column=0, sticky="ew", padx=(0, 8), **pad)
        self.passport.grid(row=2, column=1, sticky="ew", padx=(8, 0), **pad)
        self.issued.grid(row=3, column=0, sticky="ew", padx=(0, 8), **pad)
        self.snils.grid(row=3, column=1, sticky="ew", padx=(8, 0), **pad)
        self.who.grid(row=4, column=0, columnspan=2, sticky="ew", **pad)
        self.key.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        ctk.CTkLabel(body, text="* — обязательные поля", font=F(12), text_color=MUTED).grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(0, 6))
        PrimaryButton(body, "Начать проверки", self.start).grid(row=7, column=0, columnspan=2, sticky="ew")

        # Enter в поле — переход к следующему полю
        chain = [self.fio, self.dob, self.passport, self.issued, self.snils]
        for a, b in zip(chain, chain[1:]):
            a.entry.bind("<Return>", lambda e, b=b: b.entry.focus_set())
        self.snils.entry.bind("<Return>", lambda e: self.who.track.focus_set())

        self.after(30, self.fio.entry.focus_set)
        self.after(60, self._fade_in)

    def _center(self):
        try:
            scale = self._get_window_scaling()
        except Exception:
            scale = 1.0
        x = int((self.winfo_screenwidth() - WIN_W * scale) / 2)
        y = int((self.winfo_screenheight() - WIN_H * scale) / 2.3)
        self.geometry(f"{WIN_W}x{WIN_H}+{max(x, 0)}+{max(y, 0)}")

    def _fade_in(self):
        animate(self, "fade", 0.35, lambda e: self.attributes("-alpha", e))

    def start(self):
        fio = self.fio.get().strip()
        parts = fio.split()
        fam, name, otch = (parts + ["", "", ""])[:3]
        rows = [
            ("ФИО", fio), ("Фамилия", fam), ("Имя", name), ("Отчество", otch),
            ("Дата рождения", self.dob.get()), ("Паспорт", self.passport.get()),
            ("Дата выдачи паспорта", self.issued.get()), ("СНИЛС", self.snils.get()),
            ("Исполняет обязанности", self.who.value or ""),
            ("Ключ вставлен", "да" if self.key.confirmed else "нет"),
        ]
        ResultWindow(self, rows)


