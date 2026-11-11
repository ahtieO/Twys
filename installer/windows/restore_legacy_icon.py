"""Convert the exact user-supplied TWYS launch artwork into Windows icons."""
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
source=ROOT/'assets'/'twys-launch-art.png'
im=Image.open(source).convert('RGB')
if im.getpixel((0,0))!=(0,0,0):
    raise ValueError('Approved TWYS logo must retain its black background')
im=im.resize((512,512),Image.Resampling.LANCZOS)
im.save(ROOT/'assets'/'twys-icon.png',optimize=True)
im.save(ROOT/'static'/'twys-icon.png',optimize=True)
im.save(ROOT/'assets'/'twys-icon.ico',format='ICO',
        sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
print('TWYS 1.0 desktop icon generated from approved uploaded artwork')
