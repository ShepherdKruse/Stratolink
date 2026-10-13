#!/usr/bin/env python3
"""Project-bound CLI zone refill in a separate copy, allowing only fill-cache deltas."""
from pathlib import Path
import argparse,copy,hashlib,json,shutil,subprocess
from normalize_finish import parse,nodes,semantic,sha
from build_green_mask import spans,replace
CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'

def without_fill_cache(n):
    n=copy.deepcopy(n)
    def visit(v):
        if not isinstance(v,list):return
        if v and v[0]=='zone':v[:]=[x for x in v if not isinstance(x,list) or x[0]!='filled_polygon']
        for x in v:visit(x)
    visit(n);return semantic(n)

def refill(source,output,expect):
    source=source.resolve();output=output.resolve();assert source!=output and source not in output.parents
    assert not output.exists(),'Fresh output required'
    prior=json.loads((source/'normalization-proof.json').read_text());hashes=prior['output_hashes']
    assert sha(source/'stratolink.kicad_pcb')==expect
    assert all(sha(source/f)==h for f,h in hashes.items()),'Normalized snapshot changed'
    assert 'stratolink.kicad_pro' in hashes and 'stratolink.kicad_dru' in hashes,'Project and custom rules required'
    output.mkdir(parents=True)
    for f in hashes:(output/f).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/f,output/f)
    pcb=output/'stratolink.kicad_pcb';text=pcb.read_text();before=parse(text)
    cache=[(a,b,'') for a,b,d in spans(text) if text.startswith('(filled_polygon',a)]
    pcb.write_text(replace(text,cache))
    assert without_fill_cache(before)==without_fill_cache(parse(pcb.read_text()))
    unfilled_hash=sha(pcb);report_path=output/'saved-refill-drc.json'
    cmd=[CLI,'pcb','drc','--refill-zones','--save-board','--schematic-parity','--exit-code-violations','--format','json','--output',str(report_path),str(output/'stratolink.kicad_pcb')]
    result=subprocess.run(cmd,capture_output=True,text=True);(output/'saved-refill-drc.log').write_text(result.stdout+result.stderr)
    assert report_path.is_file(),'CLI DRC did not produce its report'
    after=parse((output/'stratolink.kicad_pcb').read_text())
    assert without_fill_cache(before)==without_fill_cache(after),'Saved refill changed data besides filled polygons'
    final={f:sha(output/f) for f in hashes}
    assert all(final[f]==h for f,h in hashes.items() if f!='stratolink.kicad_pcb'),'Project/library/source data changed'
    assert all(sha(source/f)==h for f,h in hashes.items()),'Normalized snapshot changed during refill'
    drc=json.loads(report_path.read_text());counts={k:len(drc[k]) for k in ('violations','unconnected_items','schematic_parity')}
    proof={'normalized_source':str(source),'normalized_pcb_sha256':expect,'filled_output':str(output),'filled_pcb_sha256':sha(output/'stratolink.kicad_pcb'),
      'only_zone_filled_polygons_may_differ':True,'source_zone_boundaries_settings_copper_pads_nets_markers_unchanged':True,
      'project_and_rules_loaded_via_CLI':True,'removed_stale_fill_cache_records_before_CLI':len(cache),'CLI_unfilled_input_sha256':unfilled_hash,'command':cmd,'DRC':counts,'CLI_exit_code':result.returncode,'output_hashes':final,
      'source_snapshot_preserved':True,'script_sha256':sha(Path(__file__)),'drc_sha256':sha(report_path)}
    (output/'saved-refill-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps({k:v for k,v in proof.items() if k!='output_hashes'},indent=2))
    assert result.returncode==0 and not any(counts.values()),'Final saved refill did not pass DRC/parity'

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--expect-pcb',required=True);a=p.parse_args();refill(a.source,a.output,a.expect_pcb)
