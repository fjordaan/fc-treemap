"""Extract GPS-tagged, sharpest frames from chosen time ranges of several DJI videos.

Usage: python -I extract_ranges.py <ranges.csv> <footage_dir> <out_dir> [options]
  ranges.csv needs columns file,start,end,keep; rows with keep=y are used.
  Overlapping/adjacent ranges of the same file are merged.
Options:
  --fixed M        take a frame every M metres (overrides --factor/--min)
  --factor F       spacing = F * altitude  (default 0.12, i.e. ~85-90% overlap)
  --min M          minimum spacing in metres (default 2)
  --max-interval S also take a frame at least every S seconds (default 3; 0 = off)
Movement includes altitude change, so climbs and descents get frames too.
"""
import argparse, csv, math, os, re, shutil, subprocess
from collections import defaultdict
from pathlib import Path
import cv2

FFMPEG = os.environ.get("FFMPEG", r"D:\Documents\Utilities\ffmpeg-20170204-b1e2192-win64-static\bin\ffmpeg.exe")
EXIFTOOL = os.environ.get("EXIFTOOL", str(Path.home() / r"AppData\Local\Programs\ExifTool\ExifTool.exe"))
OFFSETS = (-20, -10, 0, 10, 20)      # candidate frames around each target (50 fps -> +/-0.4 s)

ap = argparse.ArgumentParser()
ap.add_argument("ranges"); ap.add_argument("footage"); ap.add_argument("out")
ap.add_argument("--fixed", type=float); ap.add_argument("--factor", type=float, default=0.12)
ap.add_argument("--min", type=float, default=2.0); ap.add_argument("--max-interval", type=float, default=3.0)
args = ap.parse_args()
footage, out = Path(args.footage), Path(args.out)
out.mkdir(parents=True, exist_ok=True)

FRAME_RE = re.compile(
    r"SrtCnt : (\d+).*?\n(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\.(\d+).*?latitude: ([-\d.]+)\].*?longitude: ([-\d.]+)\]"
    r".*?rel_alt: ([-\d.]+) abs_alt: ([-\d.]+)", re.S)
FPS = 50


def move(a, b):
    dy = (b["lat"] - a["lat"]) * 111_200
    dx = (b["lon"] - a["lon"]) * 111_200 * math.cos(math.radians(a["lat"]))
    return math.sqrt(dx * dx + dy * dy + (b["rel"] - a["rel"]) ** 2)


ranges = defaultdict(list)
for r in csv.DictReader(open(args.ranges, encoding="utf-8-sig")):
    if r.get("keep", "").strip().lower() == "y":
        ranges[r["file"].strip().removesuffix(".MP4")].append((float(r["start"]), float(r["end"])))

rows_out, total = [], 0
for name in sorted(ranges):
    video = footage / f"{name}.MP4"
    text = video.with_suffix(".SRT").read_text(encoding="utf-8", errors="replace")
    frames = [dict(n=int(m[1]) - 1, dt=m[2], ms=m[3], lat=float(m[4]), lon=float(m[5]),
                   rel=float(m[6]), abs=float(m[7])) for m in FRAME_RE.finditer(text)]
    frames = [f for f in frames if abs(f["lat"]) > 0.01 or abs(f["lon"]) > 0.01]   # drop no-GPS-fix
    merged = []
    for s, e in sorted(ranges[name]):
        if merged and s <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])

    targets = []
    for s, e in merged:
        seg = [f for f in frames if s * FPS <= f["n"] <= (e + 1) * FPS]
        if not seg:
            continue
        acc, last_n, prev = float("inf"), None, None
        for f in seg:
            if prev is not None:
                acc += move(prev, f)
            prev = f
            spacing = args.fixed or max(args.min, args.factor * max(f["rel"], 1))
            due_time = args.max_interval and last_n is not None and f["n"] - last_n >= args.max_interval * FPS
            if acc >= spacing or due_time:
                targets.append(f["n"]); acc = 0.0; last_n = f["n"]
    if not targets:
        continue
    nmax = frames[-1]["n"]
    groups = [[min(max(t + o, 0), nmax) for o in OFFSETS] for t in targets]
    wanted = sorted({n for g in groups for n in g})
    print(f"{name}: {len(merged)} range(s), {len(targets)} frames ({len(wanted)} candidates)", flush=True)

    cand = out / "_candidates" / name
    shutil.rmtree(cand, ignore_errors=True); cand.mkdir(parents=True)
    script = cand / "select.txt"
    # Decode from the start (no seeking) so frame numbers match the SRT exactly
    script.write_text("select=" + "+".join(f"eq(n\\,{n})" for n in wanted))
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-i", str(video),
                    "-filter_script:v", str(script), "-vsync", "0", "-q:v", "2",
                    str(cand / "c_%05d.jpg")], check=True)
    files = sorted(cand.glob("c_*.jpg"))
    assert len(files) == len(wanted), f"{name}: decoded {len(files)} frames, expected {len(wanted)}"
    by_n = dict(zip(wanted, files))
    score = {}
    for n, p in by_n.items():
        g = cv2.imread(str(p), cv2.IMREAD_REDUCED_GRAYSCALE_2)
        score[n] = cv2.Laplacian(g, cv2.CV_64F).var()
    fmeta = {f["n"]: f for f in frames}
    used = set()
    for i, g in enumerate(groups):
        g = [n for n in g if n in fmeta and n not in used]
        if not g:
            continue          # targets closer than the candidate window: nothing new to add
        best = max(g, key=lambda n: score[n])
        used.add(best)
        f = fmeta.get(best) or fmeta[min(fmeta, key=lambda n: abs(n - best))]
        fname = f"{name}_{i:03d}_f{best:05d}.jpg"
        shutil.copy2(by_n[best], out / fname)
        rows_out.append({"SourceFile": (out / fname).as_posix(),
                         "Make": "DJI", "FocalLengthIn35mmFormat": 24,
                         "DateTimeOriginal": f["dt"].replace("-", ":"), "SubSecTimeOriginal": f["ms"],
                         "GPSLatitude": abs(f["lat"]), "GPSLatitudeRef": "N" if f["lat"] >= 0 else "S",
                         "GPSLongitude": abs(f["lon"]), "GPSLongitudeRef": "E" if f["lon"] >= 0 else "W",
                         "GPSAltitude": f["abs"], "GPSAltitudeRef": 0 if f["abs"] >= 0 else 1,
                         "UserComment": f"rel_alt={f['rel']} frame={best} sharpness={score[best]:.0f}"})
    shutil.rmtree(cand)

shutil.rmtree(out / "_candidates", ignore_errors=True)
meta = out / "frames_metadata.csv"
with open(meta, "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows_out[0].keys())); w.writeheader(); w.writerows(rows_out)
subprocess.run([EXIFTOOL, "-q", "-n", "-overwrite_original", "-ext", "jpg", f"-csv={meta}", out.as_posix()], check=True)
print(f"wrote {len(rows_out)} frames to {out}")
