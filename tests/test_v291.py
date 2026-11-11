"""TWYS 2.9.1 focused regression checks: Markets, Watchlist, desktop icon."""
from pathlib import Path
from fastapi.testclient import TestClient
from twys.app import app

ROOT=Path(__file__).resolve().parents[1]

def test_markets_chart_is_not_lined_with_duplicate_tabs():
    source=(ROOT/'static'/'v22.js').read_text(encoding='utf-8')
    assert '<div class="v22-market-tabs"><button' not in source
    assert 'data-tab="Overview"' not in source
    assert '$$(\'[data-tab]\')' not in source
    assert 'id="v22-chart"' in source
    assert 'id="v22-positioning"' in source

def test_saved_watchlist_has_independent_remove_star_and_reselection():
    source=(ROOT/'static'/'v24.js').read_text(encoding='utf-8')
    assert 'data-v24-remove=' in source
    assert 'data-v24-watch=' in source
    assert 'favorite:false' in source
    assert "v24LoadWatchlist()" in source
    assert "twys_watch_selected" in source
    assert "data-v24-row=" in source

def test_sidebar_no_longer_has_duplicate_watchlist():
    html=(ROOT/'static'/'index.html').read_text(encoding='utf-8')
    assert 'data-page="watchlist"' in html
    assert 'id="v22-watch-mini"' not in html
    assert '<div class="sidebar-spacer"></div>' in html

def test_icon_generator_uses_supplied_twys_mark_not_old_logo():
    script=(ROOT/'installer'/'windows'/'restore_legacy_icon.py').read_text(encoding='utf-8')
    assert 'MARK_PATHS' in script
    assert "'black'" in script and "'white'" in script
    assert "twys-icon.ico" in script
    assert "twys-mark.png" not in script

def test_version_is_patch_release():
    with TestClient(app) as client:
        assert client.get('/api/health').json()['version']=='2.9.1'
        assert 'TWYS 2.9.1' in client.get('/').text
