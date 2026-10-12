#!/usr/bin/env python3
"""Demand and relative-geometry screens, not an FR4/line failure simulation.

Reads the pinned existing board and writes only this analysis directory.
No strength allowable or absolute failure load is assigned.
"""
from pathlib import Path
import csv
import hashlib
import importlib.util
import json
import math
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = 'a9d6ed5'
G = 9.80665
RHO_FR4 = .0019  # g/mm3, inherited generic mass assumption.
RHO_CU = .00896  # g/mm3.
CORE_T = .31  # mm, actual CAD nominal; not delivered-board measurement.
COPPER_T = .035
FINISHED_T = .4
BARREL_T = .018  # JLC quoted average, not a minimum guaranteed thickness.


def out_csv(name, rows):
    with (HERE/name).open('w', newline='') as f:
        w=csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def bridle(total_load, half_spacing, height, closed_triangle=True):
    """Equal-tension symmetric in-plane bridle; friction/knots omitted.

    With a continuous apex->left->right->apex string, the cross-board base
    segment supplies a second inward tension at each hole.
    """
    leg = math.hypot(half_spacing,height)
    sin_a, cos_a = half_spacing/leg,height/leg
    T=total_load/(2*cos_a)
    vertical=total_load/2
    inward=T*(sin_a+(1 if closed_triangle else 0))
    return dict(apex_height_mm=height, leg_angle_from_vertical_deg=math.degrees(math.atan2(half_spacing,height)),
                topology='continuous_triangle' if closed_triangle else 'two_separately_anchored_legs',
                segment_tension_N=T, each_hole_vertical_N=vertical,
                each_hole_inward_N=inward, each_hole_resultant_N=math.hypot(inward,vertical))


def ring_mass(hole, pad, barrel=0):
    # Full rings on both faces and two holes, before credit for existing copper.
    faces=4*math.pi/4*(pad**2-hole**2)*COPPER_T*RHO_CU
    walls=2*math.pi*hole*FINISHED_T*barrel*RHO_CU
    return faces,walls


