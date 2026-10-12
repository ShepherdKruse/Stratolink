#!/usr/bin/env python3
"""Read a frozen, Git-addressed PCB with KiCad; never modify working CAD.

Run with KiCad's bundled Python. Temporary source stays in ai-working/scratch.
The default revision is the completed microphone-removal checkpoint.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess

import pcbnew
import wx

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def parse(text):
    stack = []
    root = None
    for token in re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+', text):
        if token == '(':
            item = []
            if stack:
                stack[-1].append(item)
            else:
                root = item
            stack.append(item)
        elif token == ')':
            stack.pop()
        else:
            stack[-1].append(json.loads(token) if token.startswith('"') else token)
    return root


def nodes(item, kind):
    return [x for x in item if isinstance(x, list) and x and x[0] == kind]


def one(item, kind, default=None):
    found = nodes(item, kind)
    return found[0][1:] if found else default


def contours(poly):
    def chain(c):
        return [[c.CPoint(i).x / 1e6, c.CPoint(i).y / 1e6]
                for i in range(c.PointCount())]
    return [{'shell': chain(poly.Outline(i)),
             'holes': [chain(poly.Hole(i, j)) for j in range(poly.HoleCount(i))]}
            for i in range(poly.OutlineCount())]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', default='1aed52f')
    parser.add_argument('--board', type=Path, help='Read a candidate instead of the pinned Git baseline')
    parser.add_argument('--output', type=Path, help='Required with --board; protects baseline geometry')
    args = parser.parse_args()
    if args.board and not args.output:
        parser.error('--board requires --output so baseline geometry cannot be overwritten')
    output = args.output or HERE / 'geometry_native.json'
    if args.board and output.resolve() == (HERE / 'geometry_native.json').resolve():
        parser.error('Candidate extraction may not replace geometry_native.json')
    source = (args.board.read_bytes() if args.board else subprocess.check_output(
        ['git', 'show', args.revision + ':hardware/pcb/stratolink.kicad_pcb'], cwd=ROOT))
    scratch = Path.home() / 'Repositories/ai-working/scratch/stratolink-solar-materials'
    scratch.mkdir(parents=True, exist_ok=True)
    path = scratch / 'stratolink.kicad_pcb'
    path.write_bytes(source)
    app = wx.App(False)
    board = pcbnew.LoadBoard(str(path))
    revision = (None if args.board else subprocess.check_output(['git', 'rev-parse', args.revision], cwd=ROOT).decode().strip())
    result = {'revision': revision,
              'candidate_source_path': str(args.board.resolve()) if args.board else None,
              'source_sha256': hashlib.sha256(source).hexdigest(),
              'kicad_version': pcbnew.GetBuildVersion(), 'board_thickness_mm': pcbnew.ToMM(board.GetDesignSettings().GetBoardThickness())}
    poly = pcbnew.SHAPE_POLY_SET()
    assert board.GetBoardPolygonOutlines(poly, False, None, False, False)
    result['outline_excluding_edge_cutouts'] = contours(poly)
    result['native_outline_net_area_mm2'] = poly.Area() / 1e12
    copper = {}
    for layer, name in [(pcbnew.F_Cu, 'F.Cu'), (pcbnew.B_Cu, 'B.Cu')]:
        poly = pcbnew.SHAPE_POLY_SET()
        board.ConvertBrdLayerToPolygonalContours(layer, poly)
        poly.Simplify()  # Union track/pad/zone/text overlaps before computing area.
        copper[name] = contours(poly)
    result['copper'] = copper
    drills = []
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            size = pad.GetDrillSize()
            if size.x > 0:
                drills.append({'ref': footprint.GetReference(), 'number': pad.GetNumber(),
                               'at_mm': [pcbnew.ToMM(pad.GetPosition().x), pcbnew.ToMM(pad.GetPosition().y)],
                               'size_mm': [pcbnew.ToMM(size.x), pcbnew.ToMM(size.y)],
                               'rotation_deg': pad.GetOrientationDegrees(),
                               'plated': pad.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH})
    for track in board.GetTracks():
        if isinstance(track, pcbnew.PCB_VIA):
            diameter = pcbnew.ToMM(track.GetDrillValue())
            drills.append({'ref': 'via', 'number': '',
                           'at_mm': [pcbnew.ToMM(track.GetPosition().x), pcbnew.ToMM(track.GetPosition().y)],
                           'size_mm': [diameter, diameter], 'rotation_deg': 0, 'plated': True})
    result['drills'] = drills
    result['footprints'] = {}
    for f in board.GetFootprints():
        bb = f.GetBoundingBox(False, False)
        item = {'value': f.GetValue(), 'origin_mm': [pcbnew.ToMM(f.GetPosition().x), pcbnew.ToMM(f.GetPosition().y)],
                'bounds_excluding_text_mm': [pcbnew.ToMM(bb.GetX()), pcbnew.ToMM(bb.GetY()),
                                             pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())],
                'geometry': {}}
        for layer, name in [(pcbnew.F_Fab, 'F.Fab'), (pcbnew.B_Fab, 'B.Fab'),
                            (pcbnew.F_CrtYd, 'F.CrtYd'), (pcbnew.B_CrtYd, 'B.CrtYd')]:
            pts = []
            for shape in f.GraphicalItems():
                if shape.GetLayer() != layer or not isinstance(shape, pcbnew.PCB_SHAPE):
                    continue
                bb = shape.GetBoundingBox()
                pts.extend([(pcbnew.ToMM(bb.GetX()), pcbnew.ToMM(bb.GetY())),
                            (pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()))])
            if pts:
                item['geometry'][name] = [min(x for x, y in pts), min(y for x, y in pts),
                                          max(x for x, y in pts), max(y for x, y in pts)]
        result['footprints'][f.GetReference()] = item
    tree = parse(source.decode())
    result['stackup'] = one(one(tree, 'setup'), 'stackup')
    if args.board:
        assert hashlib.sha256(args.board.read_bytes()).hexdigest() == result['source_sha256'], 'Candidate changed during extraction'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, separators=(',', ':')) + '\n')
    print(json.dumps({k: result[k] for k in ['revision', 'source_sha256', 'board_thickness_mm', 'native_outline_net_area_mm2']}, indent=2))


if __name__ == '__main__':
    main()
