"""Map red-painted problem spots to lat/lon and find video moments where the drone was above them.

Usage: python -I find_coverage.py <painted.png> <ortho.tfw> <ortho_width_px> <telemetry_per_second.csv> <out_dir>
A spot counts as "seen" when the drone's horizontal distance to it is < FOOT * altitude
(roughly inside the frame of a straight-down camera). Gimbal angle is unknown, so
angled footage is only caught if the drone happened to be nearby.
"""
import csv, json, math, sys
from collections import defaultdict
from pathlib import Path
import cv2, numpy as np
from pyproj import Transformer

painted, tfw, ortho_w, tele, out = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4], Path(sys.argv[5])
out.mkdir(parents=True, exist_ok=True)
FOOT, MIN_ALT, SKIP = 0.4, 15.0, {"DJI_0422"}   # DJI_0422 already used

a, _, _, e, x0, y0 = [float(v) for v in open(tfw).read().split()]
im = cv2.imread(painted)
scale = ortho_w / im.shape[1]
b, g, r = [im[:, :, i].astype(int) for i in range(3)]
mask = ((r > 200) & (g < 60) & (b < 60)).astype("uint8")
n, lab, stats, cent = cv2.connectedComponentsWithStats(mask, 8)
to_ll = Transformer.from_crs("EPSG:32630", "EPSG:4326", always_xy=True)

spots = []
for i in range(1, n):
    ys, xs = np.nonzero(lab == i)
    sel = np.linspace(0, len(xs) - 1, min(len(xs), 40)).astype(int)     # sample points across the blob
    pts = []
    for px, py in zip(xs[sel], ys[sel]):
        lon, lat = to_ll.transform(x0 + px * scale * a, y0 + py * scale * e)
        pts.append((lat, lon))
    clon, clat = to_ll.transform(x0 + cent[i][0] * scale * a, y0 + cent[i][1] * scale * e)
    spots.append(dict(id=i, lat=clat, lon=clon, area_m2=round(stats[i][4] * (scale * a) ** 2), pts=pts))

rows = list(csv.DictReader(open(tele)))
hits = defaultdict(lambda: defaultdict(list))     # file -> spot id -> [seconds]
for r_ in rows:
    if r_["file"] in SKIP or float(r_["alt"]) < MIN_ALT:
        continue
    lat, lon, alt = float(r_["lat"]), float(r_["lon"]), float(r_["alt"])
    kx = 111_200 * math.cos(math.radians(lat))
    for s in spots:
        if any(math.hypot((p[1] - lon) * kx, (p[0] - lat) * 111_200) < FOOT * alt for p in s["pts"]):
            hits[r_["file"]][s["id"]].append(int(r_["t"]))

# Merge seconds into time ranges per file
ranges = []
for f, by_spot in hits.items():
    secs = sorted({t for ts in by_spot.values() for t in ts})
    start = prev = secs[0]
    for t in secs[1:] + [None]:
        if t is None or t - prev > 2:
            covered = sorted(sid for sid, ts in by_spot.items() if any(start <= x <= prev for x in ts))
            alts = [float(r_["alt"]) for r_ in rows if r_["file"] == f and start <= int(r_["t"]) <= prev]
            ranges.append(dict(file=f, start=start, end=prev, alt=round(sum(alts) / len(alts)),
                               spots=" ".join(map(str, covered))))
            start = t
        prev = t if t is not None else prev

with open(out / "spots.csv", "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["spot", "lat", "lon", "area_m2", "files_covering"])
    for s in spots:
        w.writerow([s["id"], round(s["lat"], 6), round(s["lon"], 6), s["area_m2"],
                    " ".join(sorted(f for f in hits if s["id"] in hits[f]))])
with open(out / "candidate_ranges.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["file", "start", "end", "alt", "spots", "keep"]); w.writeheader()
    for rg in sorted(ranges, key=lambda x: (x["file"], x["start"])):
        w.writerow({**rg, "keep": ""})
json.dump([{k: v for k, v in s.items() if k != "pts"} for s in spots], open(out / "spots.json", "w"), indent=1)

uncovered = [s["id"] for s in spots if not any(s["id"] in hits[f] for f in hits)]
print(f"{len(spots)} spots, {len(ranges)} candidate ranges in {len(hits)} files, "
      f"{sum(r['end'] - r['start'] + 1 for r in ranges)} s total")
print("spots with no candidate footage:", uncovered)
