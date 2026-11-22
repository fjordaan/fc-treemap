"""Extract evenly spaced (by ground distance), sharpest frames from a DJI video, GPS-tagged.

Usage: python -I extract_frames.py <video.MP4> <out_dir> [spacing_m=10] [min_alt=110]
Needs: ffmpeg (FFMPEG env or default path below), exiftool (EXIFTOOL env), opencv-python, numpy.
"""
import csv, math, os, re, shutil, subprocess, sys
from pathlib import Path
import cv2

FFMPEG = os.environ.get("FFMPEG", r"D:\Documents\Utilities\ffmpeg-20170204-b1e2192-win64-static\bin\ffmpeg.exe")
EXIFTOOL = os.environ.get("EXIFTOOL", str(Path.home() / r"AppData\Local\Programs\ExifTool\ExifTool.exe"))

video, out = Path(sys.argv[1]), Path(sys.argv[2])
SPACING = float(sys.argv[3]) if len(sys.argv) > 3 else 10.0
MIN_ALT = float(sys.argv[4]) if len(sys.argv) > 4 else 110.0
OFFSETS = (-20, -10, 0, 10, 20)          # candidate frames around each target (50 fps -> +/-0.4 s)

srt = video.with_suffix(".SRT")
text = srt.read_text(encoding="utf-8", errors="replace")
FRAME_RE = re.compile(
    r"SrtCnt : (\d+).*?\n(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\.(\d+).*?latitude: ([-\d.]+)\].*?longitude: ([-\d.]+)\]"
    r".*?rel_alt: ([-\d.]+) abs_alt: ([-\d.]+)", re.S)
frames = []
for m in FRAME_RE.finditer(text):
    frames.append(dict(n=int(m[1]) - 1, dt=m[2], ms=m[3], lat=float(m[4]), lon=float(m[5]),
                       rel=float(m[6]), abs=float(m[7])))
print(f"{len(frames)} telemetry frames")


def dist(a, b):
    dy = (b["lat"] - a["lat"]) * 111_200
    dx = (b["lon"] - a["lon"]) * 111_200 * math.cos(math.radians(a["lat"]))
    return math.hypot(dx, dy)


# Pick target frames every SPACING metres of ground track (only at mapping altitude)
targets, acc, prev = [], SPACING, None
for f in frames:
    if f["rel"] < MIN_ALT:
        prev = None
        continue
    if prev is not None:
        acc += dist(prev, f)
    prev = f
    if acc >= SPACING:
        targets.append(f["n"]); acc = 0.0
nmax = frames[-1]["n"]
groups = [[min(max(t + o, 0), nmax) for o in OFFSETS] for t in targets]
wanted = sorted({n for g in groups for n in g})
print(f"{len(targets)} target positions, {len(wanted)} candidate frames to decode")

cand = out / "_candidates"
shutil.rmtree(cand, ignore_errors=True); cand.mkdir(parents=True)
script = cand / "select.txt"
script.write_text("select=" + "+".join(f"eq(n\\,{n})" for n in wanted))
subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-i", str(video),
                "-filter_script:v", str(script), "-vsync", "0", "-q:v", "2",
                str(cand / "c_%05d.jpg")], check=True)
files = sorted(cand.glob("c_*.jpg"))
assert len(files) == len(wanted), f"decoded {len(files)} frames, expected {len(wanted)}"
by_n = dict(zip(wanted, files))


def sharpness(p):
    g = cv2.imread(str(p), cv2.IMREAD_REDUCED_GRAYSCALE_2)
    return cv2.Laplacian(g, cv2.CV_64F).var()


score = {n: sharpness(p) for n, p in by_n.items()}
fmeta = {f["n"]: f for f in frames}
rows = []
for i, g in enumerate(groups):
    best = max(g, key=lambda n: score[n])
    f = fmeta[best]
    name = f"{video.stem}_{i:03d}_f{best:05d}.jpg"
    shutil.copy2(by_n[best], out / name)
    rows.append({"SourceFile": (out / name).as_posix(),
                 "Make": "DJI", "FocalLengthIn35mmFormat": 24,
                 "DateTimeOriginal": f["dt"].replace("-", ":"), "SubSecTimeOriginal": f["ms"],
                 "GPSLatitude": abs(f["lat"]), "GPSLatitudeRef": "N" if f["lat"] >= 0 else "S",
                 "GPSLongitude": abs(f["lon"]), "GPSLongitudeRef": "E" if f["lon"] >= 0 else "W",
                 "GPSAltitude": f["abs"], "GPSAltitudeRef": 0 if f["abs"] >= 0 else 1,
                 "UserComment": f"rel_alt={f['rel']} frame={best} sharpness={score[best]:.0f}"})

meta = out / "frames_metadata.csv"
with open(meta, "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
subprocess.run([EXIFTOOL, "-q", "-n", "-overwrite_original", "-ext", "jpg", f"-csv={meta}", out.as_posix()], check=True)
shutil.rmtree(cand)
print(f"wrote {len(rows)} frames to {out}")
