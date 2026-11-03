"""TWYS connected data sources. Everything is opt-in; no fabricated live data."""
from __future__ import annotations
import os, json, re, time, hashlib, threading, platform, xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from email.utils import parsedate_to_datetime
from . import engine as e
from . import ff_calendar_html as ff_html

CONFIG=e.DATA/'integrations.json'
_LOCK=threading.RLock()
_CACHE={}
PUBLIC_FEEDS={
 'Federal Reserve · Monetary Policy':'https://www.federalreserve.gov/feeds/press_monetary.xml',
 'Federal Reserve · Press':'https://www.federalreserve.gov/feeds/press_all.xml',
 'ECB · Press Releases':'https://www.ecb.europa.eu/rss/press.html',
 'Bank of England · News':'https://www.bankofengland.co.uk/rss/news',
}
# These are TWYS heuristics, NOT official severity classifications.
HIGH=re.compile(r'\b(cpi|inflation|consumer price|nonfarm|payroll|employment situation|unemployment rate|gdp|gross domestic product|interest rate|fomc|federal funds|monetary policy|pce price|central bank decision)\b',re.I)
MED=re.compile(r'\b(retail sales|pmi|producer price|ppi|jobless claims|durable goods|industrial production|consumer confidence|housing starts|manufacturing)\b',re.I)
SUPPORTED_INTERVALS={'1min','5min','15min','30min','1h','4h','1day','1week'}

def config():
    try:
        value=json.loads(CONFIG.read_text('utf-8'))
        return value if isinstance(value,dict) else {}
    except (FileNotFoundError,ValueError):return {}

def save_config(updates):
    permitted={'price_provider','symbol','interval','calendar_provider','news_sources','notion_database_id','notion_sync_interval','notion_data_sources','twelve_symbols','ai_provider','ai_model','ai_endpoint'}
    d=config()
    for k,v in updates.items():
        if k not in permitted:continue
        if k in ('symbol','notion_database_id') and len(str(v))>100:raise ValueError('Invalid setting')
        if k=='interval' and v not in SUPPORTED_INTERVALS:raise ValueError('Unsupported interval')
        if k=='price_provider' and v not in ('off','twelve_data','mt5'):raise ValueError('Unknown market provider')
        if k=='calendar_provider' and v not in ('off','forexfactory','financecalendar','fred','fmp'):raise ValueError('Unknown calendar provider')
        if k=='notion_sync_interval':v=max(60,min(3600,int(v)))
        if k=='notion_data_sources':
            if not isinstance(v,list) or len(v)>30:raise ValueError('Select up to 30 Notion sources')
            if any(not re.fullmatch(r'[a-fA-F0-9-]{32,36}',str(x)) for x in v):raise ValueError('Invalid Notion source ID')
            v=list(dict.fromkeys(v))
        if k=='ai_provider' and v not in ('off','ollama','openai','compatible'):raise ValueError('Unknown AI provider')
        if k=='ai_model' and (not isinstance(v,str) or len(v)>120):raise ValueError('Invalid model name')
        if k=='ai_endpoint':
            from urllib.parse import urlparse
            u=urlparse(str(v))
            if v and (u.scheme!='https' and not (u.scheme=='http' and u.hostname in ('localhost','127.0.0.1','::1'))):
                raise ValueError('AI endpoint requires HTTPS, except for localhost')
            if len(str(v))>300:raise ValueError('Invalid AI endpoint')
        d[k]=v
    CONFIG.parent.mkdir(exist_ok=True,parents=True)
    with _LOCK:CONFIG.write_text(json.dumps(d,indent=2),encoding='utf-8')
    return d

def secret(name):
    if os.getenv('TWYS_'+name):return os.getenv('TWYS_'+name)
    try:
        import keyring
        return keyring.get_password('TWYS Terminal',name)
    except Exception:return None

def save_secret(name,value):
    if name not in ('TWELVE_DATA_KEY','FMP_KEY','FRED_KEY','NOTION_TOKEN','MYFXBOOK_SESSION','OPENAI_API_KEY','COMPATIBLE_API_KEY'):raise ValueError('Invalid key name')
    try:
        import keyring
        if value:keyring.set_password('TWYS Terminal',name,value)
        else:
            try:keyring.delete_password('TWYS Terminal',name)
            except Exception:pass
    except Exception as ex:raise ValueError('Secure credential storage unavailable. Install keyring or use TWYS_'+name+' environment variable.') from ex

