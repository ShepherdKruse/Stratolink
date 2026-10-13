#!/usr/bin/env python3
"""Independently verify finish-only source invariants and selective native mask apertures."""
from pathlib import Path
import argparse,copy,hashlib,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'manufacturing'))
from test_stencil import parse,nodes,prop
import pcbnew,wx

def one(n,k):return next((x[1:] for x in n if isinstance(x,list) and x and x[0]==k),[])
def scalar(n,k):v=one(n,k);return v[0] if v else None
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
SILK={'F.SilkS','B.SilkS'}
def no_silk(n):
    if not isinstance(n,list):return
    assert not (n and n[0]=='layer' and len(n)>1 and n[1] in SILK),'Silkscreen item remains'
    for child in n:no_silk(child)

def strip_fp(n):
    """Ignore only authorized finish changes; retain ALL copper/paste/net fields."""
    result=[];name=n[1];margin=any('Stratolink_v1p1_'+ref+'_' in name for ref in ('U2','U3'))
    for x in n:
        if not isinstance(x,list):result.append(x);continue
        layer=scalar(x,'layer')
        if layer in SILK and x[0]!='property':continue
        if x[0]=='property':
            x=copy.deepcopy(x)
            for field in x:
                if isinstance(field,list) and field[0]=='layer' and field[1] in SILK|{'F.Fab','B.Fab'}:field[1]='PROPERTY'
        if x[0]=='pad' and margin:x=[z for z in x if not (isinstance(z,list) and z[0]=='solder_mask_margin')]
        if x[0]=='fp_poly' and 'Stratolink_v1p1_L1_' in name and layer in {'F.Mask','B.Mask'}:continue
        result.append(x)
    return result

def verify_fp(before,after):
    assert strip_fp(before)==strip_fp(after),('Footprint changed beyond finish',before[1])
    no_silk(after)
    if any('Stratolink_v1p1_'+ref+'_' in before[1] for ref in ('U2','U3')):
        assert all(scalar(p,'solder_mask_margin')=='0' for p in nodes(after,'pad'))
    if 'Stratolink_v1p1_L1_' in before[1]:
        old=nodes(before,'fp_poly');new=nodes(after,'fp_poly')
        masks=[one(p,'pts') for p in new if scalar(p,'layer') in {'F.Mask','B.Mask'}]
        paste=[one(p,'pts') for p in new if scalar(p,'layer') in {'F.Paste','B.Paste'}]
        assert len(masks)==2 and sorted(masks)==sorted(paste),'L1 mask not exact unchanged paste outline'
        assert len([p for p in old if scalar(p,'layer') in {'F.Mask','B.Mask'}])==2

