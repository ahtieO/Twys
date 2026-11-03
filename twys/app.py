"""TWYS Trading Terminal. Local-first FastAPI service, no broker connectivity."""
from __future__ import annotations
import csv, io, json, os, tempfile, threading, webbrowser, hashlib, shutil
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.request import Request as URLRequest, urlopen
from urllib.parse import urlparse
from fastapi import FastAPI, Request, HTTPException, Query
from contextlib import asynccontextmanager
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from . import engine as e, integrations as cfg, ai
from .v2_routes import router as v2_router
from . import notion_sync, marketplace, profile

@asynccontextmanager
async def app_lifespan(app):
    marketplace.init()
    notion_sync.start_background()
    try:
        yield
    finally:
        notion_sync.stop_background()

app=FastAPI(title='TWYS | TRADE WHAT YOU SEE',docs_url=None,redoc_url=None,lifespan=app_lifespan)
app.include_router(v2_router)

@app.middleware('http')
async def restrict_external_origins(request:Request,call_next):
    origin=request.headers.get('origin','')
    if origin:
        from urllib.parse import urlparse
        u=urlparse(origin)
        if u.scheme!='http' or u.hostname not in ('localhost','127.0.0.1','::1'):
            return JSONResponse({'detail':'TWYS only accepts local desktop origins.'},status_code=403)
    return await call_next(request)


static=e.ROOT/'static'
app.mount('/static',StaticFiles(directory=str(static)),name='static')
e.MEDIA.mkdir(parents=True,exist_ok=True)
app.mount('/media',StaticFiles(directory=str(e.MEDIA)),name='media')

@app.get('/',response_class=HTMLResponse)
def home():return (static/'index.html').read_text(encoding='utf-8')

@app.get('/api/health')
def health():return {'status':'ok','brand':'TWYS | TRADE WHAT YOU SEE','company':'ALL IN INC.','version':'2.9'}

@app.get('/api/profile')
def get_profile_status():
    return profile.status()

@app.post('/api/profile/select')
async def select_next_profile(request: Request):
    # Selection affects only the next launch. No journal is deleted.
    data = await request.json()
    mode = data.get('mode') if isinstance(data, dict) else None
    if mode not in ('fresh', 'existing'):
        raise HTTPException(400, 'Choose fresh or existing profile')
    path, profile_id = profile.select_profile(mode)
    return {'selected': profile_id, 'restart_required': True,
            'message': 'Close and reopen TWYS to switch profiles. Existing data is preserved.'}

@app.get('/api/dashboard')
def dashboard():
    trades=e.load_trades()
    m=e.metrics(trades)
    recent=sorted(trades,key=lambda x:x.get('traded_at') or '',reverse=True)[:10]
    return {'metrics':m,'by_instrument':e.group_metrics(trades,'instrument'),
       'by_source':e.group_metrics(trades,'source'),
       'by_rating':e.group_metrics(trades,'rating'),
       'by_rules':e.group_metrics(trades,'rules_followed'),
       'by_session':e.group_metrics(trades,'session'),
       'recent':[e.serialize(t) for t in recent], 'quality':e.quality(trades)}

@app.get('/api/facets')
def facets():
    trades=e.load_trades()
    fields=('instrument','outcome','source','session','rating','rules_followed','emotion')
    return {field:[{'value':v,'count':n} for v,n in sorted(Counter(t[field] for t in trades if t[field]).items(),key=lambda x:(-x[1],x[0]))] for field in fields}

@app.get('/api/trades')
def trades(q:str='',instrument:str='',outcome:str='',source:str='',session:str='',rating:str='',rules:str='',emotion:str='',
           data_type:str='',from_date:str=Query('',alias='from'),to_date:str=Query('',alias='to'),
           min_r:float|None=None,max_r:float|None=None,sort:str='date_desc',limit:int=Query(100,ge=1,le=2000),offset:int=Query(0,ge=0)):
    opts={'q':q,'instrument':instrument,'outcome':outcome,'source':source,'session':session,'rating':rating,
          'rules':rules,'emotion':emotion,'data_type':data_type,'from':from_date,'to':to_date,'min_r':min_r,'max_r':max_r}
    all_=e.filter_trades(e.load_trades(),opts)
    sort_map={'date_desc':('traded_at',True),'date_asc':('traded_at',False),
              'r_desc':('realized_r',True),'r_asc':('realized_r',False),'instrument':('instrument',False)}
    key,reverse=sort_map.get(sort,sort_map['date_desc'])
    rows=sorted(all_,key=lambda t:(t.get(key) is not None,t.get(key) if t.get(key) is not None else (-1e10 if key=='realized_r' else '')),reverse=reverse)
    return {'total':len(rows),'metrics':e.metrics(rows),'rows':[e.serialize(t) for t in rows[offset:offset+limit]]}

