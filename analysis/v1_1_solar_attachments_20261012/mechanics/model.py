#!/usr/bin/env python3
"""Transparent load-path screens for side-slot PV mounting, not qualification.

Panel mass and approximate wire length come from archived ZachTek sources.
Panel dimensions, accelerations, effective laminate properties, imposed thermal
differences and elastic boundary conditions are sensitivity assumptions.
No manufacturing CAD is written. See README.md for validity limits.
"""
from pathlib import Path
import csv
import hashlib
import json
import math

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
G = 9.80665
M_PANEL_KG = 0.00176
RHO_CU_G_MM3 = 8.96e-3
E_CU_MPA = 110000.0
K_CU_W_M_K = 400.0
ALPHA_CU_K = 16.5e-6
RHO_CU_OHM_MM = 1.724e-5


def csv_out(name, rows):
    with (HERE / name).open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)


def wire(diameter_mm, length_mm):
    area = math.pi * diameter_mm**2 / 4
    inertia = math.pi * diameter_mm**4 / 64
    return dict(diameter_mm=diameter_mm, length_each_mm=length_mm,
                two_wire_mass_g=2*RHO_CU_G_MM3*area*length_mm,
                ideal_pinned_buckling_N=math.pi**2*E_CU_MPA*inertia/length_mm**2,
                one_wire_resistance_ohm=RHO_CU_OHM_MM*length_mm/area,
                drop_at_50mA_mV=.05*RHO_CU_OHM_MM*length_mm/area*1000,
                two_wire_conductance_mW_per_K=2*K_CU_W_M_K*area/length_mm,
                contraction_at_80K_um=ALPHA_CU_K*80*length_mm*1000)


def required_compression(panel_force_N, length_mm, anchor_spacing_mm, com_fraction=.5):
    # Exact 2D moment balance for a pinned root and straight two-force brace.
    # O=(0,0), B=(0,-s), P=(x,-h). Wire OP is not the brace: BP is.
    # A COM at x*f gives F*x*f clockwise; brace compression C gives
    # C*x*s/L counterclockwise. Thus C=F*f*L/s. Tension has the wrong sign.
    return panel_force_N * com_fraction * length_mm / anchor_spacing_mm


