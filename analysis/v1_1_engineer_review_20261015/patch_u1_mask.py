"""U1 perimeter mask conversion; pure text patch preserves copper/paste exactly."""
from pathlib import Path
import json,hashlib,shutil,sys,math
ROOT=next(p for p in [Path.cwd(),*Path(__file__).resolve().parents] if (p/'analysis/v1_1_release_20261012/as7331/finish/build_green_mask.py').is_file())
sys.path.insert(0,str(ROOT/'analysis/v1_1_release_20261012/as7331/finish'))
from build_green_mask import parse,one,scalar,prop,change_children,set_child

def patch_footprint_text(text):
    removed=[];changed=[]
    def patch(n,b):
        if n[0]=='fp_poly' and scalar(n,'layer') in {'F.Mask','B.Mask'}:
            pts=[list(map(float,q[1:]))for q in one(n,'pts')];cx=(min(p[0]for p in pts)+max(p[0]for p in pts))/2;cy=(min(p[1]for p in pts)+max(p[1]for p in pts))/2
            if math.hypot(cx,cy)>1.2:
                removed.append(scalar(n,'uuid'));return ''
        if n[0]=='pad' and n[1]!='21':
            assert n[2]=='smd' and 1<=int(n[1])<=20
            layer=one(n,'layers');assert ('F.Cu'in layer)^('B.Cu'in layer)
            mask='B.Mask'if'B.Cu'in layer else'F.Mask';assert mask not in layer
            changed.append({'pin':n[1],'before_layers':layer,'before_clearance':scalar(n,'clearance'),'before_mask_margin':scalar(n,'solder_mask_margin')})
            b=set_child(b,'layers','(layers '+' '.join('"'+v+'"'for v in layer+[mask])+')');b=set_child(b,'solder_mask_margin','(solder_mask_margin 0.04)')
        return b
    result=change_children(text,patch);assert len(removed)==20 and len(changed)==20
    return result,{'removed_mask_polygon_uuids':removed,'perimeter_pad_before':changed,'new_mask_margin_mm':.04,'local_copper_clearance':'unchanged','preserved':'Copper shape/position/nets/clearances, paste, EP masks and pad21 thermal holes; no routing changes'}

def patch_file(path):
    original=path.read_text();records=[]
    if parse(original)[0]=='footprint':updated,ledger=patch_footprint_text(original);records.append(ledger)
    else:
        def patch(n,b):
            if n[0]=='footprint'and prop(n,'Reference')=='U1':
                v,l=patch_footprint_text(b);records.append(l);return v
            return b
        updated=change_children(original,patch)
    assert len(records)==1
    path.write_text('\n'.join(line.rstrip() for line in updated.splitlines())+'\n');return records[0]

if __name__=='__main__':
    source=Path(sys.argv[1]).resolve();output=Path(sys.argv[2]).resolve();assert not output.exists();assert source!=output
    shutil.copytree(source,output,ignore=shutil.ignore_patterns('*.png','*.log','drc*.json','*.kicad_prl','*.lck','native'))
    p=output/'stratolink.kicad_pcb';raw=p.read_bytes();ledger=patch_file(p);ledger.update(source_pcb_sha256=hashlib.sha256(raw).hexdigest(),after_pcb_sha256=hashlib.sha256(p.read_bytes()).hexdigest());files=list((output/'lib').glob('*U1*'));assert len(files)==1;ledger['library']=patch_file(files[0]);(output/'u1-mask-ledger.json').write_text(json.dumps(ledger,indent=2)+'\n');print(json.dumps({k:v for k,v in ledger.items()if k in ['source_pcb_sha256','after_pcb_sha256']},indent=2))
