"""Local offset field: drone DSM vs LiDAR in 40 m windows, keeping only confident matches.
Usage: python -I offset_field.py <lidar.tif> <os-buildings.geojson> <drone_dsm.tif> [out.csv]
Reuses the grid/masks of measure_offset.py (same folder). Needs the OSTN15 grid:
  pyproj sync --file uk_os_OSTN15_NTv2_OSGBtoETRS.tif
"""
import sys, runpy, csv
import numpy as np, cv2, rasterio
from rasterio.enums import Resampling
from pyproj import Transformer
drone = sys.argv[3]; out_csv = sys.argv[4] if len(sys.argv) > 4 else None
sys.argv = sys.argv[:3]
g = runpy.run_path(str(__import__("pathlib").Path(__file__).with_name("measure_offset.py")))
lid_hp, solid, edges, lat, lon, H, W, highpass = (g[k] for k in ("lid_hp", "solid", "edges", "lat", "lon", "H", "W", "highpass"))
with rasterio.open(drone) as d:
    f = max(1, int(0.5 / d.res[0]))
    arr = d.read(1, out_shape=(d.height // f, d.width // f), resampling=Resampling.average).astype(np.float32)
    T = d.transform * rasterio.Affine.scale(d.width / arr.shape[1], d.height / arr.shape[0]); crs = d.crs
arr[arr < -1000] = np.nan
x, y = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform(lon, lat)
inv = ~T
shifts = np.arange(-8, 8.01, 0.5)
hp = {}
for dx in shifts:
    for dy in shifts:
        c, r = inv * (x + dx, y + dy)
        s = cv2.remap(np.nan_to_num(arr, nan=-9999), c.astype(np.float32), r.astype(np.float32), cv2.INTER_LINEAR, borderValue=-9999).astype(float)
        ok = s > -1000; s[~ok] = np.nan
        hp[(dx, dy)] = (highpass(s), ok)
WIN, STEP = 40, 20
rows = []
for r0 in range(0, H - WIN + 1, STEP):
    for c0 in range(0, W - WIN + 1, STEP):
        sl = (slice(r0, r0 + WIN), slice(c0, c0 + WIN))
        m = solid[sl] & hp[(0.0, 0.0)][1][sl]
        if m.sum() < 250 or hp[(0.0, 0.0)][1][sl].mean() < 0.95:
            continue
        a = lid_hp[sl]
        sc = np.full((len(shifts), len(shifts)), -1.0)
        for i, dx in enumerate(shifts):
            for j, dy in enumerate(shifts):
                b, ok = hp[(dx, dy)]; mm = m & ok[sl]
                if mm.sum() < 200: continue
                aa, bb = a[mm] - a[mm].mean(), b[sl][mm] - b[sl][mm].mean()
                sc[i, j] = (aa * bb).sum() / (np.sqrt((aa * aa).sum() * (bb * bb).sum()) + 1e-9)
        i, j = np.unravel_index(sc.argmax(), sc.shape)
        best = sc[i, j]
        far = sc.copy(); far[max(0, i - 3):i + 4, max(0, j - 3):j + 4] = -1   # second peak >1.5 m away
        if best < 0.5 or best - far.max() < 0.1 or i in (0, len(shifts) - 1) or j in (0, len(shifts) - 1):
            continue
        # sub-pixel refine by parabola
        def para(v0, v1, v2): d = v0 - 2 * v1 + v2; return 0 if d == 0 else 0.5 * (v0 - v2) / d
        ddx = para(sc[i - 1, j], sc[i, j], sc[i + 1, j]) * 0.5; ddy = para(sc[i, j - 1], sc[i, j], sc[i, j + 1]) * 0.5
        cr, cc = r0 + WIN // 2, c0 + WIN // 2
        rows.append(dict(lat=round(float(lat[cr, cc]), 6), lon=round(float(lon[cr, cc]), 6),
                         east=round(shifts[i] + ddx, 2), north=round(shifts[j] + ddy, 2), ncc=round(best, 2), px=int(m.sum())))
print(f"{drone}: {len(rows)} confident 40 m windows")
if rows:
    E = np.array([r["east"] for r in rows]); N = np.array([r["north"] for r in rows])
    print(f"  median east {np.median(E):+.2f} m, north {np.median(N):+.2f} m;  IQR east {np.subtract(*np.percentile(E,[75,25])):.2f}, north {np.subtract(*np.percentile(N,[75,25])):.2f}")
    la = np.array([r["lat"] for r in rows]); lo = np.array([r["lon"] for r in rows])
    X = np.c_[np.ones(len(rows)), (lo - lo.mean()) * 69400 / 100, (la - la.mean()) * 111200 / 100]
    for name, v in (("east", E), ("north", N)):
        coef, *_ = np.linalg.lstsq(X, v, rcond=None)
        print(f"  trend {name}: {coef[0]:+.2f} m at centre, {coef[1]:+.2f} m per 100 m eastward, {coef[2]:+.2f} m per 100 m northward")
    for r in sorted(rows, key=lambda r: (-r["lat"], r["lon"])):
        print(f"    {r['lat']:.5f},{r['lon']:.5f}  east {r['east']:+5.2f}  north {r['north']:+5.2f}  ncc {r['ncc']}")
    if out_csv:
        with open(out_csv, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
