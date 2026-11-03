"""TWYS data ingestion, validation, and analytics. No AI is involved in calculations."""
from __future__ import annotations
import csv, io, json, re, sqlite3, hashlib, zipfile, shutil, os, sys, platform
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from statistics import mean, median
from urllib.parse import unquote

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
def default_data_dir():
    # Source installs and packaged apps must never ship someone else's journal.
    if platform.system() == 'Windows':
        return Path(os.getenv('APPDATA', str(Path.home() / 'AppData' / 'Roaming'))) / 'TWYS' / 'v2'
    if platform.system() == 'Darwin':
        return Path.home() / 'Library' / 'Application Support' / 'TWYS' / 'v2'
    return Path(os.getenv('XDG_DATA_HOME', Path.home() / '.local' / 'share')) / 'TWYS' / 'v2'
DATA = Path(os.getenv('TWYS_DATA_DIR', str(default_data_dir())))
DB = DATA / 'twys.sqlite3'
MEDIA = DATA / 'media'
PKT = timezone(timedelta(hours=5))

SCHEMA = '''
CREATE TABLE IF NOT EXISTS trades (
  uid TEXT PRIMARY KEY, source TEXT NOT NULL, source_row INTEGER, date_raw TEXT,
  traded_at TEXT, instrument TEXT, direction TEXT, session TEXT, timeframe TEXT,
  outcome TEXT, outcome_basis TEXT, realized_r REAL, r_basis TEXT,
  planned_r REAL, net_pnl REAL, lots REAL, entry_price REAL, stop_price REAL,
  exit_price REAL, rating TEXT, rules_followed TEXT, emotion TEXT, mistake TEXT,
  reasoning TEXT, review TEXT, markdown TEXT, images TEXT, flags TEXT,
  record_type TEXT, original_json TEXT NOT NULL, imported_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trades_date ON trades(traded_at);
CREATE INDEX IF NOT EXISTS idx_trades_instrument ON trades(instrument);
CREATE INDEX IF NOT EXISTS idx_trades_source ON trades(source);
CREATE TABLE IF NOT EXISTS local_hidden_trades (
 uid TEXT PRIMARY KEY, removed_at TEXT NOT NULL, reason TEXT NOT NULL DEFAULT 'user_hidden'
);
CREATE TABLE IF NOT EXISTS permanently_deleted_trades (
 uid TEXT PRIMARY KEY, deleted_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notes (
 uid TEXT PRIMARY KEY, source TEXT, source_row INTEGER, body TEXT, original_json TEXT
);
CREATE TABLE IF NOT EXISTS imports (
 id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, filename TEXT, source TEXT, 
 inserted INTEGER, updated INTEGER, notes INTEGER, media_count INTEGER, warnings TEXT
);
'''

def connection():
    DATA.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn

def clean(value):
    return str(value or '').strip()

def num(value):
    s=clean(value).replace(',','').replace('$','').replace('−','-').replace('R','').strip()
    if s in ('','-','N/A','None','nan','—'):return None
    try:
        v=float(s)
        return v if abs(v)<1e12 and v==v else None
    except ValueError:return None

# Values above this generous threshold are retained, but require user verification.
# Do not silently treat unexpected magnitude as true realized R.
REVIEW_R_THRESHOLD = 25.0

def validate_reported_r(value):
    value=num(value)
    if value is None:return None, []
    if abs(value)>REVIEW_R_THRESHOLD:
        return value, ['extreme_reported_r_requires_review']
    return value, []

def verified_r(trade):
    raw=trade.get('realized_r')
    if raw is None:return None
    if abs(raw)>REVIEW_R_THRESHOLD:return None
    try: flags=json.loads(trade.get('flags') or '[]') if isinstance(trade.get('flags'),str) else (trade.get('flags') or [])
    except (ValueError,TypeError):flags=[]
    if any(f in flags for f in ('extreme_reported_r_requires_review','extreme_price_ratio','stop_wrong_side','price_pnl_disagree','outcome_price_disagree')):return None
    return raw

