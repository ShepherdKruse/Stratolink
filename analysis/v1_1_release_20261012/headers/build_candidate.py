#!/usr/bin/env python3
"""Back-face header tack lands and contained signal-route clearance, scratch only."""
from pathlib import Path
import hashlib,importlib.util,json,subprocess,sys,uuid
import pcbnew,wx

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
BASE='59979799c5809d636639084227d9fee75c8de1d9'
OUT=Path.home()/'Repositories/ai-working/scratch/stratolink-release-20261012/headers'
CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
spec=importlib.util.spec_from_file_location('ground_builder',ROOT/'analysis/v1_1_ground_20261012/build_candidate.py')
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h);a=h.cad
LIBS={r:'Stratolink_Programming_'+s+'_1x07_P1p00_D0p50_BackTack1p20x0p88' for r,s in [('J3','Left'),('J4','Right')]}
VALUE='Programming_1x07_P1.00mm_D0.50mm'
DESC='Programming/wire pads: 7 positions, 1.00 mm pitch, 0.50 mm holes; 0.88 mm front lands and 1.20 x 0.88 mm inward-extended back tack lands.'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def vec(x,y):return pcbnew.VECTOR2I(round(x*1e6),round(y*1e6))

def main():
    names=['stratolink.kicad_pcb','stratolink.kicad_sch','stratolink.kicad_pro','fp-lib-table','sym-lib-table']
    libs=subprocess.check_output(['git','ls-tree','-r','--name-only',BASE+':hardware/pcb/lib'],cwd=ROOT,text=True).splitlines()
    names+=['lib/'+n for n in libs]
    protected={n:sha(ROOT/'hardware/pcb'/n) for n in names}
    for directory in [OUT/'baseline',OUT/'candidate']:
        directory.mkdir(parents=True,exist_ok=True)
        for n in names:
            p=directory/n;p.parent.mkdir(parents=True,exist_ok=True)
            p.write_bytes(subprocess.check_output(['git','show',BASE+':hardware/pcb/'+n],cwd=ROOT))
    directory=OUT/'candidate';pcb=directory/'stratolink.kicad_pcb'
    app=wx.App(False);b=pcbnew.LoadBoard(str(pcb))
    pad_changes=[]
    for f in b.GetFootprints():
        ref=f.GetReference()
        if ref not in LIBS:continue
        lib=LIBS[ref];f.SetFPID(pcbnew.LIB_ID('lib',lib));f.SetValue(VALUE);f.SetLibDescription(DESC)
        desc=f.GetField('Description')
        if desc:desc.SetText(DESC)
        for p in f.Pads():
            assert p.GetSize()==vec(.88,.88) and p.GetDrillSize()==vec(.5,.5)
            assert p.GetOffset()==vec(0,0)
            pos=list(p.GetPosition());front_shape=p.GetShape()
            p.Padstack().SetMode(pcbnew.PADSTACK.MODE_FRONT_INNER_BACK)
            p.SetSize(pcbnew.F_Cu,vec(.88,.88));p.SetOffset(pcbnew.F_Cu,vec(0,0))
            p.SetShape(pcbnew.F_Cu,front_shape)
            p.SetSize(pcbnew.In1_Cu,vec(.88,.88));p.SetOffset(pcbnew.In1_Cu,vec(0,0));p.SetShape(pcbnew.In1_Cu,front_shape)
            p.SetSize(pcbnew.B_Cu,vec(1.20,.88));p.SetOffset(pcbnew.B_Cu,vec(.12 if ref=='J3' else -.12,0))
            p.SetShape(pcbnew.B_Cu,front_shape)
            if ref=='J3' and p.GetNumber()=='2':p.SetThermalSpokeAngle(pcbnew.EDA_ANGLE(30,pcbnew.DEGREES_T))
            assert list(p.GetPosition())==pos and p.GetDrillSize()==vec(.5,.5)
            pad_changes.append(dict(ref=ref,number=p.GetNumber(),uuid=p.m_Uuid.AsString(),back_size_mm=[1.2,.88],back_offset_mm=[.12 if ref=='J3' else -.12,0],thermal_angle_deg=p.GetThermalSpokeAngleDegrees()))
        clone=pcbnew.FOOTPRINT(f);clone.SetPosition(vec(0,0));clone.SetReference('REF**');clone.SetValue(VALUE)
        pcbnew.FootprintSave(str(directory/'lib'),clone)
    updates={
      '57afa99e-0f6b-491c-a967-b4ab7afd6be7':((55.431,71.844239),(55.431,72.598)),
      'a5a38b4c-aafe-4539-83f2-20ee7d9a4890':((55.757116,71.518123),(55.431,71.844239)),
      'd058defb-6758-4864-9e39-79a15b1dd9f7':((55.431,72.598),(55.974,73.141)),
      'f61043a4-1291-4315-b94d-e8cfe8c45bbd':((73.932,71.733),(73.932,72.2)),
    }
    route_changes=[];rx=None
    for t in b.GetTracks():
        uid=t.m_Uuid.AsString()
        if uid not in updates:continue
        assert t.GetLayer()==pcbnew.B_Cu and t.GetWidth()==250000
        old=[list(t.GetStart()),list(t.GetEnd())];s,e=updates[uid]
        t.SetStart(vec(*s));t.SetEnd(vec(*e));route_changes.append(dict(uuid=uid,net=t.GetNetname(),before_nm=old,after_mm=[s,e]))
        if t.GetNetname()=='RX':rx=t
    assert len(route_changes)==4 and rx is not None
    added=[]
    for index,(s,e) in enumerate([((73.932,72.2),(74.906,73.174)),((74.906,73.174),(75.373,73.174))]):
        t=pcbnew.PCB_TRACK(b);t.SetLayer(pcbnew.B_Cu);t.SetWidth(250000);t.SetNetCode(rx.GetNetCode());t.SetStart(vec(*s));t.SetEnd(vec(*e))
        uid=str(uuid.uuid5(uuid.NAMESPACE_URL,'stratolink-v1.1-header-back-tack-rx/'+str(index)));generated=t.m_Uuid.AsString();b.Add(t)
        added.append(dict(uuid=uid,generated_uuid=generated,net='RX',start_mm=s,end_mm=e,width_mm=.25))
    pcbnew.SaveBoard(str(pcb),b)
    text=pcb.read_text()
    for r in added:text=text.replace(r.pop('generated_uuid'),r['uuid'])
    pcb.write_text(text)
    sch=directory/'stratolink.kicad_sch';text=sch.read_text();changes=[]
    for start,end,depth in h.spans(text):
        if depth!=1:continue
        block=text[start:end];node=a.parse(block)
        if node[0]!='symbol' or a.prop(node,'Reference') not in LIBS:continue
        ref=a.prop(node,'Reference');fields={'Footprint':'lib:'+LIBS[ref],'Value':VALUE,'Description':DESC};inner=[]
        for s,e,d in h.spans(block):
            if d!=1:continue
            prop=a.parse(block[s:e])
            if prop[0]=='property' and prop[1] in fields:
                orig=json.dumps(prop[2],ensure_ascii=False);replacement=json.dumps(fields[prop[1]],ensure_ascii=False)
                old=block[s:e];prefix='(property '+json.dumps(prop[1])+' '+orig
                assert old.startswith(prefix);inner.append((s,e,old.replace(prefix,'(property '+json.dumps(prop[1])+' '+replacement,1)))
        assert {'Footprint','Value'} <= {a.parse(block[s:e])[1] for s,e,_ in inner}
        changes.append((start,end,h.replace(block,inner)))
    assert len(changes)==2;sch.write_text(h.replace(text,changes))
    result=subprocess.run([CLI,'pcb','drc','--refill-zones','--save-board','--schematic-parity','--format','json','--output',str(HERE/'candidate-drc-project.json'),str(pcb)],check=True,capture_output=True,text=True)
    (directory/'build.log').write_text(result.stdout+result.stderr)
    for n,v in protected.items():assert sha(ROOT/'hardware/pcb'/n)==v,('Canonical source changed',n)
    manifest=dict(baseline=BASE,baseline_dir=str(OUT/'baseline'),candidate=str(directory),pad_changes=pad_changes,route_changes=route_changes,added_routes=added,libraries={r:'lib/'+n+'.kicad_mod' for r,n in LIBS.items()},files={n:sha(directory/n) for n in ['stratolink.kicad_pcb','stratolink.kicad_sch','stratolink.kicad_pro']+['lib/'+x+'.kicad_mod' for x in LIBS.values()]})
    (HERE/'candidate.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest,indent=2))

if __name__=='__main__':main()
