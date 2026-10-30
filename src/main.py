"""Рабочая сборка. Сетевые операции Python блокируются до загрузки приложения."""
import sys
sys.coinit_flags = 2
from enot_app.privacy import install
install()


def main():
    if len(sys.argv) != 1:
        return 2
    import customtkinter as ctk
    from tkinter import messagebox
    from enot_app.ui import App
    ctk.set_appearance_mode('light')
    try:
        app = App()
    except Exception:
        root = ctk.CTk()
        root.withdraw()
        messagebox.showerror('Не удалось запустить','Проверьте доступ к папке данных и убедитесь, что программа ещё не открыта. Данные не перезаписаны.')
        root.destroy()
        return 1
    app.mainloop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
