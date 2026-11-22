"""Make everything outside the cemetery transparent, so the base map shows through there.

Usage: python -I mask_to_cemetery.py <index.html> <ortho_in.tif> <ortho_out.tif> [buffer_m=15] [feather_m=4]
The cemetery outline is the union of the app's SECTIONS polygons (from index.html), closed to
fill the paths between sections, then buffered by buffer_m, with a feather_m soft edge.
"""
import re, sys
import numpy as np, cv2, rasterio
from pyproj import Transformer

html, src, dst = sys.argv[1:4]
BUF = float(sys.argv[4]) if len(sys.argv) > 4 else 15.0
FEATHER = float(sys.argv[5]) if len(sys.argv) > 5 else 4.0
R = 0.5   # mask resolution in metres

text = open(html, encoding="utf-8").read()
block = text[text.index("const SECTIONS = ["):]
block = block[:block.index("];")]
polys = [[(float(a), float(b)) for a, b in re.findall(r"\[(51\.\d+),\s*(-0\.\d+)\]", m)]
         for m in re.findall(r"coords:\[(.*?)\]\}", block)]
print(f"{len(polys)} section polygons")

with rasterio.open(src) as d:
    prof = d.profile.copy(); T = d.transform; W, H = d.width, d.height; crs = d.crs
    to = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    # mask grid at R metres
    mw, mh = int(W * T.a / R) + 1, int(H * -T.e / R) + 1
    mask = np.zeros((mh, mw), np.uint8)
    for p in polys:
        pts = []
        for lat, lon in p:
            x, y = to.transform(lon, lat)
            pts.append([(x - T.c) / R, (T.f - y) / R])
        cv2.fillPoly(mask, [np.round(pts).astype(np.int32)], 255)
    # The west entrance drive (Fulham Palace Road) isn't in any section: add it explicitly.
    for lat, lon, radius_m in ((51.48066, -0.21770, 14),):
        x, y = to.transform(lon, lat)
        cv2.circle(mask, (round((x - T.c) / R), round((T.f - y) / R)), round(radius_m / R), 255, -1)
    k = lambda m: cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (int(2 * m / R) + 1,) * 2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k(30))          # bridge paths and the west entrance between sections
    mask = cv2.dilate(mask, k(BUF))
    soft = cv2.GaussianBlur(mask.astype(np.float32) / 255, (0, 0), FEATHER / R / 2)
    soft = np.clip((soft - 0.5) * 2 + 0.5, 0, 1)
    print(f"cemetery + {BUF:.0f} m covers {(mask > 0).sum() * R * R / 10000:.1f} ha")

    prof.update(compress="deflate", tiled=True, blockxsize=512, blockysize=512, BIGTIFF="IF_SAFER")
    with rasterio.open(dst, "w", **prof) as out:
        for _, win in d.block_windows(1):
            data = d.read(window=win)
            r0, c0 = win.row_off, win.col_off
            rows = ((np.arange(win.height) + r0) * -T.e / R).astype(int).clip(0, mh - 1)
            cols = ((np.arange(win.width) + c0) * T.a / R).astype(int).clip(0, mw - 1)
            m = soft[np.ix_(rows, cols)]
            data[3] = (data[3].astype(np.float32) * m).astype(np.uint8)
            out.write(data, window=win)
print("wrote", dst)
