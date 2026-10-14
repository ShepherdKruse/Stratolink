#!/usr/bin/env python3
"""Project complete saved RF copper against the actual two-layer return geometry."""
from pathlib import Path
import argparse, hashlib, json, math
from shapely import make_valid
from shapely.geometry import Polygon, Point, LineString
from shapely.ops import unary_union


def polygons(records):
    return unary_union([make_valid(Polygon(p['shell'], p['holes'])) for p in records])


def parts(g):
    if g.is_empty:
        return []
    if g.geom_type == 'Polygon':
        return [g]
    return [p for sub in g.geoms for p in parts(sub)]


def centerline(item):
    a, b = item['start'], item['end']
    if 'mid' not in item:
        return LineString([a, b])
    m = item['mid']
    ax, ay, mx, my, bx, by = *a, *m, *b
    determinant = 2 * (ax * (my - by) + mx * (by - ay) + bx * (ay - my))
    assert abs(determinant) > 1e-12
    ux = ((ax*ax+ay*ay)*(my-by)+(mx*mx+my*my)*(by-ay)+(bx*bx+by*by)*(ay-my))/determinant
    uy = ((ax*ax+ay*ay)*(bx-mx)+(mx*mx+my*my)*(ax-bx)+(bx*bx+by*by)*(mx-ax))/determinant
    start, middle, end = [math.atan2(y-uy, x-ux) for x, y in [a, m, b]]
    span = (end-start) % (2*math.pi)
    if (middle-start) % (2*math.pi) > span:
        span -= 2*math.pi
    radius = math.dist(a, (ux, uy))
    n = max(8, math.ceil(abs(span)*radius/.01))
    return LineString([(ux+radius*math.cos(start+span*i/n), uy+radius*math.sin(start+span*i/n)) for i in range(n+1)])


def lateral_samples(traces, rf_pads, ground):
    """Sample transverse rays; report the first ground interval on each side."""
    samples = []
    def lines(geometry):
        if geometry.is_empty:
            return []
        if geometry.geom_type == 'LineString':
            return [geometry]
        return [line for g in getattr(geometry, 'geoms', []) for line in lines(g)]
    for item in traces:
        if 'start' not in item:
            continue
        curve = centerline(item)
        count = max(1, math.ceil(curve.length/.025))
        for index in range(count):
            distance = curve.length*(index+.5)/count
            point = curve.interpolate(distance)
            a, b = curve.interpolate(max(0, distance-.005)), curve.interpolate(min(curve.length, distance+.005))
            dx, dy = b.x-a.x, b.y-a.y
            norm = math.hypot(dx, dy)
            transition = [i['ref']+'.'+i['pin'] for i in rf_pads if i['geometry'].buffer(.15).covers(point)]
            sides = {}
            for sign, side in [(1, 'left'), (-1, 'right')]:
                ux, uy = -dy/norm*sign, dx/norm*sign
                # Start at nominal trace edge and inspect 1.5 mm laterally.
                edge = Point(point.x+ux*item['width_mm']/2, point.y+uy*item['width_mm']/2)
                ray = LineString([edge, (edge.x+ux*1.5, edge.y+uy*1.5)])
                intervals = sorted((min(ray.project(Point(x)) for x in line.coords), max(ray.project(Point(x)) for x in line.coords))
                                   for line in lines(ray.intersection(ground)))
                sides[side] = {'first_ground_gap_mm': intervals[0][0] if intervals else None,
                               'first_ground_width_within_1_5mm_ray_mm': intervals[0][1]-intervals[0][0] if intervals else 0}
            samples.append({'track_uuid': item['uuid'], 'xy_mm': [point.x, point.y],
                            'pad_transition': transition, **sides})
    summaries = {}
    for category, subset in [('trace_outside_pad_transitions', [s for s in samples if not s['pad_transition']]),
                             ('pad_transitions', [s for s in samples if s['pad_transition']])]:
        summaries[category] = {'sample_count': len(subset)}
        for side in ['left', 'right']:
            values = [s[side] for s in subset]
            gaps = [x['first_ground_gap_mm'] for x in values if x['first_ground_gap_mm'] is not None]
            summaries[category][side] = {'no_ground_within_1_5mm_count': sum(x['first_ground_gap_mm'] is None for x in values),
                                        'maximum_first_ground_gap_mm': max(gaps) if gaps else None,
                                        'minimum_first_ground_width_mm': min((x['first_ground_width_within_1_5mm_ray_mm'] for x in values), default=None)}
    return {'maximum_sample_pitch_mm': .025, 'ray_extent_from_trace_edge_mm': 1.5,
            'pad_transition_buffer_mm': .15, 'summary': summaries, 'samples': samples}


