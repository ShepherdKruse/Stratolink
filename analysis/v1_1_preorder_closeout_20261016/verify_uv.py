#!/usr/bin/env python3
"""Read-only AS7331 pre-order checks against the primary pin/package drawing.

Run with KiCad's bundled Python. Writes evidence and a physical orientation guide
beside this script. It does not change CAD, existing exports, or the supplier cart.
"""
from pathlib import Path
import csv
import hashlib
import json
import math
import sys
import xml.etree.ElementTree as ET

import pcbnew
import wx

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CAD = ROOT / "hardware/pcb"
FULL = ROOT / "hardware/gerbers/v1.1-final-uv-20261016"
sys.path.insert(0, str(ROOT / "analysis/v1_1_solar_attachments_20261012/review"))
import check_solar_attachments as sx


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mm(v):
    return [round(v.x / 1e6, 6), round(v.y / 1e6, 6)]


def rows(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def main():
    app = wx.App(False)
    source_names = ["stratolink.kicad_pcb", "stratolink.kicad_sch",
                    "stratolink.kicad_pro", "lib/Stratolink_UV.kicad_sym",
                    "lib/Stratolink_v1p1_U6_AS7331_OLGA16.kicad_mod",
                    "3d/AS7331_OLGA16.wrl"]
    hashes = {n: sha(CAD / n) for n in source_names}
    manifest = json.loads((FULL / "manifest.json").read_text())
    assert all(manifest["source_files"][n] == h for n, h in hashes.items())
    assert hashes["stratolink.kicad_pcb"] == "e02bf87186fc86b90569b6ea25041a34c7d2e32ef39b951847956cc2d2eb0f13"
    # DS001047 v4-00 figures 3, 4 and 59, read independently from their images.
    expected = {
        "1": ("VSSA", "power_in", "GND", -.75, -1.575),
        "2": ("VSSA", "power_in", "GND", -.25, -1.575),
        "3": ("VDDA", "power_in", "+3.3V", .25, -1.575),
        "4": ("REXT", "passive", "/UV_REXT", .75, -1.575),
        "5": ("VSSA", "power_in", "GND", 1.05, -.75),
        "6": ("VSSA", "power_in", "GND", 1.05, -.25),
        "7": ("A1", "input", "GND", 1.05, .25),
        "8": ("SYN", "input", "GND", 1.05, .75),
        "9": ("READY", "output", "unconnected-(U6-READY-Pad9)", .75, 1.575),
        "10": ("VDDD", "power_in", "+3.3V", .25, 1.575),
        "11": ("VSSD", "power_in", "GND", -.25, 1.575),
        "12": ("SDA", "bidirectional", "SDA", -.75, 1.575),
        "13": ("SCL", "input", "SCL", -1.05, .75),
        "14": ("A0", "input", "GND", -1.05, .25),
        "15": ("VSSA", "power_in", "GND", -1.05, -.25),
        "16": ("VSSA", "power_in", "GND", -1.05, -.75),
    }
    board = pcbnew.LoadBoard(str(CAD / "stratolink.kicad_pcb"))
    fps = {f.GetReference(): f for f in board.GetFootprints()}
    u6 = fps["U6"]
    assert mm(u6.GetPosition()) == [74.25, 37.49]
    assert u6.GetOrientationDegrees() == 180 and u6.GetLayer() == pcbnew.F_Cu
    lib = pcbnew.FootprintLoad(str(CAD / "lib"), "Stratolink_v1p1_U6_AS7331_OLGA16")
    pads = {p.GetNumber(): p for p in u6.Pads()}
    libpads = {p.GetNumber(): p for p in lib.Pads()}
    assert set(pads) == set(libpads) == set(expected)
    symbol = sx.nodes(sx.parse((CAD / "lib/Stratolink_UV.kicad_sym").read_text()), "symbol")[0]
    symbol_pins = {sx.field(p, "number"): (sx.field(p, "name"), p[1])
                   for unit in sx.nodes(symbol, "symbol") for p in sx.nodes(unit, "pin")}
    netlist = ET.parse(FULL / "native/netlist.xml").getroot()
    nodes = {(n.attrib["ref"], n.attrib["pin"]): net.attrib["name"]
             for net in netlist.findall("nets/net") for n in net.findall("node")}
    schematic_symbol = netlist.find("libparts/libpart[@lib='Stratolink_UV']")
    schematic_pins = {p.attrib["num"]: (p.attrib["name"], p.attrib["type"])
                      for p in schematic_symbol.findall("pins/pin")}
    pin_evidence = {}
    for num, (function, kind, net, x, y) in expected.items():
        p, lp = pads[num], libpads[num]
        assert symbol_pins[num] == schematic_pins[num] == (function, kind)
        assert nodes[("U6", num)] == p.GetNetname() == net
        assert mm(p.GetFPRelativePosition()) == mm(lp.GetFPRelativePosition()) == [x, y]
        assert mm(p.GetSize()) == mm(lp.GetSize()) == [.35, .35]
        assert p.GetLayerSet().FmtHex() == lp.GetLayerSet().FmtHex()
        assert mm(p.GetSolderPasteMargin(pcbnew.F_Paste)) == [-.025, -.025]
        placed = [round(74.25 - x, 6), round(37.49 - y, 6)]
        assert mm(p.GetPosition()) == placed
        pin_evidence[num] = dict(function=function, net=net, local_mm=[x, y],
                                 pcb_mm=placed, cpl_axes_mm=[placed[0], -placed[1]])
    assert nodes[("U6", "9")] not in [nodes[("U6", "8")], nodes[("U6", "14")]]
    support = {}
    for ref, value, mpn, lcsc in [
        ("C14", "100nF", "CL05B104KO5NNNC", "C1525"),
        ("C23", "100nF", "CL05B104KO5NNNC", "C1525"),
        ("R27", "3.3MΩ", "MCU0805MD3304BP500", "C4313228"),
    ]:
        comp = netlist.find(f"components/comp[@ref='{ref}']")
        assert comp.findtext("value") == value
        assert fps[ref].GetLayer() == pcbnew.F_Cu
        bom = next(r for r in rows(FULL / "BOM-stratolink.csv") if r["Designator"] == ref)
        assert bom["Comment"] == mpn and bom["LCSC Part #"] == lcsc
        actual_nets = {p.GetNumber(): p.GetNetname() for p in fps[ref].Pads()}
        wanted = {"1": "/UV_REXT", "2": "GND"} if ref == "R27" else {"1": "GND", "2": "+3.3V"}
        assert actual_nets == wanted
        assert all(nodes[(ref, num)] == net for num, net in wanted.items())
        support[ref] = dict(value=value, mpn=mpn, lcsc=lcsc, nets=actual_nets,
                            pcb_mm=mm(fps[ref].GetPosition()), layer="F.Cu")
    pullups = {}
    for ref, signal in [("R11", "SDA"), ("R12", "SCL")]:
        assert netlist.find(f"components/comp[@ref='{ref}']/value").text == "4.7kΩ"
        assert nodes[(ref, "1")] == "+3.3V" and nodes[(ref, "2")] == signal
        pullups[ref] = dict(ohms=4700, signal=signal, supply="+3.3V")
    cpl = next(r for r in rows(FULL / "CPL-stratolink.csv") if r["Designator"] == "U6")
    assert cpl == {"Designator": "U6", "Mid X": "74.250000", "Mid Y": "-37.490000", "Layer": "top", "Rotation": "180.000000"}
    assert len(rows(FULL / "CPL-stratolink.csv")) == 58
    full_proof = json.loads((ROOT / "analysis/v1_1_final_sweep_20261016/package-verification.json").read_text())
    delta = full_proof["UV_vs_DNP"]
    assert delta["all_retained_BOM_CPL_rows_identical"]
    assert delta["paste"]["stratolink-F_Paste.gtp"]["full_U6_apertures"] == 16
    assert delta["paste"]["stratolink-F_Paste.gtp"]["pilot_U6_apertures"] == 0
    nearest_caps = {}
    for pin in ["3", "10"]:
        a = mm(pads[pin].GetPosition())
        candidates = []
        for ref in ["C14", "C23"]:
            cap_pad = next(p for p in fps[ref].Pads() if p.GetNumber() == "2")
            b = mm(cap_pad.GetPosition())
            candidates.append((round(math.dist(a, b), 4), ref))
        d, ref = min(candidates)
        nearest_caps[pin] = {"capacitor": ref, "pad_center_distance_mm": d,
                             "scope": "straight-line geometry, not loop impedance"}
    underbody_vias = []
    for item in board.GetTracks():
        if not isinstance(item, pcbnew.PCB_VIA):
            continue
        x, y = mm(item.GetPosition())
        # Worst overall body dimensions from Figure 59: 2.70 x 3.75 mm.
        dx = max(abs(x - 74.25) - 1.35, 0)
        dy = max(abs(y - 37.49) - 1.875, 0)
        if math.hypot(dx, dy) <= item.GetWidth(pcbnew.F_Cu) / 2e6:
            underbody_vias.append(dict(uuid=item.m_Uuid.AsString(), pcb_mm=[x, y],
                net=item.GetNetname(), diameter_mm=item.GetWidth(pcbnew.F_Cu)/1e6,
                drill_mm=item.GetDrillValue()/1e6,
                front_tented=item.IsTented(pcbnew.F_Cu), back_tented=item.IsTented(pcbnew.B_Cu),
                body_overlap_mm=round(item.GetWidth(pcbnew.F_Cu)/2e6-math.hypot(dx,dy),6)))
            assert item.IsTented(pcbnew.F_Cu) and item.IsTented(pcbnew.B_Cu)
    assert all(sha(CAD / n) == h for n, h in hashes.items())
    evidence = dict(status="PASS", source_hashes=hashes,
        primary_datasheet_sha256=sha(ROOT / "analysis/v1_1_release_20261012/as7331/review/as7331-datasheet-v4-00.pdf"),
        sixteen_primary_pin_and_land_checks=pin_evidence, support=support,
        local_bypass_distance=nearest_caps, pullups=pullups, cpl=cpl,
        physical_pin1="lower-right in top view; PCB (75.000,39.065), CPL axes (75.000,-39.065) mm",
        supplier_rotation_calibration="physical orientation fully specified; supplier library convention not provided",
        full_population_references=58, full_U6_paste_apertures=16,
        vias_intersecting_maximum_U6_body=underbody_vias,
        aperture_area_to_wall_ratio_100um=.75, aperture_area_to_wall_ratio_120um=.625,
        native_files_unchanged=True)
    (HERE / "uv-checks.json").write_text(json.dumps(evidence, indent=2) + "\n")
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="800" height="820" viewBox="0 0 800 820">',
           '<rect width="800" height="820" fill="white"/>',
           '<g font-family="Arial,sans-serif" fill="#102833">',
           '<text x="40" y="42" font-size="25">U6 AS7331 physical placement target</text>',
           '<text x="40" y="73" font-size="17">Component side viewed from above. Board top is up.</text>',
           '<rect x="244" y="160" width="312" height="438" rx="5" fill="#e7ebed" stroke="#102833" stroke-width="2"/>',
           '<rect x="343" y="322" width="114" height="114" fill="#84c7d4" stroke="#102833"/>']
    # 120 px/mm; package nominal 2.60 x 3.65 mm centered at (400,379).
    for num, entry in pin_evidence.items():
        x, y = entry["pcb_mm"]
        sx_, sy_ = 400 + 120 * (x - 74.25), 379 + 120 * (y - 37.49)
        color = "#ef9b29" if num == "1" else "#a5b8bf"
        svg += [f'<rect x="{sx_-21}" y="{sy_-21}" width="42" height="42" fill="{color}" stroke="#102833"/>',
                f'<text x="{sx_}" y="{sy_+5}" text-anchor="middle" font-size="16">{num}</text>']
    svg += ['<circle cx="514" cy="553" r="9" fill="#bc5b00"/>',
            '<text x="40" y="646" font-size="19">Pin 1 / package dot: lower-right. Do not mirror.</text>',
            '<text x="40" y="679" font-size="17">Center: PCB (74.250, 37.490) mm; CPL (74.250, -37.490) mm</text>',
            '<text x="40" y="708" font-size="17">Pin 1: PCB (75.000, 39.065) mm; CPL (75.000, -39.065) mm</text>',
            '<text x="40" y="737" font-size="17">Native and exported rotation: 180 degrees, top side.</text>',
            '<text x="40" y="766" font-size="17">JLC must map its library rotation to this physical target.</text>',
            '<text x="40" y="795" font-size="14">Nominal body 2.60 x 3.65 mm; 16 lands; no center exposed pad.</text>',
            '</g></svg>']
    (HERE / "uv-placement-guide.svg").write_text("\n".join(svg) + "\n")
    print(json.dumps({"status": "PASS", "pins": 16, "source": hashes["stratolink.kicad_pcb"], "output": str(HERE / "uv-checks.json")}))


if __name__ == "__main__":
    main()
