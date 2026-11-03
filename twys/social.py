"""Instrument-focused, attributed public discussion search.

Only actual Reddit posts retrieved through the publisher's RSS endpoint are shown.
No fictional social sentiment or inferred positions are produced. When Reddit
restricts RSS access, provide direct publisher search links rather than a blank.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode, quote
import re
import xml.etree.ElementTree as ET
from . import integrations as i

ALIASES={
 'AAPL':['AAPL','Apple stock','Apple shares','Apple earnings'],
 'MSFT':['MSFT','Microsoft stock','Microsoft shares'],
 'NVDA':['NVDA','Nvidia stock','Nvidia earnings'],
 'EURUSD':['EURUSD','EUR/USD','euro dollar','EUR USD'],
 'GBPUSD':['GBPUSD','GBP/USD','cable forex'],
 'USDJPY':['USDJPY','USD/JPY','dollar yen'],
 'XAUUSD':['XAUUSD','XAU/USD','spot gold','gold futures'],
 'US100':['US100','NAS100','Nasdaq 100','NDX futures'],
 'US500':['US500','SPX','S&P 500'],
 'BTCUSDT':['BTCUSDT','Bitcoin','BTC price'],
 'BTCUSD':['BTCUSD','Bitcoin','BTC price'],
 'ETHUSDT':['ETHUSDT','Ethereum','ETH price'],
}

def lookups(symbol):
    symbol=str(symbol or '').upper()
    terms=ALIASES.get(symbol,[symbol])
    queries=[{'label':'Reddit', 'url':'https://www.reddit.com/search/?'+urlencode({'q':' OR '.join('"'+t+'"' for t in terms[:3]),'sort':'new'})},
             {'label':'X', 'url':'https://x.com/search?q='+quote(' OR '.join('"'+t+'"' for t in terms[:2]))+'&f=live'},
             {'label':'Stocktwits', 'url':'https://stocktwits.com/symbol/'+quote(symbol)}]
    return queries

def _parse_feed(payload, symbol, source_url):
    root=ET.fromstring(payload)
    ns={'a':'http://www.w3.org/2005/Atom'}
    patterns=[re.compile(r'(?<![A-Za-z0-9])'+re.escape(t)+r'(?![A-Za-z0-9])',re.I)
              for t in ALIASES.get(symbol,[symbol])]
    now=datetime.now(timezone.utc)
    rows=[]
    for node in root.findall('a:entry',ns)[:50]:
        link=node.find('a:link',ns)
        href=link.attrib.get('href','') if link is not None else ''
        title=node.findtext('a:title','',namespaces=ns).strip()
        updated=node.findtext('a:updated','',namespaces=ns)
        if not href.startswith('https://www.reddit.com/'):continue
        if not any(p.search(title) for p in patterns):continue
        try:
            age=now-datetime.fromisoformat(updated.replace('Z','+00:00'))
            if age<timedelta(0) or age>timedelta(days=14):continue
        except (ValueError,TypeError):continue
        author=node.findtext('a:author/a:name','',namespaces=ns)
        rows.append({'title':title[:240],'author':author[:90],'url':href,'source':'Reddit public RSS',
                     'published':updated,'bias':'not_classified','position_verified':False})
    return rows

def public_commentary(symbol):
    symbol=str(symbol or '').upper().strip()
    if not re.fullmatch(r'[A-Z0-9/._:-]{2,35}',symbol):
        return {'status':'invalid_symbol','items':[],'searches':[]}
    terms=ALIASES.get(symbol,[symbol])
    query_terms=[terms[0]]
    if len(terms)>1:query_terms.append(terms[1])
    urls=['https://www.reddit.com/search.rss?'+urlencode({'q':q,'sort':'new','t':'week','limit':50})
          for q in query_terms]
    entries=[];errors=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(i.fetch,url,900):url for url in urls}
        for task in as_completed(futures):
            try:entries+=_parse_feed(task.result(),symbol,futures[task])
            except Exception as ex:errors.append(type(ex).__name__)
    unique={x['url']:x for x in entries}
    result=sorted(unique.values(),key=lambda x:x['published'],reverse=True)[:15]
    return {'status':'ok' if result else 'no_matching_posts', 'items':result,
      'searches':lookups(symbol),'errors':errors,
      'scope':'Publicly indexed comments only. Not orders or verified positions.',
      'retrieved_at':datetime.now(timezone.utc).isoformat(),
      'note':'Some services restrict external RSS/search access. Direct searches remain accessible in the publisher site.'}
