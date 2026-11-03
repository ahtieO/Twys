"""Bug regressions grounded in TWYS user-reported behavior."""
import json
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from PIL import Image
from twys import integrations, marketplace, positioning, social
from twys.app import app

ROOT=Path(__file__).resolve().parents[1]

def test_journal_can_render_trade_explorer_under_journal_route():
    code=(ROOT/'static/app.js').read_text()
    assert "['trades','journal22'].includes(state.page)" in code
    assert "state.page!=='trades')return" not in code

def test_related_instruments_are_relevant_not_generic():
    assert 'XAUUSD' not in [x['symbol'] for x in marketplace.related_markets('AAPL','Stock')]
    assert 'BTCUSDT' not in [x['symbol'] for x in marketplace.related_markets('AAPL','Stock')]
    assert 'QQQ' in [x['symbol'] for x in marketplace.related_markets('AAPL','Stock')]
    assert 'GC' in [x['symbol'] for x in marketplace.related_markets('XAUUSD','Commodity')]
    assert all(x['reason'] for x in marketplace.related_markets('EURUSD','Forex'))

def test_official_euro_fx_futures_positions_are_labeled(monkeypatch):
    row=[{'lev_money_positions_long':'1000','lev_money_positions_short':'3000',
          'report_date_as_yyyy_mm_dd':'2026-10-13'}]
    monkeypatch.setattr(integrations,'fetch',lambda url,ttl=0:json.dumps(row).encode())
    result=positioning.get_cftc_financial_positioning('EURUSD')
    assert result['long_percent']==25 and result['short_percent']==75
    assert result['reported_at']=='2026-10-13'
    assert 'futures' in result['scope'].lower() and 'CONTRACTS' in result['note']
    inverse=positioning.get_cftc_financial_positioning('USDJPY')
    assert 'INVERSE' in inverse['note']

def test_cftc_financial_source_handles_missing_values(monkeypatch):
    monkeypatch.setattr(integrations,'fetch',lambda url,ttl=0:b'[{}]')
    try:positioning.get_cftc_financial_positioning('GBPUSD')
    except ValueError:pass
    else:assert False,'Missing actual CFTC contracts must be rejected'

def test_news_filter_never_shows_unfiltered_embedded_calendar():
    content=(ROOT/'static/v22.js').read_text()
    a=content.index('function v22RenderWeek()')
    b=content.index('async function v22LoadHeadlines()',a)
    assert 'v22RenderCalendarWidget' not in content[a:b]
    assert "No economic events match the selected" in content[a:b]

def test_legacy_off_calendar_uses_default_public_provider(monkeypatch):
    import datetime
    today=datetime.datetime.now().astimezone().date()
    start=today-datetime.timedelta(days=(today.weekday()+1)%7)
    payload=[{'date':today.isoformat()+'T10:30:00+00:00','country':'USD','title':'Test CPI','impact':'High','actual':'0','forecast':'1.1','previous':'1.0'}]
    monkeypatch.setattr(integrations,'config',lambda:{'calendar_provider':'off'})
    monkeypatch.setattr(integrations,'fetch',lambda url,ttl=0:json.dumps(payload).encode())
    # A live webpage must not replace the synthetic export fallback fixture.
    def unavailable(*args,**kwargs):raise OSError('primary webpage unavailable')
    monkeypatch.setattr(integrations,'_forexfactory_web_calendar',unavailable)
    result=integrations.get_calendar(start.isoformat(),(start+datetime.timedelta(days=6)).isoformat())
    assert result['status']=='ok' and result['events'][0]['actual']=='0'

def test_social_fallback_links_are_instrument_specific():
    links=social.lookups('AAPL')
    assert 'AAPL' in links[0]['url'] and 'AAPL' in links[1]['url']
    assert all(l['url'].startswith('https://') for l in links)

def test_sidebar_is_scrollable_and_icon_is_transparent():
    css=(ROOT/'static/v25.css').read_text()
    assert '.sidebar{' in css and 'overflow-y:auto' in css
    assert '.v22-watch-mini{' in css and 'overflow-y:auto' in css
    icon=Image.open(ROOT/'assets/twys-icon.png').convert('RGBA')
    assert icon.getpixel((0,0))[3]==0
    assert max(icon.getchannel('A').getextrema())==255

def test_main_api_market_relations():
    with TestClient(app) as client:
        result=client.get('/api/v2/markets/AAPL')
        assert result.status_code==200
        assert all(r['symbol']!='XAUUSD' for r in result.json()['related'])
