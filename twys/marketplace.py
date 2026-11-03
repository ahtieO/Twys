"""Local deterministic cross-domain search, watchlists and instrument research.
Search is fully usable without any language model or provider keys.
"""
from __future__ import annotations
import re, json, sqlite3
from datetime import datetime,timezone
from urllib.parse import urlencode
from . import engine as e, integrations as i, positioning

# Symbols are navigation shortcuts, NOT claims of active price coverage.
CATALOG=[
 ('XAUUSD','Gold / US dollar','Commodity'),('XAGUSD','Silver / US dollar','Commodity'),
 ('EURUSD','Euro / US dollar','Forex'),('GBPUSD','Pound / US dollar','Forex'),('USDJPY','US dollar / yen','Forex'),
 ('USDCHF','US dollar / Swiss franc','Forex'),('AUDUSD','Australian dollar / US dollar','Forex'),
 ('USDCAD','US dollar / Canadian dollar','Forex'),('NZDUSD','New Zealand dollar / US dollar','Forex'),
 ('US100','Nasdaq 100','Index'),('US500','S&P 500','Index'),('US30','Dow Jones 30','Index'),('DXY','US dollar index','Index'),
 ('AAPL','Apple','Stock'),('MSFT','Microsoft','Stock'),('NVDA','NVIDIA','Stock'),('GOOGL','Alphabet','Stock'),
 ('AMZN','Amazon','Stock'),('TSLA','Tesla','Stock'),('META','Meta Platforms','Stock'),('SPY','SPDR S&P 500 ETF','ETF'),
 ('QQQ','Invesco QQQ ETF','ETF'),('BTCUSDT','Bitcoin / Tether','Crypto'),('ETHUSDT','Ethereum / Tether','Crypto'),
 ('SOLUSDT','Solana / Tether','Crypto'),('BTCUSD','Bitcoin / US dollar','Crypto'),('ETHUSD','Ethereum / US dollar','Crypto'),
 ('WTI','WTI crude oil','Commodity'),('BRENT','Brent crude oil','Commodity'),('NG','Natural gas','Commodity'),
 ('GC','Gold futures','Future'),('CL','Crude oil futures','Future'),('ES','S&P 500 futures','Future'),('NQ','Nasdaq futures','Future')]

# Extended large-cap digital-asset shortcuts. Provider symbol directories can add more.
CATALOG.extend([(ticker+'USDT',name+' / Tether','Crypto') for ticker,name in [
 ('XRP','XRP'),('BNB','BNB'),('DOGE','Dogecoin'),('ADA','Cardano'),('AVAX','Avalanche'),
 ('DOT','Polkadot'),('LINK','Chainlink'),('LTC','Litecoin'),('BCH','Bitcoin Cash'),
 ('TRX','TRON'),('TON','Toncoin'),('NEAR','NEAR Protocol'),('UNI','Uniswap'),
 ('APT','Aptos'),('SUI','Sui'),('ATOM','Cosmos'),('ETC','Ethereum Classic'),
 ('XLM','Stellar'),('FIL','Filecoin'),('ARB','Arbitrum'),('OP','Optimism'),
 ('PEPE','Pepe'),('SHIB','Shiba Inu'),('INJ','Injective'),('AAVE','Aave'),
 ('ICP','Internet Computer'),('RENDER','Render'),('POL','Polygon'),('HBAR','Hedera')
]])

SCHEMA='''
CREATE TABLE IF NOT EXISTS watchlists(symbol TEXT PRIMARY KEY, added_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS notion_records(page_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, last_edited TEXT, original_json TEXT NOT NULL, imported_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS notion_sync_runs(id INTEGER PRIMARY KEY, at TEXT, status TEXT, records INTEGER, message TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS trade_index USING fts5(uid UNINDEXED, instrument, reasoning, review, mistake, emotion, rating, tokenize='unicode61');
CREATE TABLE IF NOT EXISTS market_headlines(uid TEXT PRIMARY KEY, title TEXT, summary TEXT, source TEXT, url TEXT, published TEXT, impact TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS news_index USING fts5(uid UNINDEXED, title, summary, source, tokenize='unicode61');
'''

