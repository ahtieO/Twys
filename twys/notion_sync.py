"""Opt-in Notion API synchronization. Stable page IDs; missing is never zero.

The integration retains original page properties and uses no unofficial scraping.
"""
from __future__ import annotations
import json, hashlib, re, threading, time, ipaddress, socket, shutil, io
from datetime import datetime,timezone
from urllib.request import Request,urlopen
from urllib.parse import urlparse
from urllib.error import HTTPError
from . import engine as e, integrations as cfg, marketplace

_VERSION='2026-03-11'
_RUN_LOCK=threading.Lock()
_THREAD=None
_STOP=threading.Event()
_LAST_DEEP_REFRESH=0.0

def request_json(path, payload=None):
    token=cfg.secret('NOTION_TOKEN')
    if not token:raise ValueError('Connect a Notion integration token in Connections first.')
    url='https://api.notion.com/v1/'+path.lstrip('/')
    if not re.fullmatch(r'https://api\.notion\.com/v1/[A-Za-z0-9/_?%=&.\-]+',url):raise ValueError('Invalid Notion endpoint')
    raw=None if payload is None else json.dumps(payload).encode('utf-8')
    request=Request(url,data=raw,headers={'Authorization':'Bearer '+token,'Notion-Version':_VERSION,
        'Content-Type':'application/json','User-Agent':'TWYS Terminal/2'},method='POST' if raw is not None else 'GET')
    try:
        with urlopen(request,timeout=16) as r:data=r.read(8_000_001)
    except HTTPError as err:
        try:detail=json.load(err).get('message','')
        except Exception:detail=''
        raise ValueError('Notion API '+str(err.code)+': '+detail[:200]) from err
    if len(data)>8_000_000:raise ValueError('Notion response too large')
    return json.loads(data)

def search_sources():
    """List data sources explicitly shared with this Notion integration."""
    cursor=None;results=[]
    for _ in range(10):
        body={'filter':{'property':'object','value':'data_source'},'page_size':100}
        if cursor:body['start_cursor']=cursor
        obj=request_json('search',body)
        results.extend([{'id':x['id'],'name':''.join(v.get('plain_text','') for v in x.get('title',[])) or 'Untitled data source'}
              for x in obj.get('results',[]) if x.get('object')=='data_source'])
        if not obj.get('has_more'):break
        cursor=obj.get('next_cursor')
        if not cursor:break
    return results

def value(p):
    typ=p.get('type','')
    if typ in ('title','rich_text'):
        return ''.join(i.get('plain_text') or i.get('text',{}).get('content','') for i in p.get(typ,[]))
    if typ in ('select','status'):return (p.get(typ) or {}).get('name')
    if typ=='multi_select':return ', '.join(v.get('name','') for v in p.get(typ,[]))
    if typ=='date':return (p.get('date') or {}).get('start')
    if typ=='number':return p.get('number')
    if typ=='checkbox':return p.get('checkbox')
    if typ=='url':return p.get('url')
    if typ=='formula':return value({'type':(p.get('formula') or {}).get('type'),**(p.get('formula') or {})})
    if typ=='files':return [{'name':v.get('name') or 'file','url':(v.get('file') or v.get('external') or {}).get('url'),'expiry_time':(v.get('file') or {}).get('expiry_time')} for v in p.get('files',[])]
    if typ=='unique_id':return (p.get('unique_id') or {}).get('number')
    if typ=='relation':return [v.get('id') for v in p.get('relation',[])]
    return p.get(typ)

def pick(row,*aliases):
    indexed={re.sub(r'[^a-z0-9]','',k.lower()):v for k,v in row.items()}
    for name in aliases:
        key=re.sub(r'[^a-z0-9]','',name.lower())
        if key in indexed and indexed[key] is not None:return indexed[key]
    return None

