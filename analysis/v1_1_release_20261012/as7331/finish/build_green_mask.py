#!/usr/bin/env python3
"""Hash-checked green-mask/no-silkscreen finish in a fresh scratch copy only."""
from pathlib import Path
import argparse,hashlib,json,re,shutil,sys,uuid
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path.insert(0,str(HERE.parent/'manufacturing'));from test_stencil import parse,nodes,prop

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def one(n,key):return next((x[1:] for x in n if isinstance(x,list) and x and x[0]==key),[])
def scalar(n,key):v=one(n,key);return v[0] if v else None
def spans(text):
    stack=[];quoted=False;escaped=False
    for i,c in enumerate(text):
        if quoted:
            if escaped:escaped=False
            elif c=='\\':escaped=True
            elif c=='"':quoted=False
        elif c=='"':quoted=True
        elif c=='(':stack.append(i)
        elif c==')':yield stack.pop(),i+1,len(stack)
    assert not stack and not quoted

def replace(text,edits):
    for s,e,value in sorted(edits,reverse=True):text=text[:s]+value+text[e:]
    return text

def change_children(text,fn):
    edits=[]
    for s,e,d in spans(text):
        if d==1:
            block=text[s:e];value=fn(parse(block),block)
            if value!=block:edits.append((s,e,value))
    return replace(text,edits)

def set_child(text,key,value):
    found=False
    def fn(n,b):
        nonlocal found
        if n[0]!=key:return b
        assert not found;found=True;return value
    text=change_children(text,fn)
    return text if found else text[:-1]+'\n'+value+'\n)'

MASK_RECT_IDS={'19552f78-8bc8-5d58-a252-cce4c7aa3763','65f5aa32-1dfc-539e-ac84-add1df7c2354'}
SILK={'F.SilkS':'F.Fab','B.SilkS':'B.Fab'}
NS=uuid.UUID('67c2cf61-e9b5-4f21-ac48-1012b7d5c6b0')

def finish_footprint(text,ref,records):
    fp=parse(text);name=fp[1]
    # Use exact local library identity from the reference-specific frozen names.
    unit_margin=bool(re.search(r'Stratolink_v1p1_U[23]_',name))
    l1=bool(re.search(r'Stratolink_v1p1_L1_',name))
    paste_polys=[n for n in nodes(fp,'fp_poly') if scalar(n,'layer') in {'F.Paste','B.Paste'}]
    def fn(n,b):
        if unit_margin and n[0]=='pad' and scalar(n,'solder_mask_margin') is not None:
            old=scalar(n,'solder_mask_margin');assert old in {'0.102','0'},('Unexpected U2/U3 mask margin',name,old)
            if old!='0':records.append({'ref':ref,'action':'pad_mask_1to1','pad':n[1],'old_margin':old})
            return set_child(b,'solder_mask_margin','(solder_mask_margin 0)')
        if l1 and n[0]=='fp_poly' and scalar(n,'layer') in {'F.Mask','B.Mask'}:
            # L1 native copper and paste polygons are congruent; the old mask
            # grows them by 0.1 mm and crosses VBAT. Keep copper/paste intact,
            # replace only mask outline by the matching 1:1 polygon.
            pts=one(n,'pts');sign=float(pts[0][1])>0
            matches=[p for p in paste_polys if (float(one(p,'pts')[0][1])>0)==sign]
            assert len(matches)==1,('L1 paste identity',name)
            target=one(matches[0],'pts')
            if pts!=target:records.append({'ref':ref,'action':'L1_mask_1to1','uuid':scalar(n,'uuid'),'old_pts':pts,'new_pts':target})
            val='(pts '+' '.join('(xy '+' '.join(x[1:])+')' for x in target)+')'
            return set_child(b,'pts',val)

        layer=scalar(n,'layer')
        if layer in SILK:
            if n[0] in {'property'}:
                records.append({'ref':ref,'action':'property_to_fab','name':n[1]})
                return set_child(b,'layer','(layer "'+SILK[layer]+'")')
            records.append({'ref':ref,'action':'remove_silk','type':n[0]});return ''
        return b
    return change_children(text,fn)

