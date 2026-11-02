import collections
import datetime as dt
import os
from pathlib import Path
import re
import time

from .domain import pick_certificate
from .engine import AutomationError

def norm(s):
    return re.sub(r'\s+', ' ', str(s)).strip().casefold().replace('ё', 'е').rstrip(':')


def rect_key(control):
    r = control.rectangle()
    return r.left,r.top,r.right,r.bottom


def confirmed(text):
    low = norm(text)
    return not re.search(r'не\s+подписан', low) and bool(re.search(r'\b(подписан[оа]?|отправлен[оа]?|выполнен[оа]?)\b', low))


def model_path():
    import win32api

    return win32api.GetShortPathName(str(Path(__file__).parent/'models'))


class LocalOCR:
    def __init__(self):
        self.api = None

    def lines(self, window):
        import tesserocr
        from PIL import ImageGrab
        if self.api is None:
            self.api = tesserocr.PyTessBaseAPI(path=model_path(), lang='rus+eng', psm=tesserocr.PSM.AUTO)
        r = window.rectangle()
        picture = ImageGrab.grab(bbox=(r.left, r.top, r.right, r.bottom), all_screens=True)
        self.api.SetImage(picture)
        self.api.Recognize()
        result = []
        iterator = self.api.GetIterator()
        if iterator:
            for line in tesserocr.iterate_level(iterator, tesserocr.RIL.TEXTLINE):
                text = (line.GetUTF8Text(tesserocr.RIL.TEXTLINE) or '').strip()
                bbox = line.BoundingBox(tesserocr.RIL.TEXTLINE)
                if text and bbox and line.Confidence(tesserocr.RIL.TEXTLINE) >= 80:
                    a, b, c, d = bbox
                    result.append((text, (a+r.left, b+r.top, c+r.left, d+r.top)))
        self.api.Clear()
        picture.close()

        singles = list(result)
        for text, box in singles:
            chain, current, used = text, box, {box}
            for _ in range(2):
                a,b,c,d = current
                below = [(t,r) for t,r in singles if r not in used and
                         0 <= r[1]-d <= max(12,d-b) and abs(r[0]-a)<=70 and
                         min(c,r[2])>max(a,r[0])]
                if not below:
                    break
                t,r = min(below,key=lambda item:item[1][1]-d)
                chain += ' '+t
                used.add(r)
                current = (min(a,r[0]),b,max(c,r[2]),r[3])
                result.append((chain,current))
        return result


class InputMonitor:
    def __init__(self, stop):
        self.stop = stop
        self.listeners = []

    def start(self):
        from pynput import mouse, keyboard
        def keyboard_filter(msg, data):
            if not data.flags & 0x10 and msg in (0x100, 0x104):
                self.stop.stop('Аварийная остановка F8.' if data.vkCode == 0x77 else 'Остановлено: пользователь нажал клавишу.')
            return False
        def mouse_filter(msg, data):
            if not data.flags & 1:
                self.stop.stop('Остановлено: пользователь тронул мышь.')
            return False
        self.listeners = [keyboard.Listener(win32_event_filter=keyboard_filter),
                          mouse.Listener(win32_event_filter=mouse_filter)]
        for listener in self.listeners:
            listener.start()
            listener.wait()

    def close(self):
        for listener in self.listeners:
            listener.stop()


