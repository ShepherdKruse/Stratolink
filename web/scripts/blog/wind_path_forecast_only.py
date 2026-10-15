"""Forward-only cloud for the blog post's "forecast vs bridge" figure: 500 particles
launched from the fix before Stratolink 3's 201-hour gap and run forward for the whole
gap with the long-gap smoother's particle model (AR(1) heading 12°, speed 15 %, τ 18 h;
pressure AR(1) 8 hPa, τ 48 h, from the fix's pressure), but with no knowledge of the
fix after the gap, plus the plain wind path: one particle with no perturbation at all,
riding the winds along the pressure line between the two fixes. GFS 0.25° at 250/300/350 hPa every 3 hours (via the ingest's NOAA
fetcher), subsampled to a global 0.5° grid, linear in time and pressure.

usage: python3 wind_path_forecast_only.py <figure data dir> [start pressure hPa, default 287] [end pressure, default 281]
reads <dir>/posterior.json (gap start/end and the drawn line's endpoints);
writes <dir>/forecast-only.json (with the plain wind path as `nominal`, [lat, lon] per step) and
forecast-only.bin (Int16 lat, lon ×100, particle-major).
"""
import json, math, os, sys
from datetime import datetime, timedelta, timezone
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import gfs_ingest as gi  # noqa: E402

DIR = sys.argv[1]; P0 = float(sys.argv[2]) if len(sys.argv) > 2 else 287.0; P1 = float(sys.argv[3]) if len(sys.argv) > 3 else 281.0
post = json.load(open(os.path.join(DIR, 'posterior.json')))
tA = post['tA']; hours = post['hours']; tB = tA + hours * 3.6e6; STEPS = post['steps']
A = post['drawn'][0]; B = post['drawn'][-1]
N, DT_H, LEVELS = 500, 1 / 3, [250, 300, 350]
SPEED_SIGMA, DIR_SIGMA, TAU_H, P_SIGMA, P_TAU_H = 0.15, 12.0, 18.0, 8.0, 48.0
LATS = np.arange(90, -90.01, -0.5); NLON = 720                     # global, lon 0 … 359.5 (wraps)
rows = np.round((90 - LATS) / 0.25).astype(int); cols = np.arange(NLON) * 2

t0 = datetime.fromtimestamp(tA / 1000, timezone.utc).replace(minute=0, second=0, microsecond=0)
t0 -= timedelta(hours=t0.hour % 3)
times = []
t = t0
while t.timestamp() * 1000 <= tB + 3 * 3.6e6:
    times.append(t); t += timedelta(hours=3)
latest = datetime.now(timezone.utc)
U = np.zeros((len(times), len(LEVELS), len(LATS), NLON), np.float32); V = np.zeros_like(U)
for k, t in enumerate(times):
    cyc, fhr = gi.pick_source(t, latest)
    for j, L in enumerate(LEVELS):
        f = gi.fetch_uv(cyc, fhr, L)
        U[k, j] = f['u'][np.ix_(rows, cols)]; V[k, j] = f['v'][np.ix_(rows, cols)]
    gi.clear_field_cache()
    print(f'{k + 1}/{len(times)} {t:%m-%d %HZ}', flush=True)
T0 = times[0].timestamp() * 1000

def wind(lat, lon, tms, p):
    fi = np.clip((LATS[0] - lat) / 0.5, 0, len(LATS) - 1.001); fj = (lon % 360) / 0.5
    i = fi.astype(int); j = fj.astype(int) % NLON; j1 = (j + 1) % NLON; a = fi - i; b = fj - np.floor(fj)
    ft = min(max((tms - T0) / 1.08e7, 0), len(times) - 1.001); k = int(ft); c = ft - k
    pc = np.clip(p, LEVELS[0], LEVELS[-1]); q = np.minimum((pc >= LEVELS[1]).astype(int), len(LEVELS) - 2); e = (pc - np.array(LEVELS)[q]) / 50.0
    out, m = [], np.arange(len(lat))
    for F in (U, V):
        val = 0
        for kk, wt in ((k, 1 - c), (k + 1, c)):
            for dq, wl in ((0, 1 - e), (1, e)):
                G = F[kk][q + dq]
                val = val + wt * wl * ((1 - a) * (1 - b) * G[m, i, j] + (1 - a) * b * G[m, i, j1]
                                       + a * (1 - b) * G[m, i + 1, j] + a * b * G[m, i + 1, j1])
        out.append(val)
    return out