def parse_date(value, kind):
    s=clean(value).replace('(GMT+5)','').strip()
    if not s:return None
    patterns=('%d/%m/%Y %I:%M %p','%d/%m/%Y') if kind=='legacy' else ('%B %d, %Y %I:%M %p','%b %d, %Y %I:%M %p')
    for p in patterns:
        try:
            parsed=datetime.strptime(s,p)
            return parsed.date().isoformat() if p=='%d/%m/%Y' else parsed.replace(tzinfo=PKT).isoformat(timespec='minutes')
        except ValueError:pass
    return None

def standard_instrument(s):
    n=clean(s).upper().replace(' ','').replace('S&P','SP').replace('SPX','SP')
    mapping={
        'SP500':'US500','US500':'US500',
        'NAS100':'US100','NASDAQ':'US100','US100':'US100',
        'US30':'US30','XAUUSD':'XAUUSD','EURUSD':'EURUSD'
    }
    return mapping.get(n,n or None)

def parse_images(s):
    return [Path(unquote(p.strip())).name for p in clean(s).split(',') if p.strip()]

def fmtkey(text):
    return re.sub(r'\s+','',clean(text)).lower()

def derive_legacy_r(entry, stop, exit_, direction, net, result):
    """Reject contradicting/broken price records; never derive R from dollar P&L alone."""
    flags=[]
    if None in (entry,stop,exit_) or direction not in ('LONG','SHORT'):
        return None,'unavailable', ['price_levels_missing']
    risk=abs(entry-stop)
    if risk <= 1e-10:
        return None,'unavailable',['zero_price_risk']
    r=(exit_-entry)*(1 if direction=='LONG' else -1)/risk
    if abs(r)>15:
        flags.append('extreme_price_ratio')
    if (direction=='LONG' and stop>entry) or (direction=='SHORT' and stop<entry):
        flags.append('stop_wrong_side')
    if net is not None and abs(net)>0.01 and abs(r)>0.02 and (net>0)!=(r>0):
        flags.append('price_pnl_disagree')
    if result=='SL' and r>0.02:flags.append('outcome_price_disagree')
    if result=='TP' and r< -0.02:flags.append('outcome_price_disagree')
    if result=='B/E' and net is not None and abs(net)>0.05:
        flags.append('breakeven_nonzero_net')
    if result=='TP' and net is not None and net<-0.05:flags.append('outcome_net_disagree')
    if result=='SL' and net is not None and net>0.05:flags.append('outcome_net_disagree')
    if result=='B/E' and net is not None and abs(net)<0.01:
        if abs(r)>0.10:flags.append('breakeven_price_disagree')
        # Actual NET=0, but price movement alone may not capture fees, changes in SL or partial fills.
        return 0.0,'net_break_even',flags
    if flags:
        return None,'excluded_discrepancy',flags
    return round(r,6),'price_derived',[]

