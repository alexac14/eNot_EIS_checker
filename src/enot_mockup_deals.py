"""Компоненты интерфейса сделок. Точка запуска рабочего приложения — main.py."""
import datetime
import sys
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from enot_mockup import (
    BG, WHITE, TEXT, MUTED, ACCENT, ACCENT_SOFT, BORDER_IDLE, BORDER_HOVER,
    TRACK, TRACK_HOVER, GREEN, GREEN_SOFT, F, animate, lerp_color,
    pointer_inside, fmt_date, Field, Segmented, KeyCard, PrimaryButton,
)
from enot_mockup_multi import Base, TableBoard, AddButton, tween, ellipsize, SafeDestroy

AMBER, AMBER_SOFT = "#9A5B00", "#FFF1D6"
GREY_T = "#566275"
DARK = "#18212F"


# ───────────────────────── модель ─────────────────────────
def plural(n):
    if 11 <= n % 100 <= 14:
        return f"{n} участников"
    return f"{n} участник" + ("" if n % 10 == 1 else "а" if 2 <= n % 10 <= 4 else "ов")


class Deal:
    def __init__(self, title, date="", people=None, history=None):
        self.title, self.date = title, date
        self.people = people or []
        self.history = history or []       # [("Первичные"|"Повторные", "дд.мм.гггг чч:мм")]

    @property
    def primary_done(self):
        return any(k == "Первичные" for k, _ in self.history)

    def status(self):
        if any(k == "Повторные" for k, _ in self.history):
            return "Завершена", GREEN, GREEN_SOFT
        if self.primary_done:
            return "Ждёт повторных", AMBER, AMBER_SOFT
        return "Черновик", GREY_T, TRACK

    def sub(self):
        s = plural(len(self.people) or 1)
        return s + (f" · сделка {self.date}" if self.date else "")

    def history_text(self):
        first = next((t for k, t in self.history if k == "Первичные"), None)
        again = next((t for k, t in reversed(self.history) if k == "Повторные"), None)
        return (f"Первичные: {first or 'не проводились'}   ·   Повторные: {again or 'не проводились'}")


# ───────────────────────── мелкие элементы ─────────────────────────
def pill(parent, text, fg, bg):
    lbl = ctk.CTkLabel(parent, text=f"  {text}  ", height=22, corner_radius=11, fg_color=bg,
                       text_color=fg, font=F(12, "bold"))
    lbl.pack(side="left", padx=(0, 6))
    return lbl


class TextButton(SafeDestroy, ctk.CTkLabel):
    def __init__(self, master, text, command, color=MUTED, hover=ACCENT):
        super().__init__(master, text=text, font=F(13), text_color=color)
        self.c0, self.c1, self.h = color, hover, 0.0
        self.bind("<Button-1>", lambda e: command())
        self.bind("<Enter>", lambda e: self.after(15, self._r))
        self.bind("<Leave>", lambda e: self.after(15, self._r))

    def _r(self):
        tween(self, "h", 1.0 if pointer_inside(self) else 0.0, 0.15,
              lambda: self.configure(text_color=lerp_color(self.c0, self.c1, self.h)))


class Toast(SafeDestroy, ctk.CTkLabel):
    """Всплывающее уведомление внизу окна: проявляется и исчезает."""

    def __init__(self, master, text):
        super().__init__(master, text="   " + text + "   ", height=38, corner_radius=12, fg_color=BG,
                         bg_color=ACCENT, text_color=BG, font=F(13, "bold"))
        self.place(relx=0.5, rely=1.0, y=-18, anchor="s")
        self.lift()
        self.v = 0.0
        tween(self, "v", 1.0, 0.25, self._p)
        self.after(3200, lambda: tween(self, "v", 0.0, 0.3, self._p))
        self.after(3600, self.destroy)

    def _p(self):
        self.configure(fg_color=lerp_color(BG, DARK, self.v), text_color=lerp_color(BG, "#FFFFFF", self.v))


