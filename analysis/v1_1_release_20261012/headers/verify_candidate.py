#!/usr/bin/env python3
"""Native connectivity, per-layer padstack and manufacturing comparison."""
from pathlib import Path
from collections import Counter
import copy,hashlib,importlib.util,json,shutil,subprocess,sys
import pcbnew,wx

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
OUT=Path.home()/'Repositories/ai-working/scratch/stratolink-release-20261012/headers'
CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
sys.path.insert(0,str(ROOT/'analysis/v1_1_ground_20261012/review'))
from verify_native import pads,physical_set,normplot,a,stripped,signature

def unordered_children(t):return sorted(json.dumps(x,sort_keys=True) for x in t)

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(args,log):
    r=subprocess.run(args,check=True,text=True,capture_output=True);log.write_text(r.stdout+r.stderr)

def main():
    m=json.loads((HERE/'candidate.json').read_text());base=Path(m['baseline_dir']);candidate=Path(m['candidate'])
    for n,v in m['files'].items():assert sha(candidate/n)==v
    old,cur=[a.parse((d/'stratolink.kicad_pcb').read_text()) for d in [base,candidate]]
    of,nf=[{a.prop(f,'Reference'):f for f in a.nodes(t,'footprint')} for t in [old,cur]]
    assert of.keys()==nf.keys();header_changes=[]
    for ref in of:
        x,y=copy.deepcopy(of[ref]),copy.deepcopy(nf[ref])
        if ref not in ['J3','J4']:assert unordered_children(x)==unordered_children(y),('Other footprint changed',ref);continue
        y[1]=x[1]
        for kind in ['descr']:
            for node in a.nodes(y,kind):node[:]=a.nodes(x,kind)[0]
        for name in ['Value','Description']:
            xp=next(p for p in a.nodes(x,'property') if p[1]==name)
            yp=next(p for p in a.nodes(y,'property') if p[1]==name);yp[2]=xp[2]
        xp,yp=[a.keyed(a.nodes(t,'pad')) for t in [x,y]]
        assert xp.keys()==yp.keys()
        for uid in xp:
            p,q=xp[uid],yp[uid];header_changes.append(dict(ref=ref,pad=p[1],uuid=uid))
            q[:]=stripped(q,{'padstack'})
            if ref=='J3' and p[1]=='2':q[:]=stripped(q,{'thermal_bridge_angle'})
            # Explicit zero front drill offset is native serialization of an unchanged position.
            dr=a.nodes(q,'drill')[0]
            for z in list(dr):
                if isinstance(z,list) and z[0]=='offset':assert z==['offset','0','0'];dr.remove(z)
            assert p==q,('Unexpected header pad mutation',ref,p[1],p,q)
        assert x==y,('Unexpected header footprint mutation',ref)
    os,ns=[a.keyed(a.nodes(t,'segment')) for t in [old,cur]]
    changed={r['uuid'] for r in m['route_changes']};added={r['uuid'] for r in m['added_routes']}
    assert not os.keys()-ns.keys() and ns.keys()-os.keys()==added
    for uid in os:
        if uid not in changed:assert os[uid]==ns[uid],('Unexpected segment',uid)
        else:assert stripped(os[uid],{'start','end'})==stripped(ns[uid],{'start','end'})
    oz,nz=[a.keyed(a.nodes(t,'zone')) for t in [old,cur]];assert oz.keys()==nz.keys()
    for uid in oz:assert stripped(oz[uid],{'filled_polygon','filled_areas_thickness'})==stripped(nz[uid],{'filled_polygon','filled_areas_thickness'})
    assert unordered_children(stripped(old,{'footprint','segment','zone'}))==unordered_children(stripped(cur,{'footprint','segment','zone'}))
    for n in ['stratolink.kicad_pro','fp-lib-table','sym-lib-table']:assert (base/n).read_bytes()==(candidate/n).read_bytes()
    oldsch,newsch=[a.parse((d/'stratolink.kicad_sch').read_text()) for d in [base,candidate]]
    syms0,syms1=[{a.prop(s,'Reference'):s for s in a.nodes(t,'symbol')} for t in [oldsch,newsch]]
    assert syms0.keys()==syms1.keys()
    sch_fields=[]
    for ref in syms0:
        x,y=syms0[ref],syms1[ref]
        if ref not in ['J3','J4']:assert x==y,('Other schematic symbol changed',ref);continue
        for name in ['Footprint','Value','Description']:
            px=[p for p in a.nodes(x,'property') if p[1]==name];py=[p for p in a.nodes(y,'property') if p[1]==name]
            assert len(px)==len(py)
            if not px:continue
            if px[0][2]!=py[0][2]:sch_fields.append(dict(ref=ref,field=name,before=px[0][2],after=py[0][2]))
            py[0][2]=px[0][2]
        assert x==y,('Header schematic changed beyond metadata',ref)
    assert oldsch==newsch
    oldlib={p.name:sha(p) for p in (base/'lib').iterdir() if p.is_file()}
    for n,v in oldlib.items():assert sha(candidate/'lib'/n)==v
    actualnew={p.name for p in (candidate/'lib').iterdir() if p.is_file()}-oldlib.keys()
    assert actualnew=={Path(p).name for p in m['libraries'].values()}
    app=wx.App(False);boards={label:pcbnew.LoadBoard(str(d/'stratolink.kicad_pcb')) for label,d in [('baseline',base),('candidate',candidate)]}
    for b in boards.values():b.BuildConnectivity()
    p0,p1=[pads(boards[k]) for k in ['baseline','candidate']];assert p0.keys()==p1.keys() and len(p1)==232
    padstacks=[]
    for uid,p in p1.items():
        q=p0[uid];ref=p.GetParentFootprint().GetReference()
        assert p.GetPosition()==q.GetPosition() and p.GetDrillSize()==q.GetDrillSize() and p.GetNetname()==q.GetNetname()
        assert physical_set(boards['baseline'].GetConnectivity(),q)==physical_set(boards['candidate'].GetConnectivity(),p),('Physical pad island changed',ref,p.GetNumber())
        if ref not in ['J3','J4']:continue
        assert p.GetSize(pcbnew.F_Cu)==q.GetSize(pcbnew.F_Cu) and p.GetOffset(pcbnew.F_Cu)==q.GetOffset(pcbnew.F_Cu)
        assert p.GetSize(pcbnew.B_Cu)==pcbnew.VECTOR2I(1200000,880000)
        assert p.GetOffset(pcbnew.B_Cu)==pcbnew.VECTOR2I(120000 if ref=='J3' else -120000,0)
        padstacks.append(dict(ref=ref,pad=p.GetNumber(),hole_center_nm=list(p.GetPosition()),hole_nm=list(p.GetDrillSize()),front_size_nm=list(p.GetSize(pcbnew.F_Cu)),back_size_nm=list(p.GetSize(pcbnew.B_Cu)),back_offset_nm=list(p.GetOffset(pcbnew.B_Cu)),thermal_angle_deg=p.GetThermalSpokeAngleDegrees()))
    assert boards['candidate'].GetConnectivity().GetUnconnectedCount(False)==0
    for ref,path in m['libraries'].items():
        f=next(f for f in boards['candidate'].GetFootprints() if f.GetReference()==ref)
        lib=pcbnew.FootprintLoad(str(candidate/'lib'),Path(path).stem)
        def spec(p):return [p.GetNumber(),list(p.GetFPRelativePosition()),list(p.GetDrillSize()),p.GetThermalSpokeAngleDegrees()]+[[list(p.GetSize(l)),list(p.GetOffset(l)),p.GetShape(l)] for l in [pcbnew.F_Cu,pcbnew.B_Cu]]
        assert sorted(spec(p) for p in f.Pads())==sorted(spec(p) for p in lib.Pads())
    drc={};exports={}
    for label,d in [('baseline',base),('candidate',candidate)]:
        report=HERE/(label+'-drc-project.json');run([CLI,'pcb','drc','--refill-zones','--schematic-parity','--format','json','--output',str(report),str(d/'stratolink.kicad_pcb')],OUT/(label+'-drc.log'))
        drc[label]=json.loads(report.read_text())
        export=OUT/(label+'-exports');export.mkdir(exist_ok=True);exports[label]=export
        run([CLI,'pcb','export','gerbers','--layers','F.Cu,B.Cu,F.Mask,B.Mask,F.Paste,B.Paste,Edge.Cuts','--output',str(export),str(d/'stratolink.kicad_pcb')],export/'gerber.log')
        run([CLI,'pcb','export','drill','--format','excellon','--excellon-units','mm','--excellon-separate-th','--output',str(export),str(d/'stratolink.kicad_pcb')],export/'drill.log')
        # 0.10mm process screen retains the bare-board mask exception, opens and all other checks.
        diag=OUT/(label+'-process-screen');shutil.copytree(d,diag,dirs_exist_ok=True)
        pro=json.loads((diag/'stratolink.kicad_pro').read_text());ds=pro['board']['design_settings']
        ds['rules']['min_clearance']=.1;ds['rules']['min_copper_edge_clearance']=.2
        ds['rule_severities']['clearance']='error';ds['rule_severities']['copper_edge_clearance']='error'
        for netclass in pro['net_settings']['classes']:netclass['clearance']=.1
        (diag/'stratolink.kicad_pro').write_text(json.dumps(pro,indent=2)+'\n')
        run([CLI,'pcb','drc','--refill-zones','--schematic-parity','--format','json','--output',str(HERE/(label+'-drc-process.json')),str(diag/'stratolink.kicad_pcb')],diag/'drc.log')
    changes=[]
    for p in exports['baseline'].iterdir():
        if p.suffix not in {'.gtl','.gbl','.gts','.gbs','.gtp','.gbp','.gm1','.drl'}:continue
        if normplot(p.read_text())!=normplot((exports['candidate']/p.name).read_text()):changes.append(p.name)
    assert not any(n.endswith(('.drl','.gtp','.gbp','.gm1')) for n in changes)
    assert not any(v['type'] in ['starved_thermal','shorting_items'] for v in drc['candidate']['violations'])
    assert not drc['candidate']['unconnected_items']
    result=dict(pcb_sha256=sha(candidate/'stratolink.kicad_pcb'),physical_pad_connectivity_sets=232,zero_opens=True,padstacks=padstacks,schematic_metadata_changes=sch_fields,
      unchanged_hole_centers_and_drills=True,unchanged_front_pad_geometry=True,unchanged_baseline_libraries=len(oldlib),new_libraries=sorted(actualnew),changed_manufacturing_plots=changes,
      project_drc={k:dict(count=len(v['violations']),types=dict(Counter(x['type'] for x in v['violations'])),parity=len(v['schematic_parity'])) for k,v in drc.items()})
    for n,v in m['files'].items():assert sha(candidate/n)==v
    (HERE/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='padstacks'},indent=2))

if __name__=='__main__':main()
