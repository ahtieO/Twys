"""Versioned, non-destructive local profiles for TWYS Windows desktop."""
from __future__ import annotations
import json, os, sys, uuid
from datetime import datetime, timezone
from pathlib import Path

def profiles_root() -> Path:
    if sys.platform == 'win32':
        return Path(os.getenv('APPDATA') or Path.home()/'AppData'/'Roaming')/'TWYS'
    if sys.platform == 'darwin':
        return Path.home()/'Library'/'Application Support'/'TWYS'
    return Path(os.getenv('XDG_DATA_HOME') or Path.home()/'.local'/'share')/'TWYS'

def legacy_profile(root: Path | None = None) -> Path:
    return (root or profiles_root())/'v2'

def _selection_path(root: Path) -> Path:
    return root/'profile_selection.json'

def _write_selection(root: Path, path: Path, profile_id: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    tmp=_selection_path(root).with_suffix('.tmp')
    tmp.write_text(json.dumps({'profile_path':str(path),'profile_id':profile_id},indent=2),encoding='utf-8')
    tmp.replace(_selection_path(root))

def _load_selection(root: Path) -> tuple[Path,str] | None:
    try:
        saved=json.loads(_selection_path(root).read_text(encoding='utf-8'))
        path=Path(saved['profile_path']).resolve()
        identity=str(saved.get('profile_id') or '')
        if not path.is_relative_to(root.resolve()):return None
        if path==legacy_profile(root).resolve() and identity=='legacy':return path,identity
        if path.parent==(root/'profiles').resolve() and identity==path.name:return path,identity
    except (OSError,ValueError,KeyError,TypeError):pass
    return None

def select_profile(mode: str, root: Path | None = None) -> tuple[Path,str]:
    """Write selection for the NEXT launch. No data or keychain records are deleted."""
    root=(root or profiles_root()).resolve()
    if mode=='existing':path,identity=legacy_profile(root),'legacy'
    elif mode=='fresh':
        identity='fresh-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]
        path=root/'profiles'/identity
    else:raise ValueError('Choose existing or fresh')
    path.mkdir(parents=True,exist_ok=True)
    _write_selection(root,path,identity)
    return path,identity

def choose_on_launch(interactive: bool = True) -> tuple[Path,str] | None:
    """Must run before importing the database-backed app."""
    if os.getenv('TWYS_DATA_DIR'):
        return Path(os.environ['TWYS_DATA_DIR']),os.getenv('TWYS_PROFILE_ID','legacy')
    root=profiles_root().resolve()
    existing=_load_selection(root)
    if existing:chosen=existing
    elif (legacy_profile(root)/'twys.sqlite3').is_file() and interactive and sys.platform=='win32':
        import ctypes
        message=('TWYS found a previous local journal.\n\n'
                 'YES: Continue with your existing trades and settings.\n'
                 'NO: Start with an empty TWYS profile.\n'
                 'CANCEL: Close TWYS without changing anything.\n\n'
                 'Your old files are never deleted.')
        choice=ctypes.windll.user32.MessageBoxW(None,message,'TWYS 2.9 · Choose your data',0x23)
        if choice==2:return None
        chosen=select_profile('existing' if choice==6 else 'fresh',root)
    else:chosen=select_profile('existing',root)
    path,identity=chosen
    os.environ['TWYS_DATA_DIR']=str(path)
    os.environ['TWYS_PROFILE_ID']=identity
    return chosen

def status() -> dict:
    root=profiles_root().resolve()
    saved=_load_selection(root)
    current_id=os.getenv('TWYS_PROFILE_ID') or (saved[1] if saved else 'legacy')
    current_path=Path(os.getenv('TWYS_DATA_DIR') or (saved[0] if saved else legacy_profile(root)))
    return {'profile_id':current_id,'is_legacy':current_id=='legacy',
            'data_directory':str(current_path),
            'legacy_available':(legacy_profile(root)/'twys.sqlite3').is_file(),
            'restart_required':bool(saved and saved[1]!=current_id)}