def fetch(url,ttl=120):
    """Fixed provider URLs only, not user-provided arbitrary URLs."""
    with _LOCK:
        saved=_CACHE.get(url)
        if saved and time.monotonic()-saved[0]<ttl:return saved[1]
    req=Request(url,headers={'User-Agent':'TWYS Terminal/2.0 (personal market research)','Accept':'application/json,application/xml,application/rss+xml, text/xml'})
    with urlopen(req,timeout=8) as r:
        blob=r.read(2_500_001)
        if len(blob)>2_500_000:raise ValueError('Provider payload exceeds limit')
    with _LOCK:_CACHE[url]=(time.monotonic(),blob)
    return blob

def impact(label):
    s=str(label or '').lower()
    if 'high' in s:return 'high'
    if 'med' in s:return 'medium'
    if 'low' in s:return 'low'
    return 'unrated'

def twys_impact(event):
    if HIGH.search(event):return 'high'
    if MED.search(event):return 'medium'
    return 'unrated'

def _iso_any(s):
    if not s:return None
    try:return datetime.fromisoformat(str(s).replace('Z','+00:00')).isoformat()
    except ValueError:return str(s)

def _matching_actuals(base_events, reported_events):
    """Enrich only exact event+currency+release-date matches from a second source.

    Do not silently match semantically different CPI measures or months.
    """
    import re
    def key(r):
        name=re.sub(r'[^a-z0-9]+','',str(r.get('event') or '').lower())
        day=str(r.get('datetime') or '')[:10]
        return (str(r.get('currency') or '').upper(),day,name)
    indexed={}
    for r in reported_events:
        if r.get('actual') is not None and str(r.get('actual')).strip()!='':
            indexed.setdefault(key(r),[]).append(r)
    for r in base_events:
        if r.get('actual') is not None:continue
        matches=indexed.get(key(r),[])
        if len(matches)==1:
            r['actual']=matches[0]['actual']
            r['actual_source']=matches[0].get('source')
            r['actual_source_url']=matches[0].get('source_url')
    return base_events

def _us_agency_calendar(start, end):
    """Limited no-key fallback with actual US release figures from agency schedules.

    This source has no consensus forecast and cannot replace worldwide FF data.
    Every record retains separate provenance.
    """
    url='https://xoomar.com/api/markets/calendar?'+urlencode({'from':start,'to':end})
    obj=json.loads(fetch(url,ttl=600))
    rows=obj.get('data',[]) if isinstance(obj,dict) else []
    if not isinstance(rows,list):raise ValueError('US agency calendar returned invalid data')
    events=[]
    for r in rows:
        if not isinstance(r,dict):continue
        dt=str(r.get('scheduledAt') or '')
        name=str(r.get('eventName') or '').strip()
        if not dt or not name:continue
        actual=r.get('actual')
        unit=str(r.get('unit') or '').strip()
        # Preserve source units, never invent a percent or convert values when
        # the provider has not declared a unit.
        events.append({'id':'xoomar:'+str(r.get('eventId') or dt+name),
            'datetime':_iso_any(dt),'currency':'USD','country':'United States',
            'event':name,'impact':impact(r.get('importance')),
            'impact_basis':'US calendar provider','actual':actual,
            'actual_status':'released' if actual is not None else 'not_reported',
            'forecast':r.get('forecast'),'previous':r.get('previous'),
            'unit':unit,'source':'XOOMAR / US official agencies',
            'source_url':'https://xoomar.com/economic-calendar-api',
            'time_precision':'timestamp'})
    return {'provider':'XOOMAR / US official agencies','events':events,
            'status':'limited_us_only','fetched_at':datetime.now(timezone.utc).isoformat(),
            'message':'US agency events only. The source does not provide consensus forecasts. Other countries are not covered.'}