rng = np.random.default_rng(3)
rho = math.exp(-DT_H / TAU_H); inn = math.sqrt(1 - rho * rho); rp = math.exp(-DT_H / P_TAU_H); ip = math.sqrt(1 - rp * rp)
lat = np.full(N, A[0]); lon = np.full(N, A[1]); sp = rng.normal(0, SPEED_SIGMA, N); dr = rng.normal(0, DIR_SIGMA, N); po = np.zeros(N)
nsteps = int(round(hours / DT_H)); record = np.rint(np.arange(STEPS) / (STEPS - 1) * nsteps).astype(int)
out = np.zeros((N, STEPS, 2)); out[:, 0] = [A[0], A[1]]; r = 1
for s in range(1, nsteps + 1):
    sp = rho * sp + inn * rng.normal(0, SPEED_SIGMA, N); dr = rho * dr + inn * rng.normal(0, DIR_SIGMA, N); po = rp * po + ip * rng.normal(0, P_SIGMA, N)
    u, v = wind(lat, lon, tA + s * DT_H * 3.6e6, P0 + po)
    k = np.maximum(0.2, 1 + sp); th = np.radians(dr)
    ur = (u * np.cos(th) - v * np.sin(th)) * k; vr = (u * np.sin(th) + v * np.cos(th)) * k
    lat = lat + vr * DT_H * 3600 / 111320; lon = lon + ur * DT_H * 3600 / (111320 * np.maximum(np.cos(np.radians(lat)), 0.05))
    while r < STEPS and record[r] == s:
        out[:, r] = np.stack([lat, lon], 1); r += 1

# the plain wind path: every perturbation held at zero, pressure along the line between the
# readings at the two fixes, in 5-minute steps (a single path needs a finer step than a cloud
# to converge: at 20 minutes it can land hundreds of km from the converged answer)
SUB = 4; nlat = np.array([A[0]]); nlon = np.array([A[1]]); nominal = [[A[0], A[1]]]; r = 1
for s in range(1, nsteps * SUB + 1):
    f = s / (nsteps * SUB); u, v = wind(nlat, nlon, tA + s * DT_H / SUB * 3.6e6, np.array([P0 + (P1 - P0) * f]))
    nlat = nlat + v * DT_H / SUB * 3600 / 111320; nlon = nlon + u * DT_H / SUB * 3600 / (111320 * max(math.cos(math.radians(nlat[0])), 0.05))
    while r < STEPS and record[r] * SUB == s:
        nominal.append([round(float(nlat[0]), 3), round(float(nlon[0]), 3)]); r += 1

def hav(a1, o1, a2, o2):
    a1, o1, a2, o2 = map(np.radians, (a1, o1, a2, o2)); d = np.sin((a2 - a1) / 2) ** 2 + np.cos(a1) * np.cos(a2) * np.sin((o2 - o1) / 2) ** 2
    return 2 * 6371 * np.arcsin(np.sqrt(d))
stats = []
for s in range(STEPS):
    c = [float(np.median(out[:, s, 0])), float(np.median(out[:, s, 1]))]
    stats.append({'r90': int(round(float(np.percentile(hav(out[:, s, 0], out[:, s, 1], c[0], c[1]), 90)), -1))})
toB = hav(out[:, -1, 0], out[:, -1, 1], B[0], B[1])
meta = {'n': N, 'steps': STEPS, 'hours': hours, 'tA': tA, 'startHpa': P0, 'endHpa': P1, 'stats': stats,
        'endToB': {'median': int(round(float(np.median(toB)), -1)), 'within300': round(float((toB <= 300).mean()), 3), 'within500': round(float((toB <= 500).mean()), 3)},
        'nominal': nominal, 'nominalToB': int(round(float(hav(nominal[-1][0], nominal[-1][1], B[0], B[1])), -1)),
        'pastMapEdge': round(float((out[:, -1, 1] > 0).mean()), 3)}
open(os.path.join(DIR, 'forecast-only.bin'), 'wb').write(np.clip(np.rint(out * 100), -32767, 32767).astype('<i2').tobytes())
json.dump(meta, open(os.path.join(DIR, 'forecast-only.json'), 'w'), separators=(',', ':'))
print('plain wind path ends', meta['nominalToB'], 'km from the fix in Spain')
print('end distance to the fix in Spain: median', meta['endToB']['median'], 'km; within 300 km', meta['endToB']['within300'], '| r90 at end', stats[-1]['r90'], '| east of 0° at the end', meta['pastMapEdge'])
