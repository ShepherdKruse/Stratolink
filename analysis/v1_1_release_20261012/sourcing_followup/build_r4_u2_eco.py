#!/usr/bin/env python3
"""Build a scratch-only R4/U2 sourcing ECO; preserve every non-property CAD node."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
spec = importlib.util.spec_from_file_location(
    "metadata_helpers", HERE.parent / "identities/build_metadata.py")
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)
cad, spans, replace = helpers.a, helpers.m.spans, helpers.m.replace
BASE = "1cac1bb"
LIBRARY = "Stratolink_v1p1_Symbols"
RADIO_SYMBOL = "RAK3172_RAK3172"
DESCRIPTION = "RAK3172 STM32WLE5CC, 32-pad, high-band regional-label variant, no TCXO, no IPEX; antenna on RF pad 12"
FIELDS = {
    "R4": {
        "Manufacturer": "YAGEO",
        "Manufacturer_Part_Number": "RC0402FR-073M65L",
        "LCSC": "C477700", "Supplier Part": "C477700",
        "Datasheet": "https://yageogroup.com/content/datasheet/asset/file/PYU-RC_GROUP_51_ROHS_L",
        "Description": "3.65 MΩ, ±1%, ±100 ppm/°C, 0402, 62.5 mW, 50 V thick-film resistor",
    },
    "U2": {
        "Value": "RAK3172-8-SM-NI", "MP": "RAK3172-8-SM-NI",
        "Manufacturer": "RAKwireless",
        "Manufacturer_Part_Number": "RAK3172-8-SM-NI",
        "LCSC": "C5452091", "Supplier Part": "C5452091",
        "Datasheet": "https://docs.rakwireless.com/product-categories/wisduo/rak3172-module/datasheet/",
        "Description": DESCRIPTION, "DESCRIPTION": DESCRIPTION,
        "Description_1": DESCRIPTION,
        # Imported SnapEDA availability is stale; do not freeze changing stock in CAD.
        "Availability": "", "AVAILABILITY": "",
    },
}
SYMBOL_FIELDS = {key: FIELDS["U2"][key] for key in
                 ("Description", "Description_1", "Datasheet", "Availability", "AVAILABILITY")}
LIBS = {
    "R4": "lib/Stratolink_v1p1_R4_R_0402_1005Metric.kicad_mod",
    "U2": "lib/Stratolink_v1p1_U2_RAK3172.kicad_mod",
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def direct(text, kind):
    return [(start, end, text[start:end], cad.parse(text[start:end]))
            for start, end, depth in spans(text)
            if depth == 1 and text[start:end].split(None, 1)[0] == "(" + kind]


def update_expected(node, values, changes, filename, label):
    for name, value in values.items():
        matches = [p for p in cad.nodes(node, "property") if p[1] == name]
        assert len(matches) == 1, (filename, label, name)
        if matches[0][2] != value:
            changes.append(dict(file=filename, component=label, property=name,
                                before=matches[0][2], after=value))
        matches[0][2] = value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "output", "report"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    assert source != output and source not in output.parents and not output.exists()
    scratch = Path.home() / "Repositories/ai-working/scratch"
    assert scratch in output.parents, "Candidate must remain in external scratch"
    manifest = json.loads((ROOT / "hardware/gerbers/v1.1-pilot/manifest.json").read_text())
    protected = manifest["source_files"]
    assert len(protected) == 160
    assert all(sha(source / name) == digest for name, digest in protected.items())
    baseline = subprocess.check_output(["git", "rev-parse", BASE], cwd=ROOT, text=True).strip()
    # Freeze the declared canonical checkpoint, not an unreviewed newer checkout.
    for name in protected:
        committed = subprocess.check_output(["git", "show", baseline + ":hardware/pcb/" + name], cwd=ROOT)
        assert hashlib.sha256(committed).hexdigest() == protected[name], name
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)

    changes = []
    filenames = ["stratolink.kicad_pcb", "stratolink.kicad_sch", *LIBS.values(),
                 "lib/" + LIBRARY + ".kicad_sym"]
    for filename in filenames:
        path = output / filename
        text = path.read_text()
        expected = copy.deepcopy(cad.parse(text))
        edits = []
        if filename in ("stratolink.kicad_pcb", "stratolink.kicad_sch"):
            pcb = filename.endswith(".kicad_pcb")
            kind = "footprint" if pcb else "symbol"
            nodes = {cad.prop(n, "Reference"): n for n in cad.nodes(expected, kind)}
            for ref, values in FIELDS.items():
                assert cad.prop(nodes[ref], "Manufacturer_Part_Number") == {
                    "R4": "0402WGF3654TCE", "U2": "RAK3172-9-SM-NI"}[ref]
                update_expected(nodes[ref], values, changes, filename, ref)
            for start, end, block, node in direct(text, kind):
                ref = cad.prop(node, "Reference")
                if ref in FIELDS:
                    edits.append((start, end, helpers.props(block, FIELDS[ref], pcb)))
            if not pcb:
                start, end, block, _ = direct(text, "lib_symbols")[0]
                library_tree = next(n for n in expected if isinstance(n, list) and n and n[0] == "lib_symbols")
                embedded = next(n for n in cad.nodes(library_tree, "symbol")
                                if n[1] == LIBRARY + ":" + RADIO_SYMBOL)
                update_expected(embedded, SYMBOL_FIELDS, changes, filename, "embedded-U2")
                inside = []
                for ls, le, lb, ln in direct(block, "symbol"):
                    if ln[1] == LIBRARY + ":" + RADIO_SYMBOL:
                        inside.append((ls, le, helpers.props(lb, SYMBOL_FIELDS, False)))
                assert len(inside) == 1
                edits.append((start, end, replace(block, inside)))
            text = replace(text, edits)
        elif filename in LIBS.values():
            ref = next(ref for ref, name in LIBS.items() if name == filename)
            assert cad.prop(expected, "Reference") == ref
            update_expected(expected, FIELDS[ref], changes, filename, ref)
            text = helpers.props(text.rstrip(), FIELDS[ref], True) + "\n"
        else:
            symbol = next(n for n in cad.nodes(expected, "symbol") if n[1] == RADIO_SYMBOL)
            update_expected(symbol, SYMBOL_FIELDS, changes, filename, "library-U2")
            for start, end, block, node in direct(text, "symbol"):
                if node[1] == RADIO_SYMBOL:
                    edits.append((start, end, helpers.props(block, SYMBOL_FIELDS, False)))
            assert len(edits) == 1
            text = replace(text, edits)
        path.write_text(text)
        assert cad.parse(path.read_text()) == expected, "Unexpected non-property change: " + filename

    changed_files = {name: {"before": digest, "after": sha(output / name)}
                     for name, digest in protected.items() if sha(output / name) != digest}
    assert set(changed_files) == set(filenames)
    assert all(sha(source / name) == digest for name, digest in protected.items())
    report = dict(status="PASS: property-only candidate; native checks follow separately",
                  baseline_commit=baseline, source=str(source), candidate=str(output),
                  script_sha256=sha(Path(__file__)), protected_source_inputs=protected,
                  source_unchanged=True, changed_files=changed_files, property_changes=changes,
                  parsed_trees_differ_only_in_declared_property_values=True,
                  geometry_nets_pin_types_fills_paste_mask_drills_unchanged=True,
                  uv_unchanged=True, r4_value_unchanged="3.65MΩ",
                  scope_notes=["U2 exact regional-label orderable changes from 9 to 8; no hardware geometry change.",
                               "Imported stale U2 stock strings cleared; live inventory is not encoded in CAD.",
                               "Generic R4 resistor symbol is shared and remains untouched.",
                               "No canonical changes, fabrication release, upload, or order."])
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k not in ("protected_source_inputs", "property_changes")}, indent=2))


if __name__ == "__main__":
    main()