def patch(source,output,expect):
    source=source.resolve();output=output.resolve()
    assert sha(source/'stratolink.kicad_pcb')==expect,'Unexpected input PCB hash'
    assert output!=source and source not in output.parents,'Output must be outside source'
    assert output!=ROOT/'hardware/pcb' and not (ROOT/'hardware/pcb') in output.parents,'Never write canonical CAD'
    if output.exists():
        report=json.loads((output/'green-mask-patch.json').read_text())
        assert report['source_pcb_sha256']==expect
        assert all(sha(source/f)==h for f,h in report['source_hashes'].items()),'Source bundle differs from completed patch'
        assert report['script_sha256']==sha(Path(__file__)),'Patch script changed; use fresh output'
        assert all(sha(output/f)==h for f,h in report['output_hashes'].items()),'Existing output differs'
        print(json.dumps({'idempotent_noop':True,'output':str(output)}));return
    names=[p.relative_to(source) for p in source.iterdir() if p.is_file() and p.suffix in {'.kicad_pcb','.kicad_sch','.kicad_pro','.kicad_dru'} or p.is_file() and p.name in {'fp-lib-table','sym-lib-table'}]
    names += [p.relative_to(source) for folder in ['lib','3d'] for p in (source/folder).rglob('*') if p.is_file() and p.name!='.DS_Store' and '__pycache__' not in p.parts]
    hashes={str(n):sha(source/n) for n in names}
    output.mkdir(parents=True)
    for n in names:(output/n).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/n,output/n)
    records=[];active=set();pcb=output/'stratolink.kicad_pcb';original=pcb.read_text();markers=[]
    def board_fn(n,b):
        if n[0]=='setup':
            def setup_fn(sn,sb):
                if sn[0]=='stackup':
                    def stack_fn(ln,lb):
                        if ln[0]=='layer' and ln[1] in {'F.Mask','B.Mask'}:
                            lb=set_child(lb,'thickness','(thickness 0.01)');return set_child(lb,'color','(color "Green")')
                        if ln[0]=='layer' and ln[1]=='dielectric 1':return set_child(lb,'thickness','(thickness 0.31)')
                        if ln[0]=='copper_finish':return '(copper_finish "ENIG")'
                        return lb
                    return change_children(sb,stack_fn)
                if sn[0]=='tenting':return '(tenting (front yes) (back yes))'
                return sb
            b=change_children(b,setup_fn)
            b=set_child(b,'pad_to_mask_clearance','(pad_to_mask_clearance 0)')
            b=set_child(b,'solder_mask_min_width','(solder_mask_min_width 0.1)')
            return set_child(b,'allow_soldermask_bridges_in_footprints','(allow_soldermask_bridges_in_footprints no)')
        if n[0]=='footprint':
            ref=prop(n,'Reference');active.add(n[1].split(':',1)[-1]);return finish_footprint(b,ref,records)
        if n[0]=='gr_rect' and scalar(n,'uuid') in MASK_RECT_IDS:
            assert one(n,'start')==['52','28'] and one(n,'end')==['78','88'];records.append({'action':'remove_full_board_mask','uuid':scalar(n,'uuid')});return ''
        if scalar(n,'layer') in SILK:
            # Replace the four former solar silk legends with small isolated
            # copper +/- markers and exact-size mask openings at the same spots.
            if n[0]=='gr_text' and n[1] in {'+','GND'}:
                sign='+' if n[1]=='+' else '-';at=' '.join(one(n,'at'));ident=scalar(n,'uuid')
                copper=f'(gr_text "{sign}" (at {at}) (layer "F.Cu") (uuid "{ident}") (effects (font (size 0.6 0.6) (thickness 0.12))))'
                mask=copper.replace('(layer "F.Cu")','(layer "F.Mask")').replace(ident,str(uuid.uuid5(NS,'marker-mask-'+ident)))
                markers.append(mask);records.append({'action':'solar_silk_to_copper','uuid':ident,'sign':sign,'at':one(n,'at')});return copper
            records.append({'action':'remove_board_silk','type':n[0]});return ''
        return b
    changed=change_children(original,board_fn)
    changed=changed[:-1]+'\n'+'\n'.join(markers)+'\n)' if changed.endswith(')') else changed.rstrip()[:-1]+'\n'+'\n'.join(markers)+'\n)\n'
    pcb.write_text(changed)
    library_records=[]
    for name in sorted(active):
        f=output/'lib'/(name+'.kicad_mod');assert f.is_file(),('Missing active local footprint',name)
        f.write_text(finish_footprint(f.read_text(),name,library_records))
    project=output/'stratolink.kicad_pro';pro=json.loads(project.read_text());pro['board']['design_settings']['rule_severities']['solder_mask_bridge']='error';pro['board']['design_settings']['rules']['solder_mask_to_copper_clearance']=0.09;project.write_text(json.dumps(pro,indent=2)+'\n')
    assert all(sha(source/f)==h for f,h in hashes.items()),'Source changed while copying'
    final={str(n):sha(output/n) for n in names}
    report={'script_sha256':sha(Path(__file__)),'source':str(source),'source_pcb_sha256':expect,'source_hashes':hashes,'output_hashes':final,'board_actions':records,'library_actions':library_records,'active_libraries':sorted(active),'intent':'Green mask, no silkscreen; zero global expansion, 0.1 mm web, 0.09 mm mask-to-foreign-copper screen; vias tented; native special mask graphics retained'}
    (output/'green-mask-patch.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'output':str(output),'source_pcb_sha256':expect,'pcb_sha256':sha(pcb),'active_libraries':len(active),'board_actions':len(records),'library_actions':len(library_records)},indent=2))

if __name__=='__main__':
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--source',type=Path,required=True);a.add_argument('--output',type=Path,required=True);a.add_argument('--expect-pcb',required=True);args=a.parse_args();patch(args.source,args.output,args.expect_pcb)
