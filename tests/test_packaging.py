"""Packaging regressions that can also run before a native Windows build."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import types
from urllib.request import ProxyHandler, build_opener

import BUILD_NATIVE
import twys_desktop

ROOT = Path(__file__).resolve().parents[1]


def test_native_build_rejects_non_windows(monkeypatch):
    import pytest
    monkeypatch.setattr(BUILD_NATIVE.platform, 'system', lambda: 'Linux')
    with pytest.raises(SystemExit, match='real Windows x64'):
        BUILD_NATIVE.main()


def test_native_build_uses_explicit_assets_and_gui_subsystem():
    args = BUILD_NATIVE.build_args()
    assert '--windowed' in args and '--onedir' in args
    payloads = [args[i + 1] for i, arg in enumerate(args) if arg == '--add-data']
    assert payloads == [f'{ROOT / "static"};static', f'{ROOT / "assets"};assets']
    assert args[args.index('--icon') + 1] == str(ROOT / 'assets/twys-icon.ico')


def test_self_test_creates_empty_private_journal_and_current_report(tmp_path):
    data = tmp_path / 'private-data'
    report = tmp_path / 'report.json'
    env = dict(os.environ, TWYS_DATA_DIR=str(data))
    process = subprocess.run([sys.executable, str(ROOT / 'twys_desktop.py'),
        '--self-test', '--report', str(report)], env=env, cwd=tmp_path,
        capture_output=True, text=True, timeout=45)
    assert process.returncode == 0, process.stderr
    result = json.loads(report.read_text())
    assert result['ok'] and result['checks']['bundled_assets']
    with sqlite3.connect(data / 'twys.sqlite3') as connection:
        assert connection.execute('SELECT count(*) FROM trades').fetchone()[0] == 0


def test_windowless_launcher_real_loopback_server_stops_cleanly(monkeypatch):
    # A fake native host lets Linux exercise real Uvicorn startup/shutdown. The
    # Windows workflow separately renders the real Edge WebView2 desktop window.
    urls = []
    stopped = []

    class Window:
        def destroy(self):
            stopped.append(True)

    def create_window(title, url, **kwargs):
        assert title.startswith('TWYS |')
        assert url.startswith('http://127.0.0.1:')
        urls.append(url)
        return Window()

    def start(**kwargs):
        with build_opener(ProxyHandler({})).open(urls[0] + '/api/health', timeout=5) as response:
            assert json.load(response)['status'] == 'ok'

    fake = types.SimpleNamespace(create_window=create_window, start=start)
    monkeypatch.setitem(sys.modules, 'webview', fake)
    # PyInstaller windowed mode has neither stream. This used to break Uvicorn's
    # default logging formatter before the service could start.
    monkeypatch.setattr(sys, 'stdout', None)
    monkeypatch.setattr(sys, 'stderr', None)
    assert twys_desktop.run_desktop() == {}
    import socket
    from urllib.parse import urlparse
    with socket.socket() as probe:
        assert probe.connect_ex(('127.0.0.1', urlparse(urls[0]).port)) != 0


def test_launcher_failure_writes_a_failed_report(monkeypatch, tmp_path):
    def fail():
        raise RuntimeError('packaged dependency missing')
    monkeypatch.setattr(twys_desktop, 'self_test', fail)
    report = tmp_path / 'failed.json'
    assert twys_desktop.main(['--self-test', '--report', str(report)]) == 1
    assert json.loads(report.read_text()) == {'ok': False, 'error': 'packaged dependency missing'}


def test_desktop_smoke_waits_for_native_loaded_event_and_checks_branding(monkeypatch):
    import threading
    loaded_handlers = []
    destroyed = threading.Event()
    urls = []

    class Loaded:
        def __iadd__(self, handler):
            loaded_handlers.append(handler)
            return self

    class Window:
        events = types.SimpleNamespace(loaded=Loaded())

        def evaluate_js(self, script):
            assert '.twys-logo' in script and 'naturalWidth' in script
            with build_opener(ProxyHandler({})).open(urls[0] + '/api/health', timeout=5) as response:
                assert json.load(response)['status'] == 'ok'
            return {'title': 'TWYS | TRADE WHAT YOU SEE', 'app': True, 'workspace': True,
                    'navigation': 12, 'logo': True}

        def destroy(self):
            destroyed.set()

    def create_window(title, url, **kwargs):
        urls.append(url)
        return Window()

    def start(**kwargs):
        for callback in loaded_handlers:
            callback()
        assert destroyed.wait(5), 'Smoke test did not close the desktop window'

    monkeypatch.setitem(sys.modules, 'webview', types.SimpleNamespace(create_window=create_window, start=start))
    result = twys_desktop.run_desktop(smoke=True)
    assert result['logo'] is True and result['navigation'] == 12