def normalize(row, kind, source, row_no, attachments, md_lookup):
    old=kind=='legacy'
    date_raw=clean(row.get('DATE') if old else row.get('Date'))
    instrument=standard_instrument((row.get('PAIR ') or row.get('PAIR')) if old else row.get('Instrument'))
    direction=clean(row.get('Type') if old else row.get('Direction')).upper() or None
    images=parse_images(row.get('Trade Image') if old else row.get('Images'))
    entry=num(row.get('Entry')) if old else None
    stop=num(row.get('Stoploss')) if old else None
    exit_=num(row.get('EXIT ') or row.get('EXIT')) if old else None
    net=num(row.get('NET')) if old else None
    outcome_raw=clean(row.get('RESULT') if old else '')
    planned=num(row.get('Planned RR')) if not old else None
    realized=num(row.get('Result RR')) if not old else None
    flags=[]
    if not old:
        realized, reported_flags=validate_reported_r(realized)
        flags.extend(reported_flags)
    markdown=md_lookup.get((fmtkey(date_raw),images[0] if images else ''),'')
    if old:
        realized,r_basis,warnings=derive_legacy_r(entry,stop,exit_,direction,net,outcome_raw)
        flags.extend(warnings)
        if outcome_raw=='TP':outcome='win';basis='recorded_result'
        elif outcome_raw=='SL':outcome='loss';basis='recorded_result'
        elif outcome_raw=='B/E':outcome='breakeven';basis='recorded_result'
        elif net is not None:outcome=('win' if net>0.01 else 'loss' if net< -0.01 else 'breakeven');basis='net_pnl'
        else:outcome=None;basis='unavailable'
        reason=clean(row.get('REASONING'));review=''
        session=None;rating=clean(row.get('RATING')) or None
        rules=clean(row.get('Rules Followed?')).upper() or None
        emotion=clean(row.get('EMOTIONS')) or None;mistake=None
        timeframe=clean(row.get('T/F')) or None;lots=num(row.get('LOTS'))
    else:
        r_basis='journal_reported' if realized is not None else 'unavailable'
        outcome=('win' if realized>0 else 'loss' if realized<0 else 'breakeven') if realized is not None else None
        basis='realized_r' if realized is not None else 'unavailable'
        reason=clean(row.get('Setup + Reasoning'));review=clean(row.get('Post Trade Review'))
        session=clean(row.get('Session')).upper() or None
        rating=clean(row.get('Rating')) or None
        rules=clean(row.get('Rules Followed')).upper() or None
        emotion=clean(row.get('Emotion')) or None;mistake=clean(row.get('Mistake')) or None
        timeframe=clean(row.get('Time Frame')) or None;lots=None
    date=parse_date(date_raw,kind)
    if date_raw and date is None:flags.append('unparsed_date')
    if date and len(date)==10:flags.append('date_only_time_unknown')
    for fn in images:
        if fn not in attachments:flags.append('missing_image:'+fn)
    if date is None and (not old and not any(clean(row.get(x)) for x in ('Instrument','Result RR','Images'))):
        # Notion has reusable entry forms, not trading records
        if any(s.strip() for s in (reason.replace('Setup :','').replace('Entry Trigger :','').replace('Invalidation :','').replace('Management Plan :',''),review)):
            typ='note'
        else:typ='template'
    elif not date and old:typ='note' if reason else 'empty'
    else:typ='trade'
    # image + date + instrument is a stable key even when notes/R are revised on later exports.
    natural='|'.join((source,date_raw,images[0] if images else '',instrument or '',direction or ''))
    if not date_raw and not images: natural += f'|row:{row_no}'
    uid=hashlib.sha256(natural.encode()).hexdigest()[:20]
    d=dict(uid=uid,source=source,source_row=row_no,date_raw=date_raw,traded_at=date,
           instrument=instrument,direction=direction,session=session,timeframe=timeframe,
           outcome=outcome,outcome_basis=basis,realized_r=realized,r_basis=r_basis,planned_r=planned,
           net_pnl=net,lots=lots,entry_price=entry,stop_price=stop,exit_price=exit_,rating=rating,
           rules_followed=rules,emotion=emotion,mistake=mistake,reasoning=reason,review=review,
           markdown=markdown,images=json.dumps(images),flags=json.dumps(flags),record_type=typ,
           original_json=json.dumps(row,ensure_ascii=False),imported_at=datetime.now(timezone.utc).isoformat())
    return d

def identify_source(headers):
    cols={h.strip().lower() for h in headers}
    if {'date','pair','entry','stoploss','result'} <= cols:return 'legacy'
    if {'date','instrument','planned rr','result rr'} <= cols:return 'modern'
    raise ValueError('Unsupported CSV schema: expected TWYS legacy price-based journal or modern R-based journal.')

