import csv, io, zipfile
from pathlib import Path
import pytest
from twys import engine as e


def test_sign_and_price_r():
    assert e.derive_legacy_r(100,98,104,'LONG',40,'TP')[:2] == (2.0,'price_derived')
    assert e.derive_legacy_r(100,102,97,'SHORT',40,'TP')[:2] == (1.5,'price_derived')
    r,basis,flags=e.derive_legacy_r(100,101,104,'LONG',40,'TP')
    assert r is None and basis=='excluded_discrepancy' and 'stop_wrong_side' in flags
    r,basis,flags=e.derive_legacy_r(100,99,101,'LONG',-20,'SL')
    assert r is None and 'price_pnl_disagree' in flags
    assert e.derive_legacy_r(100,99,101,'LONG',0,'B/E')[0] == 0
    assert e.derive_legacy_r(100,100,101,'LONG',0,'B/E')[0] is None


def test_dates_and_missing():
    assert e.parse_date('12/02/2026','legacy')=='2026-02-12'
    assert e.parse_date('August 31, 2026 9:00 AM (GMT+5)','modern').startswith('2026-08-31T09:00')
    assert e.num('') is None
    assert e.num('0')==0
    assert e.num('-1.5R')==-1.5
    assert e.standard_instrument('S&P 500')=='US500'
    assert e.standard_instrument('NAS 100')=='US100'


def test_metrics_do_not_turn_missing_to_zero():
    rows=[{'uid':'1','traded_at':'2026-01-01','outcome':'win','realized_r':2.0},
          {'uid':'2','traded_at':'2026-01-02','outcome':'loss','realized_r':-1.0},
          {'uid':'3','traded_at':'2026-01-03','outcome':'breakeven','realized_r':0.0},
          {'uid':'4','traded_at':'2026-01-04','outcome':'loss','realized_r':None}]
    m=e.metrics(rows)
    assert m['trades']==4 and m['r_coverage']==3 and m['r_missing']==1
    assert m['win_rate']==round(100/3,2) and m['expectancy_r']==round(1/3,4)
    assert m['profit_factor']==2.0 and m['max_drawdown_r']==1.0


def test_import_reimport_preserves_original_and_images(monkeypatch,tmp_path):
    monkeypatch.setattr(e,'DATA',tmp_path)
    monkeypatch.setattr(e,'DB',tmp_path/'test.sqlite3')
    monkeypatch.setattr(e,'MEDIA',tmp_path/'media')
    content='Date,Instrument,Direction,Session,Images,Setup + Reasoning,Planned RR,Result RR,Rules Followed,Rating,Emotion,Mistake,Time Frame,Post Trade Review\n'
    content+='"August 31, 2026 9:00 AM (GMT+5)",XAUUSD,SHORT,ASIA,x.png,Reasoning,2,-1,YES,Good,Calm,No Mistake,5M,Review\n'
    content+='"August 31, 2026 10:00 AM (GMT+5)",EURUSD,LONG,LONDON,,Second trade,3,,YES,Good,Calm,No Mistake,5M,Review\n'
    p=tmp_path/'source.zip'
    with zipfile.ZipFile(p,'w') as z:
        z.writestr('#TWYS.csv',content)
        z.writestr('x.png',b'fake image bytes')
    a=e.import_path(p);b=e.import_path(p)
    rows=e.load_trades()
    assert a['inserted']==2 and b['inserted']==0 and b['updated']==2
    assert len(rows)==2 and any(t['realized_r'] is None for t in rows)
    assert any('Source' not in t['original_json'] and 'Reasoning' in t['original_json'] for t in rows)
    assert e.quality(rows)['images_resolved']==1


def test_v2_starts_empty_without_shipped_journal():
    # New installations are deliberately empty; old private records never ship.
    trades=e.load_trades()
    assert len(trades)==0
    assert e.quality(trades)['total']==0
    assert e.metrics(trades)['r_coverage']==0
    assert e.metrics(trades)['win_rate'] is None


