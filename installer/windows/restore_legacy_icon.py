"""Create the approved TWYS white-on-black Windows shortcut icon.
The polygons are traced from the user-supplied 2000px square TWYS artwork.
Art is rendered with antialiasing; no app/interface logo is changed.
"""
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
# 512x512 coordinate space, based on the uploaded artwork's tight square crop.
MARK_PATHS = [
 [[402,200],[380,222],[380,244],[401,265],[380,287],[402,309],[469,309],[491,287],[491,265],[470,245],[491,222],[469,200]],
 [[287,200],[287,201],[265,222],[265,287],[264,288],[285,310],[264,331],[287,355],[353,355],[376,332],[376,223],[352,200],[330,223],[330,264],[329,265],[312,265],[311,264],[311,223]],
 [[20,288],[42,309],[65,309],[84,291],[85,289],[86,290],[86,309],[120,309],[146,284],[147,282],[148,283],[148,309],[182,309],[260,233],[261,231],[261,200],[228,200],[200,227],[199,226],[199,200],[166,200],[133,232],[132,231],[132,222],[116,205],[109,199],[86,222],[86,240],[85,241],[67,224],[65,221],[65,177],[45,157],[40,157],[20,177]],
 [[85,246],[86,247],[86,283],[85,284],[67,266]]
]
size=512
scale=4
canvas=Image.new('RGB',(size*scale,size*scale),'black')
brush=ImageDraw.Draw(canvas)
for index,polygon in enumerate(MARK_PATHS):
    brush.polygon([(x*scale,y*scale) for x,y in polygon],
                  fill='black' if index==3 else 'white')
art=canvas.resize((size,size),Image.Resampling.LANCZOS)
art.save(ROOT/'assets'/'twys-icon.png',format='PNG',optimize=True)
art.save(ROOT/'assets'/'twys-icon.ico',format='ICO',
         sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
print('TWYS approved desktop shortcut icon ready (white artwork, black background).')
