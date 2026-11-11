"""TWYS 1.0 clean-profile migration and Markets regression tests."""
from pathlib import Path
from fastapi.testclient import TestClient
from twys import profile
from twys.app import app

ROOT=Path(__file__).resolve().parents[1]

def test_clean_v1_launch_preserves_legacy_and_recovers(monkeypatch,tmp_path):
    root=tmp_path/'TWYS'
    legacy=root/'v2'
    legacy.mkdir(parents=True)
    data=legacy/'twys.sqlite3'
    data.write_bytes(b'prior private trades')
    monkeypatch.delenv('TWYS_DATA_DIR',raising=False)
    monkeypatch.delenv('TWYS_PROFILE_ID',raising=False)
    monkeypatch.setattr(profile,'profiles_root',lambda:root)
    fresh,identifier=profile.choose_on_launch(interactive=True)
    assert fresh!=legacy and identifier.startswith('fresh-')
    assert not (fresh/'twys.sqlite3').exists()
    assert data.read_bytes()==b'prior private trades'
    assert (root/'v1_first_launch_complete').exists()
    assert profile.status()['previous_available'] is True
    restored,rid=profile.select_profile('previous',root)
    assert rid=='legacy' and restored==legacy
    assert data.read_bytes()==b'prior private trades'

def test_launch_uses_same_profile_after_first_run(monkeypatch,tmp_path):
    root=tmp_path/'TWYS'
    monkeypatch.delenv('TWYS_DATA_DIR',raising=False)
    monkeypatch.delenv('TWYS_PROFILE_ID',raising=False)
    monkeypatch.setattr(profile,'profiles_root',lambda:root)
    first=profile.choose_on_launch(interactive=True)
    monkeypatch.delenv('TWYS_DATA_DIR',raising=False)
    monkeypatch.delenv('TWYS_PROFILE_ID',raising=False)
    assert profile.choose_on_launch(interactive=True)==first

def test_markets_related_button_selector_is_collection():
    source=(ROOT/'static/v22.js').read_text(encoding='utf-8')
    assert "$$('[data-related]').forEach" in source
    assert "$('[data-related]').forEach" not in source.replace("$$('[data-related]').forEach",'')
    assert 'id="v22-chart"' in source

def test_windows_shortcut_uses_new_v1_icon():
    installer=(ROOT/'installer/windows/twys.nsi').read_text()
    assert 'TWYS-v1.ico' in installer
    assert 'File /oname=TWYS-v1.ico' in installer
    assert 'assets\\twys-icon.ico' in installer

def test_public_version_and_profile_choices():
    with TestClient(app) as client:
        assert client.get('/api/health').json()['version']=='1.0.0'
        assert 'TWYS 1.0' in client.get('/').text
        assert 'previous_available' in client.get('/api/profile').json()
        assert client.post('/api/profile/select',json={'mode':'not-a-profile'}).status_code==400
