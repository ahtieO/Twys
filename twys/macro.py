"""Official macroeconomic observations. Delayed, not a live causal model."""
from __future__ import annotations
import csv
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from io import StringIO
from urllib.parse import urlencode
from . import integrations

SERIES = {
    'DFF': ('Effective federal funds rate', '%', 'daily'),
    'DGS2': ('2-year Treasury yield', '%', 'daily'),
    'DGS10': ('10-year Treasury yield', '%', 'daily'),
    'DFII10': ('10-year TIPS real yield', '%', 'daily'),
    'T10YIE': ('10-year breakeven inflation', '%', 'daily'),
    'DTWEXBGS': ('Broad trade-weighted USD index', 'index', 'daily'),
    'DEXUSEU': ('USD per EUR', 'USD/EUR', 'daily'),
    'CPIAUCSL': ('US CPI index', 'index', 'monthly'),
}

def parse_fred_csv(raw: bytes, series_id: str):
    """Only accept valid dated numeric observations, without inventing missing points."""
    rows=[]
    try:
        data = csv.DictReader(StringIO(raw.decode('utf-8-sig')))
        if not data.fieldnames or series_id not in data.fieldnames:
            raise ValueError(f'Missing expected {series_id} column')
        date_key = 'observation_date' if 'observation_date' in data.fieldnames else 'DATE'
        if date_key not in data.fieldnames:
            raise ValueError('Missing observation date')
        for row in data:
            value=str(row.get(series_id) or '').strip()
            if not value or value=='.':continue
            try:
                dt=datetime.strptime(str(row[date_key]), '%Y-%m-%d').date().isoformat()
                val=float(value)
                if not -1e8 < val < 1e8:continue
            except (ValueError,TypeError):continue
            rows.append({'date':dt,'value':val})
    except UnicodeDecodeError as exc:
        raise ValueError('Non-UTF8 macro response') from exc
    return rows

def load_one(key):
    name, unit, frequency=SERIES[key]
    result={'id':key,'name':name,'unit':unit,'frequency':frequency,
            'source':'Federal Reserve Economic Data (FRED)',
            'url':f'https://fred.stlouisfed.org/series/{key}'}
    try:
        url='https://fred.stlouisfed.org/graph/fredgraph.csv?'+urlencode({'id':key})
        rows=parse_fred_csv(integrations.fetch(url,ttl=1800),key)
        if not rows:raise ValueError('No valid observations')
        latest=rows[-1]
        prior=rows[-2] if len(rows)>1 else None
        result.update(status='ok',latest=latest,previous=prior,
                      change=None if not prior else round(latest['value']-prior['value'],5),
                      history=rows[-160:])
        if key=='CPIAUCSL' and len(rows)>=13:
            prev=rows[-13]['value']
            if prev:result['yoy_percent']=round((latest['value']/prev-1)*100,2)
    except Exception as exc:
        result.update(status='unavailable',error=f'{type(exc).__name__}: {str(exc)[:100]}',latest=None,history=[])
    return result

def report():
    with ThreadPoolExecutor(max_workers=6) as executor:
        data=list(executor.map(load_one,SERIES))
    return {'series':data,'fetched_at':datetime.now(timezone.utc).isoformat(),
            'methodology':'Official released observations; latest values may lag markets. Changes are between successive available observations. Relationships are conditional hypotheses, not causal claims or trading signals.',
            'scenarios':[
                {'title':'Inflation surprises higher','mechanism':'Markets may price higher policy rates or fewer cuts. The dollar and nominal yields sometimes strengthen; gold depends importantly on real yields and risk demand.','not_guaranteed':True},
                {'title':'Yields rise while inflation expectations remain stable','mechanism':'Rising real yields can increase the opportunity cost of holding gold. Currency moves also depend on relative rates abroad.','not_guaranteed':True},
                {'title':'EURUSD and USD strength','mechanism':'Compare US interest-rate expectations with euro-area expectations. US inflation alone does not determine EURUSD; ECB policy, relative growth and positioning also matter.','not_guaranteed':True},
            ]}


def news_brief():
    """Latest source-linked macro headlines and reported economic releases.

    Do not claim a headline caused a price movement. Headlines and event values
    are independently sourced; missing actuals remain null.
    """
    from datetime import timedelta
    import re
    pattern=re.compile(r'\b(inflation|consumer price|cpi|pce|interest rate|federal funds|fomc|fed |federal reserve|treasury yield|bond yield|monetary policy|ecb|boe|rate cut|rate hike|jobless|unemployment|payroll|gdp)\b',re.I)
    feeds=integrations.get_news()
    headlines=[x for x in feeds.get('items',[]) if pattern.search(x.get('title','')+' '+x.get('summary',''))][:24]
    now=datetime.now(timezone.utc)
    start=(now-timedelta(days=14)).date().isoformat()
    end=(now+timedelta(days=21)).date().isoformat()
    event_result=integrations.get_calendar(start,end,provider_override='financecalendar')
    events=[x for x in event_result.get('events',[]) if pattern.search(x.get('event','')) and x.get('currency') in ('USD','EUR','GBP')][:30]
    return {'headlines':headlines,'events':events,'headlines_status':feeds.get('status'),
            'calendar_status':event_result.get('status'),'calendar_message':event_result.get('message'),
            'fetched_at':now.isoformat(),
            'note':'Market relationships are hypotheses. Release dates and values are attributed to sources; none are proof of what caused a particular price move.'}
