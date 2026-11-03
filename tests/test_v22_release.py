"""Release guards for the merged Windows-first market/news workspace."""
from pathlib import Path
from fastapi.testclient import TestClient
from twys.app import app


def test_news_is_one_navigation_destination():
    html=(Path(__file__).resolve().parents[1]/'static'/'index.html').read_text()
    assert html.count('data-page="newsdesk"') == 1
    assert 'data-page="calendar"' not in html
    assert 'data-page="journal22"' in html
    assert 'v22.js' in html and 'v22.css' in html


def test_new_static_and_core_market_endpoints():
    with TestClient(app) as c:
        for route in ('/', '/static/v22.js', '/static/v22.css','/api/health','/api/v2/symbols?q=XAU'):
            result=c.get(route)
            assert result.status_code == 200, (route, result.text[:150])
        data=c.get('/api/v2/symbols?q=XAU').json()
        assert any(x['symbol']=='XAUUSD' for x in data['results'])


def test_brand_icon_and_installer_workflow_are_included():
    root=Path(__file__).resolve().parents[1]
    assert (root/'assets'/'twys-icon.ico').stat().st_size > 1000
    assert (root/'installer'/'windows'/'twys.nsi').exists()
    assert 'TWYS-Setup.exe' in (root/'installer'/'windows'/'twys.nsi').read_text()
    assert '--self-test' in (root/'.github'/'workflows'/'desktop-builds.yml').read_text()