@app.get('/api/trade/{uid}')
def detail(uid:str):
    if not all(x in '0123456789abcdef' for x in uid) or len(uid)!=20:raise HTTPException(400,'Invalid trade ID')
    c=e.connection()
    try:r=c.execute('SELECT * FROM trades WHERE uid=?',(uid,)).fetchone()
    finally:c.close()
    if not r:raise HTTPException(404,'Trade not found')
    d=e.serialize(dict(r),True)
    d['mentions']=e.mention_labels(dict(r))
    return d

@app.delete('/api/trade/{uid}')
def hide_trade(uid:str):
    """Reversible, local-only removal. Does not alter the Notion source."""
    import re
    if not re.fullmatch(r'[a-f0-9]{20}',uid):raise HTTPException(400,'Invalid trade ID')
    c=e.connection()
    try:
        record=c.execute('SELECT uid FROM trades WHERE uid=?',(uid,)).fetchone()
        if not record:raise HTTPException(404,'Trade not found')
        c.execute("INSERT OR REPLACE INTO local_hidden_trades(uid,removed_at,reason) VALUES(?,?,?)",
                 (uid,datetime.now().astimezone().isoformat(),'user_hidden'))
        c.commit()
    finally:c.close()
    marketplace.reindex()
    return {'removed':True,'uid':uid,'scope':'local_only','restorable':True}

@app.get('/api/trash')
def trash():
    c=e.connection()
    try:
        rows=c.execute("SELECT h.uid,h.reason,h.removed_at,t.instrument,t.traded_at FROM local_hidden_trades h LEFT JOIN trades t ON h.uid=t.uid ORDER BY h.removed_at DESC LIMIT 300").fetchall()
        return {'rows':[dict(r) for r in rows]}
    finally:c.close()

@app.post('/api/trash/{uid}/restore')
def restore_trade(uid:str):
    import re
    if not re.fullmatch(r'[a-f0-9]{20}',uid):raise HTTPException(400,'Invalid trade ID')
    c=e.connection()
    try:
        c.execute('DELETE FROM local_hidden_trades WHERE uid=?',(uid,));c.commit()
    finally:c.close()
    marketplace.reindex()
    return {'restored':True,'uid':uid}

@app.delete('/api/trash/{uid}/permanent')
def permanently_delete_trade(uid: str):
    """Permanently erase an already-removed local trade and its private images.

    Keeps only an opaque UID exclusion so subsequent Notion syncs do not
    recreate the deleted record. Never modifies or deletes the Notion source.
    """
    import re
    if not re.fullmatch(r'[a-f0-9]{20}', uid):
        raise HTTPException(400, 'Invalid trade ID')
    c=e.connection()
    media=[]
    try:
        c.execute('BEGIN IMMEDIATE')
        hidden=c.execute('SELECT 1 FROM local_hidden_trades WHERE uid=?',(uid,)).fetchone()
        if not hidden:
            raise HTTPException(409, 'Remove this trade from the Journal before permanently deleting it')
        record=c.execute('SELECT images,original_json FROM trades WHERE uid=?',(uid,)).fetchone()
        if record:
            try:
                media=[x.get('file') for x in json.loads(record['images'] or '[]') if isinstance(x,dict)]
            except (TypeError,ValueError):pass
            try:
                page_id=json.loads(record['original_json'] or '{}').get('notion_page_id')
            except (TypeError,ValueError):page_id=None
            if page_id:
                c.execute('CREATE TABLE IF NOT EXISTS notion_missing (page_id TEXT PRIMARY KEY, miss_count INTEGER NOT NULL DEFAULT 0)')
                c.execute('DELETE FROM notion_records WHERE page_id=?',(page_id,))
                c.execute('DELETE FROM notion_missing WHERE page_id=?',(page_id,))
        c.execute('INSERT OR REPLACE INTO permanently_deleted_trades(uid,deleted_at) VALUES(?,?)',
                  (uid,datetime.now().astimezone().isoformat()))
        c.execute('DELETE FROM trades WHERE uid=?',(uid,))
        c.execute('DELETE FROM notes WHERE uid=?',(uid,))
        c.execute('DELETE FROM local_hidden_trades WHERE uid=?',(uid,))
        c.commit()
        # No unique attachment should survive in local storage after deletion.
        # Only delete files inside TWYS's media directory that aren't referenced
        # by any other surviving trade. Never delete a file from Notion itself.
        referenced=set()
        for other in c.execute('SELECT images FROM trades').fetchall():
            try:
                referenced.update(x.get('file') for x in json.loads(other['images'] or '[]') if isinstance(x,dict) and x.get('file'))
            except (TypeError,ValueError):pass
        for filename in media:
            if (isinstance(filename,str) and re.fullmatch(r'[a-zA-Z0-9_.-]{1,160}',filename)
                    and filename not in referenced):
                try:(e.MEDIA/filename).unlink(missing_ok=True)
                except OSError:pass  # Database deletion is not reversed by filesystem permissions.
    except Exception:
        c.rollback()
        raise
    finally:c.close()
    marketplace.reindex()
    return {'deleted':True,'uid':uid,'scope':'local_only',
            'notion_unchanged':True,'will_resync':False,'undo':False}

