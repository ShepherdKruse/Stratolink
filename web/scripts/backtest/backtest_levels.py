"""Forecast-replay across pressure levels, for a chosen 2-level bracket.
Fetch the two BRACKET levels ONCE per member, integrate trajectories at every
LEVELS value (linear blends of the two fetched fields — no extra download) + a
mean-over-levels. Grid: 3 sources (rows) x (levels + mean). Caches results.

  python3 -u scripts/backtest/backtest_levels.py 2            # fetch + compute + cache + plot
  python3 -u scripts/backtest/backtest_levels.py 2 --plot-only # re-draw from cache
Outputs go to $BACKTEST_OUT (default /tmp). Run from the `web/` directory.
"""
import sys, math, pickle, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))     # web/scripts — the ingest modules
sys.path.insert(0, HERE)                          # this dir — backtest_multi
import numpy as np
import gfs_ingest as g, gefs_ingest as ge, aigefs_ingest as ai, ecmwf_ingest as ec
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
import backtest_multi as bm
OUT = bm.OUT
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

DEVICE = "stratolink-3"
TESTS = {
    "1": ("2026-05-18T02:03", "2026-05-19T13:58", "California→Mexico"),
    "2": ("2026-05-19T22:28", "2026-05-29T17:46", "Albuquerque→Spain"),
}
BRACKET = (300, 400)                       # the two discrete levels actually fetched
LEVELS = [300, 325, 350, 375, 400]         # swept levels (interpolations within BRACKET)
COLS = LEVELS + ["mean"]
def tag(): return f"{BRACKET[0]}-{BRACKET[1]}"
def pkl_path(test): return os.path.join(OUT, f"bt_levels_test{test}_{tag()}.pkl")

def blend(fLO, fHI, fhr, p):
    lo, hi = BRACKET; t = (p - lo) / (hi - lo)      # 0 at lo, 1 at hi
    uL, vL = fLO[fhr]; uH, vH = fHI[fhr]
    return (uL*(1-t) + uH*t, vL*(1-t) + vH*t)

# Diurnal-cycle scenarios: the balloon's pressure oscillates with LOCAL SOLAR time —
# sinks (higher pressure / lower altitude) pre-dawn, peaks (lower pressure) mid-afternoon.
# (P_mean hPa, peak-to-peak amplitude hPa). amp=0 would be a constant level (already in the grid).
DIURNAL = [(325, 50), (350, 50), (375, 50), (350, 100), (350, 150)]
def dkey(pm, amp): return f"{pm}±{amp//2}"
DKEYS = [dkey(pm, amp) for pm, amp in DIURNAL]

def integrate_diurnal(fLO, fHI, FHRS, as_of, p0, t0, tv, P_mean, amp):
    """Integrate one trajectory whose pressure level oscillates diurnally. At each
    step: pick P from local solar time (max P ~05h pre-dawn, min P ~17h afternoon),
    clamp to the fetched bracket, sample winds via point-bilinear then level+time blend."""
    lo, hi = BRACKET; lat, lon = p0; path = [(lat, lon)]; dt = bm.DT_MIN*60; t = t0
    while t < tv:
        h = (t - as_of).total_seconds()/3600
        a = max(f for f in FHRS if f <= h); b = min(f for f in FHRS if f >= h)
        fr = 0.0 if b == a else (h-a)/(b-a)
        solar = (t.hour + t.minute/60 + lon/15.0) % 24
        P = P_mean + (amp/2.0)*math.cos(2*math.pi*(solar-5.0)/24.0)   # peak pressure ~05h local
        P = min(hi, max(lo, P)); tt = (P-lo)/(hi-lo)
        sw = lambda fld: bm.bilin(fld, lat, lon)
        uA = sw(fLO[a][0])*(1-tt) + sw(fHI[a][0])*tt; vA = sw(fLO[a][1])*(1-tt) + sw(fHI[a][1])*tt
        uB = sw(fLO[b][0])*(1-tt) + sw(fHI[b][0])*tt; vB = sw(fLO[b][1])*(1-tt) + sw(fHI[b][1])*tt
        u = uA*(1-fr) + uB*fr; v = vA*(1-fr) + vB*fr
        lat += v*dt/111320.0; lon += u*dt/(111320.0*math.cos(math.radians(lat)))
        path.append((lat, lon)); t += timedelta(seconds=dt)
    return path

