#!/usr/bin/env python3
"""PCB mass / equal-mass area / idealized stiffness screen; not fabrication FEA.

Geometry is extracted by extract_native.py from a pinned Git revision.
Run with analysis/.venv/bin/python. Does not read or modify live CAD.
"""
from pathlib import Path
import csv
import json
import math

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np
from shapely import affinity
from shapely.geometry import Polygon, Point, LineString, box
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
CU_DENSITY = 8.96  # g/cm3; same engineering value used in prior mounting model.
FR4_DENSITIES = (1.8, 1.9, 2.0)  # uncertainty sweep; no delivered laminate certificate.
CU_THICKNESS = 0.035  # mm, per copper face in pinned KiCad stackup.
MASK_THICKNESS = 0.010  # mm, per face, per pinned KiCad stackup.
MASK_DENSITY = 1.4  # assumed g/cm3, inherited weight-budget engineering estimate.
MASK_COVERAGE = 0.9  # assumed; mask geometry not measured here.
BARREL_PLATING = 0.020  # assumed mm radial thickness; not ordered plating evidence.
THICKNESSES = (0.2, 0.4, 0.6, 0.8, 1.0, 1.6)


def polygon_union(contours):
    return unary_union([Polygon(c['shell'], c['holes']) for c in contours])


def write_csv(name, rows):
    with (HERE / name).open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def drill_shape(drill):
    x, y = drill['size_mm']
    if abs(x - y) < 1e-9:
        return Point(drill['at_mm']).buffer(x / 2, quad_segs=96)
    radius, length = min(x, y) / 2, abs(x - y)
    shape = LineString([(-length / 2, 0), (length / 2, 0)]).buffer(radius, quad_segs=96)
    if y > x:
        shape = affinity.rotate(shape, 90)
    shape = affinity.rotate(shape, -drill['rotation_deg'])
    return affinity.translate(shape, *drill['at_mm'])


def measure_geometry(data):
    """Common physical areas for both baseline sweep and a later candidate."""
    edge = polygon_union(data['outline_excluding_edge_cutouts'])
    outer = Polygon(edge.exterior)
    holes = unary_union([drill_shape(d) for d in data['drills']])
    laminate = edge.difference(holes)
    copper = {layer: polygon_union(cs).intersection(laminate) for layer, cs in data['copper'].items()}
    plated_hole_shapes = [drill_shape(d) for d in data['drills'] if d['plated']]
    barrel_section_area = sum(s.buffer(BARREL_PLATING).area-s.area for s in plated_hole_shapes)
    return edge, outer, laminate, copper, barrel_section_area


def mass_components(area, copper_area, barrel_section_area, thickness, density=1.9):
    """Same nominal material assumptions; returns grams by physical contribution."""
    core = thickness - 2*CU_THICKNESS - 2*MASK_THICKNESS
    assert core > 0
    return (area*core*density/1000,
            copper_area*CU_THICKNESS*CU_DENSITY/1000,
            area*2*MASK_THICKNESS*MASK_COVERAGE*MASK_DENSITY/1000,
            barrel_section_area*core*(CU_DENSITY-density)/1000)