class NewDealDialog(SafeDestroy, ctk.CTkToplevel):
    def __init__(self, master, on_ok, with_people=None):
        super().__init__(master, fg_color=BG)
        self.title("Новая сделка")
        self.geometry("520x400")
        self.resizable(False, False)
        self.transient(master)
        self.on_ok = on_ok
        card = ctk.CTkFrame(self, fg_color=WHITE, corner_radius=14, border_width=2, border_color=BORDER_IDLE)
        card.pack(fill="both", expand=True, padx=20, pady=20)
        ctk.CTkLabel(card, text="Новая сделка", font=F(20, "bold"), text_color=TEXT).pack(anchor="w", padx=22, pady=(18, 2))
        note = ("Участники, которых вы уже ввели, сохранятся в сделку." if with_people else
                "Участников можно добавить сразу или позже.")
        ctk.CTkLabel(card, text=note + "\nДанные лягут в отдельную папку с этим названием.",
                     font=F(13), text_color=MUTED, justify="left").pack(anchor="w", padx=22, pady=(0, 12))
        self.name = Field(card, "Адрес объекта или название ООО", "Звенигородская, 25   или   ООО «Ромашка»")
        self.name.pack(fill="x", padx=22, pady=(0, 10))
        self.date = Field(card, "Дата сделки", "дд.мм.гггг", required=False, live_format=fmt_date,
                          caption="Необязательно: напомним о повторной проверке")
        self.date.pack(fill="x", padx=22, pady=(0, 16))
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=22)
        PrimaryButton(row, "Создать сделку", self.ok).pack(side="left", fill="x", expand=True)
        AddButton(row, "Отмена", self.destroy, width=110, height=48).pack(side="right", padx=(10, 0))
        self.name.entry.bind("<Return>", lambda e: self.date.entry.focus_set())
        self.date.entry.bind("<Return>", lambda e: self.ok())
        self.after(150, lambda: (self.grab_set(), self.name.entry.focus_set()))

    def ok(self):
        title = self.name.get().strip()
        if not title:
            self.name.entry.focus_set()
            return
        self.on_ok(title, self.date.get().strip())
        self.destroy()


