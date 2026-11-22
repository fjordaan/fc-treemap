"""Side-by-side crops of two georeferenced orthophotos at each problem spot.

Usage: python -I compare_spots.py <spots.json> <a.tif> <b.tif> <out_dir> [label_a] [label_b]
Both TIFFs need a .tfw world file in the same UTM zone (EPSG:32630).
"""
import json, math, sys
from pathlib import Path
import cv2, numpy as np
from pyproj import Transformer

spots = json.load(open(sys.argv[1]))
tifs = [Path(sys.argv[2]), Path(sys.argv[3])]
out = Path(sys.argv[4]); out.mkdir(parents=True, exist_ok=True)
labels = sys.argv[5:7] or ["v1", "v2"]
T = Transformer.from_crs("EPSG:4326", "EPSG:32630", always_xy=True)
TILE = 360

imgs = []
for t in tifs:
    im = cv2.imread(str(t), cv2.IMREAD_UNCHANGED)
    a, _, _, e, x0, y0 = [float(v) for v in t.with_suffix(".tfw").read_text().split()]
    if im.shape[2] == 4:                      # flatten transparency onto white
        al = im[:, :, 3:] / 255.0
        im = (im[:, :, :3] * al + 255 * (1 - al)).astype(np.uint8)
    imgs.append((im, a, e, x0, y0))


def crop(img, x, y, half):
    im, a, e, x0, y0 = img
    c0, c1 = int((x - half - x0) / a), int((x + half - x0) / a)
    r0, r1 = int((y + half - y0) / e), int((y - half - y0) / e)
    canvas = np.full((r1 - r0, c1 - c0, 3), 255, np.uint8)
    sr0, sc0 = max(r0, 0), max(c0, 0)
    sr1, sc1 = min(r1, im.shape[0]), min(c1, im.shape[1])
    if sr1 > sr0 and sc1 > sc0:
        canvas[sr0 - r0:sr1 - r0, sc0 - c0:sc1 - c0] = im[sr0:sr1, sc0:sc1]
    return cv2.resize(canvas, (TILE, TILE), interpolation=cv2.INTER_AREA)


pairs = []
for s in spots:
    x, y = T.transform(s["lon"], s["lat"])
    half = max(12.0, math.sqrt(s["area_m2"]) * 1.3)
    row = []
    for img, lab in zip(imgs, labels):
        c = crop(img, x, y, half)
        cv2.rectangle(c, (0, 0), (TILE, 24), (0, 0, 0), -1)
        cv2.putText(c, f"spot {s['id']}  {lab}  ({2 * half:.0f} m)", (6, 17),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
        row.append(c)
    pair = np.hstack([row[0], np.full((TILE, 4, 3), 0, np.uint8), row[1]])
    cv2.imwrite(str(out / f"spot_{s['id']:02d}.jpg"), pair, [cv2.IMWRITE_JPEG_QUALITY, 90])
    pairs.append(pair)

# Overview sheets: 3 pairs per row, 15 pairs per sheet
PER_ROW, PER_SHEET = 3, 15
pw = pairs[0].shape[1]
for k in range(0, len(pairs), PER_SHEET):
    chunk = pairs[k:k + PER_SHEET]
    rows = [np.hstack(chunk[i:i + PER_ROW] + [np.full((TILE, pw, 3), 255, np.uint8)] * (PER_ROW - len(chunk[i:i + PER_ROW])))
            for i in range(0, len(chunk), PER_ROW)]
    rows = [np.vstack([r, np.full((8, r.shape[1], 3), 255, np.uint8)]) for r in rows]
    cv2.imwrite(str(out / f"overview_{k // PER_SHEET + 1}.jpg"), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 85])
print(f"{len(pairs)} spot comparisons written to {out}")
