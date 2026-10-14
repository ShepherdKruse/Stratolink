#!/usr/bin/env python3
"""Read saved native RF reference copper, including net-assigned graphics and artwork."""
from pathlib import Path
import argparse, hashlib, json, sys
import pcbnew, wx

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'analysis/v1_1_solar_attachments_20261012/materials'))
from extract_native import contours


def extract(path):
    raw = path.read_bytes()
    board = pcbnew.LoadBoard(str(path))
    board.GetDesignSettings().m_MaxError = 2000
    items, drills, all_copper = [], [], {}
    layers = [pcbnew.F_Cu, pcbnew.B_Cu]
    def xy(point):
        return [point.x / 1e6, point.y / 1e6]
    def add(item, kind, ref=None):
        if isinstance(item, pcbnew.PAD) and item.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
            return
        for layer in layers:
            if not item.IsOnLayer(layer):
                continue
            poly = pcbnew.SHAPE_POLY_SET()
            if isinstance(item, pcbnew.PCB_TEXT):
                item.TransformTextToPolySet(poly, 0, 2000, pcbnew.ERROR_OUTSIDE)
            else:
                item.TransformShapeToPolygon(poly, layer, 0, 2000, pcbnew.ERROR_OUTSIDE)
            record = {'kind': kind, 'uuid': item.m_Uuid.AsString(),
                      'net': item.GetNetname() if hasattr(item, 'GetNetname') else '',
                      'layer': board.GetLayerName(layer), 'polygons': contours(poly)}
            if ref is not None:
                record['ref'] = ref
            if isinstance(item, pcbnew.PAD):
                record.update(pin=item.GetNumber(), at=xy(item.GetPosition()))
            if isinstance(item, pcbnew.PCB_TRACK) and not isinstance(item, pcbnew.PCB_VIA):
                record.update(start=xy(item.GetStart()), end=xy(item.GetEnd()),
                              width_mm=item.GetWidth() / 1e6, length_mm=item.GetLength() / 1e6)
                if isinstance(item, pcbnew.PCB_ARC):
                    record['mid'] = xy(item.GetMid())
            items.append(record)
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            add(pad, 'pad', footprint.GetReference())
            size = list(pad.GetDrillSize())
            if max(size):
                drills.append({'ref': footprint.GetReference(), 'pin': pad.GetNumber(),
                               'uuid': pad.m_Uuid.AsString(), 'at': xy(pad.GetPosition()),
                               'size_mm': [v / 1e6 for v in size],
                               'angle_deg': pad.GetOrientationDegrees()})
        for graphic in footprint.GraphicalItems():
            add(graphic, 'footprint_graphic', footprint.GetReference())
        for field in footprint.GetFields():
            if field.IsVisible():
                add(field, 'footprint_field', footprint.GetReference())
    for track in board.GetTracks():
        add(track, track.GetClass())
        if isinstance(track, pcbnew.PCB_VIA):
            drills.append({'uuid': track.m_Uuid.AsString(), 'at': xy(track.GetPosition()),
                           'size_mm': [track.GetDrillValue() / 1e6] * 2, 'angle_deg': 0})
    for graphic in board.GetDrawings():
        add(graphic, 'board_graphic')
    for zone in board.Zones():
        if zone.GetIsRuleArea():
            continue
        for layer in layers:
            if zone.IsOnLayer(layer):
                items.append({'kind': 'zone', 'uuid': zone.m_Uuid.AsString(),
                              'net': zone.GetNetname(), 'layer': board.GetLayerName(layer),
                              'polygons': contours(zone.GetFilledPolysList(layer))})
    for layer in layers:
        poly = pcbnew.SHAPE_POLY_SET()
        board.ConvertBrdLayerToPolygonalContours(layer, poly)
        poly.Simplify()
        all_copper[board.GetLayerName(layer)] = contours(poly)
    assert path.read_bytes() == raw
    return {'pcb_sha256': hashlib.sha256(raw).hexdigest(), 'source': str(path),
            'kicad': pcbnew.GetBuildVersion(), 'items': items, 'drills': drills,
            'all_copper': all_copper, 'source_bytes_unchanged': True,
            'method': 'Native saved fills, no refill/save. Requested 2 um polygon approximation; in-memory whole-layer converter maximum error set to 2 um. Includes board and footprint graphics, visible copper fields, plated pads, vias and tracks; NPTH mechanical holes do not become copper. Drill geometry is reported separately.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pcb', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    app = wx.App(False)
    result = extract(args.pcb)
    args.output.write_text(json.dumps(result, separators=(',', ':')) + '\n')
    print(result['pcb_sha256'], len(result['items']))
