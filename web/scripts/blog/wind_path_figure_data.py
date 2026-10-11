"""Build the compact data bundle behind the interactive figures of the blog post
"Drawing the path between packets" (public/assets/wind-path/).

usage: python3 wind_path_figure_data.py <runs dir> <downloads dir> <out dir> <recon cube .slwc>

<runs dir> holds the stratolink-3 compute outputs the post is about (local reruns of
scripts/compute_forecasts.ts with the Blob token unset): prod_after_run.json and
prod_trimmed.json (two production forecast JSONs), after1-3.json / p6000_r*.json /
p20k_r*.json / p60000_r*.json (forward-sampler reruns by particle count),
twofilter_r1-3.json (two-filter reruns) and posterior2k_r1.json (2,000 posterior
draws of the 201 h gap, dumped from reconstructLongGap with a temporary capture
hook). <downloads dir> holds Natural Earth's ne_50m_land.geojson. The cube is the
device's reconstruction cube from .windcube/cubes/.
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
for g in range(hdr['nGrids']):
    nLat, nLon = hdr['dims'][g]; n = nLat * nLon
    U = np.frombuffer(raw, dtype='<i2', count=n, offset=off).reshape(nLat, nLon) / hdr['scale']; off += 2 * n
    V = np.frombuffer(raw, dtype='<i2', count=n, offset=off).reshape(nLat, nLon) / hdr['scale']; off += 2 * n
    la0, lo0 = hdr['origins'][g]; step = hdr['gridStep']; t = hdr['t0Ms'] + g * hdr['stepMs']
    st = max(1, math.ceil(max(nLat, nLon) / 26))
    ui = U[::st, ::st]; vi = V[::st, ::st]
    pos = None
    if track_t[0] <= t <= track_t[-1]:
        k = int(np.searchsorted(track_t, t)); k0 = max(0, k - 1); k1 = min(len(track_t) - 1, k)
        w = 0 if k1 == k0 else (t - track_t[k0]) / (track_t[k1] - track_t[k0])
        p = track_ll[k0] * (1 - w) + track_ll[k1] * w; pos = [r2(p[0]), r2(p[1])]
    slices.append({'t': t, 'lat0': la0, 'lon0': lo0, 'h': round((nLat - 1) * step, 2), 'w': round((nLon - 1) * step, 2),
                   'aLat': ui.shape[0], 'aLon': ui.shape[1], 'aStep': round(st * step, 2), 'off': len(blob), 'pos': pos})
    blob += np.clip(np.rint(np.stack([ui, vi], axis=-1)), -127, 127).astype(np.int8).tobytes()
json.dump({'levelHpa': hdr['levelHpa'], 'stepH': hdr['stepMs'] / 3600000, 'slices': slices}, open(f'{OUT}/tube.json', 'w'), separators=(',', ':'))
open(f'{OUT}/tube.bin', 'wb').write(bytes(blob))

# ── bridges.json: reruns of each method through the long gap ──────────────────
def gap_path(name):
    tr = json.load(open(f'{S}/{name}'))['observed']['reconstructed_track']
    tt = np.array([ms(p['time_utc']) for p in tr]); ll = np.array([[p['lat'], p['lon']] for p in tr])
    idx = np.clip(np.searchsorted(tt, gap_times), 0, len(tt) - 1)
    idx0 = np.clip(idx - 1, 0, len(tt) - 1)
    use = np.where(np.abs(tt[idx] - gap_times) <= np.abs(tt[idx0] - gap_times), idx, idx0)
    return ll[use]
groups = {'600': ['after1.json', 'after2.json', 'after3.json'], '6000': sorted(os.path.basename(f) for f in glob.glob(f'{S}/p6000_r*.json')),
          '20000': sorted(os.path.basename(f) for f in glob.glob(f'{S}/p20k_r*.json')), '60000': sorted(os.path.basename(f) for f in glob.glob(f'{S}/p60000_r*.json'))}
two = ['twofilter_r1.json', 'twofilter_r2.json', 'twofilter_r3.json']
def spread(paths):
    seps = []
    for i in range(len(paths)):
        for j in range(i + 1, len(paths)):
            seps.append(np.median(hav(paths[i][:, 0], paths[i][:, 1], paths[j][:, 0], paths[j][:, 1])))
    return round(float(np.median(seps))) if seps else None
fwd = {k: [gap_path(f) for f in files] for k, files in groups.items()}
twof = [gap_path(f) for f in two]
drawn = gap_path('prod_trimmed.json')
mean_path = np.array(gap['mean'])[np.rint(np.arange(STEPS) / (STEPS - 1) * (n1 - 1)).astype(int)]
bridges = {'steps': STEPS, 'hours': gap['dt_hours'], 'tA': tA, 'tB': tB,
           'forward': {k: {'runs': [path2(p) for p in paths], 'spreadKm': spread(paths)} for k, paths in fwd.items()},
           'twoFilter': {'runs': [path2(p) for p in twof], 'spreadKm': spread(twof)},
           'drawn': path2(drawn), 'mean': path2(mean_path)}
json.dump(bridges, open(f'{OUT}/bridges.json', 'w'), separators=(',', ':'))

# ── posterior.bin / clusters.bin / posterior.json: the draws behind the line ───
sel = np.rint(np.arange(STEPS) / (STEPS - 1) * (n1 - 1)).astype(int)
Asub = A[:, sel, :]                                    # (2000, 101, 2)
# medoid over all 2000 draws, as pathReconstructionLongGap.ts does (time-matched mean distance)
stride_idx = sel[::3]                                  # every ~6 h
lat_s = A[:, stride_idx, 0]; lon_s = A[:, stride_idx, 1]
cosl = np.cos(np.radians(lat_s.mean()))
X = np.stack([lon_s * 111.32 * cosl, lat_s * 111.32], axis=-1)   # (2000, T, 2) local km
acc = np.zeros(K)
for i in range(K):
    acc[i] = np.sqrt(((X - X[i]) ** 2).sum(-1)).mean(1).sum()
medoid = int(np.argmin(acc))
dist_to_medoid = np.sqrt(((X - X[medoid]) ** 2).sum(-1)).mean(1)
kept = np.argsort(dist_to_medoid)[:round(0.10 * K)]
trimmed = Asub[kept].mean(0)
rng = np.random.default_rng(7)
subset = np.sort(rng.choice(K, 500, replace=False))
kept_set = set(kept.tolist())
subset_kept = [int(i) for i, s in enumerate(subset) if s in kept_set]
pos_bin = np.clip(np.rint(Asub[subset] * 100), -32767, 32767).astype('<i2')
open(f'{OUT}/posterior.bin', 'wb').write(pos_bin.tobytes())

def meanshift(pts, h=250.0, iters=40):
    ref = pts.mean(0); c = math.cos(math.radians(ref[0]))
    Xp = np.stack([(pts[:, 1] - ref[1]) * 111.32 * c, (pts[:, 0] - ref[0]) * 111.32], 1); Y = Xp.copy()
    for _ in range(iters):
        d2 = ((Y[:, None, :] - Xp[None, :, :]) ** 2).sum(2); W = np.exp(-d2 / (2 * h * h)); Yn = (W @ Xp) / W.sum(1, keepdims=True)
        moved = np.hypot(*(Yn - Y).T).max(); Y = Yn
        if moved < 0.5: break
    labels = -np.ones(len(pts), dtype=int); centres = []
    for i, y in enumerate(Y):
        for k, cc in enumerate(centres):
            if math.hypot(*(y - cc)) < h / 3: labels[i] = k; break
        else: centres.append(y); labels[i] = len(centres) - 1
    order = np.argsort([-np.sum(labels == k) for k in range(len(centres))]); remap = {int(o): n for n, o in enumerate(order)}
    lab = np.array([remap[int(l)] for l in labels])
    modes = []
    for k in range(len(centres)):
        m = lab == k
        modes.append([round(float(m.mean()), 3), r2(pts[m, 0].mean()), r2(pts[m, 1].mean())])
    return lab, modes
labels = np.zeros((500, STEPS), dtype=np.int8); stats = []
full_mean = Asub.mean(0); med_path = Asub[medoid]
for s in range(STEPS):
    pts = Asub[subset, s, :]
    lab, modes = meanshift(pts); labels[:, s] = np.minimum(lab, 6)
    allpts = Asub[:, s, :]
    within = {name: round(float((hav(allpts[:, 0], allpts[:, 1], p[0], p[1]) <= 300).mean()), 3)
              for name, p in (('mean', full_mean[s]), ('drawn', trimmed[s]), ('medoid', med_path[s]))}
    stats.append({'modes': modes[:6], 'within300': within})
open(f'{OUT}/clusters.bin', 'wb').write(labels.tobytes())
posterior = {'n': 500, 'steps': STEPS, 'hours': gap['dt_hours'], 'tA': tA, 'nTotal': K, 'keptTotal': int(len(kept)),
             'kept': subset_kept, 'mean': path2(full_mean), 'medoid': path2(med_path), 'trimmed': path2(trimmed), 'drawn': path2(drawn), 'stats': stats}
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
print('medoid', medoid, 'kept', len(kept), 'subset kept', len(subset_kept), '| coast points', sum(len(l) for l in lines),
      '| tube slices', len(slices), '| forecast steps', len(hours), 'div spread', spread[-1])