def _forexfactory_web_calendar(start, end, refresh=False):
    """Read published outcomes directly from the public weekly calendar page.

    JSON exports do not include Actual. Archive successful weekly page parses to
    preserve released results through transient outages. Never use cached
    results as if they were live.
    """
    first=datetime.fromisoformat(start).date()
    last=datetime.fromisoformat(end).date()
    weeks=[]
    day=first-timedelta(days=(first.weekday()+1)%7)
    # Weekly News UI requests seven days. Bound network access in case another
    # client requests many dates, without silently implying full range coverage.
    while day<=last and len(weeks)<15:
        weeks.append(day)
        day+=timedelta(days=7)
    cache_dir=e.DATA/'calendar_cache'
    cache_dir.mkdir(exist_ok=True,parents=True)
    all_events=[]; source_states=[]
    today=datetime.now().astimezone().date()
    for week in weeks:
        cached=cache_dir/('forexfactory_web_'+week.isoformat()+'.json')
        page=ff_html.page_url(week)
        # Revalidate active week's released actuals frequently, previous weeks
        # daily (to capture revisions), and future scheduled dates hourly.
        ttl=120 if week<=today<=week+timedelta(days=6) else (86400 if week<today else 3600)
        key='ffhtml:'+page
        try:
            with _LOCK:
                saved=_CACHE.get(key)
                raw=saved[1] if (not refresh and saved and time.monotonic()-saved[0]<ttl) else None
            if raw is None:
                raw=ff_html.download_week(week)
                with _LOCK:_CACHE[key]=(time.monotonic(),raw)
            rows=ff_html.parse_week(raw,week)
            cached.write_text(json.dumps({'events':rows,'fetched_at':datetime.now(timezone.utc).isoformat()},ensure_ascii=False),encoding='utf-8')
            source_states.append('live')
        except Exception as ex:
            if not cached.is_file():
                raise ValueError('Forex Factory webpage unavailable for '+week.isoformat()+': '+str(ex)) from ex
            data=json.loads(cached.read_text(encoding='utf-8'))
            rows=data.get('events') or []
            source_states.append('cached')
        all_events.extend(rows)
    filtered=[]
    for event in all_events:
        try:
            if first<=ff_html.event_local_date(event)<=last:
                filtered.append(event)
        except (ValueError, TypeError, KeyError):
            continue
    return {'provider':'Forex Factory webpage','events':filtered[:1000],
            'status':'stale_cache' if 'cached' in source_states else 'ok',
            'fetched_at':datetime.now(timezone.utc).isoformat(),
            'message':('Showing saved results because Forex Factory is currently unreachable. They may be stale.'
                       if 'cached' in source_states else
                       'Published Actual figures are read from the calendar webpage. A missing Actual means the source has not reported one.')}


