"""Сборка рабочего приложения без дополнительных программ и пользовательских данных."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--output-root', type=Path, required=True,
                    help='Новая пустая локальная папка для результатов сборки')
parser.add_argument('--iscc', default=os.environ.get('ISCC_PATH') or shutil.which('ISCC.exe'))
args = parser.parse_args()
if not args.iscc or not Path(args.iscc).is_file():
    parser.error('Укажите компилятор Inno Setup: --iscc путь/ISCC.exe или ISCC_PATH')
out = args.output_root.resolve()
if out.exists() and any(out.iterdir()):
    parser.error('Каталог результатов должен быть пустым: сохранённые файлы не удаляются')
out.mkdir(parents=True, exist_ok=True)
subprocess.run([
    sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed', '--onedir',
    '--name', 'EnotChecks', '--distpath', str(out/'dist'), '--workpath', str(out/'build'),
    '--specpath', str(out/'build'), '--paths', str(root/'src'),
    '--collect-all', 'customtkinter', '--collect-all', 'tesserocr', '--collect-all', 'comtypes',
    '--collect-submodules', 'pywinauto', '--collect-submodules', 'pynput',
    '--icon', str(root/'src/enot_app/app.ico'),
    '--add-data', str(root/'src/enot_app/app.ico')+';enot_app',
    '--add-data', str(root/'src/enot_app/models')+';enot_app/models',
    '--add-data', str(root/'docs')+';docs', str(root/'src/main.py')
], cwd=root, check=True)
subprocess.run([str(args.iscc), '/DPackageDir='+str(out/'dist/EnotChecks'),
                '/DReleaseDir='+str(out/'release'), str(root/'installer.iss')], check=True)
print(out/'release/Setup_EnotChecks_0.1.2.exe')