def verify(source,finished):
    report=json.loads((finished/'green-mask-patch.json').read_text())
    assert report['source_pcb_sha256']==sha(source/'stratolink.kicad_pcb')
    assert all(sha(source/f)==h for f,h in report['source_hashes'].items())
    assert all(sha(finished/f)==h for f,h in report['output_hashes'].items())
    allowed_files={'stratolink.kicad_pcb','stratolink.kicad_pro'}|{'lib/'+n+'.kicad_mod' for n in report['active_libraries']}
    assert all(report['source_hashes'][f]==h for f,h in report['output_hashes'].items() if f not in allowed_files),'Non-finish file changed'
    b=parse((source/'stratolink.kicad_pcb').read_text());a=parse((finished/'stratolink.kicad_pcb').read_text())
    oldsetup=nodes(b,'setup')[0];newsetup=nodes(a,'setup')[0]
    variable={'stackup','pad_to_mask_clearance','solder_mask_min_width','allow_soldermask_bridges_in_footprints','tenting'}
    assert [x for x in oldsetup if not isinstance(x,list) or x[0] not in variable]==[x for x in newsetup if not isinstance(x,list) or x[0] not in variable]
    oldstack=nodes(oldsetup,'stackup')[0];newstack=nodes(newsetup,'stackup')[0]
    assert len(oldstack)==len(newstack)
    for before,after in zip(oldstack,newstack):
        if not isinstance(before,list):assert before==after;continue
        expected=copy.deepcopy(before)
        if before[0]=='layer' and before[1] in {'F.Mask','B.Mask','dielectric 1'}:
            for field in expected:
                if isinstance(field,list) and field[0]=='thickness':field[1]='0.31' if before[1]=='dielectric 1' else '0.01'
            if before[1] in {'F.Mask','B.Mask'}:
                colors=nodes(expected,'color')
                if colors:colors[0][1]='Green'
                else:expected.append(['color','Green'])
        if before[0]=='copper_finish':expected=['copper_finish','ENIG']
        assert expected==after,('Unexpected stackup mutation',before,after)

    beforefp={prop(f,'Reference'):f for f in nodes(b,'footprint')};afterfp={prop(f,'Reference'):f for f in nodes(a,'footprint')}
    assert set(beforefp)==set(afterfp)
    for r in beforefp:verify_fp(beforefp[r],afterfp[r])
    for name in report['active_libraries']:
        p=Path('lib')/(name+'.kicad_mod');verify_fp(parse((source/p).read_text()),parse((finished/p).read_text()))
    markers={x['uuid'] for x in report['board_actions'] if x['action']=='solar_silk_to_copper'}
    oldfull={'19552f78-8bc8-5d58-a252-cce4c7aa3763','65f5aa32-1dfc-539e-ac84-add1df7c2354'}
    def board_remainder(n,after=False):
        keep=[]
        for x in n:
            if not isinstance(x,list):keep.append(x);continue
            if x[0] in {'footprint','setup'}:continue
            if scalar(x,'layer') in SILK:continue
            if scalar(x,'uuid') in oldfull|markers:continue
            if after and x[0]=='gr_text' and scalar(x,'layer')=='F.Mask' and x[1] in {'+','-'}:continue
            keep.append(x)
        return keep
    assert board_remainder(b)==board_remainder(a,True),'Routing, outline, copper/paste, zones or other metadata changed'
    assert not any(scalar(x,'uuid') in oldfull for x in a if isinstance(x,list))
    for x in a:
        if isinstance(x,list) and x[0] not in {'setup','layers'}:no_silk(x)
    assert len(markers)==4
    allmarkers=[x for x in a if isinstance(x,list) and x and x[0]=='gr_text' and scalar(x,'uuid') in markers]
    assert len(allmarkers)==4 and sorted(x[1] for x in allmarkers)==['+','+','-','-']
    for x in allmarkers:
        assert scalar(x,'layer')=='F.Cu'
        original=next(z for z in nodes(b,'gr_text') if scalar(z,'uuid')==scalar(x,'uuid'))
        assert one(x,'at')==one(original,'at') and x[1]==('+' if original[1]=='+' else '-')
        assert one(x,'effects')==[['font',['size','0.6','0.6'],['thickness','0.12']]]

        mask=[z for z in nodes(a,'gr_text') if scalar(z,'layer')=='F.Mask' and z[1]==x[1] and one(z,'at')==one(x,'at')]
        assert len(mask)==1 and one(mask[0],'effects')==one(x,'effects'),'Copper marker/mask mismatch'
    oldpro=json.loads((source/'stratolink.kicad_pro').read_text());newpro=json.loads((finished/'stratolink.kicad_pro').read_text())
    oldpro['board']['design_settings']['rule_severities']['solder_mask_bridge']='error'
    oldpro['board']['design_settings']['rules']['solder_mask_to_copper_clearance']=.09
    assert oldpro==newpro,'Unexpected project setting change'
    board=pcbnew.LoadBoard(str(finished/'stratolink.kicad_pcb'));ds=board.GetDesignSettings()
    assert ds.m_SolderMaskExpansion==0 and ds.m_SolderMaskMinWidth==100000 and ds.m_SolderMaskToCopperClearance==90000
    assert ds.m_TentViasFront and ds.m_TentViasBack and not ds.m_AllowSoldermaskBridgesInFPs
    mask_shapes={layer:[] for layer in (pcbnew.F_Mask,pcbnew.B_Mask)}
    for fp in board.GetFootprints():
        for p in fp.Pads():
            for layer in mask_shapes:
                if p.IsOnLayer(layer):
                    poly=pcbnew.SHAPE_POLY_SET();p.TransformShapeToPolygon(poly,layer,p.GetSolderMaskExpansion(layer),1000,pcbnew.ERROR_OUTSIDE)
                    mask_shapes[layer].append(('pad '+fp.GetReference()+'.'+p.GetNumber(),poly))
        for g in fp.GraphicalItems():
            if g.GetLayer() in mask_shapes:
                poly=pcbnew.SHAPE_POLY_SET();g.TransformShapeToPolygon(poly,g.GetLayer(),0,1000,pcbnew.ERROR_OUTSIDE)
                mask_shapes[g.GetLayer()].append(('graphic '+fp.GetReference()+' '+g.m_Uuid.AsString(),poly))
    for g in board.GetDrawings():
        if g.GetLayer() in mask_shapes:
            poly=pcbnew.SHAPE_POLY_SET();g.TransformShapeToPolygon(poly,g.GetLayer(),0,1000,pcbnew.ERROR_OUTSIDE)
            mask_shapes[g.GetLayer()].append(('board '+g.m_Uuid.AsString(),poly))
    via_rows=[]
    for t in board.GetTracks():
        if t.GetClass()!='PCB_VIA':continue
        row={'uuid':t.m_Uuid.AsString(),'net':t.GetNetname(),'center_mm':[t.GetPosition().x/1e6,t.GetPosition().y/1e6],
             'annulus_radii_mm':{face:t.GetWidth(layer)/2e6 for face,layer in [('F',pcbnew.F_Cu),('B',pcbnew.B_Cu)]},
             'tented_front':bool(t.IsTented(pcbnew.F_Mask)),'tented_back':bool(t.IsTented(pcbnew.B_Mask)),
             'covering_openings':{pcbnew.LayerName(layer):[desc for desc,p in polys if p.Contains(t.GetPosition())] for layer,polys in mask_shapes.items()}}
        via_rows.append(row)
    u6=next(f for f in board.GetFootprints() if f.GetReference()=='U6');pos=u6.GetPosition()
    under=[]
    if u6.GetValue().startswith('AS7331'):
        assert u6.GetOrientationDegrees()==0,'Update body coordinate transform for rotated U6'
        for row in via_rows:
            x,y=row['center_mm']
            dx=max(abs(x-pos.x/1e6)-1.35,0);dy=max(abs(y-pos.y/1e6)-1.875,0)
            if dx*dx+dy*dy<=max(row['annulus_radii_mm'].values())**2:
                assert row['tented_front'] and row['tented_back'],'Under-U6 via not tented both faces'
                assert not any(row['covering_openings'].values()),'Native mask opening overlaps under-U6 via center'
                under.append(row)
    return {'source_pcb_sha256':sha(source/'stratolink.kicad_pcb'),'finished_pcb_sha256':sha(finished/'stratolink.kicad_pcb'),
      'copper_paste_routing_nets_outline_zones_identical_except_4_isolated_markers':True,'all_footprints_verified':len(beforefp),
      'active_libraries_verified':len(report['active_libraries']),'native_silkscreen_items':0,'solar_copper_markers':4,
      'mask_to_copper_mm':.09,'mask_min_web_mm':.1,'global_mask_expansion_mm':0,
      'vias':via_rows,'under_U6_vias':under,'under_U6_selection':'Copper annulus intersects maximum 2.7 x 3.75 mm body envelope',
      'limit':'Native aperture point test includes explicit pad margins and custom graphics. Final Gerber point test/CAM remains separate; tenting is not resin filling.'}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--finished',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args();app=wx.App(False)
    r=verify(a.source,a.finished);a.report.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k!='vias'},indent=2))