def normalize_page(page,source_id):
    props={name:value(prop) for name,prop in page.get('properties',{}).items()}
    def s(*names):
        val=pick(props,*names)
        return (', '.join(str(x) for x in val) if isinstance(val,list) else str(val).strip()) if val is not None else ''
    uid=hashlib.sha256(('notion_api|'+page['id']).encode()).hexdigest()[:20]
    date_raw=s('Date','DATE','Trade Date','Entry Date')
    parsed=date_raw
    if date_raw:
        try:parsed=datetime.fromisoformat(date_raw.replace('Z','+00:00')).isoformat() if 'T' in date_raw else datetime.fromisoformat(date_raw).date().isoformat()
        except ValueError:parsed=None
    instrument=e.standard_instrument(s('Instrument','PAIR','Symbol','Ticker','Asset'))
    r, reported_flags=e.validate_reported_r(s('Result RR','Realized R','Realised R','R multiple','R'))
    planned=e.num(s('Planned RR','Planned R','Target RR','RR'))
    direction=s('Direction','Type','Side').upper() or None
    entry=e.num(s('Entry','Entry Price'))
    stop=e.num(s('Stoploss','Stop Loss','SL','Stop Price'))
    exit_=e.num(s('EXIT','Exit Price','Close Price'))
    net=e.num(s('NET','Net P&L','P&L'))
    outcome_label=s('RESULT','Outcome','Win/Loss')
    flags=list(reported_flags)
    if r is None and entry is not None and stop is not None and exit_ is not None:
        r,basis,warnings=e.derive_legacy_r(entry,stop,exit_,direction,net,outcome_label)
        flags.extend(warnings)
    else:basis='notion_reported' if r is not None else 'unavailable'
    if r is not None: outcome='win' if r>0 else 'loss' if r<0 else 'breakeven';outcome_basis='realized_r'
    elif outcome_label.upper() in ('TP','WIN','W'):outcome='win';outcome_basis='recorded_result'
    elif outcome_label.upper() in ('SL','LOSS','L'):outcome='loss';outcome_basis='recorded_result'
    elif outcome_label.upper() in ('B/E','BE','BREAK EVEN','BREAKEVEN'):outcome='breakeven';outcome_basis='recorded_result'
    else:outcome=None;outcome_basis='unavailable'
    if not parsed:flags.append('date_missing_or_unparsed')
    raw_files=pick(props,'Images','Trade Image','Screenshots','Chart','Attachments')
    images=[]
    if isinstance(raw_files,list):
        images=[{'name':v.get('name','Image'),'file':None,'url':v.get('url'),'expiry_time':v.get('expiry_time')} for v in raw_files if isinstance(v,dict)]
    elif raw_files:images=[{'name':str(raw_files)[:100],'file':None}]
    # Notion-signed file URLs may expire; original reference stays in source page JSON.
    return dict(uid=uid,source='notion_api:'+source_id[:8],source_row=None,date_raw=date_raw,
        traded_at=parsed,instrument=instrument,direction=direction,session=s('Session').upper() or None,
        timeframe=s('Time Frame','T/F','Timeframe') or None,outcome=outcome,outcome_basis=outcome_basis,
        realized_r=r,r_basis=basis,planned_r=planned,net_pnl=net,lots=e.num(s('LOTS','Lot Size')),
        entry_price=entry,stop_price=stop,exit_price=exit_,rating=s('Rating','RATING') or None,
        rules_followed=s('Rules Followed','Rules Followed?').upper() or None,
        emotion=s('Emotion','EMOTIONS') or None,mistake=s('Mistake','Mistakes') or None,
        reasoning=s('Setup + Reasoning','REASONING','Reasoning','Setup','Notes'),
        review=s('Post Trade Review','Review','Trade Review') or None,
        markdown='',images=json.dumps(images),flags=json.dumps(flags),record_type='trade',
        original_json=json.dumps({'notion_page_id':page['id'],'url':page.get('url'),
           'last_edited_time':page.get('last_edited_time'),'properties':props},ensure_ascii=False),
        imported_at=datetime.now(timezone.utc).isoformat())

def _safe_image_url(url):
    try:
        parsed=urlparse(url)
        host=(parsed.hostname or '').lower()
        if parsed.scheme!='https' or parsed.port not in (None,443) or parsed.username or parsed.password:return False
        # Notion-hosted file URLs use signed S3/Cloudfront addresses.
        permitted=('amazonaws.com','notion-static.com','notion.so','cloudfront.net','notionusercontent.com')
        return any(host==domain or host.endswith('.'+domain) for domain in permitted)
    except (ValueError,TypeError):return False