# ───────────────────────── шапка рабочей области ─────────────────────────
class DealHeader(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        left = ctk.CTkFrame(self, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w")
        trow = ctk.CTkFrame(left, fg_color="transparent")
        trow.pack(anchor="w")
        ctk.CTkFrame(trow, fg_color=ACCENT, width=6, height=24, corner_radius=3).pack(side="left", padx=(0, 10))
        self.title = ctk.CTkLabel(trow, text="", font=F(22, "bold"), text_color=TEXT)
        self.title.pack(side="left")
        self.meta = ctk.CTkFrame(left, fg_color="transparent")
        self.meta.pack(anchor="w", pady=(6, 0))
        self.sub = ctk.CTkLabel(left, text="", font=F(13), text_color=MUTED, justify="left", anchor="w",
                                wraplength=760)
        self.sub.pack(anchor="w", pady=(6, 0))
        self.act = ctk.CTkFrame(self, fg_color="transparent")
        self.act.grid(row=0, column=1, sticky="ne")

    def _clear(self):
        for w in list(self.meta.winfo_children()) + list(self.act.winfo_children()):
            w.destroy()

    def show_quick(self, on_make_deal):
        self._clear()
        self.title.configure(text="Проверка без сделки")
        pill(self.meta, "Данные не сохраняются", GREY_T, TRACK)
        self.sub.configure(text="Нужно будет повторить проверки в день сделки? Сохраните как сделку:\n"
                                "участников не придётся вводить заново.")
        AddButton(self.act, "+  Добавить как сделку", on_make_deal, width=200, height=40).pack(anchor="e")

    def show_deal(self, deal, on_delete):
        self._clear()
        self.title.configure(text=deal.title)
        text, fg, bg = deal.status()
        pill(self.meta, text, fg, bg)
        if deal.date:
            pill(self.meta, f"Сделка {deal.date}", GREY_T, TRACK)
        self.sub.configure(text=deal.history_text() + "\nПапка сделки: Сделки\\" + deal.title)
        TextButton(self.act, "Удалить сделку", on_delete).pack(anchor="e", pady=(8, 0))


# ───────────────────────── общая логика ─────────────────────────
class DealsBase(Base):
    def init_state(self):
        self.deals = []
        self.current = None
        self.quick_people = [{}]

    def fit(self):
        # Окно сделок сохраняет выбранный пользователем размер.
        # Область участников получает оставшееся место и прокручивается.
        pass

    def build_work(self, parent, card_width):
        self.header = DealHeader(parent, self)
        self.header.configure(height=100)
        self.header.grid_propagate(False)
        self.header.pack(fill="x", pady=(0, 12))
        self.board = TableBoard(parent, width=card_width, on_change=self._chg,
                                on_resize=None)
        self.board.stable = True
        self.board.viewport.configure(height=178)
        self.board.pack(fill="both", expand=True)
        low = ctk.CTkFrame(parent, fg_color="transparent")
        low.pack(fill="x", pady=(14, 0))
        low.grid_columnconfigure(0, weight=0, minsize=300)
        low.grid_columnconfigure(1, weight=1)
        self.who = Segmented(low, "Кто сегодня исполняет обязанности", ["Нотариус", "ВРИО"])
        self.who.grid(row=0, column=0, sticky="sew", padx=(0, 14))
        self.key = KeyCard(low)
        self.key.grid(row=0, column=1, sticky="sew")
        self.go = PrimaryButton(parent, "Начать проверки", self.start)
        self.go.pack(fill="x", pady=(12, 0))
        self.forms_getter = lambda: self.board.rows

    def _chg(self):
        self.update_count(len(self.board.rows))

    def update_count(self, n):
        base = "Начать повторные проверки" if (self.current and self.current.primary_done) else "Начать проверки"
        self.go.label.configure(text=base if n <= 1 else f"{base} ({n})")

    def save_current(self):
        people = [r.values() for r in self.board.rows]
        if self.current:
            self.current.people = people
        else:
            self.quick_people = people or [{}]

    def enter_quick(self, keep_rows=False):
        self.save_current()
        self.current = None
        if not keep_rows:
            self.board.load(self.quick_people)
        self.header.show_quick(self.make_deal)
        self.update_count(len(self.board.rows))
        self.refresh_nav()

    def enter_deal(self, deal):
        if self.current is deal:
            return
        self.save_current()
        self.current = deal
        self.board.load(deal.people or [{}])
        self.header.show_deal(deal, self.delete_deal)
        self.update_count(len(self.board.rows))
        self.refresh_nav()

    def make_deal(self):
        """«Добавить как сделку»: превращает уже введённых людей в сделку."""
        NewDealDialog(self, lambda t, d: self._create(t, d, keep=True), with_people=True)

    def new_deal(self):
        NewDealDialog(self, lambda t, d: self._create(t, d, keep=False))

    def _create(self, title, date, keep):
        self.save_current()
        deal = Deal(title, date, [r.values() for r in self.board.rows] if keep and not self.current else [])
        self.deals.insert(0, deal)
        if keep and not self.current:
            self.current = deal
            self.header.show_deal(deal, self.delete_deal)
            self.update_count(len(self.board.rows))
            self.refresh_nav()
        else:
            self.enter_deal(deal)
        self.toast(f"Макет сделки «{title}» создан.")

    def delete_deal(self):
        if not self.current:
            return
        if messagebox.askyesno("Удалить сделку", f"Удалить сделку «{self.current.title}» и все сохранённые данные участников?"):
            self.deals.remove(self.current)
            self.current = None
            self.enter_quick()
            self.toast("Сделка удалена вместе с данными участников.")

    def toast(self, text):
        Toast(self, text)

    def start(self):
        if self.current:
            self.save_current()
            kind = "Повторные" if self.current.primary_done else "Первичные"
            self.current.history.append((kind, datetime.datetime.now().strftime("%d.%m.%Y %H:%M")))
            self.header.show_deal(self.current, self.delete_deal)
            self.refresh_nav()
            self.toast(f"Демонстрация: {kind.lower()} проверки, {plural(len(self.board.rows))}.")
        super().start()

    def refresh_nav(self):
        pass


# ═════════════════════════ ВАРИАНТ 1: сделки слева ═════════════════════════
class NavItem(SafeDestroy, ctk.CTkFrame):
    def __init__(self, master, title, sub, dot, on_select):
        super().__init__(master, fg_color=WHITE, corner_radius=10, height=56, border_width=2, border_color=WHITE)
        self.pack_propagate(False)
        self.sel = self.hov = 0.0
        self.dot = ctk.CTkFrame(self, width=10, height=10, corner_radius=5, fg_color=dot)
        self.dot.pack(side="left", padx=(12, 10))
        box = ctk.CTkFrame(self, fg_color="transparent")
        box.pack(side="left", fill="both", expand=True, pady=7)
        self.name = ctk.CTkLabel(box, text=ellipsize(title, 26), font=F(13, "bold"), text_color=TEXT,
                                 fg_color=WHITE, anchor="w")
        self.name.pack(anchor="w")
        self.sub = ctk.CTkLabel(box, text=sub, font=F(12), text_color=MUTED, fg_color=WHITE, anchor="w")
        self.sub.pack(anchor="w")
        for w in (self, self.dot, box, self.name, self.sub):
            w.bind("<Button-1>", lambda e: on_select())
            w.bind("<Enter>", lambda e: self.after(15, self._hover))
            w.bind("<Leave>", lambda e: self.after(15, self._hover))

    def _hover(self):
        tween(self, "hov", 1.0 if pointer_inside(self) else 0.0, 0.15, self.paint)

    def set_selected(self, on):
        self.sel = 1.0 if on else 0.0
        self.paint()

    def paint(self):
        fg = lerp_color(lerp_color(WHITE, BG, self.hov), ACCENT_SOFT, self.sel)
        self.configure(fg_color=fg, border_color=lerp_color(fg, ACCENT, self.sel))
        self.name.configure(fg_color=fg, text_color=lerp_color(TEXT, ACCENT, self.sel * 0.7))
        self.sub.configure(fg_color=fg)


class DealsSideApp(DealsBase):
    SIDE_W, CARD_W = 236, 1040

    def __init__(self):
        super().__init__(32 + self.SIDE_W + 14 + self.CARD_W + 32, 640)
        self.resizable(True, True)
        self.minsize(1180, 620)
        self.init_state()
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=32, pady=(16, 16))
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        side = ctk.CTkFrame(body, fg_color=WHITE, corner_radius=14, border_width=2,
                            border_color=BORDER_IDLE, width=self.SIDE_W)
        side.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        side.grid_propagate(False)
        side.pack_propagate(False)
        ctk.CTkLabel(side, text="Сделки", font=F(16, "bold"), text_color=TEXT).pack(anchor="w", padx=16, pady=(14, 8))
        self.search = Field(side, None, "Поиск сделки", required=False, height=38)
        self.search.pack(fill="x", padx=12)
        self.search.entry.bind("<KeyRelease>", lambda e: self.refresh_nav())
        self.quick_item = None
        self.quick_holder = ctk.CTkFrame(side, fg_color="transparent")
        self.quick_holder.pack(fill="x", padx=8, pady=(10, 2))
        ctk.CTkLabel(side, text="СОХРАНЁННЫЕ СДЕЛКИ", font=F(11, "bold"), text_color=MUTED).pack(
            anchor="w", padx=16, pady=(8, 2))
        AddButton(side, "+  Новая сделка", self.new_deal, width=200, height=40).pack(
            side="bottom", fill="x", padx=12, pady=(6, 12))
        self.list = ctk.CTkScrollableFrame(side, fg_color="transparent", corner_radius=0, height=120,
                                           scrollbar_fg_color="transparent", scrollbar_button_color="#C9D2E0",
                                           scrollbar_button_hover_color=BORDER_HOVER)
        self.list.pack(fill="both", expand=True, padx=(8, 4))

        main = ctk.CTkFrame(body, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew")
        self.build_work(main, self.CARD_W)

        self.board.add_row(focus=False, animated=False)
        self.enter_quick(keep_rows=True)
        self.after(60, lambda: self.board.rows[0].fields["fio"].entry.focus_set())
        self.after(60, self.fade_in)

    def refresh_nav(self):
        # Виджеты навигации переиспользуются: наведение не вызывает вспышек,
        # отложенные callbacks не попадают в уже уничтоженную строку меню.
        if self.quick_item is None:
            self.quick_item = NavItem(self.quick_holder, "Проверка без сделки", "данные не сохраняются", ACCENT, self.enter_quick)
            self.quick_item.pack(fill="x")
        self.quick_item.set_selected(self.current is None)
        if not hasattr(self, '_deal_items'):
            self._deal_items = {}
        for d in list(self._deal_items):
            if d not in self.deals:
                self._deal_items.pop(d).destroy()
        text = self.search.get().strip().lower()
        for d in self.deals:
            it = self._deal_items.get(d)
            if text and text not in d.title.lower():
                if it is not None:
                    it.pack_forget()
                continue
            st, fg, _ = d.status()
            if it is None:
                it = NavItem(self.list, d.title, st, fg, lambda d=d: self.enter_deal(d))
                self._deal_items[d] = it
            it.dot.configure(fg_color=fg)
            it.sub.configure(text=st, text_color=fg)
        # Порядок обновляем без уничтожения пунктов.
        visible = [self._deal_items[d] for d in self.deals if not text or text in d.title.lower()]
        for it in visible:
            it.pack_forget()
        for it in visible:
            it.pack(fill="x", pady=(0, 3))
        for d, it in self._deal_items.items():
            it.set_selected(d is self.current)


# ═════════════════════════ ВАРИАНТ 2: стартовый экран ═════════════════════════
class Tile(SafeDestroy, ctk.CTkFrame):
    """Плитка/карточка с плавной подсветкой при наведении."""

    def __init__(self, master, height, on_click):
        super().__init__(master, fg_color=WHITE, corner_radius=14, border_width=2,
                         border_color=BORDER_IDLE, height=height)
        self.pack_propagate(False)
        self.hov = 0.0
        self.kids = []
        self.on_click = on_click

    def finish(self, *labels):
        self.kids = [l for l in labels if l is not None]
        for w in [self] + self.kids:
            w.bind("<Button-1>", lambda e: self.on_click())
            w.bind("<Enter>", lambda e: self.after(15, self._hover))
            w.bind("<Leave>", lambda e: self.after(15, self._hover))

    def _hover(self):
        tween(self, "hov", 1.0 if pointer_inside(self) else 0.0, 0.18, self.paint)

    def paint(self):
        fg = lerp_color(WHITE, "#F5F8FF", self.hov)
        self.configure(fg_color=fg, border_color=lerp_color(BORDER_IDLE, ACCENT, self.hov))
        for k in self.kids:
            try:
                k.configure(fg_color=fg)
            except Exception:
                pass


class DealsHomeApp(DealsBase):
    W = 1180

    def __init__(self):
        super().__init__(self.W, 600)
        self.resizable(True, True)
        self.minsize(1180, 620)
        self.init_state()
        root_pad = ctk.CTkFrame(self, fg_color="transparent")
        root_pad.pack(fill="both", expand=True, padx=32, pady=(16, 16))
        self.home = ctk.CTkFrame(root_pad, fg_color="transparent")
        self.work = ctk.CTkFrame(root_pad, fg_color="transparent")
        self.build_home(self.home)
        back = ctk.CTkFrame(self.work, fg_color="transparent")
        back.pack(fill="x", pady=(0, 10))
        AddButton(back, "←  Все сделки", self.show_home, width=140, height=36).pack(side="left")
        self.build_work(self.work, self.W - 64)
        self.board.add_row(focus=False, animated=False)
        self.show_home()
        self.after(60, self.fade_in)

    # ── стартовый экран ──
    def build_home(self, parent):
        trow = ctk.CTkFrame(parent, fg_color="transparent")
        trow.pack(fill="x", pady=(0, 14))
        ctk.CTkFrame(trow, fg_color=ACCENT, width=6, height=24, corner_radius=3).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(trow, text="Проверки еНот", font=F(22, "bold"), text_color=TEXT).pack(side="left")

        tiles = ctk.CTkFrame(parent, fg_color="transparent")
        tiles.pack(fill="x")
        tiles.grid_columnconfigure((0, 1), weight=1, uniform="t")
        for col, (title, sub, cmd) in enumerate([
                ("Быстрая проверка", "Без сделки. Данные не сохраняются.", self.open_quick),
                ("+  Новая сделка", "Сохраним участников, чтобы повторить проверки в день сделки.", self.new_deal)]):
            t = Tile(tiles, 92, cmd)
            t.grid(row=0, column=col, sticky="ew", padx=(0, 8) if col == 0 else (8, 0))
            a = ctk.CTkLabel(t, text=title, font=F(17, "bold"), text_color=ACCENT, fg_color=WHITE)
            a.pack(anchor="w", padx=20, pady=(18, 2))
            b = ctk.CTkLabel(t, text=sub, font=F(13), text_color=MUTED, fg_color=WHITE)
            b.pack(anchor="w", padx=20)
            t.finish(a, b)

        hrow = ctk.CTkFrame(parent, fg_color="transparent")
        hrow.pack(fill="x", pady=(18, 8))
        ctk.CTkLabel(hrow, text="Сохранённые сделки", font=F(16, "bold"), text_color=TEXT).pack(side="left")
        self.search = Field(hrow, None, "Поиск сделки", required=False, height=36)
        self.search.configure(width=320)
        self.search.pack(side="right")
        self.search.entry.bind("<KeyRelease>", lambda e: self.refresh_nav())
        self.grid_area = ctk.CTkScrollableFrame(parent, fg_color="transparent", corner_radius=0, height=250,
                                                scrollbar_fg_color="transparent",
                                                scrollbar_button_color="#C9D2E0",
                                                scrollbar_button_hover_color=BORDER_HOVER)
        self.grid_area.pack(fill="x")
        for c in range(3):
            self.grid_area.grid_columnconfigure(c, weight=1, uniform="cards")

    def refresh_nav(self):
        for w in self.grid_area.winfo_children():
            w.destroy()
        text = self.search.get().strip().lower()
        i = 0
        for d in self.deals:
            if text and text not in d.title.lower():
                continue
            self._card(d, i)
            i += 1

    def _card(self, d, i):
        t = Tile(self.grid_area, 132, lambda d=d: self.open_deal(d))
        t.grid(row=i // 3, column=i % 3, sticky="ew", padx=4, pady=4)
        title = ctk.CTkLabel(t, text=ellipsize(d.title, 28), font=F(15, "bold"), text_color=TEXT, fg_color=WHITE)
        title.pack(anchor="w", padx=16, pady=(14, 1))
        sub = ctk.CTkLabel(t, text=d.sub(), font=F(13), text_color=MUTED, fg_color=WHITE)
        sub.pack(anchor="w", padx=16)
        hist = ctk.CTkLabel(t, text=d.history[-1][0] + " " + d.history[-1][1][:5] if d.history else "проверок ещё не было",
                            font=F(12), text_color=MUTED, fg_color=WHITE)
        hist.pack(anchor="w", padx=16, pady=(1, 0))
        foot = ctk.CTkFrame(t, fg_color="transparent")
        foot.pack(fill="x", padx=14, pady=(8, 0))
        st, fg, bg = d.status()
        p = ctk.CTkLabel(foot, text=f"  {st}  ", height=22, corner_radius=11, fg_color=bg, text_color=fg,
                         font=F(12, "bold"))
        p.pack(side="left")
        go = ctk.CTkLabel(foot, text="Открыть  →", font=F(13, "bold"), text_color=ACCENT, fg_color=WHITE)
        go.pack(side="right", padx=(0, 2))
        t.finish(title, sub, hist, foot, go)

    # ── переходы ──
    def show_home(self):
        self.save_current()
        self.work.pack_forget()
        self.home.pack(fill="both", expand=True)
        self.refresh_nav()
        self.after(20, self.fit)

    def show_work(self):
        self.home.pack_forget()
        self.work.pack(fill="both", expand=True)
        self.after(20, self.fit)

    def open_quick(self):
        self.enter_quick()
        self.show_work()

    def open_deal(self, deal):
        self.enter_deal(deal)
        self.show_work()

    def _create(self, title, date, keep):
        super()._create(title, date, keep)
        if self.home.winfo_ismapped():
            self.show_work()


VARIANTS = {"1": DealsSideApp, "2": DealsHomeApp}

