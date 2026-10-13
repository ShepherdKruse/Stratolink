#!/usr/bin/env python3
"""Read-only native PCB/pin audit and explicitly assumed UV energy arithmetic.

Run with KiCad's bundled Python. Writes evidence beside this script, never CAD.
"""
from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET
import pcbnew

BASE = Path(__file__).resolve().parent
REPO = BASE.parents[2]
PCB = REPO / "hardware/pcb/stratolink.kicad_pcb"
NET = REPO / "hardware/gerbers/v1.1-pilot/native/netlist.xml"
board = pcbnew.LoadBoard(str(PCB))
native = []
for footprint in board.GetFootprints():
    if footprint.GetReference() not in {"U6", "U7", "C6"}:
        continue
    native.append({
        "reference": footprint.GetReference(),
        "value": footprint.GetValue(),
        "footprint": str(footprint.GetFPID().GetLibItemName()),
        "position_mm": [pcbnew.ToMM(footprint.GetPosition().x), pcbnew.ToMM(footprint.GetPosition().y)],
        "side": footprint.GetLayerName(),
        "angle_degrees": footprint.GetOrientationDegrees(),
        "pads": [{"pin": p.GetNumber(), "net": p.GetNetname(),
                  "position_mm": [pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)],
                  "size_mm": [pcbnew.ToMM(p.GetSize().x), pcbnew.ToMM(p.GetSize().y)]}
                 for p in footprint.Pads()],
    })
u6 = next(f for f in native if f["reference"] == "U6")
expected = {"1": "+3.3V", "2": "unconnected-(U6-NC-Pad2)", "3": "GND", "4": "SCL", "5": "GND", "6": "SDA"}
assert {p["pin"]: p["net"] for p in u6["pads"]} == expected
netlist = ET.parse(NET).getroot()
sch_pins = {}
for net in netlist.findall("./nets/net"):
    for node in net.findall("node"):
        if node.get("ref") == "U6":
            sch_pins[node.get("pin")] = net.get("name")
assert sch_pins == expected
declared = netlist.findtext("./components/comp[@ref='U6']/footprint")
assert declared.split(":")[-1] == u6["footprint"]
paths = [PCB, NET, REPO / "hardware/pcb/stratolink.kicad_sch",
         REPO / "firmware/src/sensor_ltr390.cpp", REPO / "firmware/src/main.cpp",
         REPO / "firmware/src/telemetry.cpp",
         REPO / "firmware/include/telemetry.h", REPO / "firmware/include/stratolink_pins.h",
         REPO / "analysis/redesign_20261010/sensors/sources/as7331.pdf",
         REPO / "analysis/v1_1_layout_20261012/gnss_uv/sources/VEML6075.pdf",
         REPO / "analysis/v1_1_layout_20261012/gnss_uv/sources/VEML6075-EOL.pdf"]
for name in ("as7331-jlc-search.txt", "veml6075-jlc-search.txt",
             "lcsc-as7331-search.txt", "lcsc-as7331-C17474749.txt",
             "lcsc-si1133-C965911.txt", "lcsc-si1133-C3678545.txt",
             "lcsc-genicom-page1.txt", "lcsc-genicom-page2.txt",
             "lcsc-zopt2202-search.txt", "sparkfun-as7331-actual-ui.txt",
             "adafruit-as7331-actual-ui.txt"):
    paths.append(BASE.parent / "sourcing_followup" / name)
genicom_counts = [
    (BASE.parent / "sourcing_followup" / name).read_text().count('cell "0 In Stock"')
    for name in ("lcsc-genicom-page1.txt", "lcsc-genicom-page2.txt")
]
assert genicom_counts == [25, 14]
result = {
    "observed_date": "2026-10-13",
    "scope": "Read-only current native geometry and exported release schematic nets. No replacement footprint placed or routed. Power is datasheet arithmetic, not measured board power.",
    "source_hashes_sha256": {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
    "lcsc_genicom_zero_stock_cells_per_page": genicom_counts,
    "components": native,
    "u6_schematic_export_pins": sch_pins,
    "u6_schematic_footprint": declared,
    "as7331_proposed_address": "0x74 (A0=A1=GND); MS5611 occupies 0x76",
    "as7331_module_only_at3p3V": {
        "typical_active_mW": 3.3 * 1.42,
        "maximum_active_mW_at_table_conditions": 3.3 * 2,
        "one_second_maximum_measurement_mJ": 3.3 * 2,
        "one_second_per_minute_measurement_average_uW": 3.3 * 2 / 60 * 1000,
        "maximum_standby_mW_at_table_conditions": 3.3 * 0.970,
        "maximum_powerdown_uW_at_table_conditions": 3.3 * 1,
        "five_minute_typical_active_J": 3.3 * 1.42 / 1000 * 300,
    },
    "genicom_uvb_illustrative_analog_screen": {
        "source_typical_current_nA_per_sunlight_UVI": 1.4,
        "assumed_feedback_Mohm_not_a_design_selection": 10,
        "assumed_12bit_3p3V_ADC_lsb_mV": 3300 / 4096,
        "signal_mV_at_1UVI_example": 1.4 * 10,
        "ADC_counts_at_1UVI_example": 1.4 * 10 / (3300 / 4096),
        "caution": "Only illustrates small-signal analog demands. Typical source UVI correlation is not a universal solar calibration or ozone model. TIA stability, leakage, noise, offset and cold operation unqualified.",
    },
}
(BASE / "audit.json").write_text(json.dumps(result, indent=2) + "\n")
print("Verified six U6 pins and release footprint identity; saved read-only geometry, hashes and explicit energy arithmetic.")
