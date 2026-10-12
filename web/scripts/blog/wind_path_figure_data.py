"""Build the compact data bundle behind the interactive figures of the blog post
"Drawing the path between packets" (public/assets/wind-path/).

usage: python3 wind_path_figure_data.py <runs dir> <downloads dir> <out dir> <recon cube .slwc>

<runs dir> holds the stratolink-3 inputs: prod_after_run.json (a full stored forecast,
for the fixes and the 62-member ensemble), prod_trimmed.json (a forecast whose
observed.reconstructed_track is the line the dashboard draws) and posterior2k_r1.json
(2,000 posterior draws per long gap from the smoother, plus `filters`: snapshots every
3 h of up to 150 particles of each long gap's forward and backward filter, both dumped
from reconstructLongGap with temporary capture hooks).
<downloads dir> holds Natural Earth's ne_50m_land.geojson. The cube is the device's
reconstruction cube from .windcube/cubes/ (v3 single-level or v4 multi-level).
"""
import glob, json, math, os, re, struct, sys
from datetime import datetime, timezone
import numpy as np

S, D, OUT, CUBE = sys.argv[1:5]
os.makedirs(OUT, exist_ok=True)
R = 6371.0

def ms(iso):
    iso = iso.replace('Z', '+00:00'); iso = re.sub(r'\.(\d+)', lambda m: '.' + (m.group(1) + '000000')[:6], iso)
    return int(datetime.fromisoformat(iso).timestamp() * 1000)

def hav(lat1, lon1, lat2, lon2):
    la1, lo1, la2, lo2 = map(np.radians, (lat1, lon1, lat2, lon2))
    d = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(d))

def r2(x): return round(float(x), 2)
def path2(arr): return [[r2(a), r2(b)] for a, b in arr]

prod = json.load(open(f'{S}/prod_after_run.json'))          # the 62-member forecast
fixes = prod['observed']['gps_fixes']
track = json.load(open(f'{S}/prod_trimmed.json'))['observed']['reconstructed_track']   # the line the dashboard draws
post = json.load(open(f'{S}/posterior2k_r1.json'))
gap = max((g for g in post['gaps'] if 'samples' in g), key=lambda g: g['dt_hours'])
tA, tB = gap['tA'], gap['tB']
A = np.array(gap['samples'], dtype=np.float64)          # (2000, 604, 2) lat, lon
K, n1, _ = A.shape
STEPS = 101
gap_times = tA + (tB - tA) * np.arange(STEPS) / (STEPS - 1)
sample_times = tA + (tB - tA) * np.arange(n1) / (n1 - 1)

# ── flight.json: what the balloon told us ────────────────────────────────────
t0 = ms(fixes[0]['time_utc'])
seen = set(); fx = []
for f in fixes:
    key = (round(f['lat'], 4), round(f['lon'], 4)); distinct = key not in seen; seen.add(key)
    fx.append([round((ms(f['time_utc']) - t0) / 60000), r2(f['lat']), r2(f['lon']), 1 if distinct else 0])
tr = [[round((ms(p['time_utc']) - t0) / 60000), r2(p['lat']), r2(p['lon'])] for p in track[::2]]
flight = {'t0': t0, 'fixes': fx, 'track': tr,
          'gap': {'tA': round((tA - t0) / 60000), 'tB': round((tB - t0) / 60000)},
          'end': round((ms(fixes[-1]['time_utc']) - t0) / 60000)}
json.dump(flight, open(f'{OUT}/flight.json', 'w'), separators=(',', ':'))

# ── tube.json / tube.bin: the reconstruction cube's slices with decimated winds ─
raw = open(CUBE, 'rb').read(); hl = struct.unpack('<I', raw[:4])[0]; hdr = json.loads(raw[4:4 + hl].decode('utf8')); off = 4 + hl
slices = []; blob = bytearray()
track_t = np.array([ms(p['time_utc']) for p in track]); track_ll = np.array([[p['lat'], p['lon']] for p in track])
levels = hdr.get('levels') or []
if levels:                                             # v4: blend the float level from its bracketing pair, as windCube.ts does
    pf = hdr["levelHpa"]; lk1 = next(i for i, L in enumerate(levels) if L >= pf); lk0 = max(0, lk1 - 1)
    wf = 0.0 if lk1 == lk0 else (pf - levels[lk0]) / (levels[lk1] - levels[lk0])
