"""Make labelled contact sheets for time ranges listed in a CSV (file,start,end,alt,spots,...).

Usage: python -I contact_sheets.py <ranges.csv> <footage_dir> <telemetry_per_second.csv> <out_dir> [step_s=2]
"""
import csv, os, subprocess, sys, tempfile
from pathlib import Path
import cv2, numpy as np

FFMPEG = os.environ.get("FFMPEG", r"D:\Documents\Utilities\ffmpeg-20170204-b1e2192-win64-static\bin\ffmpeg.exe")
ranges, footage, tele, out = sys.argv[1], Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4])
STEP = float(sys.argv[5]) if len(sys.argv) > 5 else 2.0
W, COLS = 480, 4
out.mkdir(parents=True, exist_ok=True)
alt = {(r["file"], int(r["t"])): float(r["alt"]) for r in csv.DictReader(open(tele))}

for rg in csv.DictReader(open(ranges)):
    f, s, e = rg["file"], int(rg["start"]), int(rg["end"])
    times = list(np.arange(s, e + 1, STEP)) or [s]
    thumbs = []
    with tempfile.TemporaryDirectory() as td:
        for k, t in enumerate(times):
            p = Path(td) / f"{k}.jpg"
            subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-ss", f"{t:.2f}",
                            "-i", str(footage / f"{f}.MP4"), "-frames:v", "1",
                            "-vf", f"scale={W}:-2", "-q:v", "4", str(p)], check=True)
            im = cv2.imread(str(p))
            if im is None:
                continue
            label = f"{f}  {t:.0f}s  {alt.get((f, int(t)), 0):.0f}m"
            cv2.rectangle(im, (0, 0), (W, 26), (0, 0, 0), -1)
            cv2.putText(im, label, (6, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
            thumbs.append(im)
    if not thumbs:
        continue
    h = thumbs[0].shape[0]
    rows = (len(thumbs) + COLS - 1) // COLS
    sheet = np.full((rows * h, COLS * W, 3), 255, np.uint8)
    for k, im in enumerate(thumbs):
        y, x = divmod(k, COLS)
        sheet[y * h:y * h + im.shape[0], x * W:x * W + W] = im[:, :W]
    name = f"{f}_{s:03d}-{e:03d}s_spots-{rg['spots'].replace(' ', '-')}.jpg"
    cv2.imwrite(str(out / name), sheet, [cv2.IMWRITE_JPEG_QUALITY, 85])
    print(name)
