from pathlib import Path
import py_compile
import sys

base = Path('/home/ubuntu/work/kol_lens_windows_ready/backend')
files = [
    base / 'app.py',
    base / 'services' / 'openai_compat.py',
    base / 'services' / 'pgy_cookie_source.py',
    base / 'services' / 'intent_parser.py',
    base / 'services' / 'pgy_service.py',
    base / 'services' / 'creator_data_service.py',
]
errors = []
for path in files:
    try:
        py_compile.compile(str(path), doraise=True)
        print(f'OK {path}')
    except Exception as exc:
        errors.append((path, exc))
        print(f'ERR {path}: {exc}')

if errors:
    sys.exit(1)