def import_path(path, display_name=None):
    """Import a zip or CSV, no pathname extraction. Keep source records and images."""
    path=Path(path)
    if path.stat().st_size>180_000_000:raise ValueError('Import file exceeds 180 MB limit')
    files={}; count_media=0; warnings=[]
    if path.suffix.lower()=='.zip':
        with zipfile.ZipFile(path) as z:
            info=z.infolist()
            if len(info)>10000 or sum(x.file_size for x in info)>500_000_000:
                raise ValueError('ZIP exceeds safe file count or expanded size limit')
            for x in info:
                if x.is_dir():continue
                if x.file_size>100_000_000:raise ValueError('Oversized file in ZIP')
                # Only read CSV, markdown, and images; never extract paths verbatim.
                ext=Path(x.filename).suffix.lower()
                if ext in ('.csv','.md','.png','.jpg','.jpeg','.webp'):
                    files[x.filename]=z.read(x)
    elif path.suffix.lower()=='.csv':files[path.name]=path.read_bytes()
    else:raise ValueError('Import a Notion .zip or journal .csv file')
    csvs=[n for n in files if n.lower().endswith('.csv') and not Path(n).stem.lower().endswith('_all')]
    if not csvs:csvs=[n for n in files if n.lower().endswith('.csv')]
    if not csvs:raise ValueError('No CSV found in archive')
    MEDIA.mkdir(parents=True,exist_ok=True)
    attachments={};
    for fname,blob in files.items():
        if Path(fname).suffix.lower() not in ('.png','.jpg','.jpeg','.webp'):continue
        basename=Path(fname).name
        slug=hashlib.sha256(blob).hexdigest()[:14]+'_'+basename
        dst=MEDIA/slug
        if not dst.exists():dst.write_bytes(blob);count_media+=1
        attachments[basename]=slug
    md_lookup={}
    for name,blob in files.items():
        if Path(name).suffix.lower()!='.md':continue
        s=blob.decode('utf-8-sig',errors='replace')
        dt=re.search(r'(?im)^DATE\s*:\s*(.*)$',s)
        im=re.search(r'(?im)^Trade Image\s*:\s*(.*)$',s)
        if dt and im:
            md_lookup[(fmtkey(dt.group(1)),parse_images(im.group(1))[0] if parse_images(im.group(1)) else '')]=s
    inserts=updates=notes=0
    conn=connection()
    try:
        for csv_name in csvs:
            reader=csv.DictReader(io.StringIO(files[csv_name].decode('utf-8-sig',errors='replace')))
            kind=identify_source(reader.fieldnames or [])
            # Distinguish two Notion databases by CSV export name, but do not encode archive filename.
            source='notion_'+kind
            for ix,row in enumerate(reader,2):
                # Preserve exact original Notion field names and contents.
                row={k:(v or '') for k,v in row.items() if k is not None}
                d=normalize(row,kind,source,ix,attachments,md_lookup)
                if conn.execute('SELECT 1 FROM permanently_deleted_trades WHERE uid=?',(d['uid'],)).fetchone():
                    continue  # Local permanent removal survives repeated CSV imports.
                if d['record_type']!='trade':
                    if d['record_type']=='note':
                        conn.execute('INSERT INTO notes(uid,source,source_row,body,original_json) VALUES(?,?,?,?,?) ON CONFLICT(uid) DO UPDATE SET body=excluded.body,original_json=excluded.original_json',
                          (d['uid'],source,ix,d['reasoning'] or d['review'],d['original_json']))
                        notes+=1
                    continue
                # Resolve image references to the uniquely stored physical filename. For CSV-only imports,
                # reuse a file by exact basename if already present, otherwise preserve the unresolved name.
                resolved=[]
                for img in json.loads(d['images']):
                    key=attachments.get(img)
                    if not key:
                        possible=list(MEDIA.glob('*_'+img))
                        if len(possible)==1:key=possible[0].name
                    resolved.append({'name':img,'file':key})
                d['images']=json.dumps(resolved)
                exists=conn.execute('SELECT 1 FROM trades WHERE uid=?',(d['uid'],)).fetchone()
                if not exists:
                    same_time=conn.execute('SELECT uid FROM trades WHERE source=? AND traded_at=? AND instrument=? AND direction=? LIMIT 1',
                        (d['source'],d['traded_at'],d['instrument'],d['direction'])).fetchone()
                    if same_time:
                        old_flags=json.loads(d['flags'])
                        old_flags.append('possible_duplicate_same_time')
                        d['flags']=json.dumps(old_flags)
                        warnings.append(f'Possible distinct or duplicate trade at {d["traded_at"]} ({d["instrument"]}). Review source rows.')
                names=list(d)
                conn.execute('INSERT INTO trades('+','.join(names)+') VALUES('+','.join('?' for _ in names)+') ON CONFLICT(uid) DO UPDATE SET '+','.join(f'{k}=excluded.{k}' for k in names if k!='uid'),list(d.values()))
                if exists:updates+=1
                else:inserts+=1
        conn.execute('INSERT INTO imports(at,filename,source,inserted,updated,notes,media_count,warnings) VALUES(?,?,?,?,?,?,?,?)',
                    (datetime.now(timezone.utc).isoformat(),display_name or path.name, 'notion',inserts,updates,notes,count_media,json.dumps(warnings)))
        conn.commit()
    finally:conn.close()
    return {'inserted':inserts,'updated':updates,'notes':notes,'media_files_added':count_media,'warnings':warnings}

