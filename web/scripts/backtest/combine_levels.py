"""Combine the 250-300 and 300-400 ABQ→Spain level sweeps into one figure per
source: each pressure level's ensemble-MEAN trajectory, colored by pressure, on a
single map with the actual fix. The colored endpoint nearest the ✕ = effective level.
Pure plotting from cache — no download. Run from the `web/` directory."""
import sys, math, pickle, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..")); sys.path.insert(0, HERE)
import numpy as np
import backtest_multi as bm
OUT = bm.OUT
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize

P1 = pickle.load(open(os.path.join(OUT, "bt_levels_test2_250-300.pkl"), "rb")) \
    if os.path.exists(os.path.join(OUT, "bt_levels_test2_250-300.pkl")) \
    else pickle.load(open(os.path.join(OUT, "bt_levels_test2.pkl"), "rb"))     # 250-300 (legacy or tagged)
P2 = pickle.load(open(os.path.join(OUT, "bt_levels_test2_300-400.pkl"), "rb")) # 300-400
p0 = tuple(P1["p0"]); pv = tuple(P1["pv"]); SRCS = ["GEFS", "AIGEFS", "ECMWF"]
CMAP = plt.cm.viridis; NORM = Normalize(vmin=250, vmax=400)      # color = assumed pressure

TH = np.linspace(0, 2*np.pi, 90)
def ellipse(cov, coslat, end, chi2=1.386):     # 50% endpoint ellipse (lon, lat arrays)
    vals, vecs = np.linalg.eigh(np.array(cov)); a = np.sqrt(chi2*np.maximum(vals, 0))
    e = vecs @ (a[:, None]*np.array([np.cos(TH), np.sin(TH)]))
    return end[1] + e[0]/(111.32*coslat), end[0] + e[1]/111.32

def gather(src):
    """{level: dict(mp, miss, cov, coslat, end)} merged across both sweeps (P2's 300 wins)."""
    out = {}
    for P in (P1, P2):
        for lev in P["levels"]:
            R = P["R"].get(src, {})
            if lev in R and R[lev].get("paths"):
                arr = np.array(R[lev]["paths"])            # (members, steps, 2) = (lat,lon)
                out[lev] = dict(mp=arr.mean(axis=0), miss=R[lev]["miss"],
                                cov=R[lev]["cov"], coslat=R[lev]["coslat"], end=R[lev]["mean"])
    return dict(sorted(out.items()))

data = {s: gather(s) for s in SRCS}
SRCS = [s for s in SRCS if data[s]]

# shared extent from mean trajectories + 50% ellipses + key points
pts = [p0, pv]
for s in SRCS:
    for lev, d in data[s].items():
        mp = d["mp"]; pts += [(mp[i, 0], mp[i, 1]) for i in range(0, len(mp), 4)]
        elon, elat = ellipse(d["cov"], d["coslat"], d["end"])
        pts += [(la, lo) for la, lo in zip(elat[::8], elon[::8])]
lats = [q[0] for q in pts]; lons = [q[1] for q in pts]
px = (max(lons)-min(lons))*0.05+0.4; py = (max(lats)-min(lats))*0.05+0.4
extent = (min(lons)-px, max(lons)+px, min(lats)-py, max(lats)+py)
clat = (extent[2]+extent[3])/2; A = 1/math.cos(math.radians(clat))
W = 13; ph = (W-1.5) * A * (extent[3]-extent[2])/(extent[1]-extent[0])
fig, axes = plt.subplots(len(SRCS), 1, figsize=(W, min(15, len(SRCS)*ph+1.5)),
                         sharex=True, sharey=True, squeeze=False, constrained_layout=True)
for r, s in enumerate(SRCS):
    ax = axes[r][0]; bm.add_basemap(ax)
    best = min(data[s].items(), key=lambda kv: kv[1]["miss"])[0]
    for lev, d in data[s].items():
        c = CMAP(NORM(lev)); is_best = (lev == best)
        elon, elat = ellipse(d["cov"], d["coslat"], d["end"])      # 50% spread ellipse (outline only)
        ax.plot(elon, elat, "-", color=c, lw=1.4 if is_best else 0.8, alpha=0.8, zorder=2)
        ax.plot(d["mp"][:, 1], d["mp"][:, 0], "-", color=c, lw=2.4 if is_best else 0.8,
                alpha=0.95, zorder=4 if is_best else 3)
        ax.plot(d["mp"][-1, 1], d["mp"][-1, 0], "o", color=c, ms=7 if is_best else 3.5,
                mec="white", mew=0.7, zorder=5)
    ax.plot(p0[1], p0[0], marker="*", color="#222", ms=12, mec="white", mew=0.7, zorder=6)
    ax.plot(pv[1], pv[0], marker="X", color="#111", ms=13, mec="white", mew=1.3, zorder=7)
    ax.set_xlim(extent[0], extent[1]); ax.set_ylim(extent[2], extent[3])
    ax.set_aspect(A); ax.grid(alpha=0.15, lw=0.4); ax.tick_params(labelsize=7)
    ax.set_ylabel(s, fontsize=11, fontweight="bold")
    if r == len(SRCS)-1: ax.set_xlabel("lon", fontsize=8)
    ax.set_title(f"{s}  —  best fit at {best} hPa ({data[s][best]['miss']:.0f} km);  outline = 50% spread;  ★ start  ✕ actual",
                 fontsize=9, color="#333")
sm = ScalarMappable(norm=NORM, cmap=CMAP); sm.set_array([])
cb = fig.colorbar(sm, ax=axes, location="right", shrink=0.7, pad=0.015)
cb.set_label("assumed float pressure (hPa)  — low=high altitude, high=low altitude", fontsize=9)
cb.set_ticks([250, 300, 350, 400])
fig.suptitle(f"ABQ→Spain (10-day, {P1['disp']:.0f} km) — ensemble-mean trajectory vs assumed float pressure (250→400 hPa)\n"
             "thick line = best-fit level per source", fontsize=12)
out = os.path.join(OUT, "combine_levels_test2.png"); fig.savefig(out, dpi=200); print(f"plot -> {out}")
# also print the merged miss-vs-level table
print("\nmiss (km) by level, merged 250-400:")
alllev = sorted(set().union(*[set(data[s]) for s in SRCS]))
print("  level: " + " ".join(f"{l:>5}" for l in alllev))
for s in SRCS:
    print(f"  {s:6s}: " + " ".join(f"{data[s][l]['miss']:5.0f}" if l in data[s] else "    -" for l in alllev))
