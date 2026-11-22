# Runs inside the ODM container (has GDAL Python bindings).
# Crop to the cemetery and shift by (-0.56 m E, -0.29 m N) to remove the measured offset.
import sys
from osgeo import gdal, osr
DX, DY = -0.56, -0.29
src, dst, dsm_src, dsm_dst = sys.argv[1:5]
wgs = osr.SpatialReference(); wgs.ImportFromEPSG(4326); wgs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
utm = osr.SpatialReference(); utm.ImportFromEPSG(32630)
ct = osr.CoordinateTransformation(wgs, utm)
(xw, yn, _), (xe, ys, _) = ct.TransformPoint(-0.2190, 51.4826), ct.TransformPoint(-0.2120, 51.4779)
for s, d in ((src, dst), (dsm_src, dsm_dst)):
    gdal.Translate(d, s, projWin=[xw, yn, xe, ys], creationOptions=["COMPRESS=DEFLATE", "TILED=YES", "BIGTIFF=IF_SAFER"])
    ds = gdal.Open(d, gdal.GA_Update)
    gt = list(ds.GetGeoTransform()); gt[0] += DX; gt[3] += DY
    ds.SetGeoTransform(gt); ds = None
    print(d, "origin", gt[0], gt[3])