def load_trades():
    c=connection()
    try:return [dict(row) for row in c.execute("SELECT * FROM trades WHERE record_type='trade' AND uid NOT IN (SELECT uid FROM local_hidden_trades) ORDER BY traded_at,source_row").fetchall()]
    finally:c.close()

def serialize(row, full=False):
    allowed=['uid','source','source_row','traded_at','date_raw','instrument','direction','session','timeframe','outcome',
             'outcome_basis','realized_r','r_basis','planned_r','net_pnl','lots','entry_price','stop_price','exit_price',
             'rating','rules_followed','emotion','mistake','reasoning','review','images','flags']
    if full:allowed+=['markdown','original_json']
    d={k:row.get(k) for k in allowed}
    for key in ('images','flags'):
        d[key]=json.loads(d[key] or '[]')
    d['verified_realized_r']=verified_r(row)
    d['requires_r_review']=row.get('realized_r') is not None and d['verified_realized_r'] is None
    if full:d['original_json']=json.loads(d['original_json'] or '{}')
    return d

def filter_trades(trades, opts):
    def maybe_contains(v, needle):return needle.lower() in clean(v).lower()
    search=clean(opts.get('q')).lower()
    result=[]
    for t in trades:
        if opts.get('instrument') and t['instrument']!=opts['instrument']:continue
        if opts.get('outcome') and t['outcome']!=opts['outcome']:continue
        if opts.get('source') and t['source']!=opts['source']:continue
        if opts.get('session') and t['session']!=opts['session']:continue
        if opts.get('rating') and t['rating']!=opts['rating']:continue
        if opts.get('rules') and t['rules_followed']!=opts['rules']:continue
        if opts.get('emotion') and t['emotion']!=opts['emotion']:continue
        if opts.get('from') and (not t['traded_at'] or t['traded_at'][:10]<opts['from']):continue
        if opts.get('to') and (not t['traded_at'] or t['traded_at'][:10]>opts['to']):continue
        if opts.get('min_r') is not None and (t['realized_r'] is None or t['realized_r']<float(opts['min_r'])):continue
        if opts.get('max_r') is not None and (t['realized_r'] is None or t['realized_r']>float(opts['max_r'])):continue
        typ=opts.get('data_type')
        if typ=='price' and t['entry_price'] is None:continue
        if typ=='r_only' and (t['entry_price'] is not None or t['realized_r'] is None):continue
        if typ=='both' and (t['entry_price'] is None or t['realized_r'] is None):continue
        if search and not any(search in clean(t.get(x)).lower() for x in ('instrument','reasoning','review','mistake','emotion','rating','session','date_raw','source','direction')):continue
        result.append(t)
    return result

