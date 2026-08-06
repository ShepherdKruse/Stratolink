"""Re-run ONLY ECMWF for the ABQ→Spain 300-400 sweep (it transient-failed), merge
into the cached pickle, and re-plot the full 3-source grid. No GEFS/AIGEFS re-fetch.
Generalizes to re-running any single source after a transient failure. Run from `web/`."""
import sys, pickle, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..")); sys.path.insert(0, HERE)
import backtest_levels as blv

PKL = blv.pkl_path("2")
P = pickle.load(open(PKL, "rb"))
p0 = tuple(P["p0"]); pv = tuple(P["pv"]); t0 = P["t0"]; tv = P["tv"]
print(f"merging ECMWF into {PKL} | bracket {blv.BRACKET} levels {blv.LEVELS}", flush=True)
e_as = blv.bm.as_of_cycle(t0, 9, lambda c: blv.ec.fetch_index((c, 0), [blv.BRACKET[1]])[1] is not None)
FHRS = blv.bm.fhrs_for(e_as, t0, tv, 6)
print(f"ECMWF as-of {e_as:%m-%d %HZ}, {len(FHRS)} steps", flush=True)

per, perD = blv.ecmwf_source(e_as, FHRS, p0, t0, tv)
P["R"]["ECMWF"] = {c: blv.bm.score(per[c], pv) for c in blv.COLS if len(per[c]) >= 3}
P["RD"]["ECMWF"] = {dk: blv.bm.score(perD[dk], pv) for dk in blv.DKEYS if len(perD[dk]) >= 3}
if P["R"]["ECMWF"]:
    print("  ECMWF fixed: " + " | ".join(
        f"{c}:{P['R']['ECMWF'][c]['miss']:.0f}km/{'Y' if P['R']['ECMWF'][c]['in90'] else 'N'}"
        for c in blv.COLS if c in P["R"]["ECMWF"]), flush=True)
    bf = min((P["R"]["ECMWF"][c]["miss"], c) for c in blv.COLS if c in P["R"]["ECMWF"])
    print(f"  ECMWF diurnal: best-constant {bf[1]}={bf[0]:.0f} | " + " ".join(
        f"{dk}:{P['RD']['ECMWF'][dk]['miss']:.0f}{'*' if P['RD']['ECMWF'][dk]['miss']<bf[0] else ''}"
        for dk in blv.DKEYS if dk in P["RD"]["ECMWF"]), flush=True)
else:
    print("  ECMWF still 0 members — bailing without overwriting", flush=True); sys.exit(1)

pickle.dump(P, open(PKL, "wb")); print(f"  merged + cached -> {PKL}", flush=True)
blv.make_grid(P)