def main():
    wires = [wire(d, 90) for d in [.2, .3, .4, .5, .6, .8]]
    csv_out("wire_properties.csv", wires)
    braces = []
    for acceleration in [1, 3, 5, 10]:
        force = M_PANEL_KG * G * acceleration
        for spacing in [3, 5, 10, 15, 20]:
            compression = required_compression(force, 90, spacing)
            for w in wires:
                braces.append(dict(acceleration_g=acceleration,
                    anchor_spacing_mm=spacing,
                    panel_com_fraction_of_horizontal_span=.5,
                    compression_needed_N=compression,
                    ideal_buckling_load_to_required_ratio=w["ideal_pinned_buckling_N"]/compression,
                    **w))
    csv_out("lower_brace_screen.csv", braces)

    roots = []
    for span in [50, 70, 90]:
        for acceleration in [1, 3, 5, 10]:
            force = M_PANEL_KG * G * acceleration
            moment = force * span / 2
            for effective_couple in [.4, 1, 2, 5]:
                roots.append(dict(horizontal_span_mm=span, acceleration_g=acceleration,
                    panel_load_N=force, uniform_mass_root_moment_Nmm=moment,
                    assumed_joint_couple_separation_mm=effective_couple,
                    force_pair_magnitude_N=moment/effective_couple))
    csv_out("root_moment_screen.csv", roots)

    # These deliberately wide effective-polymer values are NOT panel properties.
    # Large delta/L invalidates the small-deflection model. A flexible PV film
    # can carry forces by membrane action/curvature, which is not modeled here.
    films=[]
    for effective_E_GPa in [1, 3, 5]:
        for thickness in [.1, .2, .3, .5]:
            for width in [30, 50]:
                span=70
                force=M_PANEL_KG*G
                inertia=width*thickness**3/12
                delta=force*span**3/(8*effective_E_GPa*1000*inertia)
                films.append(dict(effective_E_GPa=effective_E_GPa,
                    assumed_width_mm=width,assumed_thickness_mm=thickness,
                    assumed_span_mm=span,acceleration_g=1,
                    linear_uniform_load_tip_deflection_mm=delta,
                    deflection_to_span=delta/span,
                    small_deflection_screen_below_10pct=delta/span<.1))
    csv_out("unknown_film_sensitivity.csv", films)

    thermal=[]
    for alpha_panel_ppm in [5, 20, 50, 100]:
        for temp_delta_K in [40, 80]:
            thermal.append(dict(assumed_panel_CTE_ppm_per_K=alpha_panel_ppm,
                copper_CTE_ppm_per_K=ALPHA_CU_K*1e6,
                temperature_change_magnitude_K=temp_delta_K,
                common_span_mm=70,
                relative_free_expansion_magnitude_um=abs(alpha_panel_ppm*1e-6-ALPHA_CU_K)*70*temp_delta_K*1000))
    csv_out("thermal_mismatch_sensitivity.csv",thermal)

    fig, axes=plt.subplots(1,2,figsize=(12,4.7))
    spacing=[3,5,10,15,20]
    for acceleration in [1,5]:
        values=[required_compression(M_PANEL_KG*G*acceleration,90,s) for s in spacing]
        axes[0].plot(spacing,values,"o-",label=f"Required, {acceleration} g assumed load")
    for w in wires[1:5]:
        axes[0].axhline(w["ideal_pinned_buckling_N"],ls="--",alpha=.65,
            label=f"{w['diameter_mm']:.1f} mm Cu: ideal buckling")
    axes[0].set(xlabel="Vertical separation of upper slot and lower lead hole (mm)",
                ylabel="Compression force / ideal buckling force (N)",yscale="log",
                title="A lower straight brace needs compression")
    axes[0].grid(alpha=.2); axes[0].legend(fontsize=8)
    ds=[w["diameter_mm"] for w in wires]
    masses=[w["two_wire_mass_g"] for w in wires]
    axes[1].bar(ds,masses,width=.06,color="#3b8172")
    for d,m in zip(ds,masses):
        axes[1].text(d,m+.015,f"{m:.3f}",ha="center",fontsize=9)
    axes[1].set(xlabel="Bare copper wire diameter (mm)",ylabel="Two 90 mm wires (g)",
                title="Wire mass grows as diameter squared",ylim=(0,.9))
    fig.suptitle("Side-slot mounting screen: 1.76 g panel; half-span center of mass\n"
        "Straight, pinned 90 mm brace; real bowed film, bends, joints and fatigue unqualified",fontsize=11)
    fig.tight_layout();fig.savefig(HERE/"load_path_tradeoff.png",dpi=180);plt.close(fig)

    # Physical consistency checks, not validation against a prototype.
    assert abs(wire(.5,90)["two_wire_mass_g"]-.31667254)<1e-7
    assert abs(wire(.4,90)["ideal_pinned_buckling_N"]/wire(.2,90)["ideal_pinned_buckling_N"]-16)<1e-12
    assert abs(required_compression(1,90,5)/required_compression(1,90,10)-2)<1e-12
    # Explicit vector moment check for a feasible geometric example.
    x,h,s=70.,20.,10.
    length=math.hypot(x,h-s)
    force=M_PANEL_KG*G
    compression=required_compression(force,length,s)
    force_x,force_y=compression*x/length,compression*(s-h)/length
    assert abs(x*force_y+h*force_x-force*x*.5)<1e-12
    assert wire(.4,90)["two_wire_conductance_mW_per_K"] > 0
    sources=[HERE.parent/"sources/zachtek-panel.txt",
             HERE.parent/"sources/zachtek-assembly.txt"]
    # Historical RF studies are background evidence, not mechanics inputs.
    # This scoped study must reproduce even when those local studies are absent.
    optional_rf_sources=[ROOT/"analysis/redesign_20261010/radio_mechanics/README.md",
                         ROOT/"analysis/redesign_20261010/radio_mechanics/outputs/nec_summary.json"]
    optional_rf_provenance=[dict(path=str(p.relative_to(ROOT)),available=p.is_file(),
        sha256=hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None)
        for p in optional_rf_sources]
    summary=dict(checks_passed=5,panel_mass_g=M_PANEL_KG*1000,
        measurements_performed=False,source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        optional_prior_RF_evidence=optional_rf_provenance,
        provenance_note="Required source captures are included in this study. Prior local RF evidence is optional background, not a computational dependency.",
        representative_5g_root_moment_at_70mm_span_Nmm=M_PANEL_KG*G*5*35,
        compression_5g_5mm_spacing_90mm_brace_N=required_compression(M_PANEL_KG*G*5,90,5),
        compression_5g_15mm_spacing_90mm_brace_N=required_compression(M_PANEL_KG*G*5,90,15))
    (HERE/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print(json.dumps(summary,indent=2))


if __name__=="__main__":
    main()
