import base64
import datetime as dt
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import uuid


def atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.write-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def data_directory():
    override = os.environ.get('ENOT_DATA_DIR')
    if override:
        return Path(override).resolve()
    base = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[2]
    preferred = base/'Данные'
    try:
        preferred.mkdir(exist_ok=True)
        with tempfile.TemporaryFile(dir=preferred):
            pass
        return preferred
    except OSError:
        return Path(os.environ['LOCALAPPDATA'])/'EnotChecks'/'Данные'


class Repository:
    def __init__(self, root):
        self.root = Path(root).resolve()
        if str(self.root).startswith('\\\\'):
            raise ValueError('Сетевые папки не поддерживаются: выберите локальный диск.')
        if os.name == 'nt':
            import ctypes
            if ctypes.windll.kernel32.GetDriveTypeW(self.root.anchor) == 4:
                raise ValueError('Сетевой диск не поддерживается.')
        self.deals = self.root/'Сделки'
        self.deals.mkdir(parents=True, exist_ok=True)
        self.settings_path = self.root/'settings.json'
        self.settings = dict(notary='Андреева Виктория Александровна',
                             acting='Андреева Маргарита Вячеславовна', encrypt=False,
                             timeout=45, ocr=True)
        if self.settings_path.exists():
            saved = json.loads(self.settings_path.read_text(encoding='utf-8'))
            obsolete = {'zags_load_min','registry_load_min','contracts_load_min'}
            self.settings.update({k:v for k,v in saved.items() if k not in obsolete})
            if obsolete.intersection(saved):
                self.save_settings()
        else:
            self.save_settings()
        self.issues = []

    def save_settings(self):
        atomic(self.settings_path, self.settings)

    def acquire(self):
        import msvcrt
        self._lock = (self.root/'.lock').open('a+b')
        if self._lock.seek(0, 2) == 0:
            self._lock.write(b'0')
            self._lock.flush()
        self._lock.seek(0)
        try:
            msvcrt.locking(self._lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            self._lock.close()
            raise RuntimeError('Приложение уже открыто для этой папки данных.')

    def close(self):
        if hasattr(self, '_lock') and not self._lock.closed:
            import msvcrt
            self._lock.seek(0)
            msvcrt.locking(self._lock.fileno(), msvcrt.LK_UNLCK, 1)
            self._lock.close()

    def write_private(self, path, data):
        if self.settings['encrypt']:
            import win32crypt
            blob = win32crypt.CryptProtectData(json.dumps(data, ensure_ascii=False).encode('utf-8'), None, None, None, None, 1)
            data = dict(protection='windows-user', payload=base64.b64encode(blob).decode('ascii'))
        atomic(path, data)

    def read_private(self, path):
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        if data.get('protection') == 'windows-user':
            import win32crypt
            raw = win32crypt.CryptUnprotectData(base64.b64decode(data['payload']), None, None, None, 1)[1]
            data = json.loads(raw.decode('utf-8'))
        return data

    def folder(self, deal):
        raw = self.deals/deal['folder']
        if raw.exists() and getattr(raw.lstat(), 'st_file_attributes', 0) & 0x400:
            raise ValueError('Ссылки и точки перехода запрещены.')
        path = raw.resolve()
        if path.parent != self.deals.resolve() or not re.fullmatch(r'\d{4,} — .+', path.name):
            raise ValueError('Недопустимый путь сделки.')
        return path

    def list(self):
        self.issues = []
        items = []
        for folder in sorted(self.deals.iterdir()):
            if not folder.is_dir() or folder.is_symlink():
                continue
            try:
                deal = json.loads((folder/'deal.json').read_text(encoding='utf-8'))
                if deal['folder'] != folder.name:
                    raise ValueError()
                self.folder(deal)
                participants = self.read_private(folder/'participants.json')['people']
                if not isinstance(participants, list) or not all(isinstance(p, dict) for p in participants):
                    raise ValueError()
                deal['people'] = participants
                deal['runs'] = []
                for p in sorted((folder/'runs').glob('*.json')):
                    run = self.read_private(p)
                    if run['status'] == 'running':
                        run['status'] = 'interrupted'
                        run['note'] = 'Предыдущий сеанс завершился до подтверждения результата. Проверьте еНот перед повтором.'
                        self.write_private(p, run)
                    deal['runs'].append(run)
                deal['runs'].sort(key=lambda r:r['started'])
                items.append(deal)
            except Exception:
                self.issues.append(folder.name)
        return items

    def create(self, title, date='', people=None):
        title = title.strip()
        if not title:
            raise ValueError('Укажите название сделки.')
        number = max([int(p.name.split(' — ')[0]) for p in self.deals.iterdir()
                      if re.match(r'^\d+ — ', p.name)] or [0])+1
        slug = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', title).strip(' .')[:80] or 'Сделка'
        deal = dict(id=uuid.uuid4().hex, title=title, date=date, folder=f'{number:04} — {slug}',
                    people=people or [{}], runs=[])
        self.save(deal)
        return deal

    def save(self, deal):
        folder = self.folder(deal)
        folder.mkdir(exist_ok=True)
        self.write_private(folder/'participants.json', dict(schema=1, people=deal['people']))
        atomic(folder/'deal.json', {k:deal[k] for k in ('id', 'title', 'date', 'folder')})

    def save_run(self, deal, run):
        if deal is not None:
            if not re.fullmatch(r'[a-f0-9]{32}', run['id']):
                raise ValueError('Некорректный идентификатор запуска.')
            self.write_private(self.folder(deal)/'runs'/(run['id']+'.json'), run)

    def delete(self, deal):
        folder = self.folder(deal)
        shutil.rmtree(folder)


def new_run(people, signer, repeat=False):
    return dict(id=uuid.uuid4().hex, started=dt.datetime.now().isoformat(timespec='seconds'),
                kind='Повторные' if repeat else 'Первичные', signer=signer, status='running',
                people=[dict(p) for p in people], steps=[], f5_sent=False,
                capacity_skipped=[], schema=2)
