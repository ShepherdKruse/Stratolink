#!/usr/bin/env python3
"""Crossed-sheet notch geometry only; no solder or structural qualification."""
from pathlib import Path
import csv
import json
import math
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Polygon

HERE=Path(__file__).resolve().parent


def save(name, rows):
    with (HERE/name).open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)


def main():
    # Requested tolerances are a screening stack, not a fab guarantee.
    slots=[.8,1.,1.2]
    panels=[.1,.2,.3,.5]
    boards=[.3,.4,.5]
    setback=.22
    rows=[]
    for width in slots:
        for panel in panels:
            for board in boards:
                for angle in [0,15,30,45,60]:
                    rad=math.radians(angle)
                    occupied=panel/math.cos(rad)+board*abs(math.tan(rad))
                    rows.append(dict(slot_width_mm=width,
                        assumed_terminal_thickness_mm=panel,PCB_thickness_mm=board,
                        panel_tilt_from_perpendicular_deg=angle,
                        crossed_sheet_occupied_width_mm=occupied,
                        remaining_total_clearance_mm=width-occupied,
                        rigid_geometry_fits_without_clearance_allowance=occupied<=width))
    save("crossed_sheet_fit.csv",rows)
    bridges=[]
    for width in slots:
        radius=width/2
        depth=1.5
        for panel in panels:
            if panel>width:continue
            # Rectangular panel end; centered. Maximum lateral half extent tp/2.
            centered_insertion=depth-radius+math.sqrt(radius**2-(panel/2)**2)
            bridges.append(dict(slot_width_mm=width,assumed_terminal_thickness_mm=panel,
                copper_route_setback_mm=setback,
                centered_face_to_nearest_Cu_lateral_distance_mm=setback+(width-panel)/2,
                active_face_seated_against_bank_to_Cu_lateral_distance_mm=setback,
                opposite_bank_to_seated_terminal_far_face_distance_mm=setback+width-panel,
                rounded_notch_total_depth_mm=depth,
                straight_bank_length_mm=depth-radius,
                maximum_centered_rectangular_end_insertion_mm=centered_insertion,
                maximum_bank_seated_rectangular_end_insertion_mm=depth-radius))
    save("notch_solder_geometry.csv",bridges)

    # This is a sectional diagram, NOT a fabrication drawing or assembly render.
    # y runs horizontally, z vertically. Panel is normal to the PCB plane.
    fig,axes=plt.subplots(1,2,figsize=(12,6.1),sharex=True,sharey=True)
    w,t,b,s=1.,.2,.4,.22
    for ax,center,label in zip(axes,[0,-w/2+t/2],
                              ["Centered film", "Solderable face seated at one bank"]):
        for lo,hi in [(-1.35,-w/2),(w/2,1.35)]:
            ax.add_patch(Rectangle((lo,-b/2),hi-lo,b,facecolor="#ddd8bd",edgecolor="#666"))
            cu_lo=lo if hi<0 else lo+s
            cu_hi=hi-s if hi<0 else hi
            for z in [-b/2-.035,b/2]:
                ax.add_patch(Rectangle((cu_lo,z),cu_hi-cu_lo,.035,facecolor="#c78d16"))
        panel_left=center-t/2
        ax.add_patch(Rectangle((panel_left,-1),t,2,facecolor="#849d88",edgecolor="#31553c"))
        ax.plot([panel_left,panel_left],[-1,1],lw=3,color="#bcbcbc")
        # One exposed panel face supports both front/back PCB fillets.
        cu_edge=-w/2-s
        for sign in [1,-1]:
            ax.add_patch(Polygon([(cu_edge-.18,sign*(b/2+.035)),
                (panel_left,sign*(b/2+.035)),(panel_left,sign*.60)],
                facecolor="#8aa8bf",alpha=.8,edgecolor="#436b8c"))
        ax.annotate("",xy=(cu_edge,.78),xytext=(panel_left,.78),
                    arrowprops=dict(arrowstyle="|-|",color="#222"))
        ax.text((cu_edge+panel_left)/2,.85,f"{panel_left-cu_edge:.2f} mm bridge",ha="center",fontsize=10)
        ax.text(.7,.65,"Cu",color="#9a6700",fontsize=10)
        ax.text(.8,0,"FR-4",va="center",fontsize=10)
        ax.text(.45,-.73,"Open notch wall is unplated",fontsize=9,ha="center")
        ax.annotate("",xy=(-w/2,-1.10),xytext=(w/2,-1.10),
                    arrowprops=dict(arrowstyle="|-|",color="#222"))
        ax.text(0,-1.26,"Notch: 1.0 ± 0.2 mm",ha="center",fontsize=9)
        ax.annotate("",xy=(1.13,-b/2),xytext=(1.13,b/2),
                    arrowprops=dict(arrowstyle="|-|",color="#222"))
        ax.text(1.24,0,"0.4 ± 0.1 mm",rotation=90,va="center",fontsize=8)
        ax.set(title=label,xlabel="Along slot width Y (mm)",xlim=(-1.4,1.4),ylim=(-1.35,1.05),aspect="equal")
        ax.grid(alpha=.15)
    axes[0].set_ylabel("Through PCB thickness Z (mm)")
    fig.suptitle("Possible crossed-sheet solder geometry, transverse section\n"
        "Terminal + pre-tin thickness UNKNOWN (0.2 mm drawn). Idealized fillets/panel are not an assembly scale drawing.\n"
        "Yellow: GND copper; blue: possible fillets. Tolerances are screening assumptions. Dry-fit required before order.",fontsize=10)
    fig.tight_layout();fig.savefig(HERE/"notch_joint_section.png",dpi=180,bbox_inches="tight");plt.close(fig)
    assert abs(next(r for r in bridges if r['slot_width_mm']==1 and r['assumed_terminal_thickness_mm']==.2)['centered_face_to_nearest_Cu_lateral_distance_mm']-.62)<1e-12
    assert abs(next(r for r in rows if r['slot_width_mm']==1 and r['assumed_terminal_thickness_mm']==.2 and r['PCB_thickness_mm']==.4 and r['panel_tilt_from_perpendicular_deg']==0)['crossed_sheet_occupied_width_mm']-.2)<1e-12
    summary=dict(checks_passed=2,
        measured_panel_dimensions=False,
        nominal_notch_width_mm=1,assumed_width_tolerance_mm=.2,
        nominal_PCB_thickness_mm=.4,assumed_thickness_tolerance_mm=.1,
        copper_setback_mm=.22,outer_edge_copper_setback_mm=.2,notch_depth_mm=1.5,
        note="Assumed terminal thicknesses and tolerance stack; no fabrication, wetting, load or fit qualification")
    (HERE/"notch_fit_summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print(json.dumps(summary,indent=2))


if __name__=="__main__":main()