def cache_image(trade_uid,index,item,refresh=None):
    """Download only known Notion-hosted HTTPS images; validate actual image bytes.

    Returns the local filename or None. A failed image never breaks journal sync.
    """
    from PIL import Image,UnidentifiedImageError
    url=item.get('url') or ''
    if not _safe_image_url(url):return None
    existing=item.get('file')
    if existing and not refresh and (e.MEDIA/existing).is_file():return existing
    req=Request(url,headers={'User-Agent':'TWYS/2.3'},method='GET')
    try:
        with urlopen(req,timeout=9) as response:
            # Explicit size cap; ignore a misleading Content-Length.
            if int(response.headers.get('Content-Length') or 0)>12_000_000:return None
            mime=response.headers.get('Content-Type','').split(';')[0].lower()
            if mime not in ('image/png','image/jpeg','image/webp','image/gif','application/octet-stream'):return None
            content=response.read(12_000_001)
        if len(content)>12_000_000:return None
        with Image.open(io.BytesIO(content)) as im:
            if im.width*im.height>80_000_000 or im.format not in ('PNG','JPEG','WEBP','GIF'):return None
            ext={'PNG':'.png','JPEG':'.jpg','WEBP':'.webp','GIF':'.gif'}[im.format]
            im.verify()
        e.MEDIA.mkdir(parents=True,exist_ok=True)
        # Content-addressed by image identity, not just row/index. Replacing a Notion
        # screenshot at the same index must never reuse its prior cached bytes.
        canonical=urlparse(url)._replace(query='',fragment='').geturl()
        filename='notion_'+hashlib.sha256((trade_uid+':'+str(index)+':'+canonical).encode()).hexdigest()[:24]+ext
        (e.MEDIA/filename).write_bytes(content)
        return filename
    except Exception:return None

def fetch_page_images(page):
    """Add images from page body, not just the Images database property."""
    result=[];cursor=None
    try:
        for _ in range(3):
            endpoint='blocks/'+page['id']+'/children?page_size=100'
            if cursor:endpoint+='&start_cursor='+cursor
            data=request_json(endpoint)
            for block in data.get('results',[]):
                if block.get('type') not in ('image','file'):continue
                kind=block['type'];obj=block.get(kind) or {}
                detail=obj.get('file') or obj.get('external') or {}
                if detail.get('url'):
                    result.append({'name':obj.get('caption',[{}])[0].get('plain_text','') if obj.get('caption') else 'Notion chart',
                      'url':detail['url'],'expiry_time':detail.get('expiry_time'),'file':None})
            if not data.get('has_more'):break
            cursor=data.get('next_cursor')
            if not cursor:break
    except Exception:pass
    return result

def cache_page_images(item,page,previous=None,refresh=False):
    """Keep unchanged image bytes locally even when a text property was edited."""
    imgs=json.loads(item['images'])
    imgs.extend(fetch_page_images(page))
    seen=set(); unique=[]
    for x in imgs:
        key=x.get('url') or x.get('name')
        if key in seen:continue
        seen.add(key);unique.append(x)
    prior={}
    try:
        for old in json.loads(previous or '[]'):
            if not isinstance(old,dict):continue
            url=(old.get('url') or '')
            canonical=urlparse(url)._replace(query='',fragment='').geturl()
            if canonical and old.get('file') and (e.MEDIA/old['file']).is_file():prior[canonical]=old['file']
    except (TypeError,ValueError):pass
    for ix,x in enumerate(unique[:30]):
        canonical=urlparse(x.get('url') or '')._replace(query='',fragment='').geturl()
        if not refresh and canonical in prior:x['file']=prior[canonical]
        x['file']=cache_image(item['uid'],ix,x,refresh=refresh)
    item['images']=json.dumps(unique,ensure_ascii=False)
    return item

