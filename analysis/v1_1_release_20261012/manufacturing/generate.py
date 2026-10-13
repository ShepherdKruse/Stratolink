#!/usr/bin/env python3
"""Read-only, review-stage KiCad/JLC exports. Run with KiCad's bundled Python."""
import argparse, collections, csv, hashlib, json, math, re, subprocess, sys, xml.etree.ElementTree as ET, zipfile
from pathlib import Path
import pcbnew, wx

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CLI = '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
MANUAL = {'AE1','AE2','J1','J2','J3','J4','C5','J20'}
SELECTED = HERE.parent/'jlc/previous-selected-parts.txt'
OLD_CPL = ROOT/'hardware/gerbers/production_files/CPL-stratolink.csv'
OLD_REV = '9bdd19ec707455271f48f5a5d8be352fc696cf9c'
OLD_HASHES = ROOT/'analysis/v1_1_layout_20261012/pcb_audit/source_hashes.json'
ROTATION_BASELINE = ('Historical equality reproduces the repository v1 production INPUT CPL. '
                     'It is not evidence of verified JLC post-CAM placement or supplier-model rotation.')


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def natural(ref): return [int(x) if x.isdigit() else x for x in re.split(r'(\d+)',ref)]
def need(condition, text):
    if not condition: raise ValueError(text)
def write_json(p,data): p.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')
def write_csv(p,keys,rows):
    with p.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
def unique(rows, key, context):
    result={}
    for row in rows:
        ref=key(row);need(ref not in result,context+' duplicate '+ref);result[ref]=row
    return result

def read_rotation_profile(path):
    def no_duplicate_keys(pairs):
        result={}
        for key,value in pairs:
            need(key not in result,'Duplicate supplier rotation profile key: '+key);result[key]=value
        return result
    data=json.loads(path.read_text(),object_pairs_hook=no_duplicate_keys)
    need(isinstance(data,dict) and bool(data),'Supplier rotation profile must be a nonempty reference mapping')
    for ref,entry in data.items():
        need(re.fullmatch(r'[A-Z]+\d+',ref) is not None,'Invalid supplier rotation reference: '+ref)
        need(isinstance(entry,dict) and set(entry)=={'rotation_deg','evidence','reason'},'Expected rotation_deg/evidence/reason for '+ref)
        angle=entry['rotation_deg']
        need(type(angle) in (int,float) and math.isfinite(angle) and 0<=angle<360,'Absolute CPL angle must be finite and in [0,360): '+ref)
        need(angle==round(angle,6),'CPL angle supports at most six decimal places: '+ref)
        for key in ('evidence','reason'):
            need(isinstance(entry[key],str) and bool(entry[key].strip()),'Missing '+key+' for supplier rotation '+ref)
    return data

def apply_supplier_rotations(assembly,profile):
    need(set(profile)<=set(assembly),'Supplier rotation profile contains missing/manual/non-assembly refs: '+','.join(sorted(set(profile)-set(assembly))))
    corrected={ref:dict(row) for ref,row in assembly.items()};records=[]
    for ref,entry in sorted(profile.items(),key=lambda pair:natural(pair[0])):
        row=corrected[ref];base=row['rotation_deg'];row['rotation_deg']=float(entry['rotation_deg'])
        records.append(dict(ref=ref,base_rotation_deg=base,override_rotation_deg=row['rotation_deg'],
            mpn=row['mpn'],lcsc=row['lcsc'],side=row['side'],center_mm=row['center_mm'],
            evidence=entry['evidence'],reason=entry['reason'],baseline_provenance=ROTATION_BASELINE))
    need({ref:{k:v for k,v in row.items() if k!='rotation_deg'} for ref,row in corrected.items()}==
         {ref:{k:v for k,v in row.items() if k!='rotation_deg'} for ref,row in assembly.items()},'Supplier profile changed non-rotation placement data')
    return corrected,records

