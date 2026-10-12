#!/usr/bin/env python3
"""Load demands and geometric screens for the direct-solder solar mount.

No strength allowables are assigned. This model cannot qualify a PV terminal,
solder joint, PCB copper bond, or an initially bowed wire. Only this directory
is written. Run with ordinary Python 3, no third-party packages required.
"""
from pathlib import Path
import argparse
import csv
import json
import math

HERE = Path(__file__).resolve().parent
G = 9.80665
E_CU = 110000.0  # N/mm2; generic room-temperature screening value, not a lot rating.
RHO_CU = 0.00896  # g/mm3; generic copper.+

def curved_panel(length, straight, radius, insertion):
    """Uniform developed-area mass; tangent horizontal at root; y downward."""
    arc = length - straight
    angle = arc / radius
    x = straight - insertion + radius * math.sin(angle)
    y = radius * (1 - math.cos(angle))
    x_com = (straight**2 / 2 - insertion * straight
             + (straight - insertion) * arc
             + radius**2 * (1 - math.cos(angle))) / length
    y_com = radius * (arc - radius * math.sin(angle)) / length
    return dict(horizontal_tip_mm=x, downward_tip_mm=y,
                horizontal_COM_mm=x_com, downward_COM_mm=y_com,
                tip_angle_deg=math.degrees(angle))


def brace(force, x_com, x, y, lower_spacing, board_inset, diameter, eccentricity):
    """Ideal pin-jointed, straight, central brace; no other loads/preload.

    Root O=(0,0), panel P=(x,y), lower anchor B=(-inset,spacing).
    Compression at P points away from B. The required moment is opposite the
    downward panel load. Initial bow is a separate elastic imperfection screen.
    """
    length = math.hypot(x + board_inset, y - lower_spacing)
    compression = force * x_com * length / (x * lower_spacing + y * board_inset)
    area = math.pi * diameter**2 / 4
    inertia = math.pi * diameter**4 / 64
    buckling = math.pi**2 * E_CU * inertia / length**2
    ratio = compression / buckling
    # First sine-mode initial bow amplifies as e0/(1-P/Pcr). This is a
    # geometrically linear, pinned elastic screen, not nonlinear capacity.
    stress = None if ratio >= 1 else (compression / area
             + compression * eccentricity * diameter / (2 * inertia * (1-ratio)))
    return dict(wire_diameter_mm=diameter, ideal_straight_length_mm=length,
                compression_demand_N=compression, pinned_Euler_load_N=buckling,
                demand_over_ideal_buckling=ratio,
                assumed_initial_midspan_bow_mm=eccentricity,
                elastic_peak_stress_screen_MPa=stress,
                two_bare_wire_mass_g=2 * RHO_CU * area * length,
                critical_axial_shortening_um=1000 * buckling * length / (E_CU * area))


