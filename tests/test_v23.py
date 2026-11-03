"""Verified v2.3 regression tests, including safe local-only remove and R validation."""
import json
from datetime import datetime, timezone
from unittest.mock import patch
from fastapi.testclient import TestClient
from twys import engine as e, notion_sync as n, integrations as i, marketplace
from twys.app import app


def test_outlier_is_retained_but_excluded():
    row={'uid':'f'*20,'traded_at':'2026-10-16','outcome':'win','outcome_basis':'realized_r',
         'realized_r':40339.0,'flags':'[]'}
    good={'uid':'a'*20,'traded_at':'2026-10-17','outcome':'loss','outcome_basis':'realized_r',
          'realized_r':-1.0,'flags':'[]'}
    m=e.metrics([row,good])
    assert m['r_review_required']==1
    assert m['r_coverage']==1 and m['total_r']==-1 and m['wins']==0
    assert m['losses']==1 and m['win_rate']==0
    assert e.serialize(row)['realized_r']==40339 and e.serialize(row)['requires_r_review']
    assert 'extreme_reported_r_requires_review' in e.validate_reported_r('40339R')[1]


def test_trade_hide_restore_does_not_delete_source():
    uid='a'*20
    c=e.connection()
    try:
        cols=[x[1] for x in c.execute('PRAGMA table_info(trades)').fetchall()]
        record={k:None for k in cols};record.update(uid=uid,source='notion_api:test',instrument='XAUUSD',record_type='trade',
            imported_at='2026-10-18',original_json='{}',images='[]',flags='[]',realized_r=1)
        c.execute('INSERT INTO trades('+','.join(cols)+') VALUES('+','.join('?' for _ in cols)+')',list(record.values()))
        c.commit()
    finally:c.close()
    with TestClient(app) as cl:
        assert cl.get('/api/trades').json()['total']==1
        assert cl.delete('/api/trade/'+uid).json()['scope']=='local_only'
        assert cl.get('/api/trades').json()['total']==0
        assert cl.get('/api/trash').json()['rows'][0]['uid']==uid
        assert cl.post('/api/trash/'+uid+'/restore').json()['restored']
        assert cl.get('/api/trades').json()['total']==1
    c=e.connection()
    try:assert c.execute('SELECT COUNT(*) FROM trades WHERE uid=?',(uid,)).fetchone()[0]==1
    finally:c.close()


def test_forexfactory_weekly_json_normalization():
    today=datetime.now(timezone.utc).date();this_sunday=today-__import__('datetime').timedelta(days=(today.weekday()+1)%7)
    sample=[{'title':'CPI m/m','country':'CAD','date':this_sunday.isoformat()+'T08:30:00-04:00',
             'impact':'High','forecast':'0.2%','previous':'-0.1%'}]
    # Exercise the JSON fallback, independent of live primary-page availability.
    with patch.object(i,'_forexfactory_web_calendar',side_effect=OSError('primary webpage unavailable')), patch.object(i,'config',return_value={}), patch.object(i,'fetch',return_value=json.dumps(sample).encode()) as fetch:
        result=i.get_calendar(this_sunday.isoformat(),(this_sunday+__import__('datetime').timedelta(days=6)).isoformat())
    assert result['status']=='ok' and result['events'][0]['impact']=='high'
    assert result['events'][0]['currency']=='CAD'
    assert result['events'][0]['forecast']=='0.2%'
    assert any('ff_calendar_thisweek.json' in c.args[0] for c in fetch.call_args_list)


def test_notion_images_and_safe_source():
    page={'id':'8'*8+'-8888-8888-8888-888888888888','properties':{
      'Images':{'type':'files','files':[{'name':'Entry.png','type':'file','file':{'url':'https://prod-files-secure.s3.us-west-2.amazonaws.com/entry.png','expiry_time':'2026-10-18'}}]},
      'Date':{'type':'date','date':{'start':'2026-10-17'}},
      'Instrument':{'type':'select','select':{'name':'XAUUSD'}}}}
    row=n.normalize_page(page,'4'*36)
    assert json.loads(row['images'])[0]['url'].startswith('https:')
    assert n._safe_image_url(json.loads(row['images'])[0]['url'])
    for url in ['http://localhost/secret','https://169.254.169.254/a','https://amazonaws.com.attacker.io/x','file:///etc/passwd']:
        assert not n._safe_image_url(url)


