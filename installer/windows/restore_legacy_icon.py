"""Restore the original TWYS wordmark/market arrow for Windows desktop branding."""
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
mark=Image.open(ROOT/'static'/'twys-mark.png').convert('RGBA')
if mark.size!=(1024,1024):
    raise SystemExit('Expected original TWYS wordmark at 1024px')
# Keep the old white wordmark, but make its black backdrop transparent.
mark.putalpha(mark.convert('L').point(lambda value:0 if value<32 else value))
for target in (ROOT/'assets'/'twys-icon.png',ROOT/'static'/'twys-icon.png'):
    mark.save(target,format='PNG',optimize=True)
mark.save(ROOT/'assets'/'twys-icon.ico',format='ICO',
          sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
print('Restored original TWYS wordmark desktop icon')
