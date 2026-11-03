"""Source-attributed position statistics, never estimates of the whole market."""
from __future__ import annotations
import json,re
from datetime import datetime, timezone
from urllib.parse import urlencode
from . import integrations as i

SOURCES={
 'myfxbook': 'https://www.myfxbook.com/api',
 'binance': 'https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Long-Short-Ratio',
 'cftc': 'https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm',
 'ig': 'https://www.ig.com/uk/trading-strategies/_how-to-trade-using-ig-client-sentiment-240912',
 'oanda': 'https://www.oanda.com/bvi-en/skills-and-insights/oanda-labs/order-book-position-book-tool/',
}

def _number(x):
    try:return float(x) if x is not None else None
    except (ValueError,TypeError):return None

def normalize_myfxbook(data, symbol):
    """Percentage is % of tracked open position volume, not % of all retail investors."""
    return {'source':'Myfxbook Community Outlook', 'scope':'Participating Myfxbook accounts / reported positions',
        'symbol':symbol,'long_percent':_number(data.get('longPercentage')),
        'short_percent':_number(data.get('shortPercentage')),
        'long_positions':_number(data.get('longPositions')),'short_positions':_number(data.get('shortPositions')),
        'long_volume':_number(data.get('longVolume')),'short_volume':_number(data.get('shortVolume')),
        'average_long_entry':_number(data.get('avgLongPrice')),'average_short_entry':_number(data.get('avgShortPrice')),
        'source_url':SOURCES['myfxbook'],'type':'reported_broker_community_positions',
        'note':'Position counts are not unique people. Percentages and counts may use different denominators.'}

def normalize_binance(data,symbol,asof=None):
    long_=float(data['longAccount'])*100;short_=float(data['shortAccount'])*100
    return {'source':'Binance Futures', 'scope':'Binance USD-M futures accounts with net long or short position',
        'symbol':symbol,'long_percent':round(long_,3),'short_percent':round(short_,3),
        'long_positions':None,'short_positions':None,'long_volume':None,'short_volume':None,
        'source_url':SOURCES['binance'],'type':'exchange_account_ratio',
        'reported_at':datetime.fromtimestamp(int(data.get('timestamp',0))/1000,timezone.utc).isoformat() if data.get('timestamp') else asof,
        'note':'Account ratios, not the count of all buyers/sellers, trading volume or aggregate position size.'}

def get_cftc_gold_positioning(symbol):
    """No-key official weekly CFTC gold futures COT figures (NOT spot FX sentiment).

    Counts are reported contracts held by the Managed Money category. Percent
    long here is a share of long + short directional contracts in that category,
    not the proportion of accounts, unique buyers, or the entire futures market.
    """
    if symbol not in ('XAUUSD','GC'):
        return None
    url='https://publicreporting.cftc.gov/resource/72hh-3qpy.json?'+urlencode({
        'cftc_contract_market_code':'088691',
        '$order':'report_date_as_yyyy_mm_dd DESC','$limit':'1'})
    rows=json.loads(i.fetch(url,ttl=3600))
    if not isinstance(rows,list) or not rows:raise ValueError('No CFTC Gold futures report returned')
    row=rows[0]
    long_=_number(row.get('m_money_positions_long_all'))
    short_=_number(row.get('m_money_positions_short_all'))
    if long_ is None or short_ is None or (long_+short_)<=0:
        raise ValueError('CFTC managed money positions were not in the expected dataset fields')
    total=long_+short_
    return {'source':'CFTC Commitments of Traders',
            'scope':'COMEX gold futures · managed money · weekly report',
            'symbol':symbol,'long_percent':round(long_/total*100,2),
            'short_percent':round(short_/total*100,2),
            'long_positions':long_,'short_positions':short_,
            'long_volume':None,'short_volume':None,
            'reported_at':row.get('report_date_as_yyyy_mm_dd'),
            'retrieved_at':datetime.now(timezone.utc).isoformat(),
            'source_url':'https://publicreporting.cftc.gov/stories/s/Disaggregated-Futures-Only/ubmb-6exi/',
            'type':'futures_managed_money_contracts',
            'note':'Weekly futures contracts held by managed money, not live XAUUSD buyers/sellers. Percentage divides managed-money long by managed-money long plus short positions; not a percentage of trader accounts.'}

# Exchange-traded futures proxies. Currency futures can have the inverse quote
# of the spot pair displayed in TWYS; labels must make this unmistakable.
FINANCIAL_FUTURES={
    'EURUSD':('099741','CME Euro FX futures',False),
    'GBPUSD':('096742','CME British pound futures',False),
    'USDJPY':('097741','CME Japanese yen futures (JPY/USD)',True),
    'USDCHF':('092741','CME Swiss franc futures (CHF/USD)',True),
    'AUDUSD':('232741','CME Australian dollar futures',False),
    'USDCAD':('090741','CME Canadian dollar futures (CAD/USD)',True),
    'NZDUSD':('112741','CME New Zealand dollar futures',False),
    'DXY':('098662','ICE US dollar index futures',False),
    'US500':('13874A','CME E-mini S&P 500 futures',False),
    'US100':('209742','CME Nasdaq-100 E-mini futures',False),
    'US30':('124603','CBOT E-mini Dow futures',False),
}