@app.get('/api/trade/{uid}/image/{index}')
def trade_image(uid:str,index:int):
    """Serve a local cached image, or fetch the linked Notion image on demand."""
    import re
    if not re.fullmatch(r'[a-f0-9]{20}',uid) or index<0 or index>50:raise HTTPException(400,'Invalid image reference')
    c=e.connection()
    try:r=c.execute('SELECT images,original_json FROM trades WHERE uid=?',(uid,)).fetchone()
    finally:c.close()
    if not r:raise HTTPException(404,'Trade not found')
    images=json.loads(r['images'] or '[]')
    if index>=len(images):raise HTTPException(404,'Image not found')
    image=images[index]
    if image.get('file') and (e.MEDIA/Path(image['file']).name).is_file():
        return FileResponse(e.MEDIA/Path(image['file']).name,headers={'Cache-Control':'no-store'})
    if not image.get('url'):raise HTTPException(404,'No image URL')
    cached=notion_sync.cache_image(uid,index,image)
    if not cached:
        # Refresh an expired signed file URL from Notion if this record came from Notion.
        original=json.loads(r['original_json'] or '{}')
        pid=original.get('notion_page_id')
        if pid and cfg.secret('NOTION_TOKEN'):
            try:
                page=notion_sync.request_json('pages/'+pid)
                refreshed=notion_sync.normalize_page(page,'refreshed')
                replacement=json.loads(refreshed['images'])
                if index<len(replacement):
                    image['url']=replacement[index].get('url')
                    image['expiry_time']=replacement[index].get('expiry_time')
                    cached=notion_sync.cache_image(uid,index,image)
            except Exception:pass
    if not cached:raise HTTPException(404,'Notion image not available. Refresh your Notion sync.')
    image['file']=cached
    images[index]=image
    c=e.connection()
    try:c.execute('UPDATE trades SET images=? WHERE uid=?',(json.dumps(images),uid));c.commit()
    finally:c.close()
    return FileResponse(e.MEDIA/cached,headers={'Cache-Control':'no-store'})

@app.get('/api/insights')
def insights(instrument:str='',source:str='',from_date:str=Query('',alias='from'),to_date:str=Query('',alias='to')):
    t=e.filter_trades(e.load_trades(),{'instrument':instrument,'source':source,'from':from_date,'to':to_date})
    return {'metrics':e.metrics(t),'sections':e.insights(t),'universe':len(t)}

@app.get('/api/comparisons')
def comparisons():
    all_=e.load_trades()
    return {'findings':e.compare_segments(all_),'months':e.month_groups(all_)}

@app.get('/api/quality')
def quality():
    c=e.connection()
    try:
        logs=[dict(x) for x in c.execute('SELECT * FROM imports ORDER BY id DESC LIMIT 15')]
        notes=[dict(x) for x in c.execute('SELECT uid,source,source_row,body FROM notes ORDER BY source_row LIMIT 80')]
    finally:c.close()
    return {'quality':e.quality(e.load_trades()),'imports':logs,'notes':notes}

