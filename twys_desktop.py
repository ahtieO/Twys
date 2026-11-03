"""Branded desktop window around a private, loopback-only TWYS service."""
from __future__ import annotations

import argparse
import json
import socket
import sys
import threading
import time
from pathlib import Path

APP_ID = 'ALLININC.TWYS.Terminal'
WINDOW_TITLE = 'TWYS | TRADE WHAT YOU SEE · BY ALL IN INC.'


def write_report(path, **result):
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2), encoding='utf-8')


def self_test():
    """Exercise bundled imports, assets and database without creating sample trades."""
    from fastapi.testclient import TestClient
    from twys.app import app
    from twys import engine

    engine.connection().close()
    with TestClient(app) as client:
        health = client.get('/api/health')
        assert health.status_code == 200 and health.json()['status'] == 'ok'
        assert 'TWYS' in client.get('/').text
        assert client.get('/api/v2/symbols?q=XAU').status_code == 200
        for asset in ('style.css', 'app.js', 'v22.js', 'plotly.min.js', 'polish.css', 'polish.js', 'twys-icon.png'):
            response = client.get('/static/' + asset)
            assert response.status_code == 200 and response.content, asset
    return {'health': True, 'bundled_assets': True, 'database': True}


def run_desktop(smoke=False):
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    import webview
    import uvicorn
    from twys.app import app
    from twys import engine

    engine.connection().close()
    # Keep the reserved socket open until Uvicorn takes it, avoiding a port race.
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
    # A windowed executable has no stderr; Uvicorn's default logging formatter
    # calls stderr.isatty(). Disable its console logging configuration.
    config = uvicorn.Config(app, host='127.0.0.1', port=port,
                            log_config=None, log_level='error', access_log=False)
    server = uvicorn.Server(config)
    backend = threading.Thread(target=server.run, kwargs={'sockets': [listener]},
                               name='TWYS-Local-Engine', daemon=True)
    result = {}
    backend.start()
    try:
        for _ in range(150):
            if server.started:
                break
            if not backend.is_alive():
                raise RuntimeError('TWYS local backend could not start.')
            time.sleep(0.1)
        else:
            raise RuntimeError('TWYS local backend did not become ready.')
        window = webview.create_window(WINDOW_TITLE, f'http://127.0.0.1:{port}',
                                       width=1450, height=930, min_size=(900, 600),
                                       background_color='#0c0c0c')
        if smoke:
            loaded = threading.Event()

            def check_window():
                if not loaded.wait(45):
                    result['error'] = 'Desktop page did not load within 45 seconds.'
                else:
                    try:
                        result.update(window.evaluate_js('''({
                            title: document.title,
                            app: !!document.querySelector('#app'),
                            workspace: !!document.querySelector('#workspace'),
                            navigation: document.querySelectorAll('.nav-item').length,
                            logo: (() => { const mark = document.querySelector('.twys-logo');
                                return !!mark && mark.complete && mark.naturalWidth > 0; })()
                        })'''))
                    except Exception as exc:
                        result['error'] = str(exc)
                window.destroy()

            window.events.loaded += loaded.set
            threading.Thread(target=check_window, daemon=True).start()
        # Edge Chromium is mandatory on Windows; never silently fall back to IE.
        webview.start(debug=False, gui='edgechromium' if sys.platform == 'win32' else None)
        if smoke:
            if result.get('error') or not all((result.get('app'), result.get('workspace'),
                    result.get('logo'), result.get('navigation', 0) >= 10,
                    'TWYS' in result.get('title', ''))):
                raise RuntimeError('Desktop smoke test failed: ' + json.dumps(result))
        return result
    finally:
        server.should_exit = True
        backend.join(timeout=5)
        listener.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description='TWYS desktop')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--self-test', action='store_true')
    mode.add_argument('--smoke-test', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args(argv)
    try:
        checks = self_test() if args.self_test else run_desktop(args.smoke_test)
        write_report(args.report, ok=True, mode='self-test' if args.self_test else 'desktop', checks=checks)
        return 0
    except Exception as exc:
        write_report(args.report, ok=False, error=str(exc))
        if sys.platform == 'win32' and not (args.self_test or args.smoke_test):
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,
                'TWYS could not start. Your journal has not been removed.\n\n' + str(exc),
                'TWYS startup', 0x10)
        elif sys.stderr is not None:
            print('TWYS startup failed: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
