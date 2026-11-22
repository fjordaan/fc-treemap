"""Parse DJI sidecar SRT telemetry into per-second CSV, candidate segments, and an HTML map.

Usage: python -I parse_srt.py <footage_dir> <out_dir>
"""
import csv, json, math, re, sys
from pathlib import Path

footage, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)

TIME_RE = re.compile(r"^(\d\d):(\d\d):(\d\d),(\d+) -->")
LAT_RE = re.compile(r"latitude: ([-\d.]+)")
LON_RE = re.compile(r"longitude: ([-\d.]+)")
ALT_RE = re.compile(r"rel_alt: ([-\d.]+)")

# Candidate "steady pass" thresholds
MAX_VSPEED = 0.6   # m/s, climb/descent rate to count as level
MIN_HSPEED = 1.0   # m/s, must be moving horizontally
MIN_DURATION = 6   # seconds
ALT_BAND = 8       # m, max altitude variation within a segment


def parse(path):
    """Return list of (second, lat, lon, alt) using the first entry in each whole second."""
    rows, t, seen = [], None, set()
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = TIME_RE.match(line)
            if m:
                h, mi, s, _ = map(int, m.groups())
                t = h * 3600 + mi * 60 + s
                continue
            if t is not None and t not in seen and "latitude" in line:
                la, lo, al = LAT_RE.search(line), LON_RE.search(line), ALT_RE.search(line)
                # 0,0 means no GPS fix yet: skip those points
                if la and lo and al and (abs(float(la.group(1))) > 0.01 or abs(float(lo.group(1))) > 0.01):
                    seen.add(t)
                    rows.append((t, float(la.group(1)), float(lo.group(1)), float(al.group(1))))
    return rows


def dist(a, b):
    dy = (b[1] - a[1]) * 111_200
    dx = (b[2] - a[2]) * 111_200 * math.cos(math.radians(a[1]))
    return math.hypot(dx, dy)


all_secs, segments, tracks = [], [], {}
for srt in sorted(footage.glob("*.SRT")):
    rows = parse(srt)
    if len(rows) < 3:
        continue
    secs = []
    for i, r in enumerate(rows):
        a, b = rows[max(i - 1, 0)], rows[min(i + 1, len(rows) - 1)]
        dt = max(b[0] - a[0], 1)
        secs.append(dict(file=srt.stem, t=r[0], lat=r[1], lon=r[2], alt=r[3],
                         hspeed=dist(a, b) / dt, vspeed=(b[3] - a[3]) / dt))
    all_secs += secs
    tracks[srt.stem] = [[s["lat"], s["lon"], s["alt"], s["t"]] for s in secs]

    # Find runs of level, moving flight
    run = []
    def flush():
        if len(run) >= MIN_DURATION:
            alts = [s["alt"] for s in run]
            length = sum(dist((0, run[k]["lat"], run[k]["lon"]), (0, run[k+1]["lat"], run[k+1]["lon"]))
                         for k in range(len(run) - 1))
            segments.append(dict(file=srt.stem, start=run[0]["t"], end=run[-1]["t"],
                                 duration=run[-1]["t"] - run[0]["t"],
                                 alt_mean=round(sum(alts) / len(alts), 1),
                                 alt_min=min(alts), alt_max=max(alts),
                                 distance_m=round(length),
                                 mean_speed=round(length / max(run[-1]["t"] - run[0]["t"], 1), 1)))
    for s in secs:
        ok = abs(s["vspeed"]) <= MAX_VSPEED and s["hspeed"] >= MIN_HSPEED
        if ok and run and (max(r["alt"] for r in run + [s]) - min(r["alt"] for r in run + [s]) > ALT_BAND):
            flush(); run = []
        if ok:
            run.append(s)
        else:
            flush(); run = []
    flush()