@app.post('/api/import')
async def import_file(req:Request):
    name=Path(req.headers.get('x-filename','journal.zip')).name
    if not name.lower().endswith(('.zip','.csv')):raise HTTPException(400,'Choose a .zip or .csv file')
    payload=await req.body()
    if len(payload)>180_000_000:raise HTTPException(413,'Import exceeds 180 MB')
    p=None
    try:
        with tempfile.NamedTemporaryFile(suffix=Path(name).suffix,delete=False) as temp:
            temp.write(payload);p=Path(temp.name)
        result=e.import_path(p,display_name=name)
        marketplace.reindex()
        return result
    except (ValueError, OSError, __import__('zipfile').BadZipFile) as exc:
        raise HTTPException(422,str(exc))
    finally:
        if p:p.unlink(missing_ok=True)

@app.get('/api/export/trades.csv')
def export_csv():
    trs=e.load_trades(); cols=['uid','source','traded_at','instrument','direction','session','outcome','outcome_basis',
       'realized_r','r_basis','planned_r','net_pnl','entry_price','stop_price','exit_price','rating','rules_followed',
       'emotion','mistake','reasoning','review','flags','original_json']
    s=io.StringIO(); writer=csv.DictWriter(s,fieldnames=cols)
    writer.writeheader()
    for t in trs:writer.writerow({k:t[k] for k in cols})
    return Response(content='\ufeff'+s.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="TWYS_cleaned_trades.csv"'})

@app.get('/api/export/backup')
def backup():
    target=e.DATA/'backups';target.mkdir(exist_ok=True)
    now=datetime.now().strftime('%Y%m%d_%H%M%S')
    dest=target/f'TWYS_backup_{now}.sqlite3'
    import sqlite3
    c=e.connection(); dest_conn=sqlite3.connect(str(dest))
    try:c.backup(dest_conn)
    finally:dest_conn.close();c.close()
    return FileResponse(dest,filename=dest.name,media_type='application/vnd.sqlite3')

SETTINGS_FILE=e.DATA/'twys_settings.json'

def local_model():
    try:
        saved=json.loads(SETTINGS_FILE.read_text(encoding='utf-8'))
        return str(saved.get('ollama_model') or '').strip()
    except (FileNotFoundError, ValueError, OSError):
        return os.getenv('TWYS_OLLAMA_MODEL','').strip()

@app.get('/api/settings')
def get_settings():
    return {'ollama_model':local_model(),'ollama_url':os.getenv('TWYS_OLLAMA_URL','http://127.0.0.1:11434/api/chat'),
        'data_directory':str(e.DATA),'database_file':str(e.DB),'cloud_uploads':False}

@app.post('/api/settings')
async def save_settings(req:Request):
    import re
    body=await req.json(); model=str(body.get('ollama_model') or '').strip()
    if len(model)>140 or (model and not re.fullmatch(r'[a-zA-Z0-9_.:/-]+',model)):
        raise HTTPException(400,'Invalid Ollama model identifier')
    SETTINGS_FILE.write_text(json.dumps({'ollama_model':model},indent=2),encoding='utf-8')
    return get_settings()

@app.get('/api/local-models')
def list_local_models():
    base=os.getenv('TWYS_OLLAMA_URL','http://127.0.0.1:11434/api/chat')
    parsed=urlparse(base)
    if parsed.scheme!='http' or parsed.hostname not in ('127.0.0.1','localhost','::1'):
        raise HTTPException(400,'Ollama endpoint must be on localhost')
    url=f'{parsed.scheme}://{parsed.netloc}/api/tags'
    try:
        with urlopen(url,timeout=2.5) as resp:
            data=json.load(resp)
        return {'available':True,'models':[m.get('name') for m in data.get('models',[]) if m.get('name')]}
    except Exception:
        return {'available':False,'models':[]}

@app.get('/api/media-status')
def media_status():
    return {'local':True,'enabled':True,'optional_ollama_model':local_model() or None,
            'note':'Market feeds are opt-in. No broker execution or journal cloud uploads by default.'}

@app.post('/api/research')
async def research(req:Request):
    body=await req.json();question=str(body.get('question','')).strip()[:1500]
    if not question:raise HTTPException(400,'Enter a research question')
    all_=e.load_trades()
    # Extract trade evidence from journal content. A local model receives only selected records.
    terms=[x.lower() for x in __import__('re').findall(r"[a-zA-Z]{4,}",question) if x.lower() not in
           {'with','that','what','which','about','have','were','when','does','trades','trade','show','from','compare','their','them','your','mine','most','much','than','into','this','would','performance'}]
    def relevance(t):
        content=' '.join(str(t.get(k) or '') for k in ('reasoning','review','mistake','emotion','rating','instrument','session')).lower()
        return sum(content.count(term) for term in terms)
    evidence=sorted(all_,key=relevance,reverse=True)
    if terms and evidence and relevance(evidence[0])>0:evidence=[t for t in evidence if relevance(t)>0][:12]
    else:evidence=sorted(all_,key=lambda x:x['traded_at'] or '',reverse=True)[:10]
    sums=e.metrics(all_)
    group=e.group_metrics(all_,'rules_followed')
    breakdowns={field:e.group_metrics(all_,field) for field in ('instrument','rating','rules_followed','session','emotion','source','outcome')}
    breakdowns['months']=e.month_groups(all_)
    stats={k:v for k,v in sums.items() if k!='curve'}
    cited=[{'uid':t['uid'],'date':t['traded_at'],'instrument':t['instrument'],'outcome':t['outcome'],
            'r':t['realized_r'],'r_basis':t['r_basis'],'reasoning':(t['reasoning'] or '')[:1000],
            'mistake':(t['mistake'] or '')[:300],'review':(t['review'] or '')[:850]} for t in evidence]
    model=cfg.config().get('ai_model') if cfg.config().get('ai_provider','off') != 'off' else None
    if not model:
        low=question.lower()
        if any(x in low for x in ('instrument','symbol','gold','xauusd','nasdaq','us100','us500','eurusd','us30')):
            group_field='instrument'
        elif any(x in low for x in ('rating','a+','highest-rated','highest rated','excellent')):
            group_field='rating'
        elif any(x in low for x in ('disciplin','rule','plan followed','followed')):
            group_field='rules_followed'
        elif any(x in low for x in ('session','london','new york','asia')):
            group_field='session'
        elif any(x in low for x in ('emotion','fomo','greed','revenge','mistake','early entry')):
            group_field='emotion'
        elif any(x in low for x in ('month','trend','recent','period')):
            group_field='months'
        else:group_field='instrument'
        groups=breakdowns[group_field]
        qualified=[g for g in groups if g.get('r_coverage',0)>=5]
        ordered=sorted(qualified,key=lambda g:g.get('mean_r') if g.get('mean_r') is not None else float('-inf'),reverse=True)
        snippets=[]
        for g in ordered[:8]:
            name=g.get('label') or g.get('month')
            snippets.append(f'{name}: {g["trades"]} trades, {g["r_coverage"]} qualified R values, mean {g["mean_r"]:+.2f}R, win rate {g["win_rate"] if g["win_rate"] is not None else "N/A"}%.')
        summary=('Verified breakdown ('+group_field.replace('_',' ')+'):\n'+'\n'.join(snippets)+'\n\n' if snippets else '')
        summary+='The relevant original journal examples are shown below. Smaller groups and text mentions are exploratory, not proof that a behavior caused an outcome. Local Ollama can be enabled in Settings for additional source-grounded explanations.'
        return {'mode':'evidence','answer':summary,'stats':stats,'breakdowns':breakdowns,'discipline':group,'evidence':cited}

    try:
        import asyncio
        computed={'computed_global_statistics':stats,'verified_breakdowns':breakdowns,'journal_evidence':cited}
        result=await asyncio.to_thread(ai.reply,question,computed)
        if not result:raise ValueError('No AI provider selected')
        return {'mode':result['provider'],'answer':result['answer'],'stats':stats,
                'breakdowns':breakdowns,'discipline':group,'evidence':cited}
    except Exception as exc:
        return {'mode':'evidence','answer':f'AI unavailable ({type(exc).__name__}). Verified statistics and original evidence are shown instead.',
                'stats':stats,'breakdowns':breakdowns,'discipline':group,'evidence':cited}

def main():
    import uvicorn
    host='127.0.0.1';port=int(os.getenv('TWYS_PORT','8765'))
    e.connection().close()
    if os.getenv('TWYS_NO_BROWSER','')!='1':threading.Timer(1.8,lambda:webbrowser.open(f'http://{host}:{port}')).start()
    uvicorn.run(app,host=host,port=port,log_level='warning')
if __name__=='__main__':main()