def get_cftc_financial_positioning(symbol):
    """Official weekly CFTC TFF leveraged-funds FUTURES contract positions.

    This is never broker-client sentiment and never spot-market buy/sell counts.
    Exposing the original futures direction avoids misrepresenting USD/JPY and
    USD/CAD, whose standardized futures quote is the inverse of the spot pair.
    """
    if symbol not in FINANCIAL_FUTURES:return None
    code, name, inverse = FINANCIAL_FUTURES[symbol]
    url='https://publicreporting.cftc.gov/resource/gpe5-46if.json?'+urlencode({
        'cftc_contract_market_code':code,
        '$order':'report_date_as_yyyy_mm_dd DESC','$limit':'1'})
    data=json.loads(i.fetch(url,ttl=7200))
    if not isinstance(data,list) or not data:
        raise ValueError('No financial futures position report returned')
    row=data[0]
    longs=_number(row.get('lev_money_positions_long',row.get('lev_money_positions_long_all')))
    shorts=_number(row.get('lev_money_positions_short',row.get('lev_money_positions_short_all')))
    if longs is None or shorts is None or longs<0 or shorts<0 or longs+shorts<=0:
        raise ValueError('CFTC TFF contract fields missing or invalid')
    return {'source':'CFTC Traders in Financial Futures','scope':name+' · leveraged funds · weekly futures-only',
       'symbol':symbol,'type':'futures_leveraged_funds_contracts',
       'long_percent':round(100*longs/(longs+shorts),2),
       'short_percent':round(100*shorts/(longs+shorts),2),
       'long_positions':longs,'short_positions':shorts,
       'reported_at':row.get('report_date_as_yyyy_mm_dd'),
       'retrieved_at':datetime.now(timezone.utc).isoformat(),
       'source_url':'https://publicreporting.cftc.gov/resource/gpe5-46if.json?cftc_contract_market_code='+code,
       'note':('Positioning is for '+name+', not this cash/CFD instrument. '
           +'Long and short are in '+('the INVERSE quote to '+symbol if inverse else 'the underlying futures')
           +'. Counts are CONTRACTS, not unique buyers or sellers. Report is weekly and delayed.')}

def get_positioning(symbol):
    symbol=str(symbol or '').replace('/','').replace(' ','').upper()
    if not re.fullmatch(r'[A-Z0-9]{3,15}',symbol):return {'symbol':symbol,'records':[],'errors':['Invalid symbol']}
    records=[];errors=[]
    # Re-use an authenticated session from TWYS secure credential storage, not a password.
    session=i.secret('MYFXBOOK_SESSION')
    if session:
        try:
            url='https://www.myfxbook.com/api/get-community-outlook.json?'+urlencode({'session':session})
            result=json.loads(i.fetch(url,ttl=180))
            if result.get('error'):raise ValueError(result.get('message') or 'Provider error')
            for item in result.get('symbols',[]):
                if str(item.get('name','')).replace('/','').upper()==symbol:
                    rec=normalize_myfxbook(item,symbol);rec['retrieved_at']=datetime.now(timezone.utc).isoformat();records.append(rec)
        except Exception as ex:errors.append('Myfxbook unavailable: '+type(ex).__name__)
    # Public regulator reporting is available for gold futures without any personal API key.
    # The spot-gold page explicitly labels it as the related COMEX gold futures market.
    if symbol in ('XAUUSD','GC'):
        try:
            record=get_cftc_gold_positioning(symbol)
            if record:records.append(record)
        except Exception as ex:
            errors.append('CFTC data unavailable: '+type(ex).__name__)
    if symbol in FINANCIAL_FUTURES:
        try:
            record=get_cftc_financial_positioning(symbol)
            if record:records.append(record)
        except Exception as ex:
            errors.append('CFTC financial futures unavailable: '+type(ex).__name__)
    # Binance reports crypto only; no implication this represents OTC FX, CFD or futures outside Binance.
    crypto={'BTCUSDT','ETHUSDT','SOLUSDT','XRPUSDT','BNBUSDT','DOGEUSDT','ADAUSDT','AVAXUSDT','DOTUSDT','LINKUSDT','LTCUSDT','BCHUSDT','TRXUSDT','NEARUSDT','UNIUSDT','APTUSDT','SUIUSDT','ATOMUSDT','ETCUSDT','XLMUSDT','FILUSDT','ARBUSDT','OPUSDT','AAVEUSDT'}
    if symbol in crypto:
        try:
            url='https://fapi.binance.com/futures/data/globalLongShortAccountRatio?'+urlencode({'symbol':symbol,'period':'5m','limit':1})
            data=json.loads(i.fetch(url,ttl=180))
            if not isinstance(data,list) or not data:raise ValueError('No ratios available')
            rec=normalize_binance(data[-1],symbol);rec['retrieved_at']=datetime.now(timezone.utc).isoformat();records.append(rec)
        except Exception as ex:errors.append('Binance unavailable: '+type(ex).__name__)
    return {'symbol':symbol,'records':records,'errors':errors,'sources':SOURCES,
       'status':'ok' if records else 'not_available',
       'notice':'Sources cover different participant populations. Never add their counts or treat opinion polls as executed positions.'}
