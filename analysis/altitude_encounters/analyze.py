"""Exploratory altitude and encounter sensitivity, not a flight safety assessment.

Reuses the actual website float calculator through Node. See ../README.md for
assumptions, sources, units, and what the airflow illustration does NOT predict.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle
import numpy as np
from scipy.integrate import solve_ivp

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "simulation"))
from predictor.atmosphere import isa

EARTH_RADIUS_M = 6356766


def atmosphere_geometric(z_m):
    """Existing ISA takes geopotential height, not geometric GPS altitude."""
    h = EARTH_RADIUS_M * z_m / (EARTH_RADIUS_M + z_m)
    return isa.density(h), isa.pressure(h), isa.temperature(h)


def encounter_expectation(density_per_km3, speed_m_s, area_m2, days, balloons=1):
    values = [density_per_km3, speed_m_s, area_m2, days, balloons]
    if not all(math.isfinite(v) and v >= 0 for v in values):
        raise ValueError("Encounter inputs must be finite and nonnegative")
    return density_per_km3 * (speed_m_s / 1000) * (area_m2 / 1e6) * days * 86400 * balloons


def probability_at_least_one(expected):
    return -np.expm1(-np.asarray(expected))


def sphere_flow(x, y, radius=2.0, speed=250.0):
    """Steady incompressible potential flow, meridional slice of a sphere.

    This is a velocity FIELD for air, not a force model for a finite balloon.
    """
    r2 = np.asarray(x) ** 2 + np.asarray(y) ** 2
    r = np.sqrt(np.maximum(r2, 1e-20))
    factor = radius ** 3 / (2 * r ** 3)
    return speed * (1 + factor - 3 * factor * x ** 2 / r ** 2), -3 * speed * factor * x * y / r ** 2


def run_calculator(model_path):
    # Execute the existing model unchanged, then retain the exact numerical inputs.
    javascript = """
