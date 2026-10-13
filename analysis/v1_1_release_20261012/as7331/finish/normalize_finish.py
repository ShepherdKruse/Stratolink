#!/usr/bin/env python3
"""Native-save a separate final copy; prove only benign property/object ordering changes."""
from pathlib import Path
import argparse,copy,hashlib,json,shutil,sys,re
from decimal import Decimal
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'manufacturing'))
from test_stencil import parse,nodes,stable_object_order
import pcbnew,wx

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
GEOMETRY_NUMBERS={'at','start','end','mid','center','xy','xyz','size','drill','width','height','thickness','clearance',
 'solder_mask_margin','solder_paste_margin','solder_paste_margin_ratio','roundrect_rratio','chamfer_ratio',
 'thermal_gap','thermal_bridge_width','thermal_bridge_angle','min_thickness','pad_to_mask_clearance','solder_mask_min_width'}
def exact_geometry_numbers(n):
    # KiCad may print .5 as 0.5. Compare those exact decimal dimensions without
    # normalizing net labels, properties, pad numbers, UUIDs, or other strings.
    if not isinstance(n,list):return n
    n=[exact_geometry_numbers(x) for x in n]
    if n and n[0] in GEOMETRY_NUMBERS:
        n=[n[0]]+[Decimal(x) if isinstance(x,str) and re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?',x) else x for x in n[1:]]
    return n

def semantic(n):
    n=stable_object_order(copy.deepcopy(n));setup=nodes(n,'setup');assert len(setup)==1
    setup=setup[0];stacks=nodes(setup,'stackup');assert len(stacks)==1
    for layer in nodes(stacks[0],'layer'):
        # Layer sequence remains exact; only property-key serialization order
        # within a layer is irrelevant. No property values are ignored.
        attrs=[x for x in layer if isinstance(x,list)];assert len({x[0] for x in attrs})==len(attrs)
        layer[:]=[x for x in layer if not isinstance(x,list)]+sorted(attrs,key=lambda x:x[0])
    attrs=[x for x in setup if isinstance(x,list)];assert len({x[0] for x in attrs})==len(attrs)
    setup[:]=[x for x in setup if not isinstance(x,list)]+sorted(attrs,key=lambda x:x[0])
    return exact_geometry_numbers(n)

def normalize(raw,output,expect):
    raw=raw.resolve();output=output.resolve();assert raw!=output and raw not in output.parents
    assert not output.exists(),'Fresh output required'
    manifest=json.loads((raw/'green-mask-patch.json').read_text());hashes=manifest['output_hashes']
    assert sha(raw/'stratolink.kicad_pcb')==expect
    assert all(sha(raw/f)==h for f,h in hashes.items()),'Raw finish evidence changed'
    output.mkdir(parents=True)
    for f in hashes:
        (output/f).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(raw/f,output/f)
    before=parse((raw/'stratolink.kicad_pcb').read_text());board=pcbnew.LoadBoard(str(raw/'stratolink.kicad_pcb'))
    pcbnew.SaveBoard(str(output/'stratolink.kicad_pcb'),board)
    after=parse((output/'stratolink.kicad_pcb').read_text())
    assert semantic(before)==semantic(after),'Native normalization changed substantive data'
    normalized={f:sha(output/f) for f in hashes}
    assert all(normalized[f]==h for f,h in hashes.items() if f!='stratolink.kicad_pcb'),'Non-PCB copy changed'
    assert all(sha(raw/f)==h for f,h in hashes.items()),'Raw finish changed during normalization'
    report={'raw_finish':str(raw),'raw_pcb_sha256':expect,'normalized_output':str(output),'normalized_pcb_sha256':sha(output/'stratolink.kicad_pcb'),
      'only_setup_property_order_UUID_object_order_and_exact_numeric_spelling_may_differ':True,'all_property_values_geometry_connectivity_and_artwork_identical':True,
      'non_PCB_hashes_identical':True,'raw_finish_preserved':True,'output_hashes':normalized,'script_sha256':sha(Path(__file__))}
    (output/'normalization-proof.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='output_hashes'},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--raw',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--expect-pcb',required=True);a=p.parse_args();app=wx.App(False);normalize(a.raw,a.output,a.expect_pcb)
