"""Regressions: chart-preview click, aligned rail, and fast Notion sync."""
from pathlib import Path
from fastapi.testclient import TestClient
from twys.app import app
from twys import v2_routes, notion_sync as n
ROOT=Path(__file__).resolve().parents[1]

def test_screenshot_page_has_distinct_image_open_and_trade_detail():
    js=(ROOT/'static/app.js').read_text()
    assert 'v28ShowPhoto(Number(el.dataset.photoIndex))' in js
    assert 'openTrade(el.dataset.viewTrade)' in js
    assert 'attachTradeRows();}' not in js[js.index('async function loadScreenshots()'):js.index('async function loadResearch()')]
    html=(ROOT/'static/index.html').read_text()
    assert 'id="v28-photo-error"' in html
    assert 'id="v28-photo-next"' in html

def test_market_rail_cards_share_grid_alignment():
    css=(ROOT/'static/v28.css').read_text()
    assert '.v22-rail>.v22-panel{width:100%' in css
    assert '.v22-rail .v22-phead' in css

def test_sync_now_fast_vs_deep(monkeypatch):
    calls=[]
    def fake(force=False):
        calls.append(force)
        return {'sources':[], 'added':0,'updated':0,'removed':0,'errors':0}
    monkeypatch.setattr(n,'sync_selected',fake)
    with TestClient(app) as client:
        assert client.post('/api/v2/notion/sync').status_code==200
        assert client.post('/api/v2/notion/sync?deep=true').status_code==200
    assert calls==[False,True]

def test_background_sync_initialized_without_immediate_expensive_deep_scan(monkeypatch):
    # Validate code policy without starting an uncontrolled network thread.
    source=(ROOT/'twys/notion_sync.py').read_text()
    assert '_LAST_DEEP_REFRESH=time.monotonic()' in source
    assert 'deep=time.monotonic()-_LAST_DEEP_REFRESH>900' in source

def test_unchanged_screenshot_cache_not_redownloaded_after_note_edit(monkeypatch,tmp_path):
    from twys import engine as e
    import json
    monkeypatch.setattr(e,'MEDIA',tmp_path)
    old='chart.png'
    (tmp_path/old).write_bytes(b'cached')
    url='https://prod-files-secure.s3.amazonaws.com/abc.png?old-signature=1'
    new='https://prod-files-secure.s3.amazonaws.com/abc.png?new-signature=2'
    monkeypatch.setattr(n,'fetch_page_images',lambda p:[])
    def never(*args,**kwargs):raise AssertionError('Unchanged screenshot should not be downloaded')
    monkeypatch.setattr(n,'urlopen',never)
    item={'uid':'a'*20,'images':json.dumps([{'name':'chart','file':None,'url':new}])}
    saved=json.dumps([{'name':'chart','file':old,'url':url}])
    out=n.cache_page_images(item,{'id':'x'},saved,refresh=False)
    assert json.loads(out['images'])[0]['file']==old

def test_cached_trade_image_endpoint_opens_original_bytes(tmp_path,monkeypatch):
    import io,json
    from PIL import Image
    from twys import engine as e
    monkeypatch.setattr(e,'MEDIA',tmp_path)
    img=Image.new('RGB',(96,64),(20,40,100))
    binary=io.BytesIO();img.save(binary,format='PNG')
    (tmp_path/'sample-trade.png').write_bytes(binary.getvalue())
    uid='c'*20
    c=e.connection()
    try:
        c.execute('''INSERT OR REPLACE INTO trades(uid,source,images,original_json,imported_at,traded_at,instrument)
                   VALUES(?,?,?,?,?,?,?)''',(uid,'test',json.dumps([{'name':'Chart','file':'sample-trade.png'}]),'{}','2026-11-03T00:00:00Z','2026-11-03','EURUSD'))
        c.commit()
        with TestClient(app) as client:
            response=client.get('/api/trade/'+uid+'/image/0')
            assert response.status_code==200
            assert response.headers['content-type']=='image/png'
            assert response.content==binary.getvalue()
    finally:
        c.execute('DELETE FROM trades WHERE uid=?',(uid,));c.commit();c.close()


def test_fast_sync_skips_unchanged_notion_body_images(monkeypatch):
    from twys import engine as e
    source='e'*36;pid='55555555-5555-5555-5555-555555555555'
    sample={'id':pid,'object':'page','last_edited_time':'2026-11-03T03:00:00Z','in_trash':False,
            'properties':{'Date':{'type':'date','date':{'start':'2026-11-03'}},'Instrument':{'type':'select','select':{'name':'XAUUSD'}}}}
    calls=[]
    def remote(path,body=None):
        calls.append(path)
        if path.endswith('/query'):return {'results':[sample], 'has_more':False}
        return {'results':[], 'has_more':False}
    monkeypatch.setattr(n,'request_json',remote)
    assert n.sync(source)['added']==1
    calls.clear()
    assert n.sync(source)['unchanged']==1
    # No request to a page's child blocks and no external image re-download.
    assert calls==['data_sources/'+source+'/query']