def init():
    c=e.connection()
    try:
        c.executescript(SCHEMA)
        c.commit()
    finally:c.close()

def reindex():
    init();c=e.connection()
    try:
        c.execute('DELETE FROM trade_index')
        rows=c.execute('SELECT uid,instrument,reasoning,review,mistake,emotion,rating FROM trades WHERE uid NOT IN (SELECT uid FROM local_hidden_trades)').fetchall()
        c.executemany('INSERT INTO trade_index(uid,instrument,reasoning,review,mistake,emotion,rating) VALUES(?,?,?,?,?,?,?)',[(r['uid'],r['instrument'] or '',r['reasoning'] or '',r['review'] or '',r['mistake'] or '',r['emotion'] or '',r['rating'] or '') for r in rows])
        c.commit();return len(rows)
    finally:c.close()

def store_headlines(rows):
    """Local search cache for independently sourced official headline metadata."""
    import hashlib
    init();c=e.connection()
    try:
        for row in rows:
            url=row.get('url') or ''
            if not url.startswith('https://'):continue
            uid=hashlib.sha256(url.encode('utf-8')).hexdigest()[:20]
            data=(uid,row.get('title','')[:300],row.get('summary','')[:500],row.get('source','')[:100],url,
                  row.get('published'),row.get('impact'))
            c.execute('INSERT INTO market_headlines VALUES(?,?,?,?,?,?,?) ON CONFLICT(uid) DO UPDATE SET title=excluded.title,summary=excluded.summary,source=excluded.source,published=excluded.published,impact=excluded.impact',data)
        c.execute('DELETE FROM news_index')
        c.execute('INSERT INTO news_index(uid,title,summary,source) SELECT uid,title,summary,source FROM market_headlines')
        c.commit()
    finally:c.close()

def favorites():
    init();c=e.connection()
    try:return [r['symbol'] for r in c.execute('SELECT symbol FROM watchlists ORDER BY added_at DESC')]
    finally:c.close()

def set_favorite(symbol,enabled):
    symbol=str(symbol).upper().strip()
    if not re.fullmatch('[A-Z0-9/._:-]{1,35}',symbol):raise ValueError('Invalid symbol')
    init();c=e.connection()
    try:
        if enabled:c.execute('INSERT OR IGNORE INTO watchlists VALUES(?,?)',(symbol,datetime.now(timezone.utc).isoformat()))
        else:c.execute('DELETE FROM watchlists WHERE symbol=?',(symbol,))
        c.commit()
        return {'symbol':symbol,'saved':bool(enabled),'favorites':favorites()}
    finally:c.close()

def symbol_search(term='',limit=60):
    term=str(term or '').strip().lower()[:60]
    rows=[{'symbol':symbol,'name':name,'asset_class':category,'source':'TWYS shortcuts'} for symbol,name,category in CATALOG if not term or term in symbol.lower() or term in name.lower() or term in category.lower()]
    # If user types a syntactically valid symbol not in shortcuts, let them investigate it with a provider.
    if term and not rows and re.fullmatch('[a-z0-9/._:-]{2,35}',term):
        rows.insert(0,{'symbol':term.upper(),'name':'Custom symbol · verify with your data provider','asset_class':'Unknown','source':'User lookup'})
    return rows[:limit]

