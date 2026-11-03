from fastapi.testclient import TestClient
from twys.app import app


def test_endpoints_smoke():
    client=TestClient(app)
    assert client.get('/api/health').json()['status']=='ok'
    data=client.get('/api/dashboard').json()
    assert data['metrics']['trades']==0
    assert data['metrics']['r_coverage']<=data['metrics']['trades']
    assert client.get('/').status_code==200
    assert client.get('/static/app.js').status_code==200
    assert client.get('/static/plotly.min.js').status_code==200
    assert client.get('/api/comparisons').status_code==200
    trades=client.get('/api/trades?instrument=XAUUSD&limit=5').json()
    assert trades['total']==0 and trades['rows']==[]
    assert client.get('/api/trade/'+'f'*20).status_code==404
    assert client.get('/api/quality').status_code==200
    assert client.get('/api/export/trades.csv').status_code==200
    assert client.get('/api/settings').status_code==200
    assert client.get('/api/local-models').status_code==200


def test_research_evidence_mode():
    client=TestClient(app)
    response=client.post('/api/research',json={'question':'Find trades where retracement was mentioned.'})
    assert response.status_code==200
    data=response.json()
    assert 'stats' in data and 'evidence' in data
    assert data['stats']['trades']==0
    assert len(data['evidence'])==0


def test_v2_empty_market_research():
    client=TestClient(app)
    assert client.get('/api/v2/status').json()['data']['records']==0
    assert client.get('/api/v2/symbols?q=Gold').json()['results'][0]['symbol']=='XAUUSD'
    first=client.get('/api/v2/search?q=XAUUSD').json()
    assert not first['ai_used'] and any(x['kind']=='market' for x in first['results'])
    assert client.get('/api/v2/markets/XAUUSD/candles').json()['status']=='not_configured'
    assert client.get('/api/v2/markets/XAUUSD').json()['personal'] is None
    assert client.post('/api/v2/compare',json={'a':{'instrument':'XAUUSD'},'b':{'instrument':'EURUSD'}}).status_code==404
    assert client.get('/static/v2.js').status_code==200
    assert client.post('/api/v2/favorites',json={'symbol':'XAUUSD','favorite':True}).status_code==200
    assert 'XAUUSD' in client.get('/api/v2/favorites').json()['symbols']
    assert client.post('/api/v2/favorites',json={'symbol':'XAUUSD','favorite':False}).status_code==200
    assert 'XAUUSD' not in client.get('/api/v2/favorites').json()['symbols']


def test_local_api_denies_external_origins():
    client=TestClient(app)
    assert client.post('/api/v2/favorites',json={'symbol':'AAPL'},headers={'Origin':'https://untrusted.example'}).status_code==403