def test_only_one_news_calendar_and_white_wordmark():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    html=(root/'static/index.html').read_text()
    assert html.count('data-page="newsdesk"')==1
    assert 'brandmark' not in html
    assert 'v23.css' in html
    assert (root/'assets/twys-icon.ico').exists()
    assert 'Global economic calendar' not in (root/'static/v22.js').read_text().split('async function v2LoadNews()')[1].split('async function v22LoadWeek()')[0]


def test_binance_crypto_directory_augments_default_search():
    example={'symbols':[
      {'symbol':'BTCUSDT','baseAsset':'BTC','quoteAsset':'USDT','status':'TRADING'},
      {'symbol':'BTCUSDC','baseAsset':'BTC','quoteAsset':'USDC','status':'TRADING'},
      {'symbol':'BTCEUR','baseAsset':'BTC','quoteAsset':'EUR','status':'TRADING'},
      {'symbol':'BTCTRY','baseAsset':'BTC','quoteAsset':'TRY','status':'BREAK'},
      {'symbol':'SOLUSDT','baseAsset':'SOL','quoteAsset':'USDT','status':'TRADING'},
    ]}
    with patch.object(i,'fetch',return_value=json.dumps(example).encode()) as fetch:
        response=marketplace.public_crypto_symbols('BTC')
    assert response['status']=='ok' and response['count']==3
    assert [x['symbol'] for x in response['results']]==['BTCUSDT','BTCUSDC','BTCEUR']
    assert fetch.call_args.kwargs['ttl']==3600
    with TestClient(app) as cl,patch.object(i,'fetch',return_value=json.dumps(example).encode()):
        assert cl.get('/api/v2/symbols/crypto?q=BTC').json()['count']==3


def test_notion_deletion_requires_two_successful_syncs_and_restores_reappearing_page():
    source='7'*36
    pid='6'*8+'-6666-6666-6666-666666666666'
    page={'object':'page','id':pid,'last_edited_time':'2026-10-18T00:00:00.000Z',
          'properties':{'Date':{'type':'date','date':{'start':'2026-10-18'}},
                        'Instrument':{'type':'select','select':{'name':'XAUUSD'}}}}
    state={'rows':[page]}
    target_uid=n.normalize_page(page,source)['uid']
    def fake_notion(endpoint,body=None):
        if endpoint.startswith('data_sources/'):
            return {'results':state['rows'],'has_more':False}
        return {'results':[],'has_more':False}
    with patch.object(n,'request_json',side_effect=fake_notion):
        first=n.sync(source)
        assert first['added']==1 and first['removed']==0
        assert any(t['uid']==target_uid for t in e.load_trades())
        state['rows']=[]
        assert n.sync(source)['removed']==0  # transient emptiness: no deletion
        assert len(e.load_trades())>=1
        assert n.sync(source)['removed']==1
        assert not any(t['uid']==target_uid for t in e.load_trades())
        state['rows']=[page]
        assert n.sync(source)['removed']==0
        assert any(t['uid']==target_uid for t in e.load_trades())


def test_cftc_gold_futures_positioning_is_source_attributed_not_global_sentiment():
    from twys import positioning
    sample=[{'report_date_as_yyyy_mm_dd':'2026-10-13T00:00:00.000',
             'm_money_positions_long_all':'140000','m_money_positions_short_all':'60000'}]
    with patch.object(i,'fetch',return_value=json.dumps(sample).encode()) as mocked:
        result=positioning.get_cftc_gold_positioning('XAUUSD')
    assert result['long_percent']==70.0 and result['short_percent']==30.0
    assert result['long_positions']==140000 and result['short_positions']==60000
    assert result['type']=='futures_managed_money_contracts'
    assert 'not live XAUUSD buyers/sellers' in result['note']
    assert '72hh-3qpy' in mocked.call_args.args[0]
    assert positioning.get_cftc_gold_positioning('EURUSD') is None