def get_calendar(start=None,end=None,provider_override=None,refresh=False):
    settings=config(); provider=provider_override or settings.get('calendar_provider') or 'forexfactory'
    # Legacy installs saved calendar_provider='off' even though the product now
    # ships with a public weekly economic-calendar source by default.
    if provider=='off':provider='forexfactory' 
    now=datetime.now(timezone.utc)
    start=start or now.date().isoformat();end=end or (now+timedelta(days=7)).date().isoformat()
    try:
        d0=datetime.fromisoformat(start).date();d1=datetime.fromisoformat(end).date()
        if (d1-d0).days<0 or (d1-d0).days>90:raise ValueError('Calendar range must be 0–90 days')
        if provider=='forexfactory':
            # The public calendar webpage, unlike the weekly JSON export,
            # contains the published Actual column and supports week navigation.
            # Do not treat a blocked/changed webpage as a successful empty feed.
            page_error=None
            try:
                webpage=_forexfactory_web_calendar(start,end,refresh=refresh)
                if webpage['events']:
                    return webpage
                page_error='Webpage contained no events for the requested range'
            except Exception as ex:
                page_error=str(ex)[:160]
            # Official Forex Factory weekly export, not an HTML scraper.
            # The public export only covers the current week; for other weeks use
            # the user-selected alternate provider rather than fabricating rows.
            today=datetime.now().astimezone().date()
            this_sunday=today-timedelta(days=(today.weekday()+1)%7)
            request_week=d0-timedelta(days=(d0.weekday()+1)%7)
            delta=(request_week-this_sunday).days//7
            # Official FF public JSON publishes *this week only*. Previous/next
            # export URLs return 404, and the JSON has no 'actual' field. Never
            # request the nonexistent variants or imply they can provide results.
            cache_dir=e.DATA/'calendar_cache'
            week_file=cache_dir/(request_week.isoformat()+'.json')
            if delta!=0:
                alternative=get_calendar(start,end,provider_override='financecalendar')
                if alternative.get('status')=='ok' and alternative.get('events'):
                    alternative['message']='Past/future dates from Finance Calendar (not the Forex Factory weekly export). Actual values only where published.'
                    return alternative
                if week_file.is_file():
                    cached_obj=json.loads(week_file.read_text(encoding='utf-8'))
                    raw=cached_obj.get('events',[])
                    cached=True
                else:
                    try:
                        backup=_us_agency_calendar(start,end)
                        if backup['events']:
                            backup['message']='Forex Factory webpage unavailable. Showing limited US official-agency releases with actuals when published.'
                            return backup
                    except Exception:pass
                    return {'provider':'Finance Calendar','events':[], 'status':alternative.get('status','unavailable'),
                        'message':'Forex Factory publishes a current-week JSON export only. No date-range data was returned by the alternate source. '+str(alternative.get('message') or '')[:130]}
            else:
                url='https://nfs.faireconomy.media/ff_calendar_thisweek.json'
                # The export is rate limited and refreshed only hourly.
                cached=False
                try:
                    raw=json.loads(fetch(url,ttl=3600))
                    if not isinstance(raw,list):raise ValueError('Unexpected Forex Factory JSON')
                    cache_dir.mkdir(parents=True,exist_ok=True)
                    week_file.write_text(json.dumps({'fetched_at':now.isoformat(),
                        'week':request_week.isoformat(),'events':raw},ensure_ascii=False),encoding='utf-8')
                except Exception:
                    if week_file.is_file():
                        raw=json.loads(week_file.read_text(encoding='utf-8')).get('events',[])
                        cached=True
                    else:
                        alternate=get_calendar(start,end,provider_override='financecalendar')
                        if alternate.get('events'):
                            alternate['message']='Forex Factory temporarily unreachable. Showing the date-range-capable Finance Calendar source with its own coverage.'
                            return alternate
                        raise
            if not isinstance(raw,list):raise ValueError('Forex Factory export did not return a list')
            events=[]
            for ix,r in enumerate(raw):
                if not isinstance(r,dict):continue
                dt=r.get('date')
                if not dt:continue
                name=str(r.get('title') or '').strip()
                if not name:continue
                currency=str(r.get('country') or 'All').upper()
                events.append({'id':str(ix)+'_'+str(dt), 'datetime':_iso_any(dt),
                    'country':currency,'currency':currency,'event':name,
                    'impact':impact(r.get('impact')),'impact_basis':'Forex Factory export',
                    'actual':r.get('actual'),'forecast':r.get('forecast'),
                    'previous':r.get('previous'),'source':'Forex Factory weekly export',
                    'source_url':'https://www.forexfactory.com/calendar', 'time_precision':'timestamp'})
        elif provider=='financecalendar':
            url='https://www.financecalendar.com/wp-json/fc/v1/calendar?'+urlencode({'from':start,'to':end,'limit':500})
            raw=json.loads(fetch(url,ttl=900))
            source_rows=raw if isinstance(raw,list) else raw.get('events',[]) if isinstance(raw,dict) else []
            events=[]
            for r in source_rows:
                if not isinstance(r,dict):continue
                name=str(r.get('title') or r.get('name') or r.get('event') or '').strip()
                if not name:continue
                dt=r.get('time_utc') or r.get('datetime') or r.get('date_utc') or r.get('date')
                if dt and (r.get('time_utc') or r.get('date_utc')) and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?',str(dt)):
                    dt=str(dt)+'+00:00'
                currency=r.get('currency') or r.get('country') or ''
                events.append({'id':str(r.get('id') or r.get('url') or (str(dt)+'_'+name)),
                   'datetime':_iso_any(dt), 'country':r.get('country'), 'currency':currency,
                   'event':name,'impact':impact(r.get('impact')),'impact_basis':'source classification',
                   'actual':r.get('actual'),'forecast':r.get('consensus') if r.get('consensus') is not None else r.get('forecast'),
                   'previous':r.get('prior') if r.get('prior') is not None else r.get('previous'),
                   'source':'Finance Calendar', 'source_url':r.get('url') if str(r.get('url') or '').startswith('https://') else 'https://www.financecalendar.com',
                   'time_precision':'all_day' if r.get('all_day') else ('date_only' if not (dt and 'T' in str(dt)) else 'timestamp')})
        elif provider=='fmp':
            key=secret('FMP_KEY')
            if not key:return {'provider':provider,'events':[],'status':'key_required'}
            url='https://financialmodelingprep.com/stable/economic-calendar?'+urlencode({'from':start,'to':end,'apikey':key})
            raw=json.loads(fetch(url,ttl=600))
            if isinstance(raw,dict):raise ValueError(raw.get('Error Message') or raw.get('message') or 'Provider returned no event list')
            events=[]
            for r in raw:
                name=r.get('event','')
                events.append({'id':str(r.get('date'))+'_'+str(name),'datetime':_iso_any(r.get('date')),'country':r.get('country'),'currency':r.get('currency'),
                    'event':name,'impact':impact(r.get('impact')),'impact_basis':'provider',
                    'actual':r.get('actual'),'forecast':r.get('estimate'),'previous':r.get('previous'),
                    'source':'FMP','source_url':'https://site.financialmodelingprep.com/developer/docs/stable/economics-calendar'})
        elif provider=='fred':
            key=secret('FRED_KEY')
            if not key:return {'provider':provider,'events':[],'status':'key_required'}
            url='https://api.stlouisfed.org/fred/releases/dates?'+urlencode({'api_key':key,'file_type':'json','realtime_start':start,'realtime_end':end,'include_release_dates_with_no_data':'true','limit':1000})
            raw=json.loads(fetch(url,ttl=1800));events=[]
            for r in raw.get('release_dates',[]):
                name=r.get('release_name','')
                events.append({'id':str(r.get('release_id'))+'_'+str(r.get('date')),'datetime':r.get('date'),
                    'country':'US','currency':'USD','event':name,'impact':twys_impact(name),'impact_basis':'TWYS keyword estimate' if twys_impact(name)!='unrated' else 'unrated',
                    'actual':None,'forecast':None,'previous':None,'source':'FRED','source_url':'https://fred.stlouisfed.org/releases/calendar',
                    'time_precision':'date_only'})
        # The FF weekly export does not carry actual results. Where another
        # provider reports a value for the exact same currency/date/event,
        # attach that independently verified value with its own attribution.
        if provider=='forexfactory' and events:
            secondary=get_calendar(start,end,provider_override='financecalendar')
            if secondary.get('status')=='ok':
                _matching_actuals(events,secondary.get('events',[]))
        if provider=='forexfactory' and events and any(r.get('actual') is None for r in events):
            # Only exact same-name/day matches are attached as Actual values;
            # mismatched series must never be paired by keyword guessing.
            try:
                us=_us_agency_calendar(start,end)
                _matching_actuals(events,us.get('events',[]))
            except Exception:pass
        # User-selected range applies even when a provider response contains extra days.
        events=[event for event in events if event.get('datetime') and start<=str(event['datetime'])[:10]<=end]
        return {'provider':provider,'events':events[:1000],'status':'stale_cache' if provider=='forexfactory' and cached else 'ok','fetched_at':now.isoformat(),
               'message':('Forex Factory webpage unavailable: '+str(page_error or 'unknown error')+'. Export-only fallback has no Actual figures.' if page_error else 'The Forex Factory export omits Actual; outcomes are unavailable unless another verified source provides them.') if provider=='forexfactory' else 'Times are converted to your computer timezone. Coverage differs by source; visit the source for release details.' if provider=='financecalendar' else 'FRED release dates do not include forecast/actual values or reliably precise release times.' if provider=='fred' else 'Times follow provider data; confirm timezone before interpreting release timing.'}
    except Exception as ex:return {'provider':provider,'events':[],'status':'error','message':str(ex)[:250]}

