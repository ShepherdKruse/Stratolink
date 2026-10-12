#!/usr/bin/env python3
"""Read-only check of the illustrative model; writes only review evidence here."""
from pathlib import Path
import hashlib
import importlib.util
import json
import math
import numpy as np
from shapely.geometry import LineString, Polygon

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = ROOT / 'hardware/pcb/3d/solar/generate.py'
spec = importlib.util.spec_from_file_location('solar_model', SOURCE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)  # Does not invoke main or change canonical assets.

def hash_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

report = {'purpose': 'Illustrative model geometric review, not physical qualification',
          'source_sha256': hash_file(SOURCE),
          'geometry_json_sha256': hash_file(SOURCE.with_name('geometry.json')),
          'board_sha256': hash_file(ROOT / 'hardware/pcb/stratolink.kicad_pcb'),
          'sides': {}}
metadata = json.loads(SOURCE.with_name('geometry.json').read_text())
for side, sign, x in [('left', -1, 54.8-53.3165), ('right', 1, 75.2-76.6755)]:
    model, details = m.build(sign, x)
    stations = np.linspace(0, m.LENGTH, 9401)
    # Polygon occupies polymer plus the metal/cell surface offset, conservatively
    # extending full terminal metal thickness over the active region as well.
    polymer = Polygon([m.panel_point(sign, float(s), 0, 0)[:2] for s in stations]
                      + [m.panel_point(sign, float(s), 0, m.THICKNESS)[:2] for s in stations[::-1]])
    envelope = Polygon([m.panel_point(sign, float(s), 0, -m.METAL_OFFSET)[:2] for s in stations]
                       + [m.panel_point(sign, float(s), 0, m.THICKNESS)[:2] for s in stations[::-1]])
    rows = {}
    for name, vertices, faces, material in model.parts:
        if name not in ['positive copper lead', 'positive red insulation']:
            continue
        radius = m.WIRE_DIAMETER/2 if material == 'wire' else m.INSULATION_DIAMETER/2
        centres = np.array(vertices).reshape(-1, 12, 3).mean(axis=1)
        line = LineString(centres[:, :2])
        rows[name] = {'polymer_clearance_mm': line.distance(polymer)-radius,
                      'full_metal_envelope_clearance_mm': line.distance(envelope)-radius,
                      'centreline_length_mm': sum(math.dist(a,b) for a,b in zip(centres, centres[1:])),
                      'method': '2D centreline distance minus full circular radius; conservative for these panel-width-contained paths'}
        if name == 'positive copper lead':
            rows[name]['outer_hook_metal_envelope_clearance_mm'] = LineString(centres[1:18, :2]).distance(envelope)-radius
    report['sides'][side] = {'metadata_reproduced_exactly': details == metadata['sides'][side],
                              'wire_to_panel': rows}

fillet_vertices = next(vertices for name, vertices, faces, material in model.parts
                       if name == 'ground solder fillet front')
fillet_width = max(v[0] for v in fillet_vertices)-min(v[0] for v in fillet_vertices)
fillet_land_overlap = max(0, -.72-min(v[1] for v in fillet_vertices))
report['root'] = {
    'notch_width_mm': 1.0, 'notch_depth_mm': 2.0, 'tip_radius_mm': .5,
    'straight_bank_mm': 1.5, 'model_insertion_mm': m.INSERTION,
    'exposed_metal_y_mm': -.5,
    'polymer_y_span_mm': [-.5+m.METAL_OFFSET, -.5+m.METAL_OFFSET+m.THICKNESS],
    'nominal_free_gap_to_opposite_bank_mm': .5-(-.5+m.METAL_OFFSET+m.THICKNESS),
    'negative_strip_within_straight_section_mm': m.STRAIGHT-m.TERMINAL,
    'straight_margin_with_photo_high_strip_mm': m.STRAIGHT-6.5,
    'fillet_x_length_mm': fillet_width,
    'fillet_base_land_overlap_y_mm': fillet_land_overlap,
    'fillet_nominal_land_contact_area_per_face_mm2': fillet_width*fillet_land_overlap,
    'warning': 'Meniscus is illustrative. Area is from display triangles, not a qualified joint area or strength.'}
report['positive'] = {'nominal_radial_wire_to_hole_clearance_mm': (.7-.5)/2,
                      'radial_clearance_at_recorded_minimum_hole_mm': (.7-.08-.5)/2,
                      'outer_terminal_curvature_angle_degrees': math.degrees(m.TERMINAL/m.RADIUS),
                      'warning': 'Outer positive strip follows the panel curve; only root negative strip is straight.'}
(HERE / 'model-review.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report, indent=2))