class WindowsDriver:
    def __init__(self, settings, stop, process_name='eNot.exe'):
        self.settings, self.stop = settings, stop
        self.ocr = LocalOCR()
        self.apps = {}
        self.main = self.scope = None
        self.expected = {}
        self.process_name = process_name
        self.progress_visibility = lambda visible:None
    def prepare(self, inspect_only=False):
        import win32gui, win32process
        from pywinauto import Application
        candidates = []
        def visit(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd):
                return
            pid = win32process.GetWindowThreadProcessId(hwnd)[1]
            try:
                import win32api, win32con
                handle = win32api.OpenProcess(win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
                try:
                    import ctypes
                    from ctypes import wintypes
                    query = ctypes.WinDLL('kernel32',use_last_error=True).QueryFullProcessImageNameW
                    query.argtypes = (wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD))
                    query.restype = wintypes.BOOL
                    buf = ctypes.create_unicode_buffer(32768)
                    size = wintypes.DWORD(len(buf))
                    if not query(int(handle),0,buf,ctypes.byref(size)):
                        raise OSError()
                    name = buf.value
                finally:
                    handle.Close()
                if Path(name).name.casefold() == self.process_name.casefold() and win32gui.GetWindow(hwnd, 4) == 0:
                    candidates.append((hwnd, pid))
            except Exception:
                return
        win32gui.EnumWindows(visit, None)
        if len(candidates) != 1:
            raise AutomationError('Нужно одно открытое главное окно eNot.exe. Запустите еНот и закройте лишние экземпляры.')
        self.hwnd, self.pid = candidates[0]
        for backend in ('win32', 'uia'):
            self.apps[backend] = Application(backend=backend).connect(process=self.pid)
        self.main = self.apps['win32'].window(handle=self.hwnd).wrapper_object()
        self.scope = self.main
        if inspect_only:
            return
        if not self.main.is_enabled() or self._dialogs():
            raise AutomationError('Перед запуском закройте открытые диалоги еНот.')
        self.main.restore()
        self.main.maximize()
        self.main.set_focus()
        self.scope = self.main

    def _dialogs(self):
        import win32gui, win32process
        dialogs = []
        def visit(hwnd, _):
            if win32gui.IsWindowVisible(hwnd) and win32process.GetWindowThreadProcessId(hwnd)[1] == self.pid and hwnd != self.hwnd:
                if win32gui.GetWindow(hwnd, 4):
                    dialogs.append(hwnd)
        win32gui.EnumWindows(visit, None)
        return dialogs

    def guard(self):
        import win32gui
        self.stop.check()
        if not self.main or not win32gui.IsWindow(self.scope.handle):
            raise AutomationError('Окно еНот закрылось.')
        dialogs = self._dialogs()
        if any(h != self.scope.handle for h in dialogs):
            raise AutomationError('Появилось непредвиденное окно еНот. Автоматизация остановлена.')
        if not self.scope.is_enabled() or win32gui.GetForegroundWindow() != self.scope.handle:
            raise AutomationError('Нужное окно еНот потеряло фокус или заблокировано.')

    def wait(self, fn, message):
        deadline = time.monotonic()+float(self.settings.get('timeout', 45))
        while time.monotonic() < deadline:
            self.stop.check()
            result = fn()
            if result is not None and result is not False:
                return result
            self.stop.event.wait(0.2)
        raise AutomationError(message)

    def controls(self, kinds=None):
        self.stop.check()
        found = []
        for backend, app in self.apps.items():
            try:
                scope = app.window(handle=self.scope.handle).wrapper_object()
                for control in scope.descendants():
                    self.stop.check()
                    try:
                        if not control.is_visible():
                            continue
                        kind = str(getattr(control.element_info, 'control_type', '') or control.friendly_class_name())
                        cls = control.class_name()
                        if kinds is None or any(k.casefold() in (kind+' '+cls).casefold() for k in kinds):
                            found.append(control)
                    except Exception:
                        continue
            except AutomationError:
                raise
            except Exception:
                continue
        return found

    def find(self, text, kinds=None, wait=True):
        def attempt():
            hits = [c for c in self.controls(kinds) if norm(c.window_text().replace('&', '')) == norm(text)]

            unique = {}
            for c in hits:
                r = c.rectangle()
                unique[(r.left, r.top, r.right, r.bottom)] = c
            if len(unique) > 1:
                raise AutomationError('Найдено несколько элементов «'+text+'». Нужна настройка адаптера.')
            if unique:
                return next(iter(unique.values()))
            return None
        return self.wait(attempt, 'Не найден элемент «'+text+'».') if wait else attempt()

    def click(self, text, kinds=None):
        if self.scope is self.main and text in ('Добавить','Подписать'):
            self.progress_visibility(False)
        self.guard()
        control = self.find(text, kinds, wait=False)
        if control is not None:
            if not control.is_enabled():
                raise AutomationError('Элемент «'+text+'» недоступен.')
            self.guard()
            control.click_input()
            return
        if not self.settings.get('ocr', True):
            raise AutomationError('Не найден элемент «'+text+'».')
        lines = self.ocr.lines(self.scope)
        matches = [box for label, box in lines if norm(label) == norm(text)]
        if len(matches) != 1:
            raise AutomationError('Локальное распознавание не нашло однозначный элемент «'+text+'».')
        self.guard()
        from pywinauto import mouse
        a,b,c,d = matches[0]
        mouse.click(coords=((a+c)//2, (b+d)//2))

    def dialog(self, title):
        def attempt():
            self.stop.check()
            for hwnd in self._dialogs():
                import win32gui
                if norm(win32gui.GetWindowText(hwnd)) == norm(title):
                    self.scope = self.apps['win32'].window(handle=hwnd).wrapper_object()
                    self.scope.set_focus()
                    return self.scope
            return None
        return self.wait(attempt, 'Не открылось окно «'+title+'».')

    def main_again(self):
        self.wait(lambda: not self._dialogs(), 'Диалог еНот не закрылся. Проверьте сообщение в еНот.')
        self.scope = self.main
        self.main.set_focus()
        self.progress_visibility(True)

    def _signature_owned(self, hwnd, certificate_handle):
        import win32gui
        seen = set()
        owner = win32gui.GetWindow(hwnd, 4)
        while owner and owner not in seen:
            if owner in (self.main.handle, certificate_handle):
                return True
            seen.add(owner)
            owner = win32gui.GetWindow(owner, 4)
        return False

    def _signature_popup(self, hwnd):
        from pywinauto.controls.hwndwrapper import HwndWrapper
        return HwndWrapper(hwnd)

    def _signature_ready(self, window):
        controls = [c for c in window.descendants() if c.is_visible()]
        if any('edit' in c.class_name().casefold() for c in controls):
            raise AutomationError('Дополнительное окно подписания содержит поле ввода. Подтвердите его вручную; Enter не отправлен.')
        buttons = [c for c in controls if 'button' in c.class_name().casefold()]
        if not buttons:
            return False
        named = lambda c:norm(c.window_text().replace('&',''))
        ok = [c for c in buttons if named(c) in ('ок','ok')]
        cancel = [c for c in buttons if named(c) in ('отмена','cancel')]
        if len(buttons)!=2 or len(ok)!=1 or len(cancel)!=1:
            raise AutomationError('Неожиданное окно после выбора сертификата. Enter не отправлен; проверьте еНот.')
        if not window.is_enabled() or not ok[0].is_enabled():
            return False
        focus = window.get_focus()
        if focus is None or focus.handle==window.handle:
            return False
        if focus.handle!=ok[0].handle:
            raise AutomationError('В дополнительном окне подписания фокус не на ОК. Enter не отправлен.')
        return True

    def confirm_signature(self, certificate_handle):
        import win32gui
        from pywinauto.keyboard import send_keys


        self.stop.event.wait(.05)
        deadline = time.monotonic()+float(self.settings.get('timeout',45))
        while time.monotonic()<deadline:
            self.stop.check()
            if not win32gui.IsWindow(self.main.handle):
                raise AutomationError('Окно еНот закрылось перед подтверждением подписи.')
            hwnd = win32gui.GetForegroundWindow()
            if hwnd and hwnd not in (self.main.handle,certificate_handle):
                if not self._signature_owned(hwnd,certificate_handle):
                    raise AutomationError('Окно подтверждения подписи потеряло фокус. Enter не отправлен.')
                window = self._signature_popup(hwnd)
                if self._signature_ready(window):
                    self.stop.check()
                    if (win32gui.GetForegroundWindow()!=hwnd or
                        not self._signature_owned(hwnd,certificate_handle) or
                        not self._signature_ready(window)):
                        raise AutomationError('Окно подтверждения подписи изменилось. Enter не отправлен.')
                    self.scope = window
                    send_keys('{ENTER}',pause=0)
                    self.wait(lambda:not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd),
                              'Дополнительное окно подписания не закрылось. Enter уже отправлен один раз; проверьте еНот.')
                    return
            self.stop.event.wait(.02)
        raise AutomationError('Дополнительное окно подписания не появилось или не готово. Enter не отправлен; проверьте еНот.')

    def set_field(self, label, value):
        self.guard()
        anchor = self.find(label, ('Text','Static'), wait=False)
        bbox = anchor.rectangle() if anchor else None
        if bbox:
            pos = (bbox.left, bbox.top, bbox.right, bbox.bottom)
        else:
            matches = [box for text,box in self.ocr.lines(self.scope) if norm(text) == norm(label)]
            if len(matches) != 1:
                raise AutomationError('Не найдена подпись поля «'+label+'».')
            pos = matches[0]
        a,b,c,d = pos
        options = {}
        for edit in self.controls(('Edit',)):
            r = edit.rectangle()

            if r.left >= c-3 and abs((r.top+r.bottom)/2-(b+d)/2) < max(20, (d-b)):
                options[(r.left,r.top,r.right,r.bottom)] = edit
        if not options:
            raise AutomationError('Поле «'+label+'» недоступно для прямой записи. Нужна диагностика.')
        ordered = sorted(options.items(), key=lambda item:item[0][0])
        control = ordered[0][1]
        self.guard()
        try:
            control.set_edit_text(value)
            actual = control.get_value() if hasattr(control,'get_value') else control.window_text()
        except Exception:
            raise AutomationError('Не удалось прямо записать значение в поле «'+label+'».')
        if actual.strip() != value.strip():
            raise AutomationError('Поле «'+label+'» не подтвердило введённое значение.')

    def choose_ags(self):
        self.guard()
        hits = []
        for c in self.controls(('ComboBox',)):
            try:
                if 'заключение брака' in [norm(t) for t in c.item_texts()]:
                    hits.append(c)
            except Exception:
                pass
        unique = {rect_key(c):c for c in hits}
        if len(unique) != 1:
            raise AutomationError('Не удалось однозначно прочитать список «Тип АГС».')
        combo = next(iter(unique.values()))
        self.guard()
        combo.select('заключение брака')
        if norm(combo.selected_text()) != 'заключение брака':
            raise AutomationError('Тип АГС не подтверждён.')

    def check_divorce(self):
        label = 'Дополнительно запросить сведения о расторжении брака'
        hits = [c for c in self.controls(('CheckBox', 'Button')) if norm(c.window_text()) == norm(label)]
        unique = {rect_key(c):c for c in hits}
        if len(unique) != 1:
            raise AutomationError('Не удалось однозначно найти галочку расторжения брака.')
        control = next(iter(unique.values()))
        def checked():
            return control.get_toggle_state() if hasattr(control, 'get_toggle_state') else control.get_check_state()
        self.guard()
        if checked() != 1:
            control.click_input()
        if checked() != 1:
            raise AutomationError('Галочка расторжения брака не подтверждена.')

    def table_rows(self):
        tables = {}
        for table in self.controls(('ListView',)):
            if hasattr(table, 'item_count') and hasattr(table, 'get_item'):
                tables.setdefault(rect_key(table), table)
        if tables:
            if len(tables) != 1:
                raise AutomationError('Найдено несколько таблиц запросов. Нужна настройка адаптера.')
            table = next(iter(tables.values()))
            try:
                return [(' '.join(table.get_item(index, col).text()
                                  for col in range(table.column_count())), table.get_item(index, 0))
                        for index in range(table.item_count())]
            except Exception:
                raise AutomationError('Не удалось прочитать строки таблицы запросов.')
        rows = []
        for c in self.controls(('DataItem', 'ListItem')):
            try:
                parts = c.texts()
                if hasattr(c, 'descendants'):
                    parts += [x.window_text() for x in c.descendants()]
                text = ' '.join(dict.fromkeys(t for t in parts if t))
                if text:
                    rows.append((text,c))
            except Exception:
                continue
        unique = {}
        for text,c in rows:
            r = c.rectangle()
            unique[(norm(text),r.top,r.bottom)] = (text,c)
        return sorted(unique.values(), key=lambda item: (item[1].rectangle().top, item[1].rectangle().left))

    @staticmethod
    def matches_record(text, person, kind):
        return (norm(person['fio']) in norm(text) and person['dob'] in text
                and (kind is None or norm(kind) in norm(text)))

    def records(self, person, kind):
        return [(text, row) for text, row in self.table_rows() if self.matches_record(text, person, kind)]

    def newest_requests_ready(self, person, kinds):
        newest = self.table_rows()[:len(kinds)]
        return len(newest) == len(kinds) and all(
            sum(self.matches_record(text, person, kind) and bool(re.search(r'не\s+подписан', norm(text)))
                for text, row in newest) == 1 for kind in kinds)

    def reveal_first_row(self):
        self.guard()
        rows = self.table_rows()
        if rows:
            row = rows[0][1]
            if hasattr(row, 'ensure_visible'):
                row.ensure_visible()
            elif hasattr(row, 'scroll_into_view'):
                row.scroll_into_view()

    def _surface_ready(self, page):
        controls = self.controls()
        names = [norm(c.window_text().replace('&','')) for c in controls]
        title = norm(self.main.window_text())
        if page == 'registry':
            tab = 'поиск брачных договоров'
            title_matches = 'реестр нотариальных действий еис' in title
            tabs = [c for c in controls if norm(c.window_text().replace('&',''))==tab]
            if tabs:
                return title_matches and any(c.is_enabled() for c in tabs)
            marker = False
            if not marker and self.settings.get('ocr',True):
                words = [norm(t) for t,b in self.ocr.lines(self.main)]
                marker = title_matches and tab in words
            return marker
        if page == 'zags':
            marker = 'запросы в загс' in title or any(re.match(r'^запросы в загс\s*\(',n) for n in names)
        else:
            marker = 'фио стороны брачного договора' in names
            if not marker and self.settings.get('ocr',True):
                marker = any(norm(t)=='фио стороны брачного договора' for t,b in self.ocr.lines(self.main))
        buttons = [c for c in controls if norm(c.window_text().replace('&',''))=='добавить' and c.is_enabled()]

        return marker and len({rect_key(c) for c in buttons})==1

    def wait_ready(self, page):
        def ready():
            self.guard()
            return self._surface_ready(page)
        self.wait(ready,'Раздел еНот не подтвердил готовность за отведённое время. Дальнейшие действия не выполнялись.')

    def open_zags(self):
        self.guard()
        self.click('Запросы в ЗАГС')
        self.wait_ready('zags')

    def create_zags(self, person):
        kinds = ('расторжение брака', 'заключение брака')
        self.reveal_first_row()
        before = {k:len(self.records(person,k)) for k in kinds}
        if any(re.search(r'не\s+подписан',norm(t)) for k in kinds for t,c in self.records(person,k)):
            raise AutomationError('У участника уже есть неподписанные запросы ЗАГС. Завершите их вручную перед новым запуском.')
        self.click('Добавить', ('Button',))
        self.dialog('Запрос сведений в ЗАГС')
        self.choose_ags()
        self.check_divorce()
        for label, value in zip(('Фамилия', 'Имя', 'Отчество'), person['fio'].split()):
            self.set_field(label, value)
        self.set_field('Дата рождения', person['dob'])
        self.click('ОК', ('Button',))
        self.main_again()
        self.reveal_first_row()
        self.wait(lambda:self.newest_requests_ready(person, kinds),
                  'Верхние строки новых запросов ЗАГС не подтверждены. Проверьте еНот перед повтором.')
        for k in kinds:
            self.wait(lambda k=k:len(self.records(person,k)) == before[k]+1,
                      'Новые строки ЗАГС не подтверждены. Не создавайте дубликаты; проверьте еНот.')

    def open_contracts(self):
        self.click('Реестр нотариальных действий ЕИС')
        self.wait_ready('registry')
        self.click('Поиск брачных договоров')
        self.wait_ready('contracts')

    def finalize_dispatch(self):
        self.stop.check()
        if self.scope.handle != self.main.handle or self._dialogs():
            raise AutomationError('Нельзя нажать F5: открыто другое окно или диалог еНот.')
        self.guard()
        from pywinauto.keyboard import send_keys
        send_keys('{F5}',pause=0)
        self.stop.check()
        self.guard()

    def create_contract(self, person):
        self.reveal_first_row()
        count = len(self.records(person,None))
        if any(re.search(r'не\s+подписан',norm(t)) for t,c in self.records(person,None)):
            raise AutomationError('Есть неподписанный запрос брачного договора. Проверьте его перед новым запуском.')
        self.click('Добавить', ('Button',))
        self.dialog('Ввод сведений о брачном договоре')
        self.set_field('ФИО стороны брачного договора', person['fio'])
        self.set_field('Дата рождения', person['dob'])
        self.click('ОК', ('Button',))
        self.main_again()
        self.reveal_first_row()
        self.wait(lambda:self.newest_requests_ready(person, (None,)),
                  'Верхняя строка нового брачного договора не подтверждена. Проверьте еНот перед повтором.')
        self.wait(lambda:len(self.records(person,None)) == count+1,
                  'Новая строка брачного договора не подтверждена. Проверьте еНот перед повтором.')

    def sign_record(self, person, kind, signer):
        self.guard()
        all_rows = self.records(person,kind)
        total_before = len(all_rows)
        signed_before = sum(confirmed(t) for t,c in all_rows)
        rows = [(text,c) for text,c in all_rows if re.search(r'не\s+подписан',norm(text))]
        if len(rows) != 1:
            raise AutomationError('Нужна ровно одна неподписанная запись этого участника и типа. Проверьте дубликаты в еНот.')
        text, row = rows[0]
        try:
            if hasattr(row, 'ensure_visible'):
                row.ensure_visible()
            elif hasattr(row, 'scroll_into_view'):
                row.scroll_into_view()
            self.guard()
            row.select()
            if not row.is_selected():
                raise ValueError()
        except Exception:
            raise AutomationError('Невозможно подтвердить выделение нужной записи. Подписание не выполнено.')
        self.click('Подписать', ('Button',))
        self.dialog('Выбор варианта')
        lists = self.controls(('ListBox',))
        candidates = {}
        for control in lists:
            try:
                items = control.item_texts()
                if any('действует до' in norm(t) for t in items):
                    candidates[rect_key(control)] = (control, items)
            except Exception:
                pass
        if len(candidates) != 1:
            raise AutomationError('Список сертификатов недоступен для надёжного чтения.')
        control, items = next(iter(candidates.values()))
        owner = self.settings['notary' if signer == 'Нотариус' else 'acting']
        try:
            index = pick_certificate(items, signer, owner)
        except ValueError as e:
            raise AutomationError(str(e))
        self.guard()
        control.select(index)
        if index not in control.selected_indices():
            raise AutomationError('Выбор сертификата не подтверждён.')
        certificate_handle = self.scope.handle
        self.click('ОК', ('Button',))
        self.confirm_signature(certificate_handle)
        self.main_again()

        def status_changed():
            current = self.records(person,kind)
            return len(current)==total_before and sum(confirmed(t) for t,c in current)==signed_before+1
        self.wait(status_changed,
                  'Статус после подписания не подтверждён. Запрос мог быть подписан; проверьте еНот перед повтором.')

    def diagnose(self):
        safe_names = {'Добавить','Подписать','Запросы в ЗАГС','Реестр нотариальных действий ЕИС','Поиск брачных договоров',
                      'Фамилия','Имя','Отчество','Дата рождения','Тип АГС','ОК','Отмена'}
        self.prepare()
        report = dict(process='eNot.exe', controls=[], ocr_available=(Path(__file__).parent/'models/rus.traineddata').exists())
        for control in self.controls():
            try:
                info = dict(class_name=control.class_name(), kind=control.friendly_class_name())
                rect = control.rectangle()
                info['rect_pixels'] = [rect.left,rect.top,rect.right,rect.bottom]
                if hasattr(control,'control_id'):
                    info['control_id'] = control.control_id()
                name = control.window_text()
                if name in safe_names:
                    info['name'] = name
                report['controls'].append(info)
            except Exception:
                continue
        return report
