"""TWYS 2.7: released calendar figures and irreversible local trade removal."""
from __future__ import annotations

import hashlib, json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from twys import engine as e, integrations as i, ff_calendar_html as ff, notion_sync as n, marketplace
from twys.app import app

SAMPLE_WEEK=b'''<!doctype html><html><body>
<p>Calendar Time Zone: Etc/GMT (GMT +0)</p>
<table class="calendar__table"><tbody>
<tr class="calendar__row" data-event-id="105"><td class="calendar__date"><span>Mon Nov 2</span></td>
<td class="calendar__time">15:00</td><td class="calendar__currency">USD</td>
<td class="calendar__impact"><i class="icon--ff-impact-ora"></i></td>
<td class="calendar__event"><span class="calendar__event-title">ISM Manufacturing PMI</span></td>
<td class="calendar__actual"><span>55.5</span></td><td class="calendar__forecast">54.5</td>
<td class="calendar__previous">54.5</td></tr>
<tr class="calendar__row" data-event-id="106"><td class="calendar__date"></td>
<td class="calendar__time"></td><td class="calendar__currency">USD</td>
<td class="calendar__impact"><i class="icon--ff-impact-yel"></i></td>
<td class="calendar__event">Construction Spending m/m</td>
<td class="calendar__actual">-1.9%</td><td class="calendar__forecast">0.4%</td>
<td class="calendar__previous">2.0%</td></tr>
<tr class="calendar__row" data-event-id="107"><td class="calendar__date"><span>Tue Nov 3</span></td>
<td class="calendar__time">Tentative</td><td class="calendar__currency">GBP</td>
<td class="calendar__impact"><i class="icon--ff-impact-red"></i></td>
<td class="calendar__event">10-y Bond Auction</td>
<td class="calendar__actual"></td><td class="calendar__forecast"></td><td class="calendar__previous">5.42</td></tr>
</tbody></table></body></html>'''


def test_ff_webpage_parser_reads_released_actual_and_carried_time():
    events=ff.parse_week(SAMPLE_WEEK,date(2026,11,1))
    assert len(events)==3
    assert events[0]['actual']=='55.5' and events[0]['forecast']=='54.5'
    assert events[0]['impact']=='medium'
    assert events[1]['datetime']==events[0]['datetime']
    assert events[1]['actual']=='-1.9%'
    assert events[2]['actual'] is None and events[2]['time_precision']=='date_only'
    assert events[2]['impact']=='high'


def test_ff_week_switch_and_new_year_rollover():
    assert 'week=nov1.2026' in ff.page_url(date(2026,11,1))
    html=SAMPLE_WEEK.decode().replace('Mon Nov 2','Thu Dec 31').replace('Tue Nov 3','Fri Jan 1')
    rows=ff.parse_week(html,date(2026,12,27))
    assert rows[0]['datetime'].startswith('2026-12-31T')
    assert rows[2]['datetime']=='2027-01-01'


def test_source_without_confirmed_timezone_or_table_is_not_silently_accepted():
    for html in (b'<html>Blocked</html>', b'<table class="calendar__table"><tr class="calendar__row"></tr></table>'):
        try:ff.parse_week(html,date(2026,11,1))
        except ValueError:pass
        else:assert False,'Missing source data must raise a clear error'


def test_news_prefers_web_actual_over_export(monkeypatch):
    monkeypatch.setattr(i,'config',lambda:{'calendar_provider':'forexfactory'})
    monkeypatch.setattr(ff,'download_week',lambda week:SAMPLE_WEEK)
    # Do not call export JSON when the webpage has released data.
    monkeypatch.setattr(i,'fetch',lambda *a,**kw:(_ for _ in ()).throw(AssertionError('JSON fallback must not replace Actual values')))
    result=i.get_calendar('2026-11-01','2026-11-07')
    assert result['status']=='ok' and result['provider']=='Forex Factory webpage'
    assert any(x['event']=='ISM Manufacturing PMI' and x['actual']=='55.5' for x in result['events'])