def metrics(trades):
    n=len(trades); rs=[verified_r(t) for t in trades if verified_r(t) is not None]
    wins=sum(t['outcome']=='win' and not (verified_r(t) is None and t.get('outcome_basis')=='realized_r') for t in trades);losses=sum(t['outcome']=='loss' and not (verified_r(t) is None and t.get('outcome_basis')=='realized_r') for t in trades)
    be=sum(t['outcome']=='breakeven' for t in trades);unknown=n-wins-losses-be
    gains=sum(r for r in rs if r>0);abs_losses=-sum(r for r in rs if r<0)
    cum=peak=drawdown=0.0;curve=[];streak_w=streak_l=max_w=max_l=0
    for t in sorted(trades,key=lambda r:(r.get('traded_at') or '',r['uid'])):
        r=verified_r(t)
        if r is not None:
            cum+=r;peak=max(peak,cum);drawdown=max(drawdown,peak-cum)
            curve.append({'date':t['traded_at'],'value':round(cum,4),'uid':t['uid']})
        if t['outcome']=='win':streak_w+=1;streak_l=0;max_w=max(max_w,streak_w)
        elif t['outcome']=='loss':streak_l+=1;streak_w=0;max_l=max(max_l,streak_l)
        else:streak_w=streak_l=0
    return {'trades':n,'wins':wins,'losses':losses,'breakevens':be,'unknown':unknown,
        'win_rate':round(wins/(wins+losses)*100,2) if wins+losses else None,
        'resolved':wins+losses,'r_coverage':len(rs),'r_missing':n-len(rs),
        'r_review_required':sum(t.get('realized_r') is not None and verified_r(t) is None for t in trades),
        'total_r':round(sum(rs),4) if rs else None,
        'mean_r':round(mean(rs),4) if rs else None,'median_r':round(median(rs),4) if rs else None,
        'expectancy_r':round(mean(rs),4) if rs else None,
        'profit_factor':round(gains/abs_losses,4) if abs_losses else None,
        'avg_win_r':round(mean([r for r in rs if r>0]),4) if any(r>0 for r in rs) else None,
        'avg_loss_r':round(mean([r for r in rs if r<0]),4) if any(r<0 for r in rs) else None,
        'max_drawdown_r':round(drawdown,4) if curve else None,
        'max_win_streak':max_w,'max_loss_streak':max_l,'curve':curve}

def group_metrics(trades,field):
    groups=defaultdict(list)
    for t in trades:groups[str(t.get(field) or 'Not recorded')].append(t)
    return sorted([{'label':label,**{k:v for k,v in metrics(items).items() if k!='curve'}} for label,items in groups.items()],
        key=lambda x:x['trades'],reverse=True)

# Text mentions are not verified labels of trade behavior or causal signals.
KEYWORDS={'Retest / retracement':r'\b(retest|retrac(?:e|ement|ing)|pull\s*back)\b',
          'Market structure / BOS':r'\b(bos|break of structure|structure)\b',
          'Consolidation':r'\bconsolidat(?:ion|ing|ed|e)\b',
          'Volume':r'\bvolume\b','Confirmation':r'\bconfirm(?:ation|ed|ing)?\b',
          'POC / VAH':r'\b(poc|vah|val)\b','FOMO':r'\bfomo\b',
          'Early entry':r'\b(early entry|entered too early|enter(?:ed|ing)? too early|didn.t wait|did not wait)\b',
          'Overtrading':r'\bovertrad(?:e|ing)\b','Revenge':r'\brevenge\b',
          'Greed':r'\bgreed(?:y)?\b','Hesitation':r'\bhesitat(?:e|ion|ed|ing)\b',
          'Slow market':r'\b(slow market|market slowed|low volume|weak driver|dead market)\b'}

def mention_labels(t):
    s=' '.join(clean(t.get(x)) for x in ('reasoning','mistake','review'))
    return [label for label,p in KEYWORDS.items() if re.search(p,s,re.I)]

def insights(trades):
    res=[]
    for field,desc in [('rules_followed','Recorded discipline'),('rating','Recorded setup rating'),('instrument','Instrument'),('session','Session'),('emotion','Recorded emotion'),('source','Journal generation')]:
        groups=[x for x in group_metrics(trades,field) if x['label']!='Not recorded']
        if groups:res.append({'title':desc,'type':'field','field':field,'groups':groups,'limitation':('Recorded categories only. Outcome does not prove causality.' if field!='source' else 'Different journals cover different periods and measures.')})
    labelgroups=defaultdict(list)
    for t in trades:
        for label in mention_labels(t):labelgroups[label].append(t)
    res.append({'title':'Themes mentioned in trade notes','type':'mentions','field':'mentions',
                'groups':sorted([{'label':label,**{k:v for k,v in metrics(items).items() if k!='curve'}} for label,items in labelgroups.items()],key=lambda t:t['trades'],reverse=True),
                'limitation':'Keyword mentions may describe mistakes, plans, or things to avoid. They are not validated setup executions.'})
    return res