fix_ms = [ms(f['time_utc']) for f in fixes]
def gap_hours(t, step_ms):
    # longest GPS gap a slice is read by (mirrors gap_hours_at in scripts/gfs_ingest.py)
    return max([(b - a) / 3.6e6 for a, b in zip(fix_ms, fix_ms[1:]) if b > t - step_ms and a < t + step_ms] or [0.0])
pblob = bytearray(); fine_patch = {}
for g in range(hdr['nGrids']):
    nLat, nLon = hdr['dims'][g]; n = nLat * nLon
    lv = []
    for _ in range(max(1, len(levels))):
        U = np.frombuffer(raw, dtype='<i2', count=n, offset=off).reshape(nLat, nLon) / hdr['scale']; off += 2 * n
        V = np.frombuffer(raw, dtype='<i2', count=n, offset=off).reshape(nLat, nLon) / hdr['scale']; off += 2 * n
        lv.append((U, V))
    U, V = lv[0] if not levels else (lv[lk0][0] * (1 - wf) + lv[lk1][0] * wf, lv[lk0][1] * (1 - wf) + lv[lk1][1] * wf)
    la0, lo0 = hdr['origins'][g]; step = hdr['gridStep']; t = hdr['t0Ms'] + g * hdr['stepMs']
    # Every box thinned to the same 0.75° spacing on a common lattice (multiples of
    # 0.75° in lat/lon), so arrows keep one density and don't jitter between frames.
    ARROW_DEG = 0.75
    st = max(1, round(ARROW_DEG / step))
    i0 = int(round((-la0 / step))) % st; j0 = int(round((-lo0 / step))) % st
    ui = U[i0::st, j0::st]; vi = V[i0::st, j0::st]
    pos = None
    if track_t[0] <= t <= track_t[-1]:
        k = int(np.searchsorted(track_t, t)); k0 = max(0, k - 1); k1 = min(len(track_t) - 1, k)
        w = 0 if k1 == k0 else (t - track_t[k0]) / (track_t[k1] - track_t[k0])
        p = track_ll[k0] * (1 - w) + track_ll[k1] * w; pos = [r2(p[0]), r2(p[1])]
    # Magnified inset: the box's full-resolution winds over a 3° × 3° patch around
    # the balloon (kept inside the box), and where that patch sits, so the coarse
    # field can be interpolated to the same points below.
    patch = None
    PN = int(round(3.0 / step)) + 1
    if pos and nLat >= PN and nLon >= PN:
        ci = int(round((pos[0] - la0) / step)); cj = int(round((pos[1] - lo0) / step))
        pi0 = min(max(ci - PN // 2, 0), nLat - PN); pj0 = min(max(cj - PN // 2, 0), nLon - PN)
        patch = {'lat0': r2(la0 + pi0 * step), 'lon0': r2(lo0 + pj0 * step), 'n': PN, 'step': step, 'off': len(pblob)}
        pblob += np.clip(np.rint(np.stack([U[pi0:pi0 + PN, pj0:pj0 + PN], V[pi0:pi0 + PN, pj0:pj0 + PN]], axis=-1)), -127, 127).astype(np.int8).tobytes()
        fine_patch[g] = np.stack([U[pi0:pi0 + PN, pj0:pj0 + PN], V[pi0:pi0 + PN, pj0:pj0 + PN]], axis=-1)
    gh = gap_hours(t, hdr['stepMs'])
    slices.append({'t': t, 'lat0': la0, 'lon0': lo0, 'h': round((nLat - 1) * step, 2), 'w': round((nLon - 1) * step, 2),
                   'half': r2(min(20, max(9, 6 + 0.05 * gh))), 'gapH': round(gh), 'wind': bool(levels) and gh >= 6,
                   'aLat': ui.shape[0], 'aLon': ui.shape[1], 'aStep': round(st * step, 2), 'aLat0': r2(la0 + i0 * step), 'aLon0': r2(lo0 + j0 * step),
                   'off': len(blob), 'pos': pos, 'patch': patch})
    blob += np.clip(np.rint(np.stack([ui, vi], axis=-1)), -127, 127).astype(np.int8).tobytes()
# v5 cubes: the coarse outer field (float level) follows every fine grid; keep it
# thinned to ~3° for the figure's pale "around the box" arrows (tube-outer.bin).
outer = hdr.get('outer'); oblob = bytearray()
if outer:
    for g in range(hdr['nGrids']):
        nLat, nLon = outer['dims'][g]; n = nLat * nLon
        U = np.frombuffer(raw, dtype='<i2', count=n, offset=off).reshape(nLat, nLon) / hdr['scale']; off += 2 * n
        V = np.frombuffer(raw, dtype='<i2', count=n, offset=off).reshape(nLat, nLon) / hdr['scale']; off += 2 * n
        # Resample onto a fixed global 3° lattice (bilinear) cropped to the figure's
        # map, so the pale arrows sit still while the box (and the outer grid's
        # origin, which follows it) moves.
        lat0, lon0 = outer['origins'][g]; dd = outer['dLat']; d = 3.0
        glat = np.arange(6.0, 75.0 + 1e-9, d); glon = np.arange(-135.0, 24.0 + 1e-9, d)
        fi = np.clip((glat - lat0) / dd, 0, nLat - 1.001); fj = np.clip((glon - lon0) / dd, 0, nLon - 1.001)
        ii = fi.astype(int); jj = fj.astype(int); a_ = (fi - ii)[:, None]; b_ = (fj - jj)[None, :]
        bil = lambda A: ((1 - a_) * (1 - b_) * A[np.ix_(ii, jj)] + (1 - a_) * b_ * A[np.ix_(ii, jj + 1)]
                         + a_ * (1 - b_) * A[np.ix_(ii + 1, jj)] + a_ * b_ * A[np.ix_(ii + 1, jj + 1)])
        ui = bil(U); vi = bil(V)
        slices[g]['outer'] = {'lat0': float(glat[0]), 'lon0': float(glon[0]), 'aLat': ui.shape[0], 'aLon': ui.shape[1], 'aStep': d, 'off': len(oblob)}
        pt = slices[g].get('patch')
        if pt:   # the coarse field's own grid points around the inset's square (its real 1.5° density)
            span = (pt['n'] - 1) * pt['step']; m_ = dd / 2
            ii = [i for i in range(nLat) if pt['lat0'] - m_ <= lat0 + i * dd <= pt['lat0'] + span + m_]
            jj = [j for j in range(nLon) if pt['lon0'] - m_ <= lon0 + j * dd <= pt['lon0'] + span + m_]
            pt['coarse'] = [[r2(lat0 + i * dd), r2(lon0 + j * dd), int(round(float(U[i, j]))), int(round(float(V[i, j])))] for i in ii for j in jj]
            # the difference panel: box winds minus the coarse field interpolated to the same 0.25°
            # points (what a particle gains by being in the box), stored ×4 (0.25 m/s steps)
            plat = pt['lat0'] + np.arange(pt['n']) * pt['step']; plon = pt['lon0'] + np.arange(pt['n']) * pt['step']
            qi = np.clip((plat - lat0) / dd, 0, nLat - 1.001); qj = np.clip((plon - lon0) / dd, 0, nLon - 1.001)
            i2 = qi.astype(int); j2 = qj.astype(int); a2 = (qi - i2)[:, None]; b2 = (qj - j2)[None, :]
            bil2 = lambda A: ((1 - a2) * (1 - b2) * A[np.ix_(i2, j2)] + (1 - a2) * b2 * A[np.ix_(i2, j2 + 1)]
                              + a2 * (1 - b2) * A[np.ix_(i2 + 1, j2)] + a2 * b2 * A[np.ix_(i2 + 1, j2 + 1)])
            fine = fine_patch[g]
            du = fine[..., 0] - bil2(U); dv = fine[..., 1] - bil2(V)
            pt['diffOff'] = len(pblob); pt['diffRms'] = r2(np.sqrt((du ** 2 + dv ** 2).mean()))
            pblob += np.clip(np.rint(np.stack([du, dv], axis=-1) * 4), -127, 127).astype(np.int8).tobytes()
        oblob += np.clip(np.rint(np.stack([ui, vi], axis=-1)), -127, 127).astype(np.int8).tobytes()
json.dump({'levelHpa': hdr['levelHpa'], 'levels': levels, 'stepH': hdr['stepMs'] / 3600000, 'slices': slices,
           'outerStep': outer['dLat'] if outer else None}, open(f'{OUT}/tube.json', 'w'), separators=(',', ':'))
open(f'{OUT}/tube.bin', 'wb').write(bytes(blob))
if outer:
    open(f'{OUT}/tube-outer.bin', 'wb').write(bytes(oblob))
open(f'{OUT}/tube-patch.bin', 'wb').write(bytes(pblob))

def gap_path(name):
    tr = json.load(open(f'{S}/{name}'))['observed']['reconstructed_track']
    tt = np.array([ms(p['time_utc']) for p in tr]); ll = np.array([[p['lat'], p['lon']] for p in tr])
    idx = np.clip(np.searchsorted(tt, gap_times), 0, len(tt) - 1)
    idx0 = np.clip(idx - 1, 0, len(tt) - 1)
    use = np.where(np.abs(tt[idx] - gap_times) <= np.abs(tt[idx0] - gap_times), idx, idx0)
    return ll[use]
drawn = gap_path('prod_trimmed.json')

# ── posterior.bin / posterior.json: the draws behind the line ─────────────────
sel = np.rint(np.arange(STEPS) / (STEPS - 1) * (n1 - 1)).astype(int)
Asub = A[:, sel, :]                                    # (2000, 101, 2)
rng = np.random.default_rng(7)
subset = np.sort(rng.choice(K, 500, replace=False))
pos_bin = np.clip(np.rint(Asub[subset] * 100), -32767, 32767).astype('<i2')
open(f'{OUT}/posterior.bin', 'wb').write(pos_bin.tobytes())

stats = []
for s in range(STEPS):
    d = hav(Asub[:, s, 0], Asub[:, s, 1], drawn[s][0], drawn[s][1])      # every draw vs the drawn line at this hour
    stats.append({'within300': round(float((d <= 300).mean()), 3), 'r90': int(round(float(np.percentile(d, 90)), -1))})
posterior = {'n': 500, 'steps': STEPS, 'hours': gap['dt_hours'], 'tA': tA, 'nTotal': K, 'drawn': path2(drawn), 'stats': stats}
json.dump(posterior, open(f'{OUT}/posterior.json', 'w'), separators=(',', ':'))

# ── clouds.json / clouds.bin: 200 draws for each of the other long gaps ──────
cloud_meta = []; cloud_blob = bytearray(); crng = np.random.default_rng(11)
for g2 in sorted((g for g in post['gaps'] if 'samples' in g and g['dt_hours'] >= 6 and g is not gap), key=lambda g: g['tA']):
    S2 = np.array(g2['samples'], dtype=np.float64); k2, m2, _ = S2.shape
    steps2 = max(3, round(g2['dt_hours'] / 2) + 1); sel2 = np.rint(np.arange(steps2) / (steps2 - 1) * (m2 - 1)).astype(int)
    pick = np.sort(crng.choice(k2, min(200, k2), replace=False))
    arr = np.clip(np.rint(S2[pick][:, sel2, :] * 100), -32767, 32767).astype('<i2')
    cloud_meta.append({'tA': g2['tA'], 'tB': g2['tB'], 'hours': g2['dt_hours'], 'n': int(len(pick)), 'steps': steps2, 'off': len(cloud_blob) // 2})
    cloud_blob += arr.tobytes()
open(f'{OUT}/clouds.bin', 'wb').write(bytes(cloud_blob))
json.dump({'gaps': cloud_meta}, open(f'{OUT}/clouds.json', 'w'), separators=(',', ':'))

# ── filters.json / filters.bin: the two filters' clouds, for the tube figure ──
fl_meta = []; fl_blob = bytearray()
for f in sorted(post.get('filters', []), key=lambda f: (f['when'], f['dir'])):
    arr = np.clip(np.rint(np.array(f['pts'], dtype=np.float64) * 100), -32767, 32767).astype('<i2')
    fl_meta.append({'t': f['when'], 'dir': f['dir'], 'n': len(f['pts']), 'off': len(fl_blob) // 2})
    fl_blob += arr.tobytes()
open(f'{OUT}/filters.bin', 'wb').write(bytes(fl_blob))
json.dump({'snaps': fl_meta}, open(f'{OUT}/filters.json', 'w'), separators=(',', ':'))

# ── forecast.json / forecast.bin: the ensemble from the last fix ──────────────
ens = prod['ensemble']; div = prod['divergence']; nominal = prod['predicted_hindcast']['path']
H = min(len(m) for m in ens); STEP = 3
hours = list(range(0, H, STEP))
if hours[-1] != H - 1: hours.append(H - 1)
M = np.array([[m[h] for h in hours] for m in ens])    # (62, steps, 2) lon, lat
nom = np.array([nominal[h] for h in hours])            # (steps, 2) lon, lat
spread = []
for s in range(len(hours)):
    d = np.sort(hav(M[:, s, 1], M[:, s, 0], nom[s, 1], nom[s, 0])); spread.append(round(float(d[int(0.75 * (len(d) - 1))])))
fc_bin = np.clip(np.rint(np.stack([M[:, :, 1], M[:, :, 0]], -1) * 100), -32767, 32767).astype('<i2')
open(f'{OUT}/forecast.bin', 'wb').write(fc_bin.tobytes())
last = fixes[-1]
forecast = {'members': len(ens), 'gefs': prod['metadata']['members']['gefs'], 'aigefs': prod['metadata']['members']['aigefs'], 'steps': len(hours), 'hours': hours,
            'start': last['time_utc'], 'lastFix': [r2(last['lat']), r2(last['lon'])], 'median': [[r2(b), r2(a)] for a, b in nom],
            'spreadKm': spread, 'thresholdKm': div['threshold_km'], 'divergence': {'time': div['time_utc'], 'spreadKm': div['spread_km'], 'lat': r2(div['lonlat'][1]), 'lon': r2(div['lonlat'][0])}}
json.dump(forecast, open(f'{OUT}/forecast.json', 'w'), separators=(',', ':'))

# ── coast-atlantic.json: finer coastlines for the regional views ─────────────
land = json.load(open(f'{D}/ne_50m_land.geojson'))
LON0, LON1, LAT0, LAT1 = -140, 20, 0, 70
lines = []
def simplify(ring, tol=0.06):
    out = [ring[0]]
    for p in ring[1:]:
        if abs(p[0] - out[-1][0]) + abs(p[1] - out[-1][1]) >= tol: out.append(p)
    return out
for f in land['features']:
    g = f['geometry']; polys = g['coordinates'] if g['type'] == 'MultiPolygon' else [g['coordinates']]
    for poly in polys:
        for ring in poly:
            pts = simplify([[round(x, 2), round(y, 2)] for x, y in ring])
            cur = []
            for p in pts:
                if LON0 <= p[0] <= LON1 and LAT0 <= p[1] <= LAT1: cur.append(p)
                else:
                    if len(cur) > 1: lines.append(cur)
                    cur = []
            if len(cur) > 1: lines.append(cur)
json.dump(lines, open(f'{OUT}/coast-atlantic.json', 'w'), separators=(',', ':'))

for f in sorted(os.listdir(OUT)): print(f'  {f:22s} {os.path.getsize(os.path.join(OUT, f)) / 1024:7.0f} KB')
print('coast points', sum(len(l) for l in lines),
      '| tube slices', len(slices), '| forecast steps', len(hours), 'div spread', spread[-1])