def selected_parts():
    text=SELECTED.read_text().split('Unselected Parts')[0]
    parts={};groups=0
    # The UI text has one MPN immediately before Basic/Extended C-number.
    matches=list(re.finditer(r'^([^\n]+)\n(?:Basic|Extended) (C\d+)\s*$',text,re.M))
    for i,m in enumerate(matches):
        block=text[m.end():matches[i+1].start() if i+1<len(matches) else len(text)]
        refs=[]
        for line in block.splitlines():
            line=line.strip()
            if re.fullmatch(r'[A-Z]+\d+(?:,[A-Z]+\d+)*',line):refs+=line.split(',')
        need(bool(refs),'No designators in selected-part block '+m.group(2))
        for ref in refs:
            need(ref not in parts,'Duplicate previous selection '+ref)
            parts[ref]={'mpn':m.group(1).strip(),'lcsc':m.group(2)}
        groups+=1
    need(groups==28,'Previous selected-part UI must contain all 28 groups')
    return parts

def fields(f):return {x.GetName():x.GetText() for x in f.GetFields()}
def point(p):return [p.x/1e6,p.y/1e6]
def pad_center(f):
    # Never use FOOTPRINT.GetCenter: silk/fab/TH graphics can bias it.
    pads=[p.GetBoundingBox() for p in f.Pads() if p.GetAttribute()==pcbnew.PAD_ATTRIB_SMD and p.IsOnLayer(f.GetLayer())]
    need(bool(pads),'No placement-side SMD pads for '+f.GetReference())
    bounds=[min(p.GetLeft() for p in pads)/1e6,min(p.GetTop() for p in pads)/1e6,
            max(p.GetRight() for p in pads)/1e6,max(p.GetBottom() for p in pads)/1e6]
    return [round((bounds[0]+bounds[2])/2,9),round((bounds[1]+bounds[3])/2,9)],bounds

def historical_proof(old,selected,old_pcb):
    expected=json.loads(OLD_HASHES.read_text())
    need(sha(old_pcb)==expected['hardware/pcb/stratolink.kicad_pcb'],'Historical PCB hash changed')
    need(sha(OLD_CPL)==expected['hardware/gerbers/production_files/CPL-stratolink.csv'],'Historical CPL hash changed')
    fps=unique(old.GetFootprints(),lambda f:f.GetReference(),'Historical PCB')
    rows=unique(csv.DictReader(OLD_CPL.open()),lambda r:r['Designator'],'Historical CPL')
    proof=[]
    for ref in sorted(selected,key=natural):
        if ref=='MK1':continue  # removed microphone; not a convention proof for retained packages
        need(ref in rows and ref in fps,'Missing historical placement '+ref)
        f=fps[ref];r=rows[ref];center,bounds=pad_center(f);angle=f.GetOrientationDegrees()
        rotation=(180-angle if f.GetLayer()==pcbnew.B_Cu else angle)%360
        oldpos=[float(r['Mid X']),-float(r['Mid Y'])]
        delta=math.dist(center,oldpos);adelta=((rotation-float(r['Rotation'])+180)%360)-180
        need(delta<0.000003 and abs(adelta)<0.000001,'Historical convention mismatch '+ref)
        proof.append(dict(ref=ref,layer=r['Layer'],anchor_mm=point(f.GetPosition()),smd_pad_center_mm=center,
            smd_pad_bounds_mm=bounds,repository_v1_input_center_mm=oldpos,center_error_mm=delta,
            native_angle_deg=angle,repository_v1_input_rotation_deg=float(r['Rotation']),derived_rotation_deg=rotation,
            provenance=ROTATION_BASELINE))
    return rows,proof

def vertices(poly):
    return [(poly.Outline(i).CPoint(j).x/1e6,poly.Outline(i).CPoint(j).y/1e6)
            for i in range(poly.OutlineCount()) for j in range(poly.Outline(i).PointCount())]
