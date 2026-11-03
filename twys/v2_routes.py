"""TWYS 2.0 API. Independent market research and private journal contexts."""
from __future__ import annotations
from datetime import datetime,timezone
import re
from fastapi import APIRouter, Request, HTTPException, Query
from . import engine as e, marketplace as m, integrations as c, notion_sync as n, positioning as p, social, ai, macro

router=APIRouter(prefix='/api/v2')

def clean_symbol(symbol):
    symbol=str(symbol or '').strip().upper()
    if not re.fullmatch(r'[A-Z0-9/._:-]{2,35}',symbol):raise HTTPException(400,'Invalid symbol')
    return symbol

@router.get('/status')
def status():
    cov=m.coverage()
    return {'version':'2.6','terminal':'TWYS | TRADE WHAT YOU SEE','company':'ALL IN INC.',
            'data':cov,'notion':n.status(),'favorites':m.favorites(),
            'ai':ai.status(),'connected_services':c.installed_integrations(),
            'market_data':c.config().get('price_provider','off'),
            'separation':'Market intelligence is independent of your private journal. No trade execution.'}

@router.get('/search')
def search(q:str='',scope:str='all',limit:int=Query(50,ge=1,le=100)):
    if scope not in ('all','markets','journal','watchlists'):raise HTTPException(400,'Invalid scope')
    return m.search(q,scope,limit)

@router.get('/symbols')
def symbols(q:str='',limit:int=Query(80,ge=1,le=100)):
    return {'results':m.symbol_search(q,limit),'source':'TWYS shortcuts','status':'ok',
            'notice':'Shortcuts are not an exhaustive exchange catalogue; search connected provider for more.'}

@router.get('/symbols/crypto')
def public_crypto_symbols(q:str='',limit:int=Query(45,ge=1,le=80)):
    return m.public_crypto_symbols(q,limit)

@router.get('/symbols/provider')
def provider_symbols(q:str=''):
    return m.provider_lookup(q)

@router.get('/favorites')
def favorites():return {'symbols':m.favorites()}

@router.post('/favorites')
async def set_fav(req:Request):
    d=await req.json()
    try:return m.set_favorite(clean_symbol(d.get('symbol')) ,bool(d.get('favorite',True)))
    except ValueError as ex:raise HTTPException(422,str(ex))

@router.get('/markets/{symbol:path}/candles')
def candles(symbol:str,interval:str='5min',count:int=Query(140,ge=20,le=500)):
    return c.get_candles(clean_symbol(symbol),interval,count)

@router.get('/markets/{symbol:path}/positioning')
def positions(symbol:str):return p.get_positioning(clean_symbol(symbol))

@router.get('/markets/{symbol:path}/social')
def socials(symbol:str):return social.public_commentary(clean_symbol(symbol))

@router.get('/markets/{symbol:path}/suggestions')
def market_suggestions(symbol:str):return m.suggestions(clean_symbol(symbol))

@router.get('/markets/{symbol:path}')
def market(symbol:str):return m.market_brief(clean_symbol(symbol))

@router.get('/macro')
def macro_dashboard():return macro.report()

@router.get('/macro/news')
def macro_news():return macro.news_brief()

@router.get('/news')
def news():
    report=c.get_news()
    m.store_headlines(report.get('items',[]))
    return report

@router.get('/calendar')
def calendar(start:str|None=None,end:str|None=None,refresh:bool=False):return c.get_calendar(start,end,refresh=refresh)

@router.get('/coverage')
def coverage():return m.coverage()

@router.get('/connections')
def connections():
    settings=c.config()
    return {'config':settings,'secrets':{k:bool(c.secret(k)) for k in ('NOTION_TOKEN','TWELVE_DATA_KEY','FRED_KEY','FMP_KEY','MYFXBOOK_SESSION','OPENAI_API_KEY','COMPATIBLE_API_KEY')},
            'notion':n.status(),'ai':ai.status(), 'detected':c.installed_integrations(),
            'data_location':str(e.DATA),'platform':'cross-platform Python / native webview'}

@router.post('/connections')
async def save_connections(req:Request):
    d=await req.json()
    try:
        if 'config' in d:c.save_config(d.get('config') or {})
        if 'secrets' in d:
            if not isinstance(d['secrets'],dict):raise ValueError('Invalid secrets')
            for key,val in d['secrets'].items():
                if val is None:continue
                if not isinstance(val,str) or len(val)>800:raise ValueError('Invalid credential')
                c.save_secret(key,val.strip())
        return connections()
    except ValueError as ex:raise HTTPException(422,str(ex))

@router.get('/notion/sources')
def notion_sources():
    try:return {'sources':n.search_sources(),'selected':c.config().get('notion_data_sources',[]),
                'notice':'Only Notion databases shared with your integration appear here.'}
    except ValueError as ex:raise HTTPException(422,str(ex))

@router.post('/notion/sync')
def sync_now(deep:bool=False):
    # Quick sync checks Notion revision IDs; expensive screenshot rescans are opt-in.
    try:return n.sync_selected(force=deep)
    except ValueError as ex:raise HTTPException(422,str(ex))

@router.get('/notion/status')
def notion_status():return n.status()

@router.get('/ai')
def ai_settings():return ai.status()


