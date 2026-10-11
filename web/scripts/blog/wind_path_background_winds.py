"""Coarse background wind field for the blog post's maps: GFS U/V at the balloon's float
pressure over the North Atlantic view, 2.5° every 3 hours over the same window as the
stratolink-3 reconstruction cube. Reuses the ingest's NOAA S3 byte-range fetcher.

usage: python3 wind_path_background_winds.py <recon cube .slwc> <out dir>
writes <out dir>/winds.json and winds.bin (Int8 u,v in m/s, slice-major, row-major).
"""
import json, os, struct, sys, time
from datetime import datetime, timedelta, timezone
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import gfs_ingest as gi  # noqa: E402

CUBE, OUT = sys.argv[1:3]
LAT0, DLAT, NLAT = 58.0, -2.5, 19      # 58 … 13
LON0, DLON, NLON = -128.0, 2.5, 55     # -128 … 7
raw = open(CUBE, 'rb').read(); hl = struct.unpack('<I', raw[:4])[0]; hdr = json.loads(raw[4:4 + hl].decode('utf8'))
level = hdr['levelHpa']; t0 = hdr['t0Ms']; step = hdr['stepMs']; n = hdr['nGrids']
rows = np.round((90.0 - (LAT0 + DLAT * np.arange(NLAT))) / 0.25).astype(int)
cols = (np.round(((LON0 + DLON * np.arange(NLON)) % 360.0) / 0.25).astype(int)) % 1440
latest = datetime.now(timezone.utc)
blob = bytearray(); started = time.time()
for k in range(n):
    t = datetime.fromtimestamp((t0 + k * step) / 1000, timezone.utc)
    cyc, fhr = gi.pick_source(t, latest)
    uv = gi.fetch_uv_p(cyc, fhr, level)
    u = uv['u'][np.ix_(rows, cols)]; v = uv['v'][np.ix_(rows, cols)]
    blob += np.clip(np.rint(np.stack([u, v], axis=-1)), -127, 127).astype(np.int8).tobytes()
    gi.clear_field_cache()
    print(f'{k + 1}/{n} {t:%Y-%m-%d %H:%M} from {cyc:%Y-%m-%d %HZ} f{fhr:03d}  mean |wind| {np.hypot(u, v).mean():.1f} m/s  {time.time() - started:.0f}s', flush=True)
os.makedirs(OUT, exist_ok=True)
open(os.path.join(OUT, 'winds.bin'), 'wb').write(bytes(blob))
json.dump({'levelHpa': level, 't0Ms': t0, 'stepMs': step, 'n': n, 'lat0': LAT0, 'dLat': DLAT, 'nLat': NLAT, 'lon0': LON0, 'dLon': DLON, 'nLon': NLON,
           'source': 'NOAA GFS 0.25° analyses and short-range forecasts, blended to the float pressure, subsampled to 2.5°'},
          open(os.path.join(OUT, 'winds.json'), 'w'), separators=(',', ':'))
print('done', len(blob) // 1024, 'KB')
