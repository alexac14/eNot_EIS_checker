import datetime as dt
import re
from dataclasses import dataclass, field

KEYS = ('fio', 'dob', 'passport', 'issued', 'snils')

PASSPORT_REGIONS = set('01 03 04 05 07 08 10 11 12 14 15 17 18 19 20 22 24 25 26 27 28 29 30 32 33 34 36 37 38 40 41 42 44 45 46 47 48 49 50 51 52 53 54 56 57 58 60 61 63 64 65 66 67 68 69 70 71 72 73 75 76 77 78 79 80 81 82 83 84 85 86 87 88 89 90 91 92 93 94 95 96 97 98 99'.split())


def normalized(p):
    result = {k: str(p.get(k, '')).strip() for k in KEYS}
    result['fio'] = ' '.join('-'.join(s[:1].upper()+s[1:].lower() for s in w.split('-')) for w in result['fio'].split())
    for key in ('dob', 'issued'):
        raw = result[key]
        if re.fullmatch(r'\d{8}', raw):
            result[key] = f'{raw[:2]}.{raw[2:4]}.{raw[4:]}'
    raw = re.sub(r'\s', '', result['passport'])
    if re.fullmatch(r'\d{10}', raw):
        result['passport'] = f'{raw[:2]} {raw[2:4]} {raw[4:]}'
    raw = re.sub(r'[\s-]', '', result['snils'])
    if re.fullmatch(r'\d{11}', raw):
        result['snils'] = f'{raw[:3]}-{raw[3:6]}-{raw[6:9]} {raw[9:]}'
    return result


def age(birth, today):
    return today.year-birth.year-((today.month, today.day) < (birth.month, birth.day))


def anniversary(birth, years):
    try:
        return birth.replace(year=birth.year+years)
    except ValueError:
        return birth.replace(year=birth.year+years, day=28)


def valid_snils(value):
    digits = re.sub(r'[\s-]', '', value)
    if not re.fullmatch(r'\d{11}', digits):
        return False
    if int(digits[:9]) <= 1001998:
        return True
    total = sum(int(n)*w for n, w in zip(digits[:9], range(9, 0, -1)))
    check = total if total < 100 else (0 if total in (100, 101) else total % 101)
    return int(digits[9:]) == (0 if check == 100 else check)


@dataclass
class Validation:
    people: list = field(default_factory=list)
    errors: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)


def validate(people, signer, key_confirmed, seen=None, today=None):
    today = today or dt.date.today()
    seen = seen or set()
    out = Validation()
    if signer not in ('Нотариус', 'ВРИО'):
        out.errors[(-1, 'signer')] = 'Выберите, кто сегодня исполняет обязанности.'
    if not key_confirmed:
        out.errors[(-1, 'key')] = 'Вставьте ключ и подтвердите кнопкой «ОК».'
    if not people:
        out.errors[(-1, 'people')] = 'Добавьте участника.'
    batch = set()
    for i, raw in enumerate(people):
        p = normalized(raw)
        out.people.append(p)
        def error(k, text):
            out.errors[(i, k)] = text
        def warn(text):
            out.warnings.append(f'Участник {i+1}: {text}')
        fio = p['fio']
        parts = fio.split()
        if len(parts) != 3 or any(not re.fullmatch(r'[А-ЯЁа-яё]{2,}(?:-[А-ЯЁа-яё]{2,})*', w) for w in parts):
            error('fio', 'Укажите три слова русскими буквами; минимум две буквы в каждой части. Дефис допустим.')
        if re.search('[A-Za-z]', fio):
            error('fio', 'В ФИО есть латинские буквы. Замените их русскими.')
        dates = {}
        for k in ('dob', 'issued'):
            try:
                if not re.fullmatch(r'\d{2}\.\d{2}\.\d{4}', p[k]):
                    raise ValueError()
                dates[k] = dt.datetime.strptime(p[k], '%d.%m.%Y').date()
                if dates[k] > today:
                    error(k, 'Дата не может быть в будущем.')
            except ValueError:
                error(k, 'Укажите существующую дату: дд.мм.гггг.')
        birth, issued = dates.get('dob'), dates.get('issued')
        if birth and not 14 <= age(birth, today) <= 120:
            error('dob', 'Возраст должен быть от 14 до 120 лет.')
        if birth and issued and issued < anniversary(birth, 14):
            error('issued', 'Паспорт выдан до 14-летия.')
        digits = re.sub(r'\s', '', p['passport'])
        if not re.fullmatch(r'\d{10}', digits):
            error('passport', 'Паспорт должен содержать 10 цифр.')
        elif digits[:2] not in PASSPORT_REGIONS:
            error('passport', 'Неизвестный код региона бланка паспорта.')
        if p['snils'] and not valid_snils(p['snils']):
            error('snils', 'СНИЛС: нужны 11 цифр и верное контрольное число.')
        if len(parts) == 3 and not parts[2].casefold().endswith(('ич', 'вич', 'вна', 'чна', 'ична', 'оглы', 'кызы')):
            warn('необычное окончание отчества; проверьте написание.')
        if birth and issued:
            for years in (20, 45):
                limit = anniversary(birth, years)
                if today > limit+dt.timedelta(days=90) and issued < limit:
                    warn(f'паспорт выдан до {years}-летия; проверьте актуальность документа.')
                    break
            if issued < today-dt.timedelta(days=365*30) or issued == birth:
                warn('необычная дата выдачи паспорта.')
        if issued and re.fullmatch(r'\d{10}', digits):
            year = int(digits[2:4])
            nearest = min(abs(issued.year-(1900+year)), abs(issued.year-(2000+year)))
            if nearest > 3:
                warn('год бланка заметно отличается от года выдачи.')
        ident = (fio.casefold(), p['dob'])
        if ident in batch:
            error('fio', 'Этот участник уже есть в текущем списке.')
        if (ident, today.isoformat()) in seen:
            warn('по этим ФИО и дате рождения уже запускались запросы сегодня.')
        batch.add(ident)
    return out


def pick_certificate(items, signer, owner, today=None):
    today = today or dt.datetime.now()
    if isinstance(today, dt.date) and not isinstance(today, dt.datetime):
        today = dt.datetime.combine(today, dt.time())
    found = []
    for index, text in enumerate(items):
        low = text.casefold()
        if owner.casefold() not in low or 'квалифицированные сертификаты' in low:
            continue
        if ('врио' in low) != (signer == 'ВРИО'):
            continue
        match = re.search(r'действует\s+до\s*(\d{2}\.\d{2}\.\d{4})(?:\s+(\d{1,2}:\d{2}(?::\d{2})?))?', low)
        if not match:
            continue
        raw = match[1]+' '+(match[2] or '23:59:59')
        if len(raw.split()[1].split(':')) == 2:
            raw += ':00'
        try:
            expiry = dt.datetime.strptime(raw, '%d.%m.%Y %H:%M:%S')
        except ValueError:
            continue
        if expiry > today:
            found.append((expiry, index))
    if not found:
        raise ValueError('Не найден подходящий действующий сертификат с читаемым сроком.')
    found.sort(reverse=True)
    if len(found) > 1 and found[0][0] == found[1][0]:
        raise ValueError('Найдены два сертификата с одинаковым сроком; выберите сертификат вручную в еНот.')
    return found[0][1]
