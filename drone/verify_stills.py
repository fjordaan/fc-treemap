"""Pick stills that really show each edit area, checked by image matching, not just by drone position.

Usage: python -I verify_stills.py <kit_dir> <telemetry_per_second.csv> <footage_dir> [area ids, first = done first]
For each area in <kit_dir>/areas.json: candidate seconds from ALL clips where the drone was within
0.6 x altitude of the area centre; extract the frame; SIFT-match the area's crop into it; keep frames
where the whole crop is visible. Lean of tall objects depends on the line of sight (off / alt), so rank
by that. Writes <kit_dir>/stills_v2/area_NN_<rank>_<clip>_f<frame>_<alt>m_off<d>m.png and a
contact sheet area_NN_check.jpg with the crop outlined in each candidate.
"""
import csv, json, math, os, subprocess, sys
from collections import defaultdict
from pathlib import Path
import cv2, numpy as np

kit, tele, footage = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
order = [int(a) for a in sys.argv[4:]]
FFMPEG = os.environ.get("FFMPEG", r"D:\Documents\Utilities\ffmpeg-20170204-b1e2192-win64-static\bin\ffmpeg.exe")
FPS, MAX_RATIO, MAX_CAND, N_KEEP = 50, 0.6, 30, 3
out = kit / "stills_v2"; cache = out / "_cache"; cache.mkdir(parents=True, exist_ok=True)
areas = json.load(open(kit / "areas.json"))
areas.sort(key=lambda a: (order.index(a["id"]) if a["id"] in order else 99, a["id"]))
rows = [r for r in csv.DictReader(open(tele, encoding="utf-8-sig")) if abs(float(r["lat"])) > 1 and float(r["alt"]) > 12]
sift = cv2.SIFT_create(4000)
bf = cv2.BFMatcher()

def frame(clip, t):
    p = cache / f"{clip}_{t:04d}.png"
    if not p.exists():
        subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-ss", str(t), "-i", str(footage / f"{clip}.MP4"),
                        "-frames:v", "1", str(p)], check=True)
    return p

for a in areas:
    if (out / f"area_{a['id']:02d}_check.jpg").exists():
        continue   # done in an earlier run
    crop = cv2.imread(str(kit / a["file"]))
    if crop is None:
        print(f"area {a['id']:2d}: {a['file']} not found, skipped", flush=True)
        continue
    s = min(1.0, 1200 / max(crop.shape[:2]))
    small = cv2.resize(crop, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    kc, dc = sift.detectAndCompute(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), None)
    kx = 111_200 * math.cos(math.radians(a["lat"]))
    cands = []
    for r in rows:
        d = math.hypot((float(r["lon"]) - a["lon"]) * kx, (float(r["lat"]) - a["lat"]) * 111_200)
        alt = float(r["alt"])
        if d / alt <= MAX_RATIO:
            cands.append((d / alt, d, alt, r["file"], int(r["t"])))
    cands.sort()
    picked, per_clip = [], defaultdict(list)
    for c in cands:   # spread out: >= 3 s apart within a clip
        if all(abs(c[4] - t) >= 3 for t in per_clip[c[3]]):
            picked.append(c); per_clip[c[3]].append(c[4])
        if len(picked) == MAX_CAND:
            break
    results, thumbs = [], []
    for ratio, d, alt, clip, t in picked:
        p = frame(clip, t)
        img = cv2.imread(str(p))
        f = 1920 / img.shape[1]
        im2 = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
        kf, df = sift.detectAndCompute(cv2.cvtColor(im2, cv2.COLOR_BGR2GRAY), None)
        cov, inl, quad = 0.0, 0, None
        if df is not None and len(kf) > 10:
            good = [m for m, n in bf.knnMatch(dc, df, k=2) if m.distance < 0.75 * n.distance]
            if len(good) >= 15:
                H, mask = cv2.findHomography(np.float32([kc[m.queryIdx].pt for m in good]),
                                             np.float32([kf[m.trainIdx].pt for m in good]), cv2.RANSAC, 6.0)
                if H is not None:
                    inl = int(mask.sum())
                    h, w = small.shape[:2]
                    q = cv2.perspectiveTransform(np.float32([[0, 0], [w, 0], [w, h], [0, h]])[None], H)[0]
                    qa = cv2.contourArea(q)
                    if inl >= 25 and cv2.isContourConvex(q.astype(np.float32)) and qa > 100:
                        fr = np.float32([[0, 0], [im2.shape[1], 0], [im2.shape[1], im2.shape[0]], [0, im2.shape[0]]])
                        cov = cv2.intersectConvexConvex(q, fr)[0] / qa
                        quad = q
        results.append(dict(ratio=ratio, d=d, alt=alt, clip=clip, t=t, cov=cov, inl=inl, path=p))
        th = cv2.resize(im2, (480, 270))
        if quad is not None:
            cv2.polylines(th, [np.int32(quad * 0.25)], True, (0, 255, 255), 2)
        cv2.putText(th, f"{clip} {t}s {alt:.0f}m off{d:.0f}m cov{cov:.0%}", (5, 20), 0, 0.5, (0, 255, 255), 1)
        thumbs.append(th)
    ok = [r for r in results if r["cov"] >= 0.97]
    ok.sort(key=lambda r: (r["ratio"] > 0.15, -r["inl"] if r["ratio"] <= 0.15 else r["ratio"]))
    for k, r in enumerate(ok[:N_KEEP], 1):
        name = f"area_{a['id']:02d}_{k}_{r['clip']}_f{r['t'] * FPS:05d}_{r['alt']:.0f}m_off{r['d']:.0f}m.png"
        (out / name).write_bytes(r["path"].read_bytes())
    while len(thumbs) % 4:
        thumbs.append(np.zeros_like(thumbs[0]))
    if thumbs:
        cv2.imwrite(str(out / f"area_{a['id']:02d}_check.jpg"),
                    np.vstack([np.hstack(thumbs[i:i + 4]) for i in range(0, len(thumbs), 4)]), [cv2.IMWRITE_JPEG_QUALITY, 80])
    print(f"area {a['id']:2d}: {len(results)} candidates, {len(ok)} show the whole crop; kept: " +
          ", ".join(f"{r['clip']} {r['t']}s {r['alt']:.0f}m off{r['d']:.0f}m" for r in ok[:N_KEEP]), flush=True)
print("done")
