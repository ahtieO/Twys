"""Regression coverage for new macro and terminal wiring."""
from pathlib import Path
from fastapi.testclient import TestClient
from twys import macro
from twys.app import app


def test_fred_observation_parsing_skips_missing():
    b=b'observation_date,DGS10\n2026-01-01,.\n2026-01-02,4.5\n2026-01-05,4.25\n'
    assert macro.parse_fred_csv(b,'DGS10') == [
        {'date':'2026-01-02','value':4.5},
        {'date':'2026-01-05','value':4.25},
    ]


def test_macro_report_has_no_fabricated_fallback(monkeypatch):
    def unavailable(*args,**kwargs):raise OSError('offline')
    monkeypatch.setattr(macro.integrations,'fetch',unavailable)
    report=macro.report()
    assert len(report['series'])==len(macro.SERIES)
    assert all(row['status']=='unavailable' and not row['history'] and row['latest'] is None for row in report['series'])
    assert 'causal' in report['methodology']


def test_macro_api_uses_verified_values(monkeypatch):
    fake=b'observation_date,DGS10\n2026-01-01,4.4\n2026-01-02,4.2\n'
    def fetch(url,ttl=0):return fake if 'DGS10' in url else b'observation_date,unused\n'
    monkeypatch.setattr(macro.integrations,'fetch',fetch)
    response=TestClient(app).get('/api/v2/macro')
    assert response.status_code==200
    item=next(x for x in response.json()['series'] if x['id']=='DGS10')
    assert item['latest']['value']==4.2 and item['change']==-0.2


def test_v24_no_duplicate_controls_or_sidebar_overview():
    root=Path(__file__).parents[1]/'static'
    html=(root/'index.html').read_text()
    v22=(root/'v22.js').read_text()
    assert 'data-page="overview"' not in html
    assert 'id="v23-trash-entry"' not in html
    assert 'data-page="macro"' in html
    assert 'v22-tvrange" style' not in v22
    assert 'v24LoadWatchlist' in (root/'v24.js').read_text()
    assert 'v24-timeframe-note' not in v22
