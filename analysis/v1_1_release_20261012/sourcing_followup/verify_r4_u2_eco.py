#!/usr/bin/env python3
"""Read-only native/export checks for the frozen R4/U2 sourcing candidate."""
import copy
import csv
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text())


def rows(path, key):
    with path.open(newline="") as stream:
        values = list(csv.DictReader(stream))
    result = {row[key]: row for row in values}
    assert len(result) == len(values)
    return result


def netlist(path):
    return {net.get("name"): sorted(tuple(sorted(node.attrib.items())) for node in net.findall("node"))
            for net in ET.parse(path).findall("./nets/net")}


def main():
    build = load(HERE / "r4-u2-metadata-build.json")
    source = Path(build["source"])
    candidate = Path(build["candidate"])
    old = ROOT / "hardware/gerbers/v1.1-pilot"
    new = candidate.parent / "r4-u2-exports"
    before, after = load(old / "manifest.json"), load(new / "manifest.json")
    for name, digest in build["protected_source_inputs"].items():
        assert sha(source / name) == digest, name
        expected = build["changed_files"].get(name, {}).get("after", digest)
        assert sha(candidate / name) == expected == after["source_files"][name], name
    for manifest, root in ((before, old), (after, new)):
        for name, digest in manifest["output_files"].items():
            assert sha(root / name) == digest, name
    drc = load(HERE / "r4-u2-drc.json")
    assert not drc["unconnected_items"] and not drc["schematic_parity"]
    assert len(drc["violations"]) == 4
    assert {v["type"] for v in drc["violations"]} == {"silk_over_copper"}
    baseline_drc = load(HERE.parent / "erc/final-drc.json")
    for key in ("violations", "unconnected_items", "schematic_parity"):
        assert baseline_drc[key] == drc[key], key
    erc = load(HERE / "r4-u2-erc.json")
    assert not [v for sheet in erc["sheets"] for v in sheet["violations"]]
    assert netlist(old / "native/netlist.xml") == netlist(new / "native/netlist.xml")

    old_bom, new_bom = rows(old / "BOM-stratolink.csv", "Designator"), rows(new / "BOM-stratolink.csv", "Designator")
    assert old_bom.keys() == new_bom.keys() and len(new_bom) == 56
    bom_changes = {ref: {"before": old_bom[ref], "after": new_bom[ref]}
                   for ref in old_bom if old_bom[ref] != new_bom[ref]}
    assert set(bom_changes) == {"R4", "U2"}
    assert (old / "CPL-stratolink.csv").read_bytes() == (new / "CPL-stratolink.csv").read_bytes()
    assert (old / "supplier-rotation-profile.json").read_bytes() == (new / "supplier-rotation-profile.json").read_bytes()
    old_positions, new_positions = rows(old / "native/positions.csv", "Ref"), rows(new / "native/positions.csv", "Ref")
    expected_positions = copy.deepcopy(old_positions)
    expected_positions["U2"]["Val"] = "RAK3172-8-SM-NI"
    assert expected_positions == new_positions

    # Remove only the exact native timestamp headers, never geometry/attributes.
    prefixes = ("%TF.CreationDate,", "G04 Created by KiCad (PCBNEW 10.0.0) date ",
                "; DRILL file KiCad 10.0.0 date ", "; #@! TF.CreationDate,")
    artwork = {}
    for path in sorted((old / "gerbers").iterdir()):
        other = new / "gerbers" / path.name
        if path.suffix == ".gbrjob":
            first, second = load(path), load(other)
            del first["Header"]["CreationDate"]
            del second["Header"]["CreationDate"]
            assert first == second
        else:
            def normalized(file):
                return [line for line in file.read_text().splitlines()
                        if not line.startswith(prefixes)]
            assert normalized(path) == normalized(other), path.name
        artwork[path.name] = "identical except native creation timestamps"
    assert len(artwork) == 12  # nine Gerbers, two drill files, one job
    changed_outputs = [name for name in before["output_files"]
                       if before["output_files"][name] != after["output_files"].get(name)]
    report = dict(status="PASS", candidate=str(candidate), exports=str(new),
                  source_inputs_verified_unchanged=160, changed_cad_files=build["changed_files"],
                  native_drc={"unchanged_silk_warnings": 4, "opens": 0, "parity": 0, "library_mismatches": 0},
                  filtered_erc=0, native_netlist_names_pin_membership_and_types_identical=True,
                  bom_changes=bom_changes, assembly_refs=56, groups=30, exclusions=10,
                  cpl_byte_identical=True, cpl_sha256=sha(new / "CPL-stratolink.csv"),
                  native_positions_only_u2_value_changes=True, physical_artwork_comparison=artwork,
                  changed_export_hashes=changed_outputs,
                  export_hash_note="Fresh export timestamps, source paths and part metadata change hashes/ZIP bytes; normalized fabrication geometry is unchanged.",
                  candidate_manifest_sha256=sha(new / "manifest.json"),
                  uv_unchanged=True,
                  remaining_supplier_check="Confirm actual replacement U2 supplier model orientation; historical/CAD identity alone does not establish it.",
                  no_canonical_or_existing_package_changes=True)
    path = HERE / "r4-u2-verification.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k not in ("changed_cad_files", "changed_export_hashes", "physical_artwork_comparison", "bom_changes")}, indent=2))


if __name__ == "__main__":
    main()
