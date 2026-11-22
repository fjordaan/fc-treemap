#!/usr/bin/env bash
# Improved orthophoto run: extra footage from chosen ranges + denser DJI_0422, then ODM.
set -euo pipefail
cd "$(dirname "$0")"
PY=.venv/Scripts/python
STAGE=stage_v2
PROJ=odm/cemetery_v2

echo "== $(date) extracting chosen ranges"
rm -rf "$STAGE"; mkdir -p "$STAGE"
$PY -I extract_ranges.py problem_spots/candidate_ranges.csv ../Footage "$STAGE/extra"

echo "== $(date) extracting DJI_0422 every 5 m"
printf 'file,start,end,keep\nDJI_0422,0,999,y\n' > "$STAGE/ranges_0422.csv"
$PY -I extract_ranges.py "$STAGE/ranges_0422.csv" ../Footage "$STAGE/survey" --fixed 5 --max-interval 0

echo "== $(date) assembling ODM project"
rm -rf "$PROJ"; mkdir -p "$PROJ/images"
cp "$STAGE"/extra/*.jpg "$STAGE"/survey/*.jpg "$PROJ/images/"
echo "images: $(ls "$PROJ/images" | wc -l)"

echo "== $(date) running ODM"
MSYS_NO_PATHCONV=1 docker run --rm --name odm_cemetery_v2 \
  -v "$(cygpath -m "$PWD/odm"):/datasets" opendronemap/odm \
  --project-path /datasets cemetery_v2 \
  --rolling-shutter \
  --feature-quality high --pc-quality high \
  --mesh-octree-depth 12 --mesh-size 300000 \
  --orthophoto-resolution 4
echo "== $(date) done"