import {pathToFileURL} from 'node:url';
const {calculateFloat, defaults} = await import(pathToFileURL(process.argv[1]));
const evaluate = changes => {
  const input = {...defaults,...changes};
  return {input, result:calculateFloat(input)};
};
const cases = [32,36].flatMap(diameter => [80,100].map(purity => evaluate({diameter,purity})));
const sweep = [];
for(let purity=50;purity<=100;purity+=0.5) {
  for(const diameter of [32,36]) sweep.push(evaluate({diameter,purity}));
  sweep.push(evaluate({diameter:36,purity,envelope:47*(36/32)**2}));
}
const liftSweep = [1,3,6,7,10].map(freeLift=>evaluate({diameter:32,purity:80,freeLift}));
console.log(JSON.stringify({defaults,cases,sweep,liftSweep}));
"""
    raw = subprocess.check_output(["node", "--input-type=module", "-e", javascript, str(model_path)], text=True)
    return json.loads(raw)


def style():
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 11,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.labelcolor": "#27313b", "text.color": "#27313b",
        "axes.edgecolor": "#adb5bd", "xtick.color": "#475569",
        "ytick.color": "#475569", "figure.facecolor": "white",
        "axes.facecolor": "white", "savefig.facecolor": "white",
    })


def altitude_figure(data):
    fig, ax = plt.subplots(figsize=(10, 6.4))
    series = [(32,47,"32-inch diameter, 47 g envelope","#2563eb","-"),
              (36,47,"36-inch diameter, same 47 g envelope","#c05b18","-"),
              (36,47*(36/32)**2,"36-inch diameter, area-scaled 59.5 g envelope","#6b7280","--")]
    for diameter, mass, label, color, ls in series:
        rows = [r for r in data["sweep"] if r["input"]["diameter"] == diameter and abs(r["input"]["envelope"]-mass)<1e-6]
        ax.plot([r["input"]["purity"] for r in rows], [r["result"]["altitude"]/1000 for r in rows], color=color, ls=ls, lw=2.4, label=label)
    for row in data["cases"]:
        x,y = row["input"]["purity"], row["result"]["altitude"]/1000
        ax.plot(x,y,"o", color="#27313b",ms=4)
        ax.annotate(f"{y:.2f} km",(x,y),xytext=(-8,9), textcoords="offset points",ha="right",fontsize=10)
    ax.axhline(10.034,color="#9ca3af",lw=1,ls=":")
    ax.text(51,10.15,"Last reported flight-3 GPS altitude: 10.034 km",fontsize=10)
    ax.set(xlabel="Helium fraction by volume (%) • remaining gas modeled as air",
           ylabel="Predicted geometric float altitude (km)", xlim=(50,103),ylim=(8,17))
    ax.set_title("Size and gas purity set float height",loc="left",weight="bold",pad=18)
    ax.grid(alpha=.15)
    ax.legend(loc="lower right",frameon=False,fontsize=10)
    fig.text(.10,.035,"10.3 g payload • 7 g launch free lift • 98% volume utilization\nCalculator scenarios, not measured envelope volume, flight gas purity, or an altitude guarantee.",fontsize=10,color="#475569")
    fig.subplots_adjust(left=.10,right=.96,top=.88,bottom=.18)
    fig.savefig(HERE / "altitude.png",dpi=170)
    plt.close(fig)


def encounter_figure():
    fig,ax = plt.subplots(figsize=(10,6.2))
    densities = np.logspace(-3,2,350)  # aircraft per million km^3
    for n,color in [(1,"#64748b"),(10,"#059669"),(100,"#c05b18"),(1000,"#2563eb")]:
        lam = densities / 1e6 * .25 * 50/1e6 * 30*86400*n
        ax.loglog(densities,probability_at_least_one(lam)*100,lw=2.3,color=color,label=f"{n:,} balloon" + ("s" if n != 1 else ""))
    sample = probability_at_least_one(encounter_expectation(1e-6,250,50,30,1000))*100
    ax.scatter([1],[sample],color="#2563eb",zorder=5)
    ax.annotate(f"Illustrative input only\n1 aircraft / million km³ → {sample:.2f}% for 1,000 balloons",(1,sample),xytext=(.007,13),arrowprops={"arrowstyle":"-","color":"#64748b"},fontsize=10)
    ax.set(xlabel="Assumed concurrent traffic density along the balloon route\n(aircraft per million km³, including vertical distribution)",ylabel="Chance of ≥1 modeled geometric encounter (%)",ylim=(1e-6,100))
    ax.set_title("Small individual probabilities accumulate across a fleet",loc="left",weight="bold",pad=18)
    ax.legend(frameon=False,loc="lower right")
    ax.grid(which="major",alpha=.16)
    fig.text(.10,.035,"30 days per balloon • 250 m/s relative speed • assumed 50 m² effective cross-section\nHYPOTHETICAL DENSITIES. No measured traffic input. Not a Stratolink risk estimate or a damage model.",fontsize=10,color="#475569")
    fig.subplots_adjust(left=.10,right=.96,top=.88,bottom=.22)
    fig.savefig(HERE / "encounters.png",dpi=170)
    plt.close(fig)


def airflow_figure():
    fig,axes = plt.subplots(1,2,figsize=(12,5.8))
    x,y = np.meshgrid(np.linspace(-7,4,300),np.linspace(-4,4,230))
    u,v = sphere_flow(x,y)
    mask = x*x+y*y<=4
    u = np.ma.masked_where(mask,u); v = np.ma.masked_where(mask,v)
    for ax in axes:
        ax.streamplot(x,y,u,v,color="#cbd5e1",density=.65,linewidth=.8,arrowsize=.8)
        ax.add_patch(Circle((0,0),2,facecolor="#e2e8f0",edgecolor="#64748b",lw=1.2))
        ax.text(.1,-.2,"Solid nose\nsurrogate",ha="center",fontsize=10)
        ax.set(xlim=(-7,4),ylim=(-3.6,3.6),aspect="equal",xlabel="Position in body-fixed frame (m)",ylabel="Lateral / vertical offset (m)")
        ax.grid(alpha=.12)
    axes[0].set_title("An air parcel can turn around the body",loc="left",fontsize=12,pad=16)
    sol = solve_ivp(lambda t,q:sphere_flow(*q),[0,.10],[-7,.6],max_step=.00005,rtol=1e-9,atol=1e-10)
    axes[0].plot(sol.y[0],sol.y[1],color="#2563eb",lw=2.4)
    axes[0].text(-6.7,2.7,"Blue: ideal point tracer\nGray: ideal air streamlines",fontsize=10)
    axes[1].set_title("That does not establish balloon clearance",loc="left",fontsize=12,pad=16)
    axes[1].plot([-7,-2.4],[0,0],color="#c05b18",lw=2.2)
    axes[1].add_patch(Circle((-2.4,0),.4,facecolor="#fed7aa",edgecolor="#c05b18",lw=2))
    axes[1].plot([-2.4],[0],"o",color="#c05b18",ms=3)
    axes[1].annotate("Finite envelope edge\nreaches the body before\nits center reaches the surface",xy=(-2.0,0),xytext=(-6.8,2.6),arrowprops={"arrowstyle":"-","color":"#c05b18"},fontsize=10)
    axes[1].text(-6.8,-2.8,"Exactly centered: no preferred up/down direction.\nEngines, tether and payload are not represented.",fontsize=9)
    fig.suptitle("Following the air is not the same as guaranteed avoidance",x=.07,ha="left",weight="bold",fontsize=16)
    fig.text(.07,.06,"GEOMETRIC ILLUSTRATION ONLY: ideal flow around a 2 m-radius sphere; 0.4 m-radius envelope.\nThe circle is a contact construction, not a simulated balloon trajectory. No compressibility, deformation, engine suction or forces.",fontsize=10,color="#475569")
    fig.subplots_adjust(left=.07,right=.98,top=.83,bottom=.22,wspace=.26)
    fig.savefig(HERE / "airflow.png",dpi=170)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--float-model",type=Path,default=ROOT/"web/src/float-model.mjs")
    args = parser.parse_args()
    data = run_calculator(args.float_model.resolve())
    model = args.float_model.resolve()
    source_path = model.relative_to(ROOT).as_posix() if model.is_relative_to(ROOT) else model.name
    data["source"] = {"path":source_path,"sha256":hashlib.sha256(model.read_bytes()).hexdigest()}
    data["required_volume"] = []
    for z in [12000,14000,16000]:
        rho,p,t = atmosphere_geometric(z)
        row = {"altitude_m":z,"air_density_kg_m3":rho,"pressure_pa":p,"temperature_k":t}
        for case in data["cases"][:2]:
            mass = case["result"]["totalMass"]/1000
            vol = mass/rho
            row[f"volume_m3_He{case['input']['purity']}"] = vol
            row[f"diameter_in_He{case['input']['purity']}"] = (6*vol/(math.pi*.98))**(1/3)/.0254
        data["required_volume"].append(row)
    data["hypothetical_encounter"] = {"density_per_km3":1e-6,"speed_m_s":250,"area_m2":50,"days":30,
        "probabilities":{str(n):float(probability_at_least_one(encounter_expectation(1e-6,250,50,30,n))) for n in [1,10,100,1000]}}
    (HERE/"results.json").write_text(json.dumps(data,indent=2)+"\n")
    style(); altitude_figure(data); encounter_figure(); airflow_figure()
    print(json.dumps({k:v for k,v in data.items() if k not in ["sweep"]},indent=2))


if __name__ == "__main__":
    main()