def main():
    data = json.loads((HERE / 'geometry_native.json').read_text())
    edge, outer, laminate, copper, barrel_section_area = measure_geometry(data)
    area, copper_area = laminate.area, sum(c.area for c in copper.values())
    minx, miny, maxx, maxy = outer.bounds
    width, height = maxx-minx, maxy-miny
    # Extra drill radius was removed before plating. Replace that annulus with copper
    # rather than adding copper atop assumed FR4. Finished-hole values are CAD nominal.
    geometry = {'revision': data['revision'], 'source_sha256': data['source_sha256'],
                'width_mm': width, 'height_mm': height, 'outer_outline_area_mm2': outer.area,
                'edge_cutout_area_mm2': outer.area-edge.area,
                'edge_outline_net_area_mm2': edge.area, 'drilled_area_mm2': edge.area-area,
                'laminate_net_area_mm2': area, 'copper_area_mm2': {k: v.area for k,v in copper.items()},
                'copper_coverage_of_net_laminate': {k: v.area/area for k,v in copper.items()},
                'plated_holes': sum(d['plated'] for d in data['drills']),
                'unplated_drill_holes': sum(not d['plated'] for d in data['drills']),
                'plating_cross_section_mm2_assumed_20um': barrel_section_area,
                'measurement_method': 'KiCad 10 polygon conversion + overlap union + shape intersection + subtraction of all finished drills; arcs polygonized by KiCad.'}

    def mass(a, t, density=1.9, retain_copper=False):
        ratio = a/area
        parts = mass_components(a, copper_area*(1 if retain_copper else ratio), barrel_section_area, t, density)
        return sum(parts), parts

    shapes = [dict(name='Current outline', area_mm2=area, height_mm=height, width_mm=width,
                   fit='As modeled from current source')]
    for height_mm in (53.298,49.298,45.0,40.0,35.0):
        # Repack study only: original rounded-outline/drill loss fraction retained.
        candidate_area = area * height_mm/height
        shapes.append(dict(name=f'{height_mm:.3f} mm repack', area_mm2=candidate_area,
                           height_mm=height_mm,width_mm=width,
                           fit='Requires rerouting/relocation; not an outline edit'))
    rows=[]
    for s in shapes:
        for t in THICKNESSES:
            nominal, components = mass(s['area_mm2'],t)
            rows.append(dict(**s, nominal_thickness_mm=t, core_thickness_mm=t-.09,
                             mass_g_density_1p8=mass(s['area_mm2'],t,1.8)[0],
                             mass_g_density_1p9=nominal,
                             mass_g_density_2p0=mass(s['area_mm2'],t,2.0)[0],
                             mass_g_fixed_original_copper=mass(s['area_mm2'],t,retain_copper=True)[0],
                             fr4_mass_g=components[0], copper_mass_g=components[1],
                             mask_mass_g=components[2], barrel_density_correction_g=components[3],
                             geometric_flexural_stiffness_ratio=(t/.4)**3,
                             beam_end_load_stiffness_ratio_long_axis=(t/.4)**3*(height/s['height_mm'])**3,
                             orderable_status='0.2 mm hypothetical only; procurement not established' if t==.2 else 'Thickness screen; exact stackup/order quote unverified'))
    write_csv('mass_sweep.csv',rows)
    baseline=mass(area,.4)[0]
    equal=[]
    for t in THICKNESSES:
        # Affine mass in area; barreling held constant because the circuit/holes remain.
        m0=mass(0,t)[0]; coefficient=(mass(area,t)[0]-m0)/area
        ae=(baseline-m0)/coefficient
        m0r=mass(0,t,retain_copper=True)[0]
        cr=(mass(area,t,retain_copper=True)[0]-m0r)/area
        aer=(baseline-m0r)/cr
        equal.append(dict(thickness_mm=t,equal_mass_area_mm2_proportional_copper=ae,
                          area_fraction=ae/area,area_reduction_percent=100*(1-ae/area),
                          same_width_equivalent_length_mm=height*ae/area,
                          equal_mass_area_mm2_retained_copper=aer,
                          retained_copper_equivalent_length_mm=height*aer/area,
                          ideal_same_span_stiffness_ratio=(t/.4)**3))
    write_csv('equal_mass_thresholds.csv',equal)
    # Illustrative support span: a flat strip, same material, no slots or stress concentration.
    # Useful ratios; not a panel-solder load-capacity claim.
    stiffness=[]
    for t in THICKNESSES:
        for span in (16.0,19.802,23.36):
            stiffness.append(dict(thickness_mm=t,support_span_mm=span,
                                  normalized_same_width_beam_stiffness=(t/.4)**3*(19.802/span)**3,
                                  relative_local_bending_stress_same_moment=(.4/t)**2))
    write_csv('support_span_stiffness.csv',stiffness)
    material_sensitivity=[]
    for density_ratio in (.5,.75,1,1.25):
        for modulus_ratio in (.1,.5,1,2):
            material_sensitivity.append(dict(density_relative_to_FR4=density_ratio,
                                             modulus_relative_to_FR4=modulus_ratio,
                                             thickness_ratio_for_same_stiffness=modulus_ratio**(-1/3),
                                             substrate_mass_ratio_for_same_stiffness=density_ratio*modulus_ratio**(-1/3),
                                             scope='Generic material screen, not properties of a named delivered laminate'))
    write_csv('material_sensitivity.csv',material_sensitivity)

    # Native CAD envelope excludes outward antenna illustrations. Those illustrations
    # are not substrate and cannot set the board's lower height bound.
    relevant = {ref: data['footprints'][ref] for ref in ['C5','U2','U3','U5','U4','J20','R7','C21']}
    geometry['important_component_envelopes'] = relevant
    geometry['baseline_mass_g_nominal_density_1p9'] = baseline
    geometry['baseline_mass_parts_g'] = dict(zip(['core','planar_copper','mask','barrel_density_correction'],mass(area,.4)[1]))
    geometry['baseline_mass_range_g_density_only'] = [mass(area,.4,d)[0] for d in (1.8,2)]
    geometry['assumptions'] = {'FR4_density_range_g_cm3': list(FR4_DENSITIES), 'copper_density_g_cm3': CU_DENSITY,
                               'copper_each_face_mm':CU_THICKNESS,'mask_each_face_mm':MASK_THICKNESS,
                               'mask_coverage_assumed':MASK_COVERAGE,'mask_density_assumed_g_cm3':MASK_DENSITY,
                               'barrel_plating_assumed_mm':BARREL_PLATING,
                               'excluded_mass':'surface finish, silkscreen, solder, components, adhesives, panel mounts',
                               'shorter_outline':'same width; original fractional geometric loss; two bounds: proportional copper and original retained copper; no layout generated',
                               'stiffness':'homogeneous same-material plate/beam ratios only; copper anisotropy, slots, thermal strain and joint details excluded'}
    (HERE/'summary.json').write_text(json.dumps(geometry,indent=2)+'\n')

    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(1,3,figsize=(15,6),gridspec_kw={'width_ratios':[1,1.25,1.2]})
    ax=axes[0]
    x,y=outer.exterior.xy;ax.fill(x,y,color='#edf1f4',ec='#334155',lw=1)
    for ring in edge.interiors:
        x,y=ring.xy;ax.fill(x,y,color='white',ec='#64748b',lw=.5)
    colors={'C5':'#cc842a','U2':'#4e72b8','U3':'#48917b','J20':'#946cac'}
    for ref in colors:
        f=data['footprints'][ref]
        bb = (f['geometry'].get('B.Fab') if ref=='C5' else
              f['geometry'].get('F.CrtYd') if ref in ('U3','J20') else
              f['bounds_excluding_text_mm'])
        a,b,c,d=bb; ax.add_patch(Rectangle((a,b),c-a,d-b,fc=colors[ref],alpha=.28,ec=colors[ref]))
        ax.text((a+c)/2,(b+d)/2,ref,ha='center',va='center',color='#182435')
    for r in ['J1','J2']:
        x,y=data['footprints'][r]['origin_mm'];ax.plot(x,y,'ko',ms=3)
    ax.set_aspect('equal');ax.set_ylim(maxy+1,miny-1);ax.set_xlim(minx-3,maxx+3)
    ax.set_title(f'Existing layout\n{width:.2f} × {height:.2f} mm')
    ax.set_xlabel('Board X (mm)');ax.set_ylabel('Board Y (mm)')
    ax=axes[1]
    for t,color in [(.4,'#178076'),(.6,'#cb8425'),(.8,'#8752a0'),(1.0,'#bc5353')]:
        ls=np.linspace(30,height,100)
        ax.plot(ls,[mass(area*l/height,t)[0] for l in ls],label=f'{t:g} mm',color=color,lw=2)
    ax.axhline(baseline,color='#475569',ls='--',lw=1,label='Current 0.4 mm mass')
    ax.axvspan(30,35.5,color='#cbd5e1',alpha=.35)
    ax.set(xlabel='Same-width repacked board length (mm)',ylabel='Modeled bare-board mass (g)',title='Thicker only stays light after a large shrink')
    ax.legend(fontsize=9,loc='upper left');ax.grid(alpha=.18)
    ax=axes[2]
    subset=[e for e in equal if e['thickness_mm']>=.4]
    xs=np.arange(len(subset)); vals=[e['same_width_equivalent_length_mm'] for e in subset]
    ax.bar(xs,vals,color=['#178076','#cb8425','#8752a0','#bc5353','#64748b'])
    for i,v in enumerate(vals):ax.text(i,v+1,f'{v:.1f}',ha='center',fontsize=10)
    ax.axhline(35.5,color='#cc842a',ls=':',lw=2)
    ax.text(4.4,36.8,'Cap: 34.5 mm max + 1 mm margin',ha='right',fontsize=8,color='#9b611b')
    ax.set_xticks(xs,[f'{e["thickness_mm"]:g}' for e in subset]);ax.set_ylim(0,65)
    ax.set(xlabel='Finished thickness scenario (mm)',ylabel='Equal-mass board length (mm)',title='Length needed to match today’s mass')
    fig.suptitle(f'Board-thickness screen from actual copper and outline · nominal bare PCB {baseline:.2f} g\nDensity 1.9 g/cm³; same copper fraction after repack; all shorter layouts are hypothetical',fontsize=13)
    fig.text(.02,.03,'C5 is on the rear, overlapping front modules. Shorter outlines require component relocation and rerouting; none is a released layout.',fontsize=9)
    fig.tight_layout(rect=[0,.075,1,.89]);fig.savefig(HERE/'mass_and_fit.png',dpi=200);fig.savefig(HERE/'mass_and_fit.svg');plt.close(fig)
    checks={'outline_single_connected_polygon':edge.geom_type=='Polygon','copper_clipped_to_substrate':all(c.area<=area for c in copper.values()),
            'native_outline_area_agrees':abs(edge.area-data['native_outline_net_area_mm2'])<1e-6,
            'density_range_brackets_nominal':mass(area,.4,1.8)[0]<baseline<mass(area,.4,2)[0],
            'thickness_monotonic_at_fixed_area':all(mass(area,a)[0]<mass(area,b)[0] for a,b in zip(THICKNESSES,THICKNESSES[1:])),
            'baseline_equal_mass_recovers_area':abs(equal[1]['area_fraction']-1)<1e-10,
            'stiffness_doubles_thickness_eightfold':abs((.8/.4)**3-8)<1e-12}
    assert all(checks.values()),checks
    (HERE/'checks.json').write_text(json.dumps(checks,indent=2)+'\n')
    print(json.dumps({'geometry':{k:geometry[k] for k in ['laminate_net_area_mm2','copper_area_mm2','baseline_mass_g_nominal_density_1p9','baseline_mass_range_g_density_only']},'equal_mass':equal,'checks':checks},indent=2))


if __name__=='__main__':
    main()
