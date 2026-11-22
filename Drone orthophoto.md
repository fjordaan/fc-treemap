# Drone orthophoto base layer

The map's **Drone (May 2026)** base layer is a single, seamless, straight-down photo of the cemetery, stitched together from drone video footage. At about 4–5 cm per pixel it's sharper than the Esri satellite imagery, and more recent.

Link straight to it with `?drone=1`, the same way `?satellite=1` works.

## Source footage

- 86 DJI video clips filmed on 7 May 2026: 4K (3840×2160), 50 fps, HEVC, 24 mm-equivalent lens.
- Each clip has a sidecar `.SRT` subtitle file that records, for every frame, the time, GPS position, height above take-off (`rel_alt`), sea-level altitude (`abs_alt`) and camera settings. This is the overlay VLC shows. It does **not** record the gimbal (camera) angle.
- Most clips are low-level or angled shots. One clip, **DJI_0422**, is a 2.5-minute survey flight straight down at a constant 120 m, flown as parallel north–south lines with about 60 m between them. On its own it covers the whole cemetery.

The footage (39 GB) and the intermediate files are not kept in this repo, only the finished tiles and the scripts.

## Process

1. **Read the telemetry** (`drone/parse_srt.py`). This parses every `.SRT` into a per-second CSV of position, altitude and speed. It picks out the steady level-flight segments and draws an HTML map of all the flight tracks, coloured by altitude. That is how DJI_0422 was found, without watching the footage. View the map at [trees.fulhamcemeteryfriends.org.uk/drone/tracks_map.html](https://trees.fulhamcemeteryfriends.org.uk/drone/tracks_map.html). Thin lines are whole flights, and thick lines are level, moving segments.
2. **Extract frames** (`drone/extract_frames.py`). This takes one frame every 10 m of ground travelled (about 90% overlap), choosing the sharpest of 5 nearby frames each time. Each frame is saved as a full-resolution JPG with the GPS position, altitude, time and focal length written into its EXIF (with [ExifTool](https://exiftool.org/)). DJI_0422 gave 86 frames.
3. **Make the orthophoto** with [OpenDroneMap](https://opendronemap.org/) (ODM), run in Docker. ODM matches the frames, rebuilds the ground and trees in 3D, and projects that model straight down. A simple panorama stitch can't do this, which is why trees don't lean away from the centre. The result is a georeferenced GeoTIFF.

   ```
   docker run --rm -v <work>/odm:/datasets opendronemap/odm --project-path /datasets cemetery --orthophoto-resolution 5 --tiles
   ```

   With 86 frames this took 49 minutes on a 12-core PC with 16 GB of RAM. The result: all 86 images placed, 0.94 px reprojection error, 4.3 cm/px ground resolution, and GPS agreement of about 1.9 m.
4. **Cut map tiles.** This uses `gdal2tiles.py`, which comes with the ODM Docker image. It writes standard XYZ tiles (the same numbering Leaflet and OpenStreetMap use) as WebP at quality 80:

   ```
   docker run --rm --entrypoint gdal2tiles.py -v <work>:/w opendronemap/odm --xyz --zoom=15-21 --tiledriver=WEBP --webp-quality=80 --webviewer=none --resampling=lanczos /w/odm/cemetery/odm_orthophoto/odm_orthophoto.tif /w/tiles
   ```

   This gives 1,719 tiles, 13 MB in total. A phone only downloads the few tiles on screen, typically 100–300 KB. ODM's own `--tiles` output was 286 MB, because it's PNG and includes a zoom 22 level with no real extra detail.

## In the app

In `index.html` the layer is a `L.layerGroup` of the Esri satellite tiles with the drone tiles on top:

- `tiles/drone-2026-05/{z}/{x}/{y}.webp`, from zoom 15 to 21, which matches the app's `maxZoom`.
- A `bounds` setting with the tile set's extent, so Leaflet never asks for tiles that don't exist.
- Outside the survey area, and when zoomed out below 15, Esri shows through.

The tile folder is named after the survey date. A new or improved version should go into a new folder (e.g. `tiles/drone-2026-05-v2/`), so browsers don't mix old cached tiles with new ones.

## Known issues and next steps

- **Smearing at the edges.** The outer edges were only seen by one or two frames at a steep angle, so they're smeared. This is mostly outside the cemetery.
- **Some smeared spots inside.** These are mostly along walls and boundary trees. They were marked on a copy of the orthophoto, and `drone/find_coverage.py` then searched the telemetry of all 84 other clips for moments when the drone was above them. `drone/contact_sheets.py` makes labelled thumbnail sheets of those moments, to choose usable footage by eye.
- **Planned improved run.** This would add the chosen extra footage, use denser frames from DJI_0422, and switch on ODM's rolling-shutter correction (video sensors read out line by line, which skews moving frames) and higher quality settings.

## Tools

- ffmpeg/ffprobe, for decoding video and extracting frames
- ExifTool, for writing GPS EXIF tags
- Python 3 with `opencv-python-headless`, `numpy` and `pyproj`
- Docker Desktop with the `opendronemap/odm` image