def search(query,scope='all',limit=45):
    """Lexical search returns snippets and deep links, not hallucinated recommendations."""
    q=' '.join(str(query or '').strip().split())[:120]; term=q.lower(); out=[]
    if scope in ('all','markets'):
        for v in symbol_search(q,limit=30):out.append({'kind':'market','title':v['symbol'],'subtitle':v['name']+' · '+v['asset_class'],'id':v['symbol']})
    if scope in ('all','journal') and q:
        init();c=e.connection()
        try:
            try:
                words=re.findall(r'\w+',q,flags=re.UNICODE)[:8]
                fts=' OR '.join('"'+w.replace('"','')+'"' for w in words)
                records=c.execute('SELECT uid,instrument,snippet(trade_index,2,"[","]","…",12) AS excerpt FROM trade_index WHERE trade_index MATCH ? LIMIT 30',(fts,)).fetchall() if words else []
            except sqlite3.OperationalError:
                records=[]
            for r in records:out.append({'kind':'journal','title':r['instrument'] or 'Trade','subtitle':r['excerpt'],'id':r['uid']})
        finally:c.close()
    if scope in ('all','watchlists'):
        for symbol in favorites():
            if not term or term in symbol.lower():out.append({'kind':'favorite','title':symbol,'subtitle':'Saved watchlist instrument','id':symbol})
    if scope in ('all','markets') and q:
        init();c=e.connection()
        try:
            words=re.findall(r'\w+',q,flags=re.UNICODE)[:8]
            if words:
                match=' OR '.join('"'+word.replace('"','')+'"' for word in words)
                rows=c.execute('SELECT h.title,h.source,h.url FROM news_index n JOIN market_headlines h ON h.uid=n.uid WHERE news_index MATCH ? ORDER BY rank LIMIT 20',(match,)).fetchall()
                for r in rows:out.append({'kind':'news','title':r['title'],'subtitle':r['source']+' · Official headline','id':r['url']})
        except sqlite3.OperationalError:pass
        finally:c.close()
    return {'query':q,'results':out[:limit],'engine':'TWYS SQLite FTS5 + instrument index + cached official headlines','ai_used':False,'count':len(out[:limit])}

def public_crypto_symbols(query, limit=45):
    """Search Binance's published SPOT exchange directory, no account or API key.

    A symbol-directory hit does not guarantee that TradingView can chart it,
    or that a given country can access Binance services.
    """
    term=str(query or '').upper().strip()
    if not re.fullmatch(r'[A-Z0-9]{3,24}',term):
        return {'results':[],'status':'invalid_query','provider':'Binance Spot directory'}
    try:
        url='https://data-api.binance.vision/api/v3/exchangeInfo'
        document=json.loads(i.fetch(url,ttl=3600))
        if not isinstance(document,dict) or not isinstance(document.get('symbols'),list):
            raise ValueError('Unexpected exchange directory response')
        rows=[]
        for value in document['symbols']:
            if not isinstance(value,dict) or value.get('status')!='TRADING':continue
            symbol=str(value.get('symbol') or '')
            base=str(value.get('baseAsset') or '')
            quote=str(value.get('quoteAsset') or '')
            if term not in symbol and term not in base:continue
            # Display USDT/USD-type instruments first, otherwise show the real traded quote.
            rows.append({'symbol':symbol,'name':f'{base} / {quote}',
                         'asset_class':'Crypto','exchange':'Binance Spot',
                         'source':'Binance public exchange directory'})
        preference={'USDT':0,'USDC':1,'FDUSD':2,'BTC':3,'ETH':4}
        rows.sort(key=lambda d:(0 if d['symbol'].startswith(term) else 1,
                 preference.get(d['name'].split(' / ')[-1],9),len(d['symbol'])))
        return {'results':rows[:limit],'status':'ok','provider':'Binance Spot directory',
                'count':len(rows),'notice':'Symbols show available exchange pairs, not universally accessible trading or verified chart coverage.'}
    except Exception as ex:
        return {'results':[],'status':'provider_unavailable','provider':'Binance Spot directory',
                'message':str(ex)[:140]}

def provider_lookup(query):
    """Provider-wide discovery when Twelve Data is configured. No key means no remote search."""
    term=str(query or '').strip()[:60]
    if len(term)<2:return {'results':[],'status':'too_short'}
    key=i.secret('TWELVE_DATA_KEY')
    if not key:return {'results':[],'status':'key_required','provider':'Twelve Data'}
    try:
        url='https://api.twelvedata.com/symbol_search?'+urlencode({'symbol':term,'apikey':key,'outputsize':40})
        data=json.loads(i.fetch(url,ttl=1800))
        if not isinstance(data,dict) or data.get('status')=='error':raise ValueError(data.get('message','Provider error'))
        results=[{'symbol':r.get('symbol'),'name':r.get('instrument_name') or r.get('name') or '',
                  'exchange':r.get('exchange') or '', 'asset_class':r.get('instrument_type') or 'Market',
                  'source':'Twelve Data'} for r in data.get('data',[]) if r.get('symbol')]
        return {'results':results[:40],'status':'ok','provider':'Twelve Data','note':'Provider coverage varies by plan and exchange.'}
    except Exception as ex:return {'results':[],'status':'error','message':str(ex)[:180]}

