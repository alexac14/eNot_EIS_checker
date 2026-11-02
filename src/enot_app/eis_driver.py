import re
from dataclasses import dataclass

from .driver import WindowsDriver, norm, rect_key
from .engine import AutomationError


def label_name(text):
    return norm(str(text).replace('&', '').replace('*', '').lstrip(' -')).rstrip(':')


def digits(text):
    return re.sub(r'\D', '', str(text))


@dataclass(frozen=True)
class JournalRecord:
    number: str
    fio: str
    dob: str
    status: str
    request_type: str = ''
    snils: str = ''

    def matches(self, person, page):
        return (norm(self.fio) == norm(person['fio']) and self.dob == person['dob'] and
                (page != 'capacity' or (label_name(self.request_type) == 'о дееспособности'
                 and digits(self.snils) == digits(person['snils']))))


class EISDriver(WindowsDriver):
    SECTIONS = {'population': 'Запросы в регистр населения', 'capacity': 'Запросы в ГИС ЕЦП'}
    DOCUMENT = 'Паспорт гражданина Российской Федерации'
    HISTORY = 'Все имеющиеся в ЕРН сведения (актуальные и исторические)'

    def __init__(self, settings, stop, process_name='EISClient.exe'):
        super().__init__(settings, stop, process_name)
        self.page = None

    def prepare(self):
        try:
            super().prepare()
        except AutomationError:
            raise AutomationError('Не удалось подготовить клиент ЕИС. Нужно одно главное окно EISClient.exe без открытых диалогов; проверьте одинаковые права приложений.')
        if not norm(self.main.window_text()).startswith('клиент еис'):
            raise AutomationError('Заголовок найденного EISClient.exe не соответствует клиенту ЕИС.')

    def guard(self):
        try:
            super().guard()
        except AutomationError as exc:
            from .engine import StopRequested
            if isinstance(exc, StopRequested):
                raise
            raise AutomationError('Клиент ЕИС потерял фокус, закрыт или показывает неожиданное окно. Дальнейшие действия остановлены.')

    def activate(self):
        self.stop.check()
        self.progress_visibility(False)
        if self._dialogs() or not self.main.is_enabled():
            raise AutomationError('Перед переходом в клиент ЕИС закройте его диалоги.')
        self.scope = self.main
        self.main.restore()
        self.main.maximize()
        self.main.set_focus()
        self.guard()
        self.progress_visibility(True)

    def element(self, text, kinds=None, required=True):
        hits = {rect_key(c): c for c in self.controls(kinds)
                if label_name(c.window_text()) == label_name(text)}
        if len(hits) > 1:
            raise AutomationError('Клиент ЕИС: несколько элементов «'+text+'». Нужна диагностика структуры.')
        if hits:
            return next(iter(hits.values()))
        if required:
            raise AutomationError('Клиент ЕИС: недоступен элемент «'+text+'». Нужна диагностика структуры.')

    def press(self, text):
        self.guard()
        self.progress_visibility(False)
        control = self.element(text)
        if not control.is_enabled():
            raise AutomationError('Клиент ЕИС: элемент «'+text+'» недоступен.')
        self.guard()
        try:
            control.click_input()
        except Exception:
            raise AutomationError('Клиент ЕИС: действие «'+text+'» не подтверждено. Проверьте клиент перед повтором.')

    def navigation_present(self, text):
        return self.element(text, required=False) is not None

    def navigate(self, text):
        self.guard()
        self.progress_visibility(False)
        self.press(text)

    def _ready(self, page):
        self.guard()
        return (label_name(self.SECTIONS[page]) in label_name(self.main.window_text()) and
                (button := self.element('Новый запрос', required=False)) is not None and button.is_enabled())

    def open_service(self, page):
        self.page = None
        section = self.SECTIONS[page]
        if not self._ready(page):
            if not self.navigation_present(section):
                self.navigate('Сервисы ЕИС')
                self.wait(lambda: self.navigation_present(section),
                          'Клиент ЕИС: не открылось меню «Сервисы ЕИС».')
            self.navigate(section)
            self.wait(lambda: self._ready(page), 'Клиент ЕИС: нужный раздел не подтвердил готовность.')
        self.page = page

        if self.element('Сбросить фильтр', required=False) is not None:
            self.press('Сбросить фильтр')
        self.journal_records()
        self.progress_visibility(True)

    def open_population(self):
        self.open_service('population')

    def open_capacity(self):
        self.open_service('capacity')

    @staticmethod
    def parse_journal(headers, rows):
        names = [label_name(h) for h in headers]
        required = ['номер', 'фио', 'дата рождения', 'статус запроса']
        if any(names.count(name) != 1 for name in required):
            raise AutomationError('Клиент ЕИС: структура журнала не распознана. Отправка не выполнялась.')
        result = []
        for cells in rows:
            if len(cells) != len(names):
                raise AutomationError('Клиент ЕИС: ячейки журнала недоступны для надёжного чтения.')
            record = dict(zip(names, cells))
            number = record['номер'].strip()
            if not number:
                raise AutomationError('Клиент ЕИС: номер записи журнала не прочитан.')
            result.append(JournalRecord(number, record['фио'].strip(), record['дата рождения'].strip(),
                                        record['статус запроса'].strip(), record.get('тип запроса', '').strip(),
                                        record.get('снилс', '').strip()))
        if len({r.number for r in result}) != len(result):
            raise AutomationError('Клиент ЕИС: номера записей журнала неоднозначны.')
        return result

    def journal_records(self):
        self.guard()
        if self.scope.handle != self.main.handle or not self.page or not self._ready(self.page):
            raise AutomationError('Клиент ЕИС: журнал нужного раздела не подтверждён.')
        tables = {}
        for c in self.controls(('ListView',)):
            if hasattr(c, 'column_count') and hasattr(c, 'get_item'):
                tables.setdefault(rect_key(c), c)
        if tables:
            if len(tables) != 1:
                raise AutomationError('Клиент ЕИС: найдено несколько журналов.')
            table = next(iter(tables.values()))
            headers = [table.get_column(i)['text'] for i in range(table.column_count())]
            rows = [[table.get_item(i, col).text() for col in range(table.column_count())]
                    for i in range(table.item_count())]
            return self.parse_journal(headers, rows)

        grids = {rect_key(c): c for c in self.controls(('DataGrid', 'Table'))}
        if len(grids) != 1:
            raise AutomationError('Клиент ЕИС: таблица запросов недоступна через Win32/UIA. Нужна диагностика на рабочем ПК.')
        grid = next(iter(grids.values()))
        headers = sorted(grid.descendants(control_type='HeaderItem'), key=lambda c: c.rectangle().left)
        rows = []
        for row in grid.children(control_type='DataItem'):
            cells = sorted(row.children(), key=lambda c: c.rectangle().left)
            rows.append([c.window_text() for c in cells])
        if not headers:
            raise AutomationError('Клиент ЕИС: заголовки таблицы недоступны через UIA.')
        return self.parse_journal([c.window_text() for c in headers], rows)

    def field(self, label):
        self.guard()
        anchor = self.element(label, ('Text', 'Static'))
        a = anchor.rectangle()
        choices = {}
        for control in self.controls(('Edit', 'DateTimePicker')):
            r = control.rectangle()
            if r.left >= a.right-3 and abs((r.top+r.bottom-a.top-a.bottom)/2) <= max(15, a.height()):
                choices.setdefault(rect_key(control), control)
        if not choices:
            raise AutomationError('Клиент ЕИС: поле «'+label+'» недоступно для записи и чтения.')

        return min(choices.values(), key=lambda c: c.rectangle().left)

    def read_field(self, label):
        control = self.field(label)
        if hasattr(control, 'get_time'):
            value = control.get_time()
            return f'{value.wDay:02}.{value.wMonth:02}.{value.wYear:04}'
        try:
            return str(control.get_value() if hasattr(control, 'get_value') else control.window_text()).strip()
        except Exception:
            raise AutomationError('Клиент ЕИС: значение поля «'+label+'» не прочитано.')

    def write_field(self, label, value):
        control = self.field(label)
        self.guard()
        try:
            if hasattr(control, 'set_time'):
                day, month, year = value.split('.')


                control.set_focus()
                self.guard()
                control.type_keys('{HOME}'+day+'{RIGHT}'+month+'{RIGHT}'+year+'{TAB}',
                                  set_foreground=False,pause=.05)
            elif hasattr(control, 'set_edit_text'):
                control.set_edit_text(value)
            elif hasattr(control, 'set_value'):
                control.set_value(value)
            else:
                raise ValueError()
        except Exception:
            raise AutomationError('Клиент ЕИС: поле «'+label+'» не поддерживает подтверждаемую запись.')
        self.assert_field(label, value)

    def assert_field(self, label, value):
        actual = self.read_field(label)
        equal = digits(actual) == digits(value) if label in ('СНИЛС', 'Серия и номер') else actual == value
        if not equal:
            raise AutomationError('Клиент ЕИС: поле «'+label+'» не подтвердило введённое значение. Запрос не отправлен.')

    def selected(self, text):
        control = self.element(text)
        for method in ('is_checked', 'get_check_state', 'is_selected', 'get_toggle_state'):
            if hasattr(control, method):
                try:
                    value = getattr(control, method)()
                    return value == 1
                except Exception:
                    continue
        raise AutomationError('Клиент ЕИС: состояние переключателя «'+text+'» не прочитано.')

    def choose(self, text):
        self.guard()
        if not self.selected(text):
            self.press(text)
        self.wait(lambda: self.selected(text), 'Клиент ЕИС: переключатель не подтвердил выбор.')

    def choose_document(self):
        matches = {}
        for combo in self.controls(('ComboBox',)):
            try:
                if self.DOCUMENT in combo.item_texts():
                    matches.setdefault(rect_key(combo), combo)
            except Exception:
                continue
        if len(matches) != 1:
            raise AutomationError('Клиент ЕИС: список видов документов недоступен или неоднозначен.')
        combo = next(iter(matches.values()))
        self.guard()
        combo.select(self.DOCUMENT)
        if combo.selected_text() != self.DOCUMENT:
            raise AutomationError('Клиент ЕИС: вид документа не подтверждён.')

    def _confirm_sent(self, person, before):
        self.guard()
        if not self._ready(self.page):
            return False
        current = self.journal_records()
        fresh = [r for r in current if r.number not in before]
        if len(fresh) > 1:
            raise AutomationError('Клиент ЕИС: после отправки появилось несколько новых запросов. Проверьте журнал перед повтором.')
        if not fresh:
            return False
        row = fresh[0]
        if not row.matches(person, self.page):
            raise AutomationError('Клиент ЕИС: данные новой записи не совпадают с участником. Проверьте журнал перед повтором.')
        status = label_name(row.status)
        if status in ('ошибка', 'ошибка отправки', 'отклонен', 'отклонён'):
            raise AutomationError('Клиент ЕИС: журнал сообщил об ошибке запроса. Проверьте его вручную.')
        return status in ('отправлен', 'отправлено', 'выполнен', 'выполнено', 'в обработке', 'принят')

    def submit(self, person, page):
        from .domain import normalized, valid_snils
        person = normalized(person)
        if page == 'capacity' and not valid_snils(person['snils']):
            raise AutomationError('Клиент ЕИС: для дееспособности нужен корректный СНИЛС.')
        self.guard()
        if self.page != page or not self._ready(page):
            raise AutomationError('Клиент ЕИС: перед созданием запроса открыт другой раздел.')
        before_rows = self.journal_records()
        if any(r.matches(person, page) and label_name(r.status) in ('черновик', 'не отправлен') for r in before_rows):
            raise AutomationError('Клиент ЕИС: уже есть неотправленный запрос этого участника. Завершите его вручную.')
        before = {r.number for r in before_rows}
        self.press('Новый запрос')
        self.dialog('Запрос в ЕРН' if page == 'population' else 'Создание запроса')
        if page == 'population':
            self.choose('Документ, удостоверяющий личность')
            self.choose_document()
        else:
            self.choose('о дееспособности')
        surname, first, patronymic = person['fio'].split()
        fields = [('Фамилия', surname), ('Имя', first), ('Отчество', patronymic), ('Дата рождения', person['dob'])]
        if page == 'population':
            fields += [('Серия и номер', person['passport']), ('Дата выдачи', person['issued'])]
        else:
            fields += [('СНИЛС', person['snils'])]
        for label, value in fields:
            self.write_field(label, value)
        if page == 'population':
            self.choose(self.HISTORY)
            self.choose('Все сведения')

        for label, value in fields:
            self.assert_field(label, value)
        if page == 'population':
            if not self.selected('Документ, удостоверяющий личность') or not self.selected(self.HISTORY) or not self.selected('Все сведения'):
                raise AutomationError('Клиент ЕИС: параметры регистра населения изменились. Запрос не отправлен.')
            self.choose_document()
        elif not self.selected('о дееспособности'):
            raise AutomationError('Клиент ЕИС: тип сведений изменился. Запрос не отправлен.')
        self.press('Отправить')

        self.main_again()
        self.wait(lambda: self._confirm_sent(person, before),
                  'Клиент ЕИС: отправка не подтверждена новой записью журнала. Запрос мог уйти; проверьте журнал перед повтором.')

    def create_population(self, person):
        self.submit(person, 'population')

    def create_capacity(self, person):
        self.submit(person, 'capacity')

    def diagnose(self):
        super().prepare(inspect_only=True)

        safe = {'Новый запрос', 'Отправить', 'Сервисы ЕИС', *self.SECTIONS.values(),
                'Фамилия', 'Имя', 'Отчество', 'Дата рождения', 'СНИЛС', 'Серия и номер', 'Дата выдачи'}
        safe.update({'Вид документа', 'Документ, удостоверяющий личность', self.HISTORY,
                     'Все сведения', 'о дееспособности', 'Номер', 'ФИО', 'Статус запроса', 'Тип запроса'})
        report = dict(process='EISClient.exe', read_only=True, scopes=[])
        handles=[self.main.handle,*self._dialogs()]
        for handle in handles:
            self.scope=self.apps['win32'].window(handle=handle).wrapper_object()
            scope=dict(main=(handle==self.main.handle),controls=[])
            title=self.scope.window_text()
            if title in ('Запрос в ЕРН','Создание запроса'):scope['dialog']=title
            for c in self.controls():
                info = dict(class_name=c.class_name(), kind=c.friendly_class_name(), rect=list(rect_key(c)))

                kind=str(getattr(c.element_info,'control_type','') or c.friendly_class_name()).casefold()
                if kind in ('text','static','button','radiobutton','headeritem','menuitem') and label_name(c.window_text()) in {label_name(s) for s in safe}:
                    info['name'] = c.window_text()
                scope['controls'].append(info)
            report['scopes'].append(scope)
        return report
