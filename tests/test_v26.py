"""TWYS 2.6 regression tests for current Notion revisions and historical macro data."""
from __future__ import annotations
import io, json
from datetime import datetime,timedelta
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from fastapi.testclient import TestClient
from twys import notion_sync as n, integrations as i, engine as e, macro
from twys.app import app

ROOT=Path(__file__).resolve().parents[1]

def test_journal_has_single_navigation_destination():
    html=(ROOT/'static/index.html').read_text()
    assert html.count('data-page="journal22"')==1
    assert 'data-page="trades"' not in html
    assert 'Sync recent edits' in (ROOT/'static/v22.js').read_text()
    assert 'Recheck all screenshots' in (ROOT/'static/v22.js').read_text()

def test_notion_sync_refetches_same_revision_when_forced(monkeypatch):
    source='f'*36; pid='a'*8+'-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
    state={'outcome':'Loss'}
    def row():return {'object':'page','id':pid,'last_edited_time':'2026-10-30T10:00:00.000Z','properties':{
        'Date':{'type':'date','date':{'start':'2026-10-30'}},
        'Instrument':{'type':'select','select':{'name':'EURUSD'}},
        'Outcome':{'type':'select','select':{'name':state['outcome']}},}}
    def fake(path,body=None):
        if '/query' in path:return {'results':[row()], 'has_more':False}
        return {'results':[], 'has_more':False}
    monkeypatch.setattr(n,'request_json',fake)
    assert n.sync(source)['added']==1
    state['outcome']='Win'
    assert n.sync(source)['unchanged']==1
    assert n.sync(source,force=True)['updated']==1  # content changed despite unchanged revision
    uid=n.normalize_page(row(),source)['uid']
    db=e.connection()
    try:
        saved=db.execute('SELECT outcome FROM trades WHERE uid=?',(uid,)).fetchone()
        assert saved['outcome']=='win'
    finally:db.close()

def test_notion_replaced_screenshot_does_not_reuse_old_cache(monkeypatch,tmp_path):
    image_a=Image.new('RGB',(4,4),(0,200,0));image_b=Image.new('RGB',(4,4),(200,0,0))
    def blob(image):
        output=io.BytesIO();image.save(output,format='PNG');return output.getvalue()
    contents={'a':blob(image_a),'b':blob(image_b)}
    class Reply:
        headers={'Content-Length':'100','Content-Type':'image/png'}
        def __init__(self,data):self.data=data
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,n):return self.data[:n]
    def request(req,timeout=9):
        return Reply(contents['a'] if '/a.png' in req.full_url else contents['b'])
    monkeypatch.setattr(n,'urlopen',request)
    monkeypatch.setattr(e,'MEDIA',tmp_path)
    uid='f'*20
    path_a=n.cache_image(uid,0,{'url':'https://prod-files-secure.s3.amazonaws.com/a.png'})
    path_b=n.cache_image(uid,0,{'url':'https://prod-files-secure.s3.amazonaws.com/b.png'})
    assert path_a and path_b and path_a!=path_b
    assert (tmp_path/path_a).read_bytes()!= (tmp_path/path_b).read_bytes()

def test_calendar_previous_next_week_uses_supported_range_provider(monkeypatch):
    today=datetime.now().astimezone().date()
    sunday=today-timedelta(days=(today.weekday()+1)%7)
    prev=sunday-timedelta(days=7)
    args=[]
    def fetched(url,ttl=900):
        args.append(url)
        return json.dumps({'events':[{'title':'CPI','currency':'USD','datetime':prev.isoformat()+'T08:30:00+00:00','actual':'1.1','consensus':'1.0','prior':'0.9'}]}).encode()
    monkeypatch.setattr(i,'config',lambda:{'calendar_provider':'forexfactory'})
    monkeypatch.setattr(i,'fetch',fetched)
    # Verify the date-range fallback even on a runner with working web access.
    def unavailable(*args,**kwargs):raise OSError('primary webpage unavailable')
    monkeypatch.setattr(i,'_forexfactory_web_calendar',unavailable)
    result=i.get_calendar(prev.isoformat(),(prev+timedelta(days=6)).isoformat())
    assert result['status']=='ok' and result['events'][0]['actual']=='1.1'
    assert len(args)==1 and 'financecalendar.com' in args[0]
    assert 'ff_calendar_lastweek' not in args[0]

def test_matching_actuals_are_exact_and_keep_provenance():
    base=[{'currency':'USD','datetime':'2026-11-02T12:00:00Z','event':'CPI m/m','actual':None},
          {'currency':'EUR','datetime':'2026-11-02T12:00:00Z','event':'CPI m/m','actual':None}]
    other=[{'currency':'USD','datetime':'2026-11-02T17:00:00Z','event':'CPI m/m','actual':'0.0%', 'source':'Finance Calendar','source_url':'https://www.financecalendar.com'}]
    i._matching_actuals(base,other)
    assert base[0]['actual']=='0.0%' and base[0]['actual_source']=='Finance Calendar'
    assert base[1]['actual'] is None

def test_macro_news_is_attributed_and_related(monkeypatch):
    monkeypatch.setattr(i,'get_news',lambda:{'status':'ok','items':[
        {'title':'Fed announces rate decision', 'source':'Federal Reserve','url':'https://www.federalreserve.gov/x'},
        {'title':'Banknote imagery', 'source':'ECB','url':'https://www.ecb.europa.eu/x'}]})
    monkeypatch.setattr(i,'get_calendar',lambda *args,**kwargs:{'status':'ok','events':[
        {'event':'CPI m/m','currency':'USD','actual':'0.3','source':'Finance Calendar'},
        {'event':'Holiday','currency':'CAD'}]})
    result=macro.news_brief()
    assert len(result['headlines'])==1 and len(result['events'])==1
    assert result['events'][0]['actual']=='0.3'
    with TestClient(app) as client:
        route=client.get('/api/v2/macro/news')
        assert route.status_code==200 and route.json()['events'][0]['event']=='CPI m/m'