# Curated research neighbors, not a claim of statistical correlation or co-movement.
RELATED={
 'AAPL':[('MSFT','Large-cap technology peer'),('GOOGL','Large-cap technology peer'),('QQQ','Nasdaq 100 ETF'),('SPY','Broad US equities'),('NVDA','Technology sector peer')],
 'MSFT':[('AAPL','Large-cap technology peer'),('GOOGL','Large-cap technology peer'),('QQQ','Nasdaq 100 ETF'),('NVDA','Technology sector peer')],
 'NVDA':[('AMD','Semiconductor industry peer'),('QQQ','Nasdaq 100 ETF'),('MSFT','Technology ecosystem'),('SOXX','Semiconductor ETF')],
 'EURUSD':[('DXY','US dollar strength benchmark'),('GBPUSD','Major European currency'),('USDCHF','Dollar / Swiss franc'),('USDJPY','Dollar / yen')],
 'GBPUSD':[('DXY','US dollar benchmark'),('EURUSD','Major European FX pair'),('USDJPY','Another major USD currency')],
 'USDJPY':[('DXY','Broad US dollar benchmark'),('EURUSD','Major USD pair'),('US500','US stock index')],
 'XAUUSD':[('GC','Gold futures'),('XAGUSD','Silver spot'),('DXY','US dollar benchmark'),('EURUSD','Major USD pair')],
 'XAGUSD':[('XAUUSD','Related precious metal'),('GC','Gold futures'),('DXY','US dollar benchmark')],
 'DXY':[('EURUSD','Largest DXY currency component'),('GBPUSD','Dollar exchange rate'),('USDJPY','Dollar exchange rate'),('XAUUSD','Dollar-denominated gold')],
 'US100':[('QQQ','Nasdaq 100 tracking ETF'),('US500','Broad US equity index'),('NVDA','Large Nasdaq stock'),('AAPL','Large Nasdaq stock')],
 'US500':[('SPY','S&P 500 tracking ETF'),('US100','US growth-heavy index'),('US30','Dow Jones index')],
 'BTCUSDT':[('ETHUSDT','Large crypto asset'),('SOLUSDT','Large crypto asset'),('BTCUSD','Bitcoin USD market')],
}

def related_markets(symbol, asset_class=None):
    symbol=str(symbol or '').upper()
    if symbol in RELATED: candidates=RELATED[symbol]
    elif symbol.endswith('USDT') or asset_class=='Crypto':
        candidates=[('BTCUSDT','Crypto market benchmark'),('ETHUSDT','Large crypto asset'),('SOLUSDT','Large crypto asset')]
    elif asset_class=='Stock':
        candidates=[('SPY','Broad US equity market'),('QQQ','Nasdaq-heavy equity ETF')]
    elif asset_class=='Forex':
        candidates=[('DXY','US dollar benchmark'),('EURUSD','Major USD currency pair')]
    elif asset_class=='Index':
        candidates=[('US500','Broad US equities'),('US100','Growth-heavy US equities')]
    else:candidates=[]
    return [{'symbol':s,'reason':reason} for s,reason in candidates if s!=symbol][:5]

def market_brief(symbol):
    symbol=str(symbol or '').upper().strip()
    if not re.fullmatch(r'[A-Z0-9/._:-]{2,35}',symbol):raise ValueError('Invalid symbol')
    info=next(({'name':name,'asset_class':category} for s,name,category in CATALOG if s==symbol),{'name':symbol,'asset_class':'Unknown'})
    trades=e.filter_trades(e.load_trades(),{'instrument':symbol})
    # Not all symbols (e.g. Nasdaq = US100 in journal) correspond to provider symbology.
    return {'symbol':symbol,**info,'related':related_markets(symbol, info['asset_class']), 'favorite':symbol in favorites(),
       'personal':{'count':len(trades),'metrics':e.metrics(trades)} if trades else None,
       'source_note':'Personal history and market-wide statistics are kept separate. Reported positioning never represents all market participants.'}