def main():
    helper=ROOT/'analysis/v1_1_solar_attachments_20261012/layout/cad_helpers.py'
    spec=importlib.util.spec_from_file_location('cad_helpers',helper)
    cad=importlib.util.module_from_spec(spec);spec.loader.exec_module(cad)
    raw=subprocess.check_output(['git','show',f'{BASE}:hardware/pcb/stratolink.kicad_pcb'],cwd=ROOT)
    board=cad.parse(raw.decode())
    holes=[]
    for o in cad.nodes(board,'gr_circle'):
        if cad.scalar(o,'layer')!='Edge.Cuts':continue
        c=cad.floats(o,'center');e=cad.floats(o,'end')
        holes.append(dict(center_mm=c,radius_mm=math.dist(c,e)))
    holes.sort(key=lambda h:h['center_mm'][0])
    assert len(holes)==2 and abs(holes[0]['center_mm'][1]-31.745)<1e-9
    old_d=2*holes[0]['radius_mm']
    top_edge=next(cad.floats(x,'start')[1] for x in cad.nodes(board,'gr_line')
        if cad.scalar(x,'layer')=='Edge.Cuts' and cad.floats(x,'start')[1]==29.397)
    corner_r=holes[0]['center_mm'][1]-top_edge
    half_spacing=(holes[1]['center_mm'][0]-holes[0]['center_mm'][0])/2
    board_width=2*corner_r+2*half_spacing
    source=dict(commit=BASE,board_sha256=hashlib.sha256(raw).hexdigest(),holes=holes,
                corner_radius_mm=corner_r,top_edge_y_mm=top_edge,half_spacing_mm=half_spacing,
                finished_thickness_mm=FINISHED_T,FR4_core_mm=CORE_T,foil_each_face_mm=COPPER_T)
    (HERE/'geometry.json').write_text(json.dumps(source,indent=2)+'\n')

    geometry=[]
    for label,d,pad,barrel in [('existing_routed',old_d,None,0),('2mm_NPTH',2,None,0),
                              ('2mm_PTH_3p2pad',2,3.2,BARREL_T),('2p2mm_PTH_3p2pad',2.2,3.2,BARREL_T)]:
        drilled_d=d+2*barrel
        for shift in [0,.3,.5,1.0]:
            top_lig=corner_r+shift-drilled_d/2
            side_lig=corner_r+shift-drilled_d/2
            # Diagonal shift in both x inward and y down; straight edges become
            # the nearest boundary. Quarter arc alone is farther away.
            arc_lig=math.hypot(corner_r+shift,shift)-drilled_d/2
            recovered_core=2*math.pi/4*(old_d**2-drilled_d**2)*CORE_T*RHO_FR4
            ring,wall=ring_mass(d,pad,barrel) if pad else (0,0)
            geometry.append(dict(variant=label,finished_hole_diameter_mm=d,
                substrate_drill_diameter_model_mm=drilled_d,diagonal_shift_each_axis_mm=shift,
                top_FR4_ligament_mm=top_lig,side_FR4_ligament_mm=side_lig,
                rounded_arc_FR4_ligament_mm=arc_lig,
                minimum_FR4_ligament_mm=min(top_lig,side_lig,arc_lig),
                ligament_relative_to_existing=top_lig/(corner_r-old_d/2),
                full_width_two_hole_net_section_mm=board_width-2*drilled_d,
                core_mass_recovered_mg=1000*recovered_core,
                full_face_ring_Cu_mass_mg=1000*ring,average_barrel_Cu_mass_mg=1000*wall,
                explicit_core_full_rings_and_barrel_mass_subtotal_mg=1000*(recovered_core+ring+wall)))
    out_csv('geometry_comparison.csv',geometry)

    demands=[]
    for mass in [5,10,20,30]:
        for factor in [1,3,5,10]:
            W=mass/1000*G*factor
            for height in [10,20,40,80]:
                for closed in [True,False]:
                    demands.append(dict(payload_mass_g=mass,assumed_load_factor=factor,total_vertical_load_N=W,
                                        **bridle(W,half_spacing,height,closed)))
    out_csv('bridle_loads.csv',demands)

    corner_cases=[]
    for height in [10,20,40,80]:
        reference=bridle(.020*G*5,half_spacing,height)
        for share in [1,2]:
            for misalign in [0,15,30,60]:
                F=reference['each_hole_resultant_N']*share
                angle=math.radians(misalign)
                corner_cases.append(dict(apex_height_mm=height,
                    prescribed_local_load_multiplier=share,
                    case='balanced' if share==1 else 'one_corner_twice_balanced_vector_screen',
                    out_of_plane_misalignment_deg=misalign,
                    local_resultant_N=F,in_plane_force_N=F*math.cos(angle),
                    transverse_force_N=F*math.sin(angle),
                    scope='Prescribed corner fixture load; double-vector case is not an equilibrium model of a slipping asymmetric loop'))
    out_csv('one_corner_misalignment.csv',corner_cases)

    stress=[]
    # A20g,5x load example is a transparent chosen comparison, not user payload
    # mass, a measured shock or a certified requirement. Results scale linearly.
    W=.020*G*5
    for row in geometry:
        for height in [10,20,40,80]:
            b=bridle(W,half_spacing-row['diagonal_shift_each_axis_mm'],height)
            F=b['each_hole_resultant_N'];lig=row['minimum_FR4_ligament_mm']
            for line in [.1,.2,.3,.5]:
                stress.append(dict(variant=row['variant'],diagonal_shift_each_axis_mm=row['diagonal_shift_each_axis_mm'],
                    apex_height_mm=height,line_diameter_assumption_mm=line,hole_resultant_N=F,
                    FR4_core_thickness_mm=CORE_T,
                    nominal_line_bearing_demand_MPa=F/(line*CORE_T),
                    misleading_full_hole_bearing_MPa=F/(row['finished_hole_diameter_mm']*CORE_T),
                    conservative_minimum_ligament_two_plane_shear_demand_MPa=F/(2*lig*CORE_T),
                    average_full_board_net_section_vertical_stress_MPa=W/(CORE_T*row['full_width_two_hole_net_section_mm'])))
    out_csv('stress_demand.csv',stress)

    # Out-of-plane strip screen: choose explicit width and unsupported reach,
    # rather than claiming the perforated plate has a particular clamp line.
    bends=[]
    for width in [2,4,8]:
        for reach in [2,5,10]:
            for E in [15000,20000,25000]:
                for Fz in [.02,.1,.5,1]:
                    I=width*CORE_T**3/12
                    bends.append(dict(assumed_effective_strip_width_mm=width,assumed_cantilever_reach_mm=reach,
                        assumed_FR4_modulus_MPa=E,transverse_force_N=Fz,
                        nominal_bare_core_root_stress_MPa=6*Fz*reach/(width*CORE_T**2),
                        nominal_bare_core_tip_deflection_mm=Fz*reach**3/(3*E*I),
                        linear_deflection_over_span=Fz*reach**2/(3*E*I),
                        below_10pct_small_deflection_screen=Fz*reach**2/(3*E*I)<.1,
                        scope='Hypothetical local strip; actual support and anisotropy unresolved'))
    out_csv('out_of_plane_screen.csv',bends)

    stiffness=[]
    for E in [15000,20000,25000]:
        bare=E*CORE_T**3/12
        skin=2*110000*(COPPER_T**3/12+COPPER_T*(CORE_T/2+COPPER_T/2)**2)
        stiffness.append(dict(assumed_FR4_modulus_MPa=E,bare_core_EI_per_unit_width_Nmm=bare,
            bonded_full_two_face_Cu_EI_per_unit_width_Nmm=bare+skin,
            ideal_local_stiffness_ratio=(bare+skin)/bare,
            bare_core_extensional_rigidity_N_per_mm=E*CORE_T,
            bonded_full_two_face_extensional_rigidity_N_per_mm=E*CORE_T+2*110000*COPPER_T,
            ideal_local_extensional_stiffness_ratio=(E*CORE_T+2*110000*COPPER_T)/(E*CORE_T),
            scope='Upper comparison only: perfectly bonded continuous full-width skins; real ring and existing copper differ'))
    out_csv('copper_stiffness_screen.csv',stiffness)

    elastic=[]
    for k in [1,10,100]:
        for h in [.01,.05,.1]:
            weight=.020*G
            peak=weight+math.sqrt(weight**2+2*k*weight*h)
            elastic.append(dict(payload_mass_g=20,assumed_effective_spring_N_per_m=k,
                initial_slack_fall_m=h,ideal_peak_force_N=peak,peak_over_static_weight=peak/weight,
                scope='Linear undamped initially unextended equivalent spring; not a characterized user bridle'))
    out_csv('elastic_slack_screen.csv',elastic)

    # Meaningful equilibrium and relative-scaling checks only.
    b=bridle(1,half_spacing,20)
    assert abs(2*b['each_hole_vertical_N']-1)<1e-12
    assert abs(b['segment_tension_N']*(20/math.hypot(half_spacing,20))-.5)<1e-12
    b2=bridle(1,half_spacing,20,False)
    assert abs((b['each_hole_inward_N']-b2['each_hole_inward_N'])-b['segment_tension_N'])<1e-12
    assert abs((corner_r-old_d/2)-.99749305814)<1e-8
    assert abs((corner_r-1)-1.348)<1e-10
    assert abs(ring_mass(2,3.2,0)[0]-ring_mass(2,3.2,BARREL_T)[0])<1e-12
    selected=next(r for r in geometry if r['variant']=='2mm_PTH_3p2pad' and r['diagonal_shift_each_axis_mm']==0)
    summary=dict(source=source,checks_passed=6,
        recommendation='Keep centers; 2.0 mm finished PTH with 3.2 mm ground rings; compare actual-string first articles for rim abrasion',
        selected_geometry=selected,
        representative_loads=[bridle(.020*G*5,half_spacing,h) for h in [10,20,40,80]],
        material_allowables_assigned=False,actual_line_properties_known=False,
        measured_hardware_tests=False,FEM_performed=False,
        interpretation='Demand and ideal relative stiffness only; no absolute breaking load or safety factor')
    (HERE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