def write_csv(name, rows):
    with (HERE / name).open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--length', type=float, default=94.0,
                   help='Photo-grid-derived nominal developed span, mm; not a drawing tolerance')
    p.add_argument('--width', type=float, default=75.0,
                   help='Photo-grid-derived nominal strip length, mm; not a drawing tolerance')
    p.add_argument('--radius', type=float, default=140.0,
                   help='Assembly bend-radius assumption, mm')
    p.add_argument('--straight', type=float, default=7.0,
                   help='Straight terminal length before the bend, mm')
    p.add_argument('--insertion', type=float, default=1.5,
                   help='Insertion into notch measured from outside board edge, mm')
    p.add_argument('--terminal', type=float, default=5.0,
                   help='Nominal terminal strip width; positive brace meets strip midpoint')
    args = p.parse_args()
    mass_g = 1.76  # ZachTek SKU1044 published single-panel mass.
    radius, straight, insertion = args.radius, args.straight, args.insertion
    # Statics root at the selected bank's nominal bonded-patch center. Shape
    # coordinates remain measured from the outer PCB edge and upper bank.
    root_x = -(insertion + .20)/2
    lower_spacing, board_inset = 31.0, 1.48 + root_x
    shape = curved_panel(args.length, straight, radius, insertion)
    attachment = curved_panel(args.length-args.terminal/2, straight, radius, insertion)
    com_lever = shape['horizontal_COM_mm'] - root_x
    attach_x = attachment['horizontal_tip_mm'] - root_x
    force_1g = mass_g / 1000 * G
    demands = []
    for length in [args.length-4, args.length, args.length+4]:
        for bend_radius in [95.0, 140.0, 180.0, 100000.0]:
            s = curved_panel(length, straight, bend_radius, insertion)
            for acceleration in [1, 3, 5, 10]:
                demands.append(dict(developed_span_mm=length, bend_radius_mm=bend_radius,
                    assumed_acceleration_g=acceleration, panel_force_N=force_1g*acceleration,
                    root_moment_Nmm=force_1g*acceleration*(s['horizontal_COM_mm']-root_x), **s))
    write_csv('gravity_demand.csv', demands)

    braces = []
    for acceleration in [1, 3, 5, 10]:
        for diameter in [.4, .5, .6]:
            for initial_bow in [0, 1, 2, 5]:
                braces.append(dict(assumed_acceleration_g=acceleration,
                    **brace(force_1g*acceleration, com_lever,
                            attach_x, attachment['downward_tip_mm'],
                            lower_spacing, board_inset, diameter, initial_bow)))
    write_csv('brace_screen.csv', braces)

    hook_rows = []
    for acceleration in [1, 5, 10]:
        C = brace(force_1g*acceleration, com_lever,
                  attach_x,attachment['downward_tip_mm'],
                  lower_spacing, board_inset, .5, 0)['compression_demand_N']
        for offset in [.5, 1, 2, 3]:
            moment = C*offset
            hook_rows.append(dict(assumed_acceleration_g=acceleration,
                brace_force_N=C, force_line_offset_mm=offset,
                local_end_moment_Nmm=moment,
                half_mm_wire_nominal_bend_stress_MPa=32*moment/(math.pi*.5**3)))
    write_csv('end_hook_screen.csv', hook_rows)

    # Nominal bond-patch traction, not solder/foil strength. Treat two identical
    # fillets as sharing the load and integrate through their combined breadth.
    # The pure bending term follows q(x)=12 M x/l^3; peak q=6M/l^2 N/mm.
    # A real peel edge may have a singular traction and a flexible adherend.
    # Thus this geometric scaling is not an accurate local peel stress.
    overlaps = []
    for notch_depth in [1.5, 2.0, 2.5, 3.0]:
        for notch_width in [.8, 1.0, 1.2]:
            overlap = notch_depth - notch_width/2 - .20
            for acceleration in [1, 5, 10]:
                F = force_1g*acceleration
                M = F*com_lever
                overlaps.append(dict(notch_depth_mm=notch_depth,
                    notch_width_mm=notch_width,
                    nominal_straight_bank_copper_overlap_mm=overlap,
                    assumed_acceleration_g=acceleration, root_moment_Nmm=M,
                    ideal_bending_peak_line_traction_N_per_mm=6*M/overlap**2,
                    direct_load_mean_line_traction_N_per_mm=F/overlap,
                    minimal_couple_force_if_arm_equals_full_overlap_N=M/overlap,
                    overlap_squared_relative_to_baseline=(overlap/.8)**2))
    write_csv('notch_overlap_screen.csv', overlaps)

    handling = []
    for force in [.02, .05, .1, .25, .5]:
        for x in [com_lever, shape['horizontal_tip_mm']-root_x]:
            handling.append(dict(assumed_applied_force_N=force, lever_mm=x,
                moment_Nmm=force*x,
                equivalent_uniform_panel_acceleration_by_moment_g=force*x/(force_1g*com_lever)))
    write_csv('handling_demand.csv', handling)

    thermal = []
    length_wire = brace(force_1g, com_lever,
                      attach_x, attachment['downward_tip_mm'],
                      lower_spacing, board_inset, .5, 0)['ideal_straight_length_mm']
    for length_mismatch_um in [10, 25, 50, 100, 200, 500]:
        # Arc-length excess of a shallow half-sine, delta≈pi² e²/(4 L).
        bow = 2/math.pi*math.sqrt(length_wire*length_mismatch_um/1000)
        thermal.append(dict(imposed_excess_length_um=length_mismatch_um,
                            chord_length_mm=length_wire,
                            half_sine_bow_amplitude_mm=bow))
    write_csv('length_mismatch_screen.csv', thermal)

    # Independent checks of geometry, units, and force sign.
    n = 100000
    ds = args.length/n
    numeric_x = sum((min((i+.5)*ds,straight)-insertion
                     +radius*math.sin(max(0,(i+.5)*ds-straight)/radius))
                    for i in range(n))/n
    assert abs(numeric_x-shape['horizontal_COM_mm']) < 1e-8
    b = brace(force_1g*5,com_lever,attach_x,
              attachment['downward_tip_mm'],lower_spacing,board_inset,.5,0)
    fx=b['compression_demand_N']*(attach_x+board_inset)/b['ideal_straight_length_mm']
    fy=b['compression_demand_N']*(attachment['downward_tip_mm']-lower_spacing)/b['ideal_straight_length_mm']
    assert abs(attach_x*fy-attachment['downward_tip_mm']*fx
               +force_1g*5*com_lever) < 1e-12
    d2=brace(force_1g,com_lever,attach_x,attachment['downward_tip_mm'],lower_spacing,board_inset,.5,0)
    d1=brace(force_1g,com_lever,attach_x,attachment['downward_tip_mm'],lower_spacing,board_inset,.4,0)
    assert abs(d2['pinned_Euler_load_N']/d1['pinned_Euler_load_N']-(.5/.4)**4)<1e-12
    assert abs(d2['two_bare_wire_mass_g']/d1['two_bare_wire_mass_g']-(.5/.4)**2)<1e-12
    assert abs((2.5-.5-.2)/.8-2.25)<1e-12
    summary=dict(
        purpose='Demand/geometry screen; no predicted joint capacity or strength qualification',
        dimensions_basis='94 ±2 x 75 ±1.5 mm photo-derived estimate from ZachTek photograph metric grid; qualification/metrology contains provenance; uncertainty is not manufacturing tolerance',
        nominal_panel_mass_g=mass_g, developed_span_mm=args.length, width_mm=args.width,
        assembly_shape_assumptions=dict(radius_mm=radius,straight_terminal_mm=straight,insertion_mm=insertion,
                                        lower_anchor_from_upper_bank_mm=lower_spacing,positive_hole_inset_from_bond_center_mm=board_inset,
                                        nominal_bond_center_from_outer_edge_mm=root_x,COM_lever_from_bond_center_mm=com_lever,
                                        terminal_width_mm=args.terminal,positive_attachment_developed_s_mm=args.length-args.terminal/2),
        positive_attachment=dict(horizontal_mm=attachment['horizontal_tip_mm'],downward_mm=attachment['downward_tip_mm'],
                                 across_panel_width_mm=0),
        shape=shape, checks_passed=5,
        representative_root_moment_1g_Nmm=force_1g*com_lever,
        representative_root_moment_5g_Nmm=force_1g*5*com_lever,
        representative_5g_half_mm_wire=b,
        no_material_strength_allowables_assumed=True,
        no_physical_tests_performed=True,
        remaining_unknowns=['Terminal layer stack and peel strength','Wire temper, diameter tolerance and straightness',
                            'Actual wetting area and solder process','Thermal mismatch and joint fatigue','Real launch/handling load envelope'])
    (HERE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
