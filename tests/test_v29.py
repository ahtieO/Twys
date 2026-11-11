"""TWYS 2.9 validates fresh data isolation, branding and theme support."""
from pathlib import Path
from fastapi.testclient import TestClient
from twys import profile,integrations
from twys.app import app

def test_fresh_profile_preserves_existing_data(tmp_path):
    root=tmp_path/'TWYS'
    old=root/'v2'
    old.mkdir(parents=True)
    (old/'twys.sqlite3').write_bytes(b'private user journal')
    (old/'integrations.json').write_text('{"notion_database_id":"private"}')
    fresh,profile_id=profile.select_profile('fresh',root)
    assert not (fresh/'twys.sqlite3').exists()
    assert (old/'twys.sqlite3').read_bytes()==b'private user journal'
    assert profile._load_selection(root)==(fresh.resolve(),profile_id)
    assert profile.select_profile('existing',root)[0]==old
    assert (old/'integrations.json').exists()

def test_reject_external_profile_path(tmp_path):
    root=tmp_path/'TWYS'
    root.mkdir()
    (root/'profile_selection.json').write_text('{"profile_path":"/etc","profile_id":"fresh-invalid"}')
    assert profile._load_selection(root) is None

def test_distinct_keychain_per_profile(monkeypatch):
    monkeypatch.setenv('TWYS_PROFILE_ID','legacy')
    assert integrations._keyring_service()=='TWYS Terminal'
    monkeypatch.setenv('TWYS_PROFILE_ID','fresh-one')
    assert integrations._keyring_service()=='TWYS Terminal:fresh-one'
    monkeypatch.setenv('TWYS_PROFILE_ID','fresh-two')
    assert integrations._keyring_service()!='TWYS Terminal:fresh-one'

def test_theme_profile_api_and_text_brand():
    with TestClient(app) as client:
        content=client.get('/').text
        assert 'id="theme-switch"' in content
        assert 'v29.css' in content and 'v29.js' in content
        assert '<header class="identity"><div class="brandtext">' in content
        assert '<img class="twys-logo"' not in content
        assert 'TWYS 2.9.1' in content
        assert client.get('/api/health').json()['version']=='2.9.1'
        assert client.get('/api/profile').status_code==200
        assert client.post('/api/profile/select',json={'mode':'wrong'}).status_code==400

def test_wordmark_icon_is_transparent():
    from PIL import Image
    root=Path(__file__).resolve().parents[1]
    icon=Image.open(root/'assets/twys-icon.png').convert('RGBA')
    assert icon.getpixel((0,0))[3]==0
    assert icon.getchannel('A').getextrema()[1]==255