def compare(a,b):
    t=e.load_trades()
    def subset(filters):
        safe={key:value for key,value in (filters or {}).items() if key in ('instrument','source','session','rating','rules','emotion','outcome','from','to','data_type') and isinstance(value,str)}
        return e.filter_trades(t,safe)
    first,second=subset(a),subset(b)
    ma,mb=e.metrics(first),e.metrics(second)
    delta={field:round(ma[field]-mb[field],4) if isinstance(ma.get(field),(int,float)) and isinstance(mb.get(field),(int,float)) else None for field in ('win_rate','expectancy_r','mean_r','total_r','profit_factor')}
    return {'a':{'filters':a,'metrics':ma,'count':len(first)},'b':{'filters':b,'metrics':mb,'count':len(second)},
            'delta_a_minus_b':delta,'warnings':['Comparisons reflect recorded trades, not an independently verified backtest.',
            'Different R coverage or small samples can bias comparisons.']}

def coverage():
    rows=e.load_trades();n=len(rows);labels={}
    fields=['instrument','session','rating','rules_followed','emotion','mistake','planned_r','realized_r','entry_price','stop_price','exit_price','reasoning','review','images']
    for field in fields:
        count=sum(v.get(field) is not None and v.get(field) not in ('', '[]') for v in rows)
        labels[field]={'available':count>0,'records':count,'total':n,'fraction':round(count/n,3) if n else 0}
    return {'records':n,'fields':labels,'sections':{
        'performance':labels['realized_r']['available'],
        'psychology':labels['emotion']['available'] or labels['mistake']['available'],
        'price_execution':all(labels[k]['available'] for k in ('entry_price','stop_price','exit_price')),
        'setup':labels['reasoning']['available'] or labels['rating']['available'],
        'screenshot_review':labels['images']['available'],
        'planned_vs_realized':labels['planned_r']['available'] and labels['realized_r']['available']}}


def suggestions(symbol):
    """Non-AI descriptive observations; no causal or trade recommendations."""
    symbol=str(symbol or '').upper()
    data=e.load_trades()
    t=[r for r in data if r.get('instrument')==symbol]
    other=[r for r in data if r.get('instrument')!=symbol]
    a=e.metrics(t);b=e.metrics(other)
    findings=[]
    if a['r_coverage']>=8 and b['r_coverage']>=8:
        findings.append({'title':'Personal historical expectancy comparison',
                         'statement':f'{symbol}: {a["mean_r"]:+.2f}R average versus {b["mean_r"]:+.2f}R across other recorded markets.',
                         'sample':{'market':len(t),'market_valid_r':a['r_coverage'],'others':len(other),'others_valid_r':b['r_coverage']},
                         'limitation':'Different time periods and setups. Descriptive only, not evidence this instrument causes better performance.'})
    with_rules=[r for r in t if r.get('rules_followed')=='YES']
    without_rules=[r for r in t if r.get('rules_followed')=='NO']
    yes=e.metrics(with_rules);no=e.metrics(without_rules)
    if yes['r_coverage']>=5 and no['r_coverage']>=5:
        findings.append({'title':'Recorded discipline difference',
                         'statement':f'Rules followed: {yes["mean_r"]:+.2f}R average; rules not followed: {no["mean_r"]:+.2f}R.',
                         'sample':{'with_rules':len(with_rules),'without_rules':len(without_rules)},
                         'limitation':'Self-reported labels and retrospective trade outcomes. Not causal or predictive.'})
    return {'symbol':symbol,'findings':findings,'trades':len(t),'r_coverage':a['r_coverage'],
            'ai_used':False,'status':'ok' if findings else 'insufficient_evidence',
            'notice':'These observations never predict future price movements or provide trade entry signals.'}