def check(source):
    d = json.loads(source.read_text())
    items = [dict(i, geometry=polygons(i['polygons'])) for i in d['items']]
    layer_union = {layer: polygons(d['all_copper'][layer]) for layer in ['F.Cu', 'B.Cu']}
    completeness = {}
    for layer in layer_union:
        combined = unary_union([i['geometry'] for i in items if i['layer'] == layer])
        full = layer_union[layer]
        missing = full.difference(combined.buffer(.005)).area
        extra = combined.difference(full.buffer(.005)).area
        completeness[layer] = {'missing_area_beyond_5um_mm2': missing, 'extra_area_beyond_5um_mm2': extra,
                               'raw_symmetric_difference_mm2': full.symmetric_difference(combined).area}
        assert missing < 1e-8 and extra < 1e-8, ('Incomplete whole-layer extraction', layer, completeness[layer])
    gnd = {layer: unary_union([i['geometry'] for i in items if i['layer'] == layer and i['net'] == 'GND']) for layer in layer_union}
    other_back = [i for i in items if i['layer'] == 'B.Cu' and i['net'] != 'GND']
    foreign = unary_union([i['geometry'] for i in other_back])
    rf = [i for i in items if i['layer'] == 'F.Cu' and i['net'] == 'Net-(AE2-A)']
    traces = [i for i in rf if i['kind'] in ['PCB_TRACK', 'PCB_ARC', 'board_graphic']]
    trace = unary_union([i['geometry'] for i in traces])
    antenna = unary_union([i['geometry'] for i in rf if i.get('ref') == 'AE2'])
    path = unary_union([centerline(i) for i in traces if 'start' in i])
    regions = {'full_front_RF_net': unary_union([i['geometry'] for i in rf]),
               'trace_and_fillets': trace, 'trace_outside_antenna_pad': trace.difference(antenna),
               'trace_beyond_antenna_pad_and_0_15mm_transition': trace.difference(antenna.buffer(.15))}
    for i in rf:
        if i['kind'] == 'pad':
            regions['pad_'+i['ref']+'.'+i['pin']] = i['geometry']
    projection = {}
    for name, geometry in regions.items():
        intersect = geometry.intersection(foreign)
        affected = []
        for i in other_back:
            area = geometry.intersection(i['geometry']).area
            if area > 1e-8:
                affected.append({'kind': i['kind'], 'uuid': i['uuid'], 'net': i['net'],
                                 'ref': i.get('ref'), 'pin': i.get('pin'), 'overlap_mm2': area})
        projection[name] = {'area_mm2': geometry.area, 'rear_GND_fraction': geometry.intersection(gnd['B.Cu']).area / geometry.area,
                            'rear_GND_missing_mm2': geometry.difference(gnd['B.Cu']).area,
                            'rear_GND_missing_beyond_5um_mm2': geometry.difference(gnd['B.Cu'].buffer(.005)).area,
                            'opposite_non_GND_overlap_mm2': intersect.area, 'opposite_non_GND_items': affected}
    # Return-plane components and plated-ground interconnections, using the saved
    # fill plus pads/tracks/graphics. No minimum-width inference from DRC exclusions.
    components = [(layer, p) for layer in gnd for p in parts(gnd[layer])]
    parent = list(range(len(components)))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    def join(indices):
        for i in indices[1:]:
            parent[find(i)] = find(indices[0])
    paired = {}
    for i in items:
        if i['net'] == 'GND' and i['kind'] in ['pad', 'PCB_VIA']:
            paired.setdefault(i['uuid'], []).append(i)
    for entries in paired.values():
        if {i['layer'] for i in entries} != {'F.Cu', 'B.Cu'}:
            continue
        touching = [n for n, (layer, component) in enumerate(components)
                    if any(i['layer'] == layer and component.intersects(i['geometry']) for i in entries)]
        join(touching)
    receiver_pads = [i for i in items if i.get('ref') == 'U3' and i.get('pin') in ['10', '12'] and i['layer'] == 'F.Cu']
    assert len(receiver_pads) == 2 and all(i['net'] == 'GND' for i in receiver_pads)
    target = {find(n) for n, (layer, p) in enumerate(components) if any(layer == i['layer'] and p.intersects(i['geometry']) for i in receiver_pads)}
    corridor = trace.buffer(1.0)
    nearby = [{'layer': layer, 'component': n, 'area_in_1mm_corridor_mm2': p.intersection(corridor).area,
               'connected_to_receiver_ground_via_saved_copper_and_plated_ground': find(n) in target}
              for n, (layer, p) in enumerate(components) if p.intersection(corridor).area > 1e-8]
    return {'pcb_sha256': d['pcb_sha256'], 'geometry_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'whole_layer_extraction_check': completeness, 'front_rf_item_counts': {k: sum(i['kind'] == k for i in rf) for k in sorted({i['kind'] for i in rf})},
            'trace_centerline_length_mm': path.length, 'native_trace_length_sum_mm': sum(i.get('length_mm', 0) for i in traces),
            'centerline_missing_rear_GND_mm': path.difference(gnd['B.Cu']).length,
            'centerline_missing_rear_GND_outside_antenna_transition_mm': path.difference(antenna.buffer(.15)).difference(gnd['B.Cu']).length,
            'projection': projection, 'return_components_in_1mm_corridor': nearby,
            'lateral_front_ground': lateral_samples(traces, [i for i in rf if i['kind'] == 'pad'], gnd['F.Cu']),
            'receiver_ground_pads_share_return_network': len(target) == 1,
            'all_corridor_ground_connected_to_receiver': all(i['connected_to_receiver_ground_via_saved_copper_and_plated_ground'] for i in nearby),
            'limits': ['Native copper polygons include plated-pad/via drill interiors; physical drilling is separately recorded by the extractor. The antenna PTH and its clearance transition are reported independently rather than counted as a continuous reference plane.',
                       'Polygon approximation tolerance is 2 um per native item, with a 5 um reconciliation tolerance against the whole-layer converter. Tiny boundary discrepancies are not guaranteed manufacturing margins.',
                       'Transverse front-ground sampling has at most 25 um spacing along each actual trace/arc. Pad/ESD/antenna transitions are reported separately. It cannot rule out an unsampled narrower interruption or establish a continuous guard from graph connectivity alone.',
                       'A connected finite return and full projected reference do not establish 50 ohm impedance, return-current distribution, antenna matching, noise isolation or RF performance.']}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--geometry', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    result = check(a.geometry)
    a.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ['projection', 'return_components_in_1mm_corridor', 'lateral_front_ground']}, indent=2))
    print(json.dumps(result['lateral_front_ground']['summary'], indent=2))
