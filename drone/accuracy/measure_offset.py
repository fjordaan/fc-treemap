"""Measure the horizontal offset of a drone DSM against the EA LiDAR First Return DSM.

Usage: python -I measure_offset.py <lidar_dsm.tif (EPSG:27700)> <os-buildings.geojson> <drone_dsm.tif> [...]

Method (as in fc-treemap issue #2):
- 1 m grid in British National Grid (EPSG:27700) over the cemetery.
- Grid points converted to lat/lng with OSTN15 (EPSG:27700 -> ETRS89, 0.03 m), treated as WGS84
  (the convention web maps use), then to the drone DSM's CRS (UTM 30N) to sample it.
- Heights high-passed (minus a 15 m Gaussian) so ground level and any tilt don't matter.
- The drone DSM is resampled at shifted positions; the shift with the best normalised
  cross-correlation is the drone layer's displacement from true position (+east, +north).
- Masks: "buildings" = OS building outlines +/- 3 m (walls/roof edges; excludes trees);
  "all" = everywhere (includes trees, which changed between 2023 leaf-off and May 2026).
"""
import json, sys
import numpy as np, cv2, rasterio
from rasterio.enums import Resampling
from pyproj import Transformer
from pyproj.transformer import TransformerGroup

lidar_path, bld_path, drones = sys.argv[1], sys.argv[2], sys.argv[3:]

osgb_to_etrs = TransformerGroup(27700, 4258).transformers[0]
assert osgb_to_etrs.accuracy and osgb_to_etrs.accuracy < 0.1, "OSTN15 grid missing (run: pyproj sync --file uk_os_OSTN15_NTv2_OSGBtoETRS.tif)"
ll_to_osgb = TransformerGroup(4258, 27700).transformers[0]

# Grid over the cemetery (lat/lng box from the app's section layout, plus margin)
# EPSG:4258 takes (lat, lon); EPSG:27700 returns (easting, northing)
(E0, N0), (E1, N1) = ll_to_osgb.transform(51.4783, -0.2186), ll_to_osgb.transform(51.4823, -0.2124)
E0, N0, E1, N1 = np.floor(E0), np.floor(N0), np.ceil(E1), np.ceil(N1)
ge, gn = np.meshgrid(np.arange(E0, E1) + 0.5, np.arange(N1, N0, -1) - 0.5)
H, W = ge.shape

with rasterio.open(lidar_path) as d:
    win = rasterio.windows.from_bounds(E0, N0, E1, N1, d.transform)
    lid = d.read(1, window=win, out_shape=(H, W)).astype(np.float64)
    lid[lid < -1000] = np.nan

lat, lon = osgb_to_etrs.transform(ge, gn)

# Building mask from OS outlines (GeoJSON in lat/lng), drawn on the grid, edges +/- 3 m
bmask = np.zeros((H, W), np.uint8)
for f in json.load(open(bld_path, encoding="utf-8"))["features"]:
    geom = f["geometry"]
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    for poly in polys:
        for ring in poly:
            pts = np.array([ll_to_osgb.transform(la, lo) for lo, la in ring])
            px = np.round(np.c_[pts[:, 0] - E0, N1 - pts[:, 1]]).astype(np.int32)
            cv2.fillPoly(bmask, [px], 1)
edges = cv2.dilate(bmask, np.ones((7, 7), np.uint8)) - cv2.erode(bmask, np.ones((7, 7), np.uint8))
building_zone = cv2.dilate(bmask, np.ones((7, 7), np.uint8)).astype(bool)


def highpass(a):
    v = np.nan_to_num(a, nan=np.nanmedian(a))
    return v - cv2.GaussianBlur(v, (0, 0), 15)


lid_hp = highpass(lid)
# "solid" features: stand > 2.5 m above surroundings in the leaf-off LiDAR (buildings, walls,
# conifers/evergreens), plus a 2 m margin so their edges count. Deciduous trees are excluded.
solid = cv2.dilate((lid_hp > 2.5).astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool) | edges.astype(bool)


def ncc(a, b, m):
    a, b = a[m], b[m]
    a = a - a.mean(); b = b - b.mean()
    return float((a * b).sum() / (np.sqrt((a * a).sum() * (b * b).sum()) + 1e-9))


for dpath in drones:
    with rasterio.open(dpath) as d:
        to_d = Transformer.from_crs("EPSG:4326", d.crs, always_xy=True)
        f = max(1, int(0.5 / d.res[0]))                       # pre-average to ~0.5 m
        arr = d.read(1, out_shape=(d.height // f, d.width // f), resampling=Resampling.average).astype(np.float32)
        nod = d.nodata
        T = d.transform * rasterio.Affine.scale(d.width / arr.shape[1], d.height / arr.shape[0])
    valid_d = np.isfinite(arr) & ((arr != nod) if nod is not None else True) & (arr > -1000)
    arr[~valid_d] = np.nan
    x, y = to_d.transform(lon, lat)
    inv = ~T

    def sample(dx, dy):
        c, r = inv * (x + dx, y + dy)
        out = cv2.remap(np.nan_to_num(arr, nan=-9999), c.astype(np.float32), r.astype(np.float32), cv2.INTER_LINEAR,
                        borderValue=-9999)
        out = out.astype(np.float64); out[out < -1000] = np.nan
        return out

    base = sample(0, 0)
    have = np.isfinite(base) & np.isfinite(lid)
    drone_hp_cache = {}

    def score(dx, dy, m):
        key = (round(dx, 2), round(dy, 2))
        if key not in drone_hp_cache:
            s = sample(dx, dy)
            drone_hp_cache[key] = (highpass(s), np.isfinite(s))
        hp, ok = drone_hp_cache[key]
        mm = m & ok
        return ncc(lid_hp, hp, mm) if mm.sum() > 50 else -1

    def best(m):
        grid = [(dx, dy) for dx in np.arange(-8, 8.01, 1.0) for dy in np.arange(-8, 8.01, 1.0)]
        sc = {g: score(*g, m) for g in grid}
        (bx, by) = max(sc, key=sc.get)
        for step, span in ((0.25, 1.0), (0.05, 0.25)):
            grid = [(bx + i, by + j) for i in np.arange(-span, span + 1e-6, step) for j in np.arange(-span, span + 1e-6, step)]
            sc = {g: score(*g, m) for g in grid}
            (bx, by) = max(sc, key=sc.get)
        return bx, by, sc[(bx, by)], score(0, 0, m)

    print(f"\n{dpath}")
    print(f"  grid {W}x{H} m, drone data on {have.mean():.0%} of it, building-edge pixels {int((edges.astype(bool) & have).sum())}")
    for name, m in (("buildings", edges.astype(bool) & have), ("solid", solid & have), ("all", have)):
        bx, by, s, s0 = best(m)
        print(f"  {name:9s}: drone layer is {bx:+.2f} m east, {by:+.2f} m north of true  (NCC {s:.3f}, unshifted {s0:.3f})")
    # variation across the area: 3x3 sub-areas, buildings+all pixels within each
    print("  3x3 sub-areas (solid features only; N row first)  east/north in m [NCC, pixels]:")
    for iy in range(3):
        row = []
        for ix in range(3):
            sub = np.zeros_like(have)
            sub[iy * H // 3:(iy + 1) * H // 3, ix * W // 3:(ix + 1) * W // 3] = True
            m = have & sub & solid
            if m.sum() < 800:
                row.append("        (too few)        "); continue
            bx, by, s, _ = best(m)
            row.append(f"{bx:+5.2f} {by:+5.2f} [{s:.2f},{int(m.sum()):5d}]")
        print("    " + "   ".join(row))
