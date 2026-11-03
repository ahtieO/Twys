from datetime import datetime
from twys import notion_sync, marketplace, engine


def test_notion_stable_uid_and_missing_data():
    page={'id':'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee','last_edited_time':'2026-10-16T00:00:00Z',
          'properties':{'Date':{'type':'date','date':{'start':'2026-10-16'}},
                        'Instrument':{'type':'select','select':{'name':'XAUUSD'}},
                        'Result RR':{'type':'number','number':0},
                        'Setup + Reasoning':{'type':'rich_text','rich_text':[{'plain_text':'Wait for BOS'}]}}}
    a=notion_sync.normalize_page(page,'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee')
    page['properties']['Setup + Reasoning']['rich_text'][0]['plain_text']='Updated after review'
    b=notion_sync.normalize_page(page,'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee')
    assert a['uid']==b['uid']
    assert a['realized_r']==0 and a['outcome']=='breakeven'
    assert b['review'] is None and b['reasoning']=='Updated after review'
    assert b['entry_price'] is None


def test_market_news_index_without_ai():
    marketplace.store_headlines([{'url':'https://www.federalreserve.gov/newsevents/pressreleases/monetary.htm',
                                  'title':'Federal Reserve monetary policy meeting',
                                  'summary':'Official statement','source':'Federal Reserve',
                                  'published':'2026-10-16','impact':'high'}])
    found=marketplace.search('monetary',scope='all')
    assert any(x['kind']=='news' for x in found['results'])
    assert found['ai_used'] is False


def test_notion_blank_template_not_counted(monkeypatch):
    from unittest.mock import patch
    source='eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'
    with patch.object(notion_sync.cfg,'config',return_value={'notion_database_id':source}), \
         patch.object(notion_sync,'request_json',return_value={'results':[{'id':'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
              'object':'page','last_edited_time':'2026-10-16T00:00:00Z','properties':{}}], 'has_more':False}):
        report=notion_sync.sync(source)
    assert report['added']==0 and engine.load_trades()==[]


def test_replay_and_compare_removed():
    from fastapi.testclient import TestClient
    from twys.app import app
    client=TestClient(app)
    assert client.post('/api/v2/compare',json={'a':{},'b':{}}).status_code==404
    assert client.get('/api/v2/candles/datasets').status_code==404
    assert client.get('/api/v2/markets/XAUUSD/suggestions').json()['ai_used'] is False
