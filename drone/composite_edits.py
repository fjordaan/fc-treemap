"""Paste Photoshop-edited crops back into the master orthophoto.

Usage: python -I composite_edits.py <master.tif> <edited_dir> <out.tif> <report_dir>
Each edited file is named crop_NN_x<col>_y<row>_<w>x<h>.tif (its position in the master).
Only pixels that differ from the master are written, so overlapping crops combine. A pixel changed
differently in two crops is a conflict: the later crop wins and it is reported. Alpha is kept.
Writes before/after JPGs per crop to report_dir.
"""
import re, sys
from pathlib import Path
import cv2, numpy as np, rasterio

master, edited, dst, rep = sys.argv[1:5]
# Optional 5th arg: area ids to paste FIRST (so overlapping crops pasted later win), e.g. "5,15"
FIRST = [int(x) for x in sys.argv[5].split(",")] if len(sys.argv) > 5 else []
rep = Path(rep); rep.mkdir(parents=True, exist_ok=True)
with rasterio.open(master) as d:
    prof = d.profile.copy()
    img = d.read()                                   # (4, H, W) RGBA
orig = img[:3].copy()
owner = np.zeros(img.shape[1:], np.uint8)           # which crop last changed a pixel
problems = 0
def order(f):
    aid = int(re.match(r"crop_(\d+)", f.name).group(1)) if re.match(r"crop_(\d+)", f.name) else 999
    return (FIRST.index(aid) if aid in FIRST else len(FIRST), aid)
for f in sorted(Path(edited).glob("crop_*.tif"), key=order):
    m = re.match(r"crop_(\d+)_x(\d+)_y(\d+)_(\d+)x(\d+)\.tif$", f.name)
    if not m:
        print(f"{f.name}: name not understood, skipped"); problems += 1; continue
    aid, c0, r0, w, h = map(int, m.groups())
    e = cv2.imread(str(f), cv2.IMREAD_UNCHANGED)
    if e is None or e.dtype != np.uint8 or e.ndim != 3 or e.shape[2] not in (3, 4):
        print(f"{f.name}: not an 8-bit RGB TIFF ({None if e is None else (e.dtype, e.shape)}), skipped"); problems += 1; continue
    if e.shape[:2] != (h, w):
        print(f"{f.name}: size {e.shape[1]}x{e.shape[0]} differs from {w}x{h}, skipped"); problems += 1; continue
    new = np.transpose(e[:, :, 2::-1] if e.shape[2] == 3 else e[:, :, [2, 1, 0]], (2, 0, 1))   # BGR -> RGB, (3,h,w)
    win = (slice(r0, r0 + h), slice(c0, c0 + w))
    before = orig[:, win[0], win[1]]
    changed = (new != before).any(0)
    frac = changed.mean()
    diff = np.abs(new.astype(int) - before).max(0)[changed]
    tiny = (diff <= 3).mean() if changed.any() else 0
    cur = img[:3, win[0], win[1]]
    prev = owner[win]
    conflict = changed & (prev > 0) & (cur != new).any(0)
    cur[:, changed] = new[:, changed]
    prev[changed] = aid
    alpha0 = (changed & (img[3][win] == 0)).sum()
    warn = []
    if frac > 0.9 and tiny > 0.5:
        warn.append("almost every pixel changed slightly: colour profile conversion on save?")
    if conflict.any():
        warn.append(f"{conflict.sum()} px also changed in an earlier crop, this one wins")
    if alpha0:
        warn.append(f"{alpha0} changed px are in transparent (no-data) area, invisible")
    print(f"area {aid:2d}: {changed.sum():8d} px changed ({frac:5.1%}) " + ("; ".join(warn) if warn else "ok"), flush=True)
    # before / after with changed area outlined
    b = np.ascontiguousarray(np.transpose(before, (1, 2, 0))[:, :, ::-1])
    a = np.ascontiguousarray(np.transpose(new, (1, 2, 0))[:, :, ::-1])
    s = min(1.0, 900 / max(h, w))
    b, a = [cv2.resize(x, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) for x in (b, a)]
    mk = cv2.resize(changed.astype(np.uint8) * 255, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_NEAREST)
    cnts, _ = cv2.findContours(cv2.dilate(mk, np.ones((5, 5), np.uint8)), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    o = b.copy(); cv2.drawContours(o, cnts, -1, (0, 0, 255), 2)
    cv2.imwrite(str(rep / f"area_{aid:02d}_before_after.jpg"),
                np.hstack([o, np.full((o.shape[0], 10, 3), 255, np.uint8), a]), [cv2.IMWRITE_JPEG_QUALITY, 88])

prof.update(compress="deflate", tiled=True, blockxsize=512, blockysize=512, BIGTIFF="IF_SAFER")
with rasterio.open(dst, "w", **prof) as out:
    out.write(img)
print(f"wrote {dst}" + (f"; {problems} file(s) skipped" if problems else ""))