def quality(trades):
    flags=Counter(f for t in trades for f in json.loads(t.get('flags') or '[]'))
    out={'total':len(trades),'sources':dict(Counter(t['source'] for t in trades)),
         'r_by_basis':dict(Counter(t['r_basis'] for t in trades)),
         'missing':{col:sum(not t.get(col) and t.get(col)!=0 for t in trades) for col in ('traded_at','instrument','session','rating','rules_followed','emotion','planned_r','realized_r','entry_price','review')},
         'flags':dict(flags),'images':sum(len(json.loads(t['images'] or '[]')) for t in trades),
         'images_resolved':sum(sum(bool(p.get('file')) for p in json.loads(t['images'] or '[]')) for t in trades),
         'images_missing':sum(sum(not p.get('file') for p in json.loads(t['images'] or '[]')) for t in trades)}
    return out

def compare_segments(trades):
    """Exploratory comparisons only, never causal or out-of-sample proof."""
    fields=['rules_followed','instrument','rating','session','emotion']
    outputs=[]
    for field in fields:
        labels=sorted({t.get(field) for t in trades if t.get(field)})
        for label in labels:
            # Legacy numeric ratings and modern text ratings belong to different scales.
            if field=='rating':
                domain='notion_legacy' if clean(label).isdigit() else 'notion_modern'
                pool=[t for t in trades if t['source']==domain]
            else:pool=trades
            group=[t for t in pool if t.get(field)==label]
            others=[t for t in pool if t.get(field)!=label]
            if len(group)<5 or len(others)<5:continue
            a,b=metrics(group),metrics(others)
            if a['r_coverage']<4 or b['r_coverage']<4:continue
            diff=round(a['mean_r']-b['mean_r'],4)
            score=min(a['r_coverage'],b['r_coverage'])
            if score>=30: strength='Descriptive, reasonable sample'
            elif score>=12:strength='Descriptive, limited sample'
            else:strength='Preliminary, small sample'
            next_test={'rules_followed':'Compare the same setup and time period with rules followed versus not followed.',
                'instrument':'Compare the same setup and session across instruments.',
                'rating':'Audit rating definitions and compare equivalent setups in later trades.',
                'session':'Compare matched instruments and setups within each session.',
                'emotion':'Check whether emotion was recorded before or after the trade, then compare similar setups.'}[field]
            outputs.append({'field':field,'segment':label,'group_count':len(group),'comparison_count':len(others),
                'group_r_count':a['r_coverage'],'comparison_r_count':b['r_coverage'],
                'group_mean_r':a['mean_r'],'comparison_mean_r':b['mean_r'],
                'group_win_rate':a['win_rate'],'comparison_win_rate':b['win_rate'],
                'delta_r':diff,'strength':strength,
                'interpretation':('This group had higher observed average R in the journal.' if diff>0 else
                                  'This group had lower observed average R in the journal.' if diff<0 else 'No average R difference in this sample.'),
                'limitation':'Observational comparison; different time periods, setups, and missing R values can distort the result. Not a causal or validated strategy signal.',
                'next_test':next_test})
    outputs.sort(key=lambda x:(-min(x['group_r_count'],x['comparison_r_count']),-abs(x['delta_r'])))
    return outputs

def month_groups(trades):
    grouped=defaultdict(list)
    for t in trades:
        if t['traded_at']:grouped[t['traded_at'][:7]].append(t)
    return [{'month':month,**{k:v for k,v in metrics(rows).items() if k!='curve'}} for month,rows in sorted(grouped.items())]