def levels_from_fields(fLO, fHI, FHRS, as_of, p0, t0, tv):
    mlp = {}
    for p in LEVELS:
        F = {"as_of": as_of}
        for fhr in FHRS: F[fhr] = blend(fLO, fHI, fhr, p)
        mlp[p] = bm.integrate(F, FHRS, p0, t0, tv)
    n = min(len(mlp[p]) for p in LEVELS)
    mean = [(sum(mlp[p][i][0] for p in LEVELS)/len(LEVELS),
             sum(mlp[p][i][1] for p in LEVELS)/len(LEVELS)) for i in range(n)]
    return mlp, mean

def member_source(name, members, fetch_level, as_of, FHRS, p0, t0, tv):
    lo, hi = BRACKET; per = {c: [] for c in COLS}; perD = {dk: [] for dk in DKEYS}
    for k, mem in enumerate(members):
        try:
            fLO, fHI = {}, {}
            tasks = [(fhr, lv) for fhr in FHRS for lv in BRACKET]
            with ThreadPoolExecutor(max_workers=8) as ex:
                for (fhr, lv), uv in ex.map(lambda t: (t, fetch_level(mem, as_of, t[0], t[1])), tasks):
                    (fLO if lv == lo else fHI)[fhr] = uv
            mlp, mean = levels_from_fields(fLO, fHI, FHRS, as_of, p0, t0, tv)
            for p in LEVELS: per[p].append(mlp[p])
            per["mean"].append(mean)
            for (pm, amp), dk in zip(DIURNAL, DKEYS):
                perD[dk].append(integrate_diurnal(fLO, fHI, FHRS, as_of, p0, t0, tv, pm, amp))
            print(f"  {name} [{k+1}/{len(members)}] member {mem}", flush=True)
        except Exception as e:
            print(f"  {name} {mem}: skipped ({e})", flush=True)
    return per, perD

