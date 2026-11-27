"""Cut lossless edit crops of painted areas from the master orthophoto, and find overhead stills.

Usage: python -I make_edit_kit.py <painted.png> <paint.json> <master.tif> <ranges.csv> <footage_dir> <out_dir>
Writes per area:
  crop_NN_x<col>_y<row>_<w>x<h>.tif   RGB crop of the master (edit this; keep size)
  stills/area_NN_<rank>_<clip>_f<frame>_<alt>m_off<d>m.png   most overhead video frames
and areas.json with crop positions (for pasting back) and area centres.
"""
import csv, json, math, os, re, subprocess, sys
from collections import defaultdict
from pathlib import Path
import cv2, numpy as np, rasterio
from pyproj import Transformer

painted, pjson, master, ranges_csv, footage, out = sys.argv[1:7]
footage, out = Path(footage), Path(out)
(out / "stills").mkdir(parents=True, exist_ok=True)
FFMPEG = os.environ.get("FFMPEG", r"D:\Documents\Utilities\ffmpeg-20170204-b1e2192-win64-static\bin\ffmpeg.exe")
MARGIN_M, N_STILLS, FPS = 4.0, 3, 50
SHIFT = (-0.56, -0.29)            # master was shifted by this; drone GPS is in the unshifted frame

meta = json.load(open(pjson))
im = cv2.imread(painted); b, g, r = [im[:, :, i].astype(int) for i in range(3)]
n, lab, st, cen = cv2.connectedComponentsWithStats(((r > 200) & (g < 60) & (b < 60)).astype(np.uint8), 8)

areas = []
with rasterio.open(master) as d:
    T, W, H, crs = d.transform, d.width, d.height, d.crs
    to_ll = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    m = int(MARGIN_M / T.a)
    for i in range(1, n):
        x, y, w, h, _ = st[i]
        c0 = max(int(meta["offset_x"] + x * meta["scale"]) - m, 0)
        r0 = max(int(meta["offset_y"] + y * meta["scale"]) - m, 0)
        c1 = min(int(meta["offset_x"] + (x + w) * meta["scale"]) + m, W)
        r1 = min(int(meta["offset_y"] + (y + h) * meta["scale"]) + m, H)
        win = rasterio.windows.Window(c0, r0, c1 - c0, r1 - r0)
        data = d.read(window=win)
        rgb = np.transpose(data[:3], (1, 2, 0))[:, :, ::-1]          # to BGR for OpenCV
        name = f"crop_{i:02d}_x{c0:05d}_y{r0:05d}_{c1 - c0}x{r1 - r0}.tif"
        cv2.imwrite(str(out / name), rgb, [cv2.IMWRITE_TIFF_COMPRESSION, 5])   # LZW, lossless
        cx, cy = T * ((c0 + c1) / 2, (r0 + r1) / 2)
        lon, lat = to_ll.transform(cx - SHIFT[0], cy - SHIFT[1])        # back to GPS frame
        areas.append(dict(id=i, file=name, col=c0, row=r0, width=c1 - c0, height=r1 - r0,
                          lat=lat, lon=lon, size_m=[round((c1 - c0) * T.a, 1), round((r1 - r0) * T.a, 1)]))
        print(f"area {i:2d}: {name}  ({areas[-1]['size_m'][0]} x {areas[-1]['size_m'][1]} m)")

# Candidate footage: survey flight + user-kept ranges (known straight-down or near it)
use = defaultdict(list)
use["DJI_0422"].append((0, 9999))
for row in csv.DictReader(open(ranges_csv, encoding="utf-8-sig")):
    if row.get("keep", "").strip().lower() == "y":
        use[row["file"].strip()].append((float(row["start"]), float(row["end"])))
FRAME_RE = re.compile(r"SrtCnt : (\d+).*?latitude: ([-\d.]+)\].*?longitude: ([-\d.]+)\].*?rel_alt: ([-\d.]+)", re.S)
frames = []
for clip, rs in use.items():
    for mm in FRAME_RE.finditer((footage / f"{clip}.SRT").read_text(encoding="utf-8", errors="replace")):
        fn, la, lo, al = int(mm[1]) - 1, float(mm[2]), float(mm[3]), float(mm[4])
        if al > 12 and any(s * FPS <= fn <= (e + 1) * FPS for s, e in rs) and abs(la) > 0.01:
            frames.append((clip, fn, la, lo, al))

wanted = defaultdict(set)
for a in areas:
    kx = 111_200 * math.cos(math.radians(a["lat"]))
    scored = sorted(((math.hypot((lo - a["lon"]) * kx, (la - a["lat"]) * 111_200), al, clip, fn)
                     for clip, fn, la, lo, al in frames), key=lambda t: t[0] / t[1])
    picks = []
    for dist, al, clip, fn in scored:
        if dist / al > 0.35:
            break
        if all(not (c == clip and abs(f - fn) < 4 * FPS) for _, _, c, f in picks):   # >=4 s apart
            picks.append((dist, al, clip, fn))
        if len(picks) == N_STILLS:
            break
    a["stills"] = []
    for k, (dist, al, clip, fn) in enumerate(picks, 1):
        name = f"area_{a['id']:02d}_{k}_{clip}_f{fn:05d}_{al:.0f}m_off{dist:.0f}m.png"
        a["stills"].append(name); wanted[clip].add((fn, name))
    print(f"area {a['id']:2d}: {len(picks)} stills " + ", ".join(f"{c} {al:.0f}m off {d:.0f}m" for d, al, c, _ in picks))

json.dump(areas, open(out / "areas.json", "w"), indent=1)

# Extract stills losslessly (PNG), one decode pass per clip
for clip, items in wanted.items():
    items = sorted(items)
    tmp = out / "stills" / f"_{clip}"
    tmp.mkdir(exist_ok=True)
    sel = "+".join(f"eq(n\\,{fn})" for fn in sorted({fn for fn, _ in items}))
    (tmp / "sel.txt").write_text("select=" + sel)
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-i", str(footage / f"{clip}.MP4"),
                    "-filter_script:v", str(tmp / "sel.txt"), "-vsync", "0", str(tmp / "s_%04d.png")], check=True)
    outs = sorted(tmp.glob("s_*.png"))
    fns = sorted({fn for fn, _ in items})
    assert len(outs) == len(fns), f"{clip}: got {len(outs)} frames, wanted {len(fns)}"
    by_fn = dict(zip(fns, outs))
    for fn, name in items:
        data = by_fn[fn].read_bytes()
        (out / "stills" / name).write_bytes(data)
    for p in tmp.iterdir():
        p.unlink()
    tmp.rmdir()
    print(f"{clip}: {len(items)} stills extracted", flush=True)
print("done")
