"""Hero image for "Drawing the path between packets": Stratolink 3's track with the
2,000 posterior bridges across the eight-day gap and the line the dashboard draws.

usage: python3 wind_path_hero.py <runs dir> <downloads dir> <out jpg>
(same <runs dir> and <downloads dir> as wind_path_figure_data.py)
"""
import json, math, re, sys
from datetime import datetime
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection, PolyCollection

S, D, OUT = sys.argv[1:4]
BG, LAND, COAST, BORDER, INK = '#f6f4ef', '#e8e5de', '#cbc6ba', '#dbd6cb', '#2b2a27'
BLUE, RED = '#328cb3', '#d34a53'
W, H = 2400, 1230                      # the post hero's 1.95 aspect
LON0, LON1, LAT0, LAT1 = -130.0, 8.0, 6.0, 64.0

def ms(iso):
    iso = iso.replace('Z', '+00:00'); iso = re.sub(r'\.(\d+)', lambda m: '.' + (m.group(1) + '000000')[:6], iso)
    return int(datetime.fromisoformat(iso).timestamp() * 1000)

prod = json.load(open(f'{S}/prod_trimmed.json')); track = prod['observed']['reconstructed_track']; fixes = prod['observed']['gps_fixes']
post = json.load(open(f'{S}/posterior2k_r1.json')); gap = max((g for g in post['gaps'] if 'samples' in g), key=lambda g: g['dt_hours'])
A = np.array(gap['samples'])
tt = np.array([ms(p['time_utc']) for p in track]); ll = np.array([[p['lat'], p['lon']] for p in track])
land = json.load(open(f'{D}/ne_50m_land.geojson')); borders = json.load(open(f'{D}/ne_50m_admin_0_boundary_lines_land.geojson'))

fig = plt.figure(figsize=(W / 100, H / 100), dpi=100); ax = fig.add_axes([0, 0, 1, 1]); ax.set_facecolor(BG); fig.patch.set_facecolor(BG)
polys = [np.array(poly[0]) for f in land['features'] for poly in (f['geometry']['coordinates'] if f['geometry']['type'] == 'MultiPolygon' else [f['geometry']['coordinates']])]
ax.add_collection(PolyCollection([p for p in polys if p[:, 0].min() < LON1 + 5 and p[:, 0].max() > LON0 - 5], facecolors=LAND, edgecolors=COAST, linewidths=0.8, zorder=0))
ax.add_collection(LineCollection([np.array(c) for f in borders['features'] for c in (f['geometry']['coordinates'] if f['geometry']['type'] == 'MultiLineString' else [f['geometry']['coordinates']])], colors=BORDER, linewidths=0.6, zorder=0.5))
ax.add_collection(LineCollection([A[i][:, ::-1] for i in range(len(A))], colors=BLUE, linewidths=0.9, alpha=0.045, zorder=2))
pre = tt <= gap['tA']; after = tt >= gap['tB']; inside = (tt >= gap['tA']) & (tt <= gap['tB'])
for m in (pre, after): ax.plot(ll[m, 1], ll[m, 0], color=INK, lw=2.4, zorder=4)
ax.plot(ll[inside, 1], ll[inside, 0], color=RED, lw=3.2, zorder=5)
ax.scatter([f['lon'] for f in fixes], [f['lat'] for f in fixes], s=9, color=INK, lw=0, zorder=6)
ax.set_xlim(LON0, LON1); ax.set_ylim(LAT0, LAT1); ax.set_aspect(1 / math.cos(math.radians((LAT0 + LAT1) / 2))); ax.axis('off')
fig.savefig(OUT, dpi=100, pil_kwargs={'quality': 90, 'optimize': True}); print('wrote', OUT)