def _image_sources(serialized):
    try: items=json.loads(serialized or '[]')
    except (ValueError,TypeError):return []
    return [(x.get('name'),urlparse(x.get('url') or '')._replace(query='',fragment='').geturl())
            for x in items if isinstance(x,dict)]

def sync(data_source_id=None, force=False):
    with _RUN_LOCK:
        source=(data_source_id or cfg.config().get('notion_database_id') or '').strip()
        if not re.fullmatch(r'[A-Fa-f0-9-]{32,36}',source):raise ValueError('Select a valid Notion data source ID')
        marketplace.init(); rows=[];cursor=None
        try:
            for _ in range(100):
                body={'page_size':100}
                if cursor:body['start_cursor']=cursor
                page=request_json('data_sources/'+source+'/query',body)
                rows.extend(x for x in page.get('results',[]) if x.get('object')=='page' and not x.get('in_trash'))
                if not page.get('has_more'):break
                cursor=page.get('next_cursor')
                if not cursor:break
            else:raise ValueError('Notion query exceeded 10,000-page cap; use a narrower database')
            added=updated=unchanged=0
            removed=0
            c=e.connection()
            try:
                for page in rows:
                    pid=page['id'];rev=page.get('last_edited_time')
                    prev=c.execute('SELECT last_edited,original_json FROM notion_records WHERE page_id=?',(pid,)).fetchone()
                    if prev and prev['last_edited']==rev and not force:unchanged+=1;continue
                    item=normalize_page(page,source)
                    if c.execute('SELECT 1 FROM permanently_deleted_trades WHERE uid=?',(item['uid'],)).fetchone():
                        # Deliberate permanent local deletion: preserve the tombstone
                        # rather than recreating private trade data on future syncs.
                        unchanged+=1
                        continue
                    previous_trade=c.execute('SELECT images FROM trades WHERE uid=?',(item['uid'],)).fetchone() if prev else None
                    if item['traded_at']:
                        item=cache_page_images(item,page,previous_trade['images'] if previous_trade else None,refresh=force)
                    if not item['traded_at']:
                        # Preserve source page without incorrectly counting a blank template as a trade.
                        c.execute('INSERT INTO notion_records VALUES(?,?,?,?,?) ON CONFLICT(page_id) DO UPDATE SET last_edited=excluded.last_edited,original_json=excluded.original_json,imported_at=excluded.imported_at',
                         (pid,source,rev,item['original_json'],datetime.now(timezone.utc).isoformat()))
                        unchanged+=1;continue
                    keys=list(item)
                    c.execute('INSERT INTO trades('+','.join(keys)+') VALUES('+','.join('?' for _ in keys)+') ON CONFLICT(uid) DO UPDATE SET '+','.join(k+'=excluded.'+k for k in keys if k!='uid'),list(item.values()))
                    c.execute('INSERT INTO notion_records VALUES(?,?,?,?,?) ON CONFLICT(page_id) DO UPDATE SET last_edited=excluded.last_edited,original_json=excluded.original_json,imported_at=excluded.imported_at',
                     (pid,source,rev,item['original_json'],datetime.now(timezone.utc).isoformat()))
                    if prev:
                        original_changed=prev['original_json']!=item['original_json']
                        images_changed=bool(previous_trade and _image_sources(previous_trade['images']) != _image_sources(item['images']))
                        if original_changed or images_changed:updated+=1
                        else:unchanged+=1
                    else:added+=1
                # Full successful pagination is required before reconciling missing pages.
                # Two consecutive missing syncs are required to hide a Notion page.
                present={page['id'] for page in rows}
                c.execute('''CREATE TABLE IF NOT EXISTS notion_missing (page_id TEXT PRIMARY KEY, miss_count INTEGER NOT NULL DEFAULT 0)''')
                existing=c.execute('SELECT page_id FROM notion_records WHERE source_id=?',(source,)).fetchall()
                for rec in existing:
                    pid=rec['page_id']
                    if pid in present:
                        c.execute('DELETE FROM notion_missing WHERE page_id=?',(pid,))
                        # A trade that reappears in Notion may be reactivated, but never
                        # override an explicit user choice to hide it locally.
                        restored_uid=hashlib.sha256(('notion_api|'+pid).encode()).hexdigest()[:20]
                        c.execute('DELETE FROM local_hidden_trades WHERE uid=? AND reason=?',
                                  (restored_uid,'notion_no_longer_in_source'))
                        continue
                    c.execute('INSERT INTO notion_missing(page_id,miss_count) VALUES(?,1) ON CONFLICT(page_id) DO UPDATE SET miss_count=miss_count+1',(pid,))
                    miss=c.execute('SELECT miss_count FROM notion_missing WHERE page_id=?',(pid,)).fetchone()[0]
                    if miss==2:
                        uid=hashlib.sha256(('notion_api|'+pid).encode()).hexdigest()[:20]
                        c.execute("INSERT OR IGNORE INTO local_hidden_trades(uid,removed_at,reason) VALUES(?,?,?)",(uid,datetime.now(timezone.utc).isoformat(),'notion_no_longer_in_source'))
                        removed+=1
                report={'added':added,'updated':updated,'unchanged':unchanged,'removed':removed,'pages_seen':len(rows),'source_id':source,'status':'ok'}
                c.execute('INSERT INTO notion_sync_runs(at,status,records,message) VALUES(?,?,?,?)',(datetime.now(timezone.utc).isoformat(),'ok',len(rows),json.dumps(report)))
                c.commit()
            finally:c.close()
            if added or updated or removed:marketplace.reindex()
            return report
        except Exception as err:
            c=e.connection()
            try:
                c.execute('INSERT INTO notion_sync_runs(at,status,records,message) VALUES(?,?,?,?)',
                    (datetime.now(timezone.utc).isoformat(),'error',0,str(err)[:200]));c.commit()
            finally:c.close()
            raise