def ecmwf_source(as_of, FHRS, p0, t0, tv):
    lo, hi = BRACKET; idxmap = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for cs, m in ex.map(lambda s: ec.fetch_index((as_of, s), list(BRACKET)), FHRS):
            if m: idxmap[cs] = m
    members = [m for m in ec.MEMBERS if all((as_of, s) in idxmap and m in idxmap[(as_of, s)] for s in FHRS)]
    def roll(uv):
        u, v = uv; return (np.roll(u, u.shape[1]//2, axis=1), np.roll(v, v.shape[1]//2, axis=1))
    per = {c: [] for c in COLS}; perD = {dk: [] for dk in DKEYS}
    for k, mem in enumerate(members):
        try:
            fLO, fHI = {}, {}
            with ThreadPoolExecutor(max_workers=6) as ex:
                for s, uv in ex.map(lambda s: (s, roll(ec.fetch_member_field(mem, (as_of, s), idxmap, lo, lo, 0.0))), FHRS): fLO[s] = uv
                for s, uv in ex.map(lambda s: (s, roll(ec.fetch_member_field(mem, (as_of, s), idxmap, hi, hi, 0.0))), FHRS): fHI[s] = uv
            mlp, mean = levels_from_fields(fLO, fHI, FHRS, as_of, p0, t0, tv)
            for p in LEVELS: per[p].append(mlp[p])
            per["mean"].append(mean)
            for (pm, amp), dk in zip(DIURNAL, DKEYS):
                perD[dk].append(integrate_diurnal(fLO, fHI, FHRS, as_of, p0, t0, tv, pm, amp))
            print(f"  ECMWF [{k+1}/{len(members)}] member {mem}", flush=True)
        except Exception as e:
            print(f"  ECMWF e{mem}: skipped ({e})", flush=True)
    return per, perD

def draw_cell(ax, R, p0, pv, color, title, extent, show_x, ylabel):
    bm.add_basemap(ax)
    for pth in R["paths"]:
        ax.plot([q[1] for q in pth], [q[0] for q in pth], "-", color=color, alpha=0.16, lw=0.5, zorder=1)
    ax.plot(R["ends"][:, 1], R["ends"][:, 0], ".", color=color, ms=2.3, alpha=0.4, zorder=2)
    vals, vecs = np.linalg.eigh(R["cov"]); th = np.linspace(0, 2*np.pi, 100)
    for chi2, ls in [(1.386, ":"), (4.605, "--")]:
        a = np.sqrt(chi2*np.maximum(vals, 0)); e = vecs @ (a[:, None]*np.array([np.cos(th), np.sin(th)]))
        ax.plot(R["mean"][1]+e[0]/(111.32*R["coslat"]), R["mean"][0]+e[1]/111.32, ls, color=color, lw=0.9, alpha=0.7, zorder=3)
    ax.plot(p0[1], p0[0], marker="o", color="#404040", ms=3.5, mec="white", mew=0.5, zorder=6)
    ax.plot(R["mean"][1], R["mean"][0], marker="D", mfc="none", mec=color, ms=4.5, mew=0.9, zorder=6)
    ax.plot(pv[1], pv[0], marker="x", color="#c0392b", ms=5.5, mew=1.2, zorder=7)
    ax.set_xlim(extent[0], extent[1]); ax.set_ylim(extent[2], extent[3])
    ax.set_aspect(1/math.cos(math.radians(R["mean"][0])))
    ax.grid(alpha=0.15, lw=0.4, zorder=0); ax.tick_params(labelsize=6)
    if show_x: ax.set_xlabel("lon", fontsize=7)
    if ylabel: ax.set_ylabel(ylabel, fontsize=10, fontweight="bold")
    ax.set_title(f"{title}\nmiss {R['miss']:.0f}km · 50%{'Y' if R['in50'] else 'N'} 90%{'Y' if R['in90'] else 'N'}",
                 fontsize=7.3, color="#333", linespacing=1.25)

def make_grid(P):
    R, p0, pv = P["R"], tuple(P["p0"]), tuple(P["pv"])
    rows = [s for s in ["GEFS", "AIGEFS", "ECMWF"] if R.get(s)]; ncol = len(COLS)   # skip empty sources
    allpts = [p0, pv] + [tuple(e) for src in rows for c in COLS if c in R[src] for e in R[src][c]["ends"]]
    lons = [q[1] for q in allpts]; lats = [q[0] for q in allpts]
    px = (max(lons)-min(lons))*0.08+0.3; py = (max(lats)-min(lats))*0.08+0.3
    extent = (min(lons)-px, max(lons)+px, min(lats)-py, max(lats)+py)
    clat = (extent[2]+extent[3])/2; A = 1/math.cos(math.radians(clat))
    lon_span = extent[1]-extent[0]; lat_span = extent[3]-extent[2]
    W = 3*ncol; panel_w = (W-1.5)/ncol; panel_h = panel_w * A * lat_span/lon_span
    fig_h = min(15, max(6, 3*panel_h + 1.6))
    nrow = len(rows)
    fig, axes = plt.subplots(nrow, ncol, figsize=(W, fig_h * nrow/3), sharex=True, sharey=True, constrained_layout=True, squeeze=False)
    for r, src in enumerate(rows):
        for cc, c in enumerate(COLS):
            ax = axes[r][cc]; lab = "mean (all levels)" if c == "mean" else f"{c} hPa"
            if c in R[src]:
                draw_cell(ax, R[src][c], p0, pv, bm.LINE[src], lab, extent,
                          show_x=(r == nrow-1), ylabel=(src if cc == 0 else None))
            else:
                ax.text(0.5, 0.5, "no data", ha="center", va="center", fontsize=7); ax.axis("off")
    fig.suptitle(f"{P['leg']} leg (test {P['test']}, {P['t0']:%m-%d %HZ} +{P['gap_h']:.0f}h) — skill vs float pressure, {tag()} hPa band\n"
                 f"start ●  forecast-mean ◇  actual ✕   ·   ellipses 50%(dotted)/90%(dashed)   ·   actual displacement {P['disp']:.0f} km",
                 fontsize=11)
    out = os.path.join(OUT, f"backtest_levels_test{P['test']}_{tag()}.png"); fig.savefig(out, dpi=200); print(f"  plot -> {out}", flush=True)

def run(test):
    START, VERIFY, LEG = TESTS[test]
    fixes = g.mission_fixes(DEVICE, datetime(2026, 5, 16, tzinfo=timezone.utc))
    p0, t0 = bm.nearest_fix(fixes, START); pv, tv = bm.nearest_fix(fixes, VERIFY)
    gap_h = (tv-t0).total_seconds()/3600
    print(f"{LEG}: {t0:%m-%d %H:%M}Z ({p0[0]:.2f},{p0[1]:.2f}) -> {tv:%m-%d %H:%M}Z ({pv[0]:.2f},{pv[1]:.2f}) "
          f"gap {gap_h:.0f}h actual {bm.km(p0,pv):.0f} km | bracket {BRACKET} levels {LEVELS}", flush=True)
    g_as = bm.as_of_cycle(t0, 6, lambda c: bm._try(lambda: g.http_get(ge.gefs_member_url("gec00", c, 0)+".idx")))
    a_as = bm.as_of_cycle(t0, 9, ai.cycle_exists)
    e_as = bm.as_of_cycle(t0, 9, lambda c: ec.fetch_index((c, 0), [BRACKET[1]])[1] is not None)
    raw = {}
    raw["GEFS"] = member_source("GEFS", ge.ALL_MEMBERS, ge.fetch_member_level, g_as, bm.gefs_fhrs(g_as, t0, tv), p0, t0, tv)
    raw["AIGEFS"] = member_source("AIGEFS", ai.MEMBERS, ai.fetch_member_level, a_as, bm.fhrs_for(a_as, t0, tv, 6), p0, t0, tv)
    raw["ECMWF"] = ecmwf_source(e_as, bm.fhrs_for(e_as, t0, tv, 6), p0, t0, tv)
    R = {}; RD = {}
    for src, (per, perD) in raw.items():
        R[src] = {c: bm.score(per[c], pv) for c in COLS if len(per[c]) >= 3}
        RD[src] = {dk: bm.score(perD[dk], pv) for dk in DKEYS if len(perD[dk]) >= 3}
        print(f"  {src} fixed: " + " | ".join(f"{c}:{R[src][c]['miss']:.0f}km/{'Y' if R[src][c]['in90'] else 'N'}" for c in COLS if c in R[src]), flush=True)
    print("\n=== DIURNAL vs best constant level (ensemble-mean miss, km) ===", flush=True)
    for src in R:
        if not R[src]: continue
        bf = min((R[src][c]['miss'], c) for c in COLS if c in R[src])
        print(f"  {src}: best-constant {bf[1]}={bf[0]:.0f} | " +
              " ".join(f"{dk}:{RD[src][dk]['miss']:.0f}{'*' if RD[src][dk]['miss']<bf[0] else ''}" for dk in DKEYS if dk in RD[src]), flush=True)
    print("  (* = diurnal scenario beats the best constant level)", flush=True)
    P = dict(test=test, leg=LEG, R=R, RD=RD, diurnal=DIURNAL, dkeys=DKEYS,
             p0=list(p0), pv=list(pv), t0=t0, tv=tv, gap_h=gap_h, disp=bm.km(p0, pv), levels=LEVELS, bracket=BRACKET)
    pickle.dump(P, open(pkl_path(test), "wb")); print(f"  cached -> {pkl_path(test)}", flush=True)
    make_grid(P)

if __name__ == "__main__":
    test = next((a for a in sys.argv[1:] if not a.startswith("--")), "1")
    if "--plot-only" in sys.argv:
        make_grid(pickle.load(open(pkl_path(test), "rb"))); print("re-plotted from cache")
    else:
        run(test)