def _localname(tag):return tag.rsplit('}',1)[-1]

def rss_items(xml_bytes,source):
    root=ET.fromstring(xml_bytes);items=[]
    for el in root.iter():
        if _localname(el.tag) not in ('item','entry'):continue
        fields={}
        for child in el:
            name=_localname(child.tag)
            if name in ('title','link','pubDate','updated','published','description','summary'):
                fields[name]=child.attrib.get('href') or ''.join(child.itertext()).strip()
        title=fields.get('title','')
        if not title:continue
        dt=fields.get('pubDate') or fields.get('updated') or fields.get('published')
        try:dt=parsedate_to_datetime(dt).isoformat()
        except Exception:dt=_iso_any(dt)
        items.append({'title':title[:300],'url':fields.get('link',''),'published':dt,'source':source,
                      'impact':twys_impact(title),'impact_basis':'TWYS headline keyword estimate',
                      'summary':re.sub(r'<[^>]*>',' ',fields.get('description') or fields.get('summary') or '')[:350]})
    return items

def get_news():
    news=[];issues=[]
    def retrieve(name,url):
        return name,rss_items(fetch(url,ttl=300),name)[:35]
    # Avoid waiting for four serial provider timeouts when a feed is unavailable.
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs={pool.submit(retrieve,name,url):name for name,url in PUBLIC_FEEDS.items()}
        for job in as_completed(jobs):
            try:_,items=job.result();news.extend(items)
            except Exception as ex:issues.append(f'{jobs[job]}: {type(ex).__name__}')
    news.sort(key=lambda d:d.get('published') or '',reverse=True)
    return {'items':news[:100],'sources':list(PUBLIC_FEEDS),'warnings':issues,'status':'ok' if news else 'unavailable',
            'notice':'Original official agency headlines. TWYS severity is an unverified keyword category, not a prediction of price impact.'}