def mask_proof(board,gerbers,stem):
    outline=pcbnew.SHAPE_POLY_SET();need(board.GetBoardPolygonOutlines(outline,False),'Invalid native outline')
    outline_points=vertices(outline);need(bool(outline_points),'Empty outline')
    result={}
    for face,cu,suffix in [('F',pcbnew.F_Cu,'gts'),('B',pcbnew.B_Cu,'gbs')]:
        p=gerbers/(stem+'-'+face+'_Mask.'+suffix);s=p.read_text()
        for token in ['%TF.FilePolarity,Negative*%','%FSLAX46Y46*%','%MOMM*%','%LPD*%']:
            need(token in s,'Unexpected mask Gerber convention: '+token)
        need('%LPC*%' not in s,'Clear-polarity mask operation requires full boolean CAM review')
        rectangles=[]
        for block in re.findall(r'G36\*\n(.*?)G37\*',s,re.S):
            pts=[];valid=True
            for line in block.splitlines():
                m=re.fullmatch(r'X(-?\d+)Y(-?\d+)D0[12]\*',line)
                if m:pts.append((int(m[1])/1e6,-int(m[2])/1e6))
                elif line.strip() and line not in {'G01*','D02*'}:valid=False
            if not valid or len(pts)!=5 or pts[0]!=pts[-1]:continue
            xs=sorted(set(x for x,y in pts));ys=sorted(set(y for x,y in pts))
            if len(xs)==2 and len(ys)==2 and set(pts)=={(x,y) for x in xs for y in ys}:
                if all(a[0]==b[0] or a[1]==b[1] for a,b in zip(pts,pts[1:])):rectangles.append([xs[0],ys[0],xs[-1],ys[-1]])
        copper=pcbnew.SHAPE_POLY_SET();board.ConvertBrdLayerToPolygonalContours(cu,copper);copper.Simplify()
        cupts=vertices(copper);need(bool(cupts),'Empty native copper')
        matching=[r for r in rectangles if all(r[0]<x<r[2] and r[1]<y<r[3] for x,y in outline_points+cupts)]
        need(bool(matching),'No full-face opening rectangle covering outline AND every copper island on '+face)
        bounds=max(matching,key=lambda r:(r[2]-r[0])*(r[3]-r[1]))
        margin=min(min(x-bounds[0],bounds[2]-x,y-bounds[1],bounds[3]-y) for x,y in outline_points)
        result[face]=dict(mask_file=p.name,opening_bounds_mm=bounds,outline_overrun_min_mm=margin,
            native_copper_islands=copper.OutlineCount(),all_copper_and_board_vertices_inside=True,
            dark_full_region=True,negative_mask_file=True,no_clear_plot_operations=True)
    job=json.loads((gerbers/(stem+'-job.gbrjob')).read_text())
    masks=[x for x in job['MaterialStackup'] if x['Type']=='SolderMask']
    need(len(masks)==2 and all(x['Thickness']==0 for x in masks),'Job stackup must specify zero mask on both faces')
    result['board_thickness_mm']=job['GeneralSpecs']['BoardThickness']
    result['interpretation']='Negative mask-file polarity identifies openings; full-face dark rectangles remove mask. Empty mask Gerbers are not accepted as no mask.'
    return result

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--candidate',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True);ap.add_argument('--stem',default='stratolink')
    ap.add_argument('--allow-part-change',action='append',default=[],metavar='REF',help='Explicitly permit a changed historical Supplier Part/MPN; still requires identical PCB/SCH fields')
    ap.add_argument('--supplier-rotation-profile',type=Path,
                    help='Reviewed JSON ref mapping with absolute rotation_deg plus evidence and reason; changes CPL rotation only')
    args=ap.parse_args();source=args.candidate.resolve();out=args.output.resolve();stem=args.stem
    need(source.is_dir(),'Missing candidate folder');need(not out.exists(),'Output must be a fresh folder')
    need(source!=out and source not in out.parents,'Output must be outside candidate source')
    pcb=source/(stem+'.kicad_pcb');sch=source/(stem+'.kicad_sch');need(pcb.is_file() and sch.is_file(),'PCB/SCH pair required')
    profile_path=args.supplier_rotation_profile.resolve() if args.supplier_rotation_profile else None
    profile_hash=sha(profile_path) if profile_path else None
    profile=read_rotation_profile(profile_path) if profile_path else {}
    # Hash manufacturing inputs, not the editor's changing UI/history files or
    # documentation that links back to the generated package manifest.
    roots=[source/(stem+suffix) for suffix in ('.kicad_pcb','.kicad_sch','.kicad_pro','.kicad_dru')]
    roots += [source/'fp-lib-table',source/'sym-lib-table']
    sourcefiles=sorted({p for p in roots if p.is_file()} |
        {p for folder in (source/'lib',source/'3d') for p in folder.rglob('*')
         if p.is_file() and p.suffix not in {'.log','.lck','.pyc','.pyo'}
         and '__pycache__' not in p.relative_to(source).parts
         and p.name != '.DS_Store' and not p.name.startswith('~')})
    hashes={str(p.relative_to(source)):sha(p) for p in sourcefiles}
    out.mkdir(parents=True);native=out/'native';native.mkdir();gerbers=out/'gerbers';gerbers.mkdir();logs=out/'logs';logs.mkdir()
    commands=[]
    def run(name,cmd):
        commands.append(cmd);r=subprocess.run(cmd,text=True,capture_output=True)
        (logs/(name+'.log')).write_text(r.stdout+r.stderr);need(r.returncode==0,name+' failed; see log')
    app=wx.App(False);board=pcbnew.LoadBoard(str(pcb));fps=unique(board.GetFootprints(),lambda f:f.GetReference(),'Candidate PCB')
    # Recreate the immutable flown board from Git instead of depending on an
    # untracked historical audit snapshot in this particular checkout.
    old_pcb=native/'historical-v1.kicad_pcb'
    old_pcb.write_bytes(subprocess.check_output(['git','show',OLD_REV+':hardware/pcb/stratolink.kicad_pcb'],cwd=ROOT))
    selected=selected_parts();old=pcbnew.LoadBoard(str(old_pcb));shipped,proof=historical_proof(old,selected,old_pcb)
    write_json(out/'historical-placement-proof.json',proof)
    run('netlist',[CLI,'sch','export','netlist','--format','kicadxml','--output',str(native/'netlist.xml'),str(sch)])
    comps=unique(ET.parse(native/'netlist.xml').findall('.//components/comp'),lambda c:c.get('ref'),'Native netlist')
    run('positions',[CLI,'pcb','export','pos','--format','csv','--units','mm','--side','both','--output',str(native/'positions.csv'),str(pcb)])
    rawpos=unique(csv.DictReader((native/'positions.csv').open()),lambda r:r['Ref'],'Native position file')
    assembly={};exclusions=[];changes=[]
    for ref in sorted(set(fps)|set(comps),key=natural):
        need(ref in fps,'Schematic reference has no PCB footprint: '+ref);f=fps[ref]
        reason=('manual assembly / no purchased placement' if ref in MANUAL else
                'mechanical board-only feature' if f.GetAttributes() & pcbnew.FP_BOARD_ONLY else
                'DNP' if f.IsDNP() else 'excluded from BOM AND placement in native footprint' if f.IsExcludedFromBOM() and f.IsExcludedFromPosFiles() else None)
        if reason:exclusions.append(dict(ref=ref,reason=reason));continue
        need(ref in comps,'PCB assembly footprint absent from netlist: '+ref)
        need(not f.IsExcludedFromBOM() and not f.IsExcludedFromPosFiles(),'Inconsistent BOM/placement exclusions for '+ref)
        need(ref in rawpos,'Assembly reference absent from native position file: '+ref)
        pc=fields(f);sc={x.get('name'):x.text or '' for x in comps[ref].findall('fields/field')}
        for key in ['Supplier Part','Manufacturer_Part_Number']:
            need(pc.get(key) and pc.get(key)==sc.get(key),'PCB/SCH missing or differing '+key+' for '+ref)
        need(re.fullmatch(r'C\d+',pc['Supplier Part']) is not None,'Invalid LCSC Supplier Part '+ref)
        for data in [pc,sc]:need(not data.get('LCSC') or data['LCSC']==pc['Supplier Part'],'Conflicting LCSC field '+ref)
        part={'mpn':pc['Manufacturer_Part_Number'],'lcsc':pc['Supplier Part']}
        if ref in selected and part!=selected[ref]:
            need(ref in args.allow_part_change,'Changed selected part requires --allow-part-change '+ref)
            changes.append(dict(ref=ref,previous=selected[ref],current=part))
        center,bounds=pad_center(f);anchor=point(f.GetPosition());offset=[center[i]-anchor[i] for i in range(2)]
        explicit=[pc.get('Placement Offset X'),pc.get('Placement Offset Y')]
        if any(x is not None for x in explicit):
            need(all(x is not None for x in explicit),'Both placement offsets required for '+ref)
            # Explicit offsets are footprint-local millimeters; bottom flips local X.
            dx,dy=map(float,explicit);dx=-dx if f.GetLayer()==pcbnew.B_Cu else dx;r=math.radians(f.GetOrientationDegrees())
            center=[anchor[0]+dx*math.cos(r)+dy*math.sin(r),anchor[1]-dx*math.sin(r)+dy*math.cos(r)]
            method='Explicit footprint-local Placement Offset X/Y metadata'
        else:
            method='Placement-side SMD copper pad bounding center; excludes TH pads and all text/graphics/models'
            if ref not in selected:need(math.dist(center,anchor)<.000003,'New part with offset center needs explicit Placement Offset X/Y: '+ref)
        angle=float(rawpos[ref]['Rot']);side=rawpos[ref]['Side'];rotation=(180-angle if side=='bottom' else angle)%360
        need(side==('bottom' if f.GetLayer()==pcbnew.B_Cu else 'top'),'Native placement side mismatch '+ref)
        oldrow=shipped.get(ref)
        assembly[ref]=dict(ref=ref,value=f.GetValue(),footprint=str(f.GetFPID().GetLibItemName()),**part,
            native_anchor_mm=anchor,smd_pad_center_mm=pad_center(f)[0],smd_pad_bounds_mm=bounds,
            center_mm=center,placement_method=method,native_angle_deg=angle,rotation_deg=rotation,side=side,
            prior_cpl=None if oldrow is None else oldrow,
            delta_from_prior_mm=None if oldrow is None else [center[0]-float(oldrow['Mid X']),-center[1]-float(oldrow['Mid Y'])],
            new_part=ref not in selected)
    need(bool(assembly),'Empty assembly population')
    need(set(args.allow_part_change)=={x['ref'] for x in changes},'Unused part-change allowance is an error')
    assembly,rotation_overrides=apply_supplier_rotations(assembly,profile)
    rotation_audit=dict(baseline_provenance=ROTATION_BASELINE,
        profile_path=str(profile_path) if profile_path else None,profile_sha256=profile_hash,
        overrides=rotation_overrides,only_cpl_rotation_changes=True)
    if profile_path:
        need(sha(profile_path)==profile_hash,'Supplier rotation profile changed during export')
        (out/'supplier-rotation-profile.json').write_bytes(profile_path.read_bytes())
    # One BOM row per reference keeps custom package identities explicit and avoids accidental quantity grouping.
    bom=[{'Comment':r['mpn'],'Designator':ref,'Footprint':r['footprint'],'LCSC Part #':r['lcsc']} for ref,r in assembly.items()]
    cpl=[{'Designator':ref,'Mid X':f"{r['center_mm'][0]:.6f}",'Mid Y':f"{-r['center_mm'][1]:.6f}",'Layer':r['side'],'Rotation':f"{r['rotation_deg']:.6f}"} for ref,r in assembly.items()]
    need({r['Designator'] for r in bom}=={r['Designator'] for r in cpl}==set(assembly),'BOM/CPL population mismatch')
    write_csv(out/'BOM-stratolink.csv',['Comment','Designator','Footprint','LCSC Part #'],bom)
    write_csv(out/'CPL-stratolink.csv',['Designator','Mid X','Mid Y','Layer','Rotation'],cpl)
    write_json(out/'assembly-audit.json',dict(assembly=assembly,exclusions=exclusions,explicit_part_changes=changes,
        supplier_rotation_profile=rotation_audit,
        removed_prior_selected=sorted(set(selected)-set(fps),key=natural),bom_and_cpl_refs_identical=True,
        previous_selected_source_sha256=sha(SELECTED),historical_pcb_sha256=sha(old_pcb),historical_pcb_commit=OLD_REV,historical_cpl_sha256=sha(OLD_CPL)))
    run('gerbers',[CLI,'pcb','export','gerbers','--layers','F.Cu,B.Cu,F.Mask,B.Mask,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,Edge.Cuts','--output',str(gerbers),str(pcb)])
    run('drill',[CLI,'pcb','export','drill','--format','excellon','--drill-origin','absolute','--excellon-units','mm','--excellon-separate-th','--generate-report','--report-path',str(native/'drill-report.txt'),'--output',str(gerbers),str(pcb)])
    mask=mask_proof(board,gerbers,stem);write_json(out/'no-mask-proof.json',mask)
    expected={stem+'-'+name+'.'+ext for name,ext in [('F_Cu','gtl'),('B_Cu','gbl'),('F_Paste','gtp'),('B_Paste','gbp'),('F_Mask','gts'),('B_Mask','gbs'),('F_Silkscreen','gto'),('B_Silkscreen','gbo'),('Edge_Cuts','gm1')]}
    expected|={stem+'-PTH.drl',stem+'-NPTH.drl',stem+'-job.gbrjob'}
    need(expected<={p.name for p in gerbers.iterdir()},'Missing required named manufacturing export')
    with zipfile.ZipFile(out/'fabrication-review.zip','w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(gerbers.iterdir()):z.write(p,p.name)
    readme=f'''# Manufacturing review package — not an order release\n\nSource: `{source}`\nPCB SHA-256: `{hashes[stem+'.kicad_pcb']}`\n\n{len(assembly)} assembly references; BOM and CPL populations match. Explicit manual/DNP exclusions are in `assembly-audit.json`. Original native KiCad position CSV and netlist are under `native/`.\n\nOrder/process instructions: **NO SOLDER MASK ON EITHER FACE, NO VIA TENTING.** Both mask Gerbers contain whole-board openings with edge overrun; stackup mask thickness is zero. Do not interpret empty mask data as a no-mask instruction. Board nominal thickness is {mask['board_thickness_mm']} mm. Confirm no-mask processing and finish in supplier CAM review. Preserve copper, paste, outline and separate plated/nonplated drills. Silkscreen exports retain source graphics. Any silk-over-exposed-copper advisories require supplier disposition; the baseline has four.\n\nCPL: millimeters, absolute board coordinates, Y negated, X not mirrored on the bottom. Placement centers are placement-side SMD copper-pad bounding centers (not footprint graphics/text); U2's corner anchor needs a substantial center correction. Retained package centers and bottom rotation `(180-native_angle) mod 360` reproduce the repository v1 production INPUT CPL, not a verified JLC post-CAM file. Supplier-model rotations require actual preview evidence for old and new parts alike. This export applies {len(rotation_overrides)} explicit supplier rotation overrides; base/override angles, exact orderables, reasons and evidence are recorded in `assembly-audit.json` and the manifest. When supplied, the exact profile is copied to `supplier-rotation-profile.json`. It changes only CPL angles, not native CAD, centers, sides, population or BOM identity. No rotation is guessed from a footprint filename. New non-centered packages require explicit local Placement Offset X/Y metadata.\n\nNo global paste reduction is performed. The F/B paste files are native source artwork, including any U7-specific change actually present in this candidate. Stencil thickness and any CAM-applied aperture reduction are supplier process decisions requiring the U5/U7 assembly review. Do not silently apply a second global reduction.\n\nThis generator does not qualify electrical operation, DRC exceptions, fabrication tolerances, new-part stock, supplier rotation libraries, or stencil process capability. It creates auditable files for review and performs no upload or order.\n'''
    (out/'README.md').write_text(readme)
    after={str(p.relative_to(source)):sha(p) for p in sourcefiles};need(after==hashes,'SOURCE FILES CHANGED during export')
    if profile_path:need(sha(profile_path)==profile_hash==sha(out/'supplier-rotation-profile.json'),'Supplier rotation profile changed during export')
    manifest=dict(status='review-only; not released to manufacture',source=str(source),source_files=hashes,
        native_kicad_version=pcbnew.GetBuildVersion(),commands=commands,assembly_count=len(assembly),
        exclusion_count=len(exclusions),no_duplicates=True,no_missing_population_refs=True,source_unchanged=True,
        historical_pcb_commit=OLD_REV,
        supplier_rotation_profile=rotation_audit,
        evidence_files={str(p):sha(p) for p in [SELECTED,OLD_CPL,old_pcb,OLD_HASHES,Path(__file__)]+([profile_path] if profile_path else [])},
        output_files={str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()})
    write_json(out/'manifest.json',manifest)
    print(json.dumps(dict(output=str(out),pcb_sha256=hashes[stem+'.kicad_pcb'],assembly_count=len(assembly),exclusions=exclusions,source_unchanged=True),indent=2))

if __name__=='__main__':main()
