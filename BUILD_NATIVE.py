"""Build the branded, windowless Windows x64 application (no personal data)."""
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def build_args():
    # Explicit inputs only: never bundle the checkout or a user's data directory.
    return [
        sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
        '--windowed', '--onedir', '--name', 'TWYS',
        '--distpath', str(ROOT / 'dist'), '--workpath', str(ROOT / 'build'),
        '--specpath', str(ROOT / 'build'),
        '--icon', str(ROOT / 'assets' / 'twys-icon.ico'),
        '--add-data', f'{ROOT / "static"};static',
        '--add-data', f'{ROOT / "assets"};assets',
        '--collect-all', 'webview', '--collect-data', 'tzdata',
        '--collect-submodules', 'keyring.backends',
        '--hidden-import', 'uvicorn.logging',
        '--hidden-import', 'uvicorn.loops.auto',
        '--hidden-import', 'uvicorn.protocols.http.auto',
        '--hidden-import', 'uvicorn.protocols.websockets.auto',
        '--hidden-import', 'uvicorn.lifespan.on',
        str(ROOT / 'twys_desktop.py'),
    ]


def main():
    if platform.system() != 'Windows' or platform.machine().lower() not in ('amd64', 'x86_64'):
        raise SystemExit('TWYS-Setup.exe must be built with x64 Python on a real Windows x64 runner.')
    if sys.maxsize <= 2**32:
        raise SystemExit('Use a 64-bit Python installation to build TWYS.')
    subprocess.run(build_args(), cwd=ROOT, check=True)
    if not (ROOT / 'dist' / 'TWYS' / 'TWYS.exe').is_file():
        raise RuntimeError('PyInstaller did not produce dist/TWYS/TWYS.exe.')


if __name__ == '__main__':
    main()