def sync_selected(force=False):
    sources=cfg.config().get('notion_data_sources') or []
    if not sources:
        old=cfg.config().get('notion_database_id')
        sources=[old] if old else []
    if not sources:raise ValueError('Select at least one Notion data source')
    results=[]
    for source in sources:
        try:results.append(sync(source,force=force))
        except Exception as exc:results.append({'source_id':source,'status':'error','message':str(exc)[:220]})
    return {'sources':results,'added':sum(r.get('added',0) for r in results),
        'updated':sum(r.get('updated',0) for r in results),
        'removed':sum(r.get('removed',0) for r in results),
        'errors':sum(r.get('status')!='ok' for r in results)}

def status():
    marketplace.init();c=e.connection()
    try:row=c.execute('SELECT * FROM notion_sync_runs ORDER BY id DESC LIMIT 1').fetchone()
    finally:c.close()
    sources=cfg.config().get('notion_data_sources') or []
    return {'configured':bool(cfg.secret('NOTION_TOKEN') and sources),
        'data_sources':sources,'last_run':dict(row) if row else None,
        'interval_seconds':cfg.config().get('notion_sync_interval',90),
        'connection_mode':'Notion API token; selected shared data sources',
        'note':'The Notion desktop app is not required. The integration only sees databases shared with it.'}

def auto_sync_loop():
    global _LAST_DEEP_REFRESH
    while not _STOP.is_set():
        if cfg.secret('NOTION_TOKEN') and cfg.config().get('notion_data_sources'):
            try:
                # Periodically refresh body blocks, not only properties. Notion block
                # images can change without an observable property revision.
                deep=time.monotonic()-_LAST_DEEP_REFRESH>900
                report=sync_selected(force=deep)
                if deep and not report.get('errors'):_LAST_DEEP_REFRESH=time.monotonic()
            except Exception:pass
        _STOP.wait(int(cfg.config().get('notion_sync_interval',90)))

def start_background():
    global _THREAD, _LAST_DEEP_REFRESH
    if _THREAD is None or not _THREAD.is_alive():
        # A full image-body scan at startup blocked manual sync for minutes.
        # Start with a quick revision-based pass, deep-check later.
        _LAST_DEEP_REFRESH=time.monotonic()
        _STOP.clear(); _THREAD=threading.Thread(target=auto_sync_loop,daemon=True,name='TWYS-Notion-Sync');_THREAD.start()

def stop_background():_STOP.set()