def installed_integrations():
    found=[]
    if platform.system()=='Windows':
        bases=[os.getenv('PROGRAMFILES',''),os.getenv('PROGRAMFILES(X86)',''),os.getenv('LOCALAPPDATA','')]
        for path in bases:
            if not path:continue
            for name,sub in [('MetaTrader 5','MetaTrader 5'),('MetaTrader 4','MetaTrader 4'),('Ollama','Programs/Ollama')]:
                if (Path(path)/sub).exists() and name not in found:found.append(name)
    try:
        import MetaTrader5
        if 'MetaTrader 5' not in found:found.append('MetaTrader 5 Python bridge')
    except ImportError:pass
    return found

def get_candles(symbol=None,interval=None,count=120):
    settings=config();provider=settings.get('price_provider','off')
    symbol=str(symbol or settings.get('symbol') or 'XAUUSD').strip().upper()
    interval=str(interval or settings.get('interval') or '5min').strip()
    count=min(500,max(20,int(count)))
    if not re.fullmatch(r'[A-Z0-9/.:_-]{2,35}',symbol):return {'status':'error','error':'Invalid symbol'}
    if interval not in SUPPORTED_INTERVALS:return {'status':'error','error':'Invalid interval'}
    if provider=='off':return {'status':'not_configured','provider':'off','symbol':symbol,'candles':[]}
    try:
        if provider=='twelve_data':
            key=secret('TWELVE_DATA_KEY')
            if not key:return {'status':'key_required','provider':provider,'symbol':symbol,'candles':[]}
            aliases={'XAUUSD':'XAU/USD','EURUSD':'EUR/USD','BTCUSD':'BTC/USD'}
            p_symbol=aliases.get(symbol,symbol)
            url='https://api.twelvedata.com/time_series?'+urlencode({'symbol':p_symbol,'interval':interval,'outputsize':count,'apikey':key})
            obj=json.loads(fetch(url,ttl=30))
            if obj.get('status')=='error':raise ValueError(obj.get('message','Provider error'))
            bars=[]
            for row in reversed(obj.get('values',[])):
                bars.append({'time':row.get('datetime'),'open':float(row['open']),'high':float(row['high']),
                             'low':float(row['low']),'close':float(row['close']),'volume':float(row['volume']) if row.get('volume') else None})
            if not bars:raise ValueError('Provider returned no candles for this symbol/interval')
            return {'status':'ok','provider':provider,'symbol':symbol,'provider_symbol':p_symbol,'interval':interval,'candles':bars,
                    'received_at':datetime.now(timezone.utc).isoformat(),'is_live':False,'latency_note':'Polled provider candles; realtime rights and delay depend on subscription. Latest candle may be incomplete.',
                    'timezone':obj.get('meta',{}).get('exchange_timezone')}
        if provider=='mt5':
            import MetaTrader5 as mt5
            if not mt5.initialize():raise ValueError('Cannot initialize installed MT5 terminal')
            try:
                named={'1min':mt5.TIMEFRAME_M1,'5min':mt5.TIMEFRAME_M5,'15min':mt5.TIMEFRAME_M15,'30min':mt5.TIMEFRAME_M30,
                       '1h':mt5.TIMEFRAME_H1,'4h':mt5.TIMEFRAME_H4,'1day':mt5.TIMEFRAME_D1,'1week':mt5.TIMEFRAME_W1}
                bars=mt5.copy_rates_from_pos(symbol,named[interval],0,count)
                if bars is None:raise ValueError('No MT5 candles. Check broker symbol and chart history')
                candles=[{'time':datetime.fromtimestamp(int(r['time']),timezone.utc).isoformat(),
                          **{field:float(r[field]) for field in ('open','high','low','close')},'volume':float(r['tick_volume'])} for r in bars]
            finally:mt5.shutdown()
            return {'status':'ok','provider':provider,'symbol':symbol,'interval':interval,'candles':candles,
                    'received_at':datetime.now(timezone.utc).isoformat(),'is_live':False,'latency_note':'Polled from local MT5 terminal; provider and connectivity determine freshness.'}
    except Exception as ex:return {'status':'error','provider':provider,'symbol':symbol,'candles':[],'error':str(ex)[:240]}