def test_local_trash_permanent_delete_preserves_notion_and_prevents_resync(tmp_path,monkeypatch):
    marketplace.init()
    page_id='a1a1a1a1-1111-4444-9999-abcdef123456'
    uid=hashlib.sha256(('notion_api|'+page_id).encode()).hexdigest()[:20]
    source='b'*36
    data={
        'uid':uid,'source':'notion_api:'+source[:8], 'traded_at':'2026-11-02T10:00:00+00:00',
        'instrument':'XAUUSD','record_type':'trade', 'images':json.dumps([{'name':'chart','file':'safe_trade.png'}]),
        'original_json':json.dumps({'notion_page_id':page_id}), 'imported_at':datetime.now(timezone.utc).isoformat(),
    }
    monkeypatch.setattr(e,'MEDIA',tmp_path)
    (tmp_path/'safe_trade.png').write_bytes(b'secret-local-bytes')
    db=e.connection()
    try:
        db.execute('CREATE TABLE IF NOT EXISTS notion_missing (page_id TEXT PRIMARY KEY, miss_count INTEGER NOT NULL DEFAULT 0)')
        cols=','.join(data)
        db.execute(f'INSERT INTO trades({cols}) VALUES({",".join("?" for _ in data)})',list(data.values()))
        db.execute('INSERT INTO notion_records(page_id,source_id,last_edited,original_json,imported_at) VALUES(?,?,?,?,?)',
                   (page_id,source,'2026-11-02',data['original_json'],data['imported_at']))
        db.commit()
    finally:db.close()
    with TestClient(app) as client:
        assert client.delete('/api/trade/'+uid).status_code==200
        response=client.delete('/api/trash/'+uid+'/permanent')
        assert response.status_code==200, response.text
        assert response.json()['undo'] is False
        assert all(x['uid']!=uid for x in client.get('/api/trash').json()['rows'])
        assert client.get('/api/trade/'+uid).status_code==404
        assert not (tmp_path/'safe_trade.png').exists()
        assert client.delete('/api/trash/'+uid+'/permanent').status_code==409
    db=e.connection()
    try:
        assert db.execute('SELECT uid FROM permanently_deleted_trades WHERE uid=?',(uid,)).fetchone()
    finally:db.close()
    def fake(endpoint,body=None):
        return {'results':[{'object':'page','id':page_id,'last_edited_time':'2026-11-03T12:00:00Z',
                            'properties':{'Date':{'type':'date','date':{'start':'2026-11-02'}},
                                          'Instrument':{'type':'select','select':{'name':'XAUUSD'}}}}],
                'has_more':False}
    monkeypatch.setattr(n,'request_json',fake)
    report=n.sync(source,force=True)
    assert report['added']==0
    db=e.connection()
    try:assert db.execute('SELECT uid FROM trades WHERE uid=?',(uid,)).fetchone() is None
    finally:db.close()


def test_news_interface_surfaces_actual_and_refresh_and_purge_controls():
    root=Path(__file__).resolve().parents[1]
    js=(root/'static/v22.js').read_text()
    assert 'v27Reading(e.actual,e)' in js
    assert 'id="v27-refresh"' in js
    assert 'of ${events.length} releases show published actuals' in js
    appjs=(root/'static/app.js').read_text()
    assert "data-permanent=" in appjs and '/permanent' in appjs


def test_no_key_us_agency_fallback_preserves_actual_and_missing_forecast(monkeypatch):
    payload={'data':[{'eventName':'Initial Jobless Claims','scheduledAt':'2026-11-05T13:30:00Z',
                      'importance':'high','actual':201000,'previous':202000,'forecast':None,'unit':'persons'}]}
    monkeypatch.setattr(i,'fetch',lambda url,ttl=0:json.dumps(payload).encode())
    rows=i._us_agency_calendar('2026-11-01','2026-11-07')['events']
    assert len(rows)==1 and rows[0]['actual']==201000
    assert rows[0]['forecast'] is None
    assert rows[0]['currency']=='USD'
    assert 'XOOMAR' in rows[0]['source']


def test_second_source_must_not_overwrite_matching_actual():
    a=[{'currency':'USD','datetime':'2026-11-02T15:00:00+00:00',
        'event':'ISM Manufacturing PMI','actual':'55.5'}]
    b=[{'currency':'USD','datetime':'2026-11-02T15:00:00+00:00',
        'event':'ISM Manufacturing PMI','actual':'99'}]
    i._matching_actuals(a,b)
    assert a[0]['actual']=='55.5'