with open(out / "telemetry_per_second.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(all_secs[0].keys()))
    w.writeheader()
    for s in all_secs:
        w.writerow({k: (round(v, 6) if isinstance(v, float) else v) for k, v in s.items()})

with open(out / "segments.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(segments[0].keys()) + ["nadir"])
    w.writeheader()
    for s in segments:
        w.writerow({**s, "nadir": ""})

# Per-file summary
summary = {}
for s in all_secs:
    d = summary.setdefault(s["file"], dict(dur=0, amin=1e9, amax=-1e9))
    d["dur"] = max(d["dur"], s["t"]); d["amin"] = min(d["amin"], s["alt"]); d["amax"] = max(d["amax"], s["alt"])
with open(out / "files_summary.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["file", "duration_s", "alt_min", "alt_max", "n_segments", "segment_seconds"])
    for k, d in summary.items():
        segs = [g for g in segments if g["file"] == k]
        w.writerow([k, d["dur"], d["amin"], d["amax"], len(segs), sum(g["duration"] for g in segs)])

html = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>Drone tracks</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>html,body,#map{height:100%;margin:0;font-family:sans-serif}
#panel{position:absolute;top:10px;right:10px;z-index:1000;background:#fff;padding:8px 10px;border-radius:6px;
box-shadow:0 1px 4px #0005;font-size:13px;max-width:260px}
.bar{height:10px;background:linear-gradient(90deg,hsl(240,90%,45%),hsl(120,90%,40%),hsl(60,90%,45%),hsl(0,90%,45%))}</style>
</head><body><div id="map"></div><div id="panel">
<b>Altitude</b> <span id="lo"></span>&ndash;<span id="hi"></span> m<div class="bar"></div>
<label><input type="checkbox" id="onlyseg"> Only candidate segments</label><br>
Min altitude: <input type="range" id="minalt" min="0" max="150" value="0"> <span id="mav">0</span> m<br>
<small>Thin = whole track, thick = level moving segment. Click for details.</small></div>
<script>
const tracks = __TRACKS__, segs = __SEGS__;
const map = L.map('map').setView([51.4803, -0.2163], 17);  // Fulham Cemetery
const sat = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
  {maxZoom:21,maxNativeZoom:19,attribution:'Imagery &copy; Esri'}).addTo(map);
const street = L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png',
  {maxZoom:21,maxNativeZoom:20,subdomains:'abcd',attribution:'&copy; OpenStreetMap contributors &copy; CARTO'});
L.control.layers({'Satellite':sat,'Street map':street},{},{position:'topleft'}).addTo(map);
let lo=1e9,hi=-1e9; for(const k in tracks) for(const p of tracks[k]){lo=Math.min(lo,p[2]);hi=Math.max(hi,p[2]);}
document.getElementById('lo').textContent=lo.toFixed(0); document.getElementById('hi').textContent=hi.toFixed(0);
const col=a=>`hsl(${240-240*Math.min(1,Math.max(0,(a-lo)/(hi-lo||1)))},90%,45%)`;
let layer=L.layerGroup().addTo(map);
function draw(){
  layer.clearLayers(); const only=document.getElementById('onlyseg').checked, minA=+document.getElementById('minalt').value;
  document.getElementById('mav').textContent=minA;
  for(const k in tracks){ const pts=tracks[k];
    if(!only){ for(let i=1;i<pts.length;i++){ if(pts[i][2]<minA) continue;
      L.polyline([pts[i-1].slice(0,2),pts[i].slice(0,2)],{color:col(pts[i][2]),weight:2,opacity:.6}).addTo(layer)
       .bindPopup(`${k} @ ${pts[i][3]}s, ${pts[i][2].toFixed(1)} m`); } }
    for(const s of segs.filter(s=>s.file===k && s.alt_mean>=minA)){
      const sp=pts.filter(p=>p[3]>=s.start&&p[3]<=s.end).map(p=>p.slice(0,2));
      L.polyline(sp,{color:col(s.alt_mean),weight:6,opacity:.9}).addTo(layer)
       .bindPopup(`<b>${k}</b> ${s.start}&ndash;${s.end}s (${s.duration}s)<br>alt ${s.alt_mean} m, ${s.distance_m} m @ ${s.mean_speed} m/s`);
    } }
}
document.getElementById('onlyseg').onchange=draw; document.getElementById('minalt').oninput=draw; draw();
</script></body></html>"""
html = html.replace("__TRACKS__", json.dumps({k: [[round(a, 6), round(b, 6), round(c, 1), t] for a, b, c, t in v]
                                               for k, v in tracks.items()}))
html = html.replace("__SEGS__", json.dumps(segments))
(out / "tracks_map.html").write_text(html, encoding="utf-8")

print(f"files: {len(tracks)}  seconds: {len(all_secs)}  candidate segments: {len(segments)}")
