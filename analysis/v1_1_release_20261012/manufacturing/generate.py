#!/usr/bin/env python3
"""Review-stage KiCad/JLC exports; never modify source CAD. Run with KiCad Python."""
import argparse, collections, csv, hashlib, json, math, re, shutil, subprocess, sys, xml.etree.ElementTree as ET, zipfile
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

def read_population_profile(path):
    def no_duplicates(pairs):
        result={}
        for key,value in pairs:
            need(key not in result,'Duplicate population profile key: '+key)
            result[key]=value
        return result
    profile=json.loads(path.read_text(),object_pairs_hook=no_duplicates)
    need(isinstance(profile,dict) and bool(profile),'Population profile must be a nonempty object')
    return profile

def apply_population(assembly, profile):
    """Omit explicitly identified parts after validating the complete design."""
    if profile is None:
        return assembly, []
    need(set(profile)=={'name','omit'} and isinstance(profile['name'],str) and bool(profile['name'].strip()),
         'Population profile requires name and omit')
    omit=profile['omit']
    need(isinstance(omit,dict) and bool(omit),'Population omit mapping must be nonempty')
    need(set(omit)<=set(assembly),'Population profile names absent/non-assembly references')
    records=[]
    for ref,entry in sorted(omit.items(),key=lambda pair:natural(pair[0])):
        need(isinstance(entry,dict) and set(entry)=={'mpn','lcsc','reason'},'Population identity/reason required for '+ref)
        need(isinstance(entry['reason'],str) and bool(entry['reason'].strip()),'Population reason missing for '+ref)
        need(all(entry[k]==assembly[ref][k] for k in ('mpn','lcsc')),'Population identity mismatch for '+ref)
        records.append(dict(ref=ref,reason='Assembly variant DNP: '+entry['reason'],mpn=entry['mpn'],lcsc=entry['lcsc']))
    result={ref:row for ref,row in assembly.items() if ref not in omit}
    need(bool(result),'Population profile removes all assembly parts')
    return result,records

def stencil_variant(source_pcb, destination_pcb, omitted):
    """Make an export-only copy with omitted parts' pad paste removed."""
    board=pcbnew.LoadBoard(str(source_pcb))
    fps=unique(board.GetFootprints(),lambda f:f.GetReference(),'Stencil copy')
    need(set(omitted)<=set(fps),'Missing stencil omission reference')
    changes=[]
    for ref in sorted(omitted,key=natural):
        f=fps[ref]
        # Reject custom paste graphics rather than silently leaving an aperture.
        need(not any(g.GetLayer() in {pcbnew.F_Paste,pcbnew.B_Paste} for g in f.GraphicalItems()),
             'DNP footprint has explicit paste graphics requiring review: '+ref)
        for pad in f.Pads():
            layers=pad.GetLayerSet();removed=[]
            for layer in (pcbnew.F_Paste,pcbnew.B_Paste):
                if layers.Contains(layer):
                    layers.RemoveLayer(layer);removed.append(board.GetLayerName(layer))
            if removed:
                pad.SetLayerSet(layers)
                changes.append(dict(ref=ref,pad=pad.GetNumber(),uuid=pad.m_Uuid.AsString(),removed_layers=removed))
    need(bool(changes),'Requested DNP stencil variant removes no paste')
    pcbnew.SaveBoard(str(destination_pcb),board)
    return dict(source_pcb_sha256=sha(source_pcb),stencil_pcb_sha256=sha(destination_pcb),
                omitted_refs=sorted(omitted,key=natural),pad_changes=changes,
                intent='Export-only paste-layer removal; complete native design remains unchanged')

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

def polygon_contains(point, contour):
    """Even/odd polygon containment; boundary counts as exposed aperture."""
    x,y=point;inside=False
    for a,b in zip(contour,contour[1:]+contour[:1]):
        dx,dy=b[0]-a[0],b[1]-a[1];den=dx*dx+dy*dy
        t=max(0,min(1,((x-a[0])*dx+(y-a[1])*dy)/den)) if den else 0
        if math.hypot(x-a[0]-t*dx,y-a[1]-t*dy)<1e-9:return True
        if (a[1]>y)!=(b[1]>y) and a[0]+(y-a[1])*dx/dy>x:inside=not inside
    return inside

def mask_region_contains(point,region):
    return bool(sum(polygon_contains(point,contour) for contour in region)%2)

def selective_mask_regions(text):
    """Strict parser for KiCad's minimum-web, polygonized mask export.

    Unknown flashes, arcs, polarity changes and transforms fail closed rather
    than allowing a full-face opening to evade a rectangle-only heuristic.
    """
    for token in ('%TF.FilePolarity,Negative*%','%FSLAX46Y46*%','%MOMM*%','%LPD*%'):
        need(token in text,'Unexpected selective mask convention: '+token)
    need('%LPC*%' not in text,'Selective-mask clear polarity needs boolean CAM review')
    regions=[];contours=None;contour=None
    for raw in text.splitlines():
        line=raw.strip()
        if not line or line.startswith('G04 ') or line.startswith('%TF.'):continue
        if line in {'%FSLAX46Y46*%','%MOMM*%','%LPD*%','G01*','M02*'}:continue
        if line=='G36*':
            need(contours is None,'Nested mask region');contours=[];contour=None;continue
        if line=='G37*':
            need(contours is not None and contour is not None and len(contour)>2,'Invalid mask region')
            contours.append(contour);regions.append(contours);contours=None;contour=None;continue
        m=re.fullmatch(r'X(-?\d+)Y(-?\d+)D0([12])\*',line)
        if m:
            need(contours is not None,'Non-region mask stroke')
            pt=(int(m[1])/1e6,-int(m[2])/1e6)
            if m[3]=='2':
                if contour:
                    need(len(contour)>2,'Invalid mask contour');contours.append(contour)
                contour=[pt]
            else:
                need(contour is not None,'Mask draw before move');contour.append(pt)
            continue
        need(False,'Unsupported selective-mask Gerber operation: '+line)
    need(contours is None and bool(regions),'Incomplete or empty selective mask regions')
    return regions

def green_finish_proof(board,gerbers,stem):
    """Check current green-mask/no-silkscreen intent against native exports.

    This gate complements the separate mask-aperture/DRC/CAM review; it is not
    a Gerber rasterizer or a supplier registration-tolerance qualification.
    """
    silk={pcbnew.F_SilkS,pcbnew.B_SilkS}
    need(not any(x.GetLayer() in silk for x in board.GetDrawings()),'Board still contains silkscreen artwork')
    for f in board.GetFootprints():
        need(not any(x.GetLayer() in silk for x in list(f.GraphicalItems())+list(f.GetFields())+[f.Reference(),f.Value()]),
             'Footprint still contains a silkscreen item: '+f.GetReference())
    job=json.loads((gerbers/(stem+'-job.gbrjob')).read_text())
    masks=[x for x in job['MaterialStackup'] if x['Type']=='SolderMask']
    need(len(masks)==2 and all(x.get('Thickness',0)>0 for x in masks),'Green mask requires two nonzero-thickness mask layers')
    need(all(str(x.get('Color','')).lower()=='green' for x in masks),'Both mask layers must be green')
    need(job['GeneralSpecs']['Finish']=='ENIG','Gerber job must specify ENIG')
    result=dict(finish='green solder mask / ENIG / no silkscreen',mask_stackup=masks,
                board_thickness_mm=job['GeneralSpecs']['BoardThickness'],native_silkscreen_items=0,
                limitation='Native/export intent gate; separate aperture geometry, DRC and supplier CAM review required')
    outline=pcbnew.SHAPE_POLY_SET();need(board.GetBoardPolygonOutlines(outline,False),'Invalid outline')
    outline_points=vertices(outline);need(bool(outline_points),'Empty outline')
    native_outline_points=[pcbnew.VECTOR2I(round(x*1e6),round(y*1e6)) for x,y in outline_points]
    # Check native artwork as well as the actual exported regions. An old
    # whole-board rectangle gains rounded corners during minimum-web plotting,
    # so checking only axis-aligned Gerber rectangle vertices is insufficient.
    native_masks=[]
    for g in board.GetDrawings():
        if g.GetLayer() in {pcbnew.F_Mask,pcbnew.B_Mask}:native_masks.append((g,g.GetLayer(),0))
    for f in board.GetFootprints():
        for g in f.GraphicalItems():
            if g.GetLayer() in {pcbnew.F_Mask,pcbnew.B_Mask}:native_masks.append((g,g.GetLayer(),0))
        for p in f.Pads():
            for layer in (pcbnew.F_Mask,pcbnew.B_Mask):
                if p.IsOnLayer(layer):native_masks.append((p,layer,p.GetSolderMaskExpansion(layer)))
    for item,layer,margin in native_masks:
        poly=pcbnew.SHAPE_POLY_SET();item.TransformShapeToPolygon(poly,layer,margin,1000,pcbnew.ERROR_OUTSIDE)
        need(not all(poly.Contains(p) for p in native_outline_points),'Native mask opening spans the complete board outline')
    mask_regions={}
    for face,ext in [('F','gts'),('B','gbs')]:
        path=gerbers/(stem+'-'+face+'_Mask.'+ext);s=path.read_text()
        regions=selective_mask_regions(s);mask_regions[face]=regions
        need(not any(all(mask_region_contains(p,region) for p in outline_points) for region in regions),
             'Exported mask opening spans the complete board outline on '+face)
        # Also reject split openings that collectively expose every outline
        # vertex; that does not establish the intended selective finish.
        need(not all(any(mask_region_contains(p,region) for region in regions) for p in outline_points),
             'Mask openings collectively expose the complete board perimeter on '+face)
        result[face]=dict(mask_file=path.name,sha256=sha(path),has_selective_openings=True,
                         polygon_regions=len(regions),full_board_opening_rejected=True)
    for face,ext in [('F','gto'),('B','gbo')]:
        path=gerbers/(stem+'-'+face+'_Silkscreen.'+ext);s=path.read_text()
        need(not re.search(r'D0[13]\*|G36\*',s),'Silkscreen Gerber contains drawn/flashed artwork: '+path.name)
    fps=unique(board.GetFootprints(),lambda f:f.GetReference(),'Finish check')
    solar=[]
    for ref in ('J1','J2'):
        for pad in fps[ref].Pads():
            checked_faces=[]
            for copper,mask in ((pcbnew.F_Cu,pcbnew.F_Mask),(pcbnew.B_Cu,pcbnew.B_Mask)):
                if pad.IsOnLayer(copper):
                    need(pad.IsOnLayer(mask),'Solar soldering pad lacks mask opening: '+ref+'.'+pad.GetNumber())
                    face='F' if copper==pcbnew.F_Cu else 'B';center=point(pad.GetPosition())
                    need(any(mask_region_contains(center,r) for r in mask_regions[face]),
                         'Solar soldering pad center is covered in actual mask Gerber: '+ref+'.'+pad.GetNumber()+' '+face)
                    checked_faces.append(face)
            solar.append(dict(ref=ref,pad=pad.GetNumber(),net=pad.GetNetname(),center_mm=point(pad.GetPosition()),
                              gerber_center_open_on_faces=checked_faces))
    result['solar_soldering_pads_open']=solar
    return result

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--candidate',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True);ap.add_argument('--stem',default='stratolink')
    ap.add_argument('--allow-part-change',action='append',default=[],metavar='REF',help='Explicitly permit a changed historical Supplier Part/MPN; still requires identical PCB/SCH fields')
    ap.add_argument('--supplier-rotation-profile',type=Path,
                    help='Reviewed JSON ref mapping with absolute rotation_deg plus evidence and reason; changes CPL rotation only')
    ap.add_argument('--population-profile',type=Path,
                    help='Explicit assembly-only omissions with exact MPN/LCSC identity and reason; native design stays populated')
    ap.add_argument('--finish',choices=['bare','green-mask-no-silk'],default='bare',
                    help='Explicit finish gate; bare is retained only for historical package reproduction')
    args=ap.parse_args();source=args.candidate.resolve();out=args.output.resolve();stem=args.stem
    need(source.is_dir(),'Missing candidate folder');need(not out.exists(),'Output must be a fresh folder')
    need(source!=out and source not in out.parents,'Output must be outside candidate source')
    pcb=source/(stem+'.kicad_pcb');sch=source/(stem+'.kicad_sch');need(pcb.is_file() and sch.is_file(),'PCB/SCH pair required')
    profile_path=args.supplier_rotation_profile.resolve() if args.supplier_rotation_profile else None
    profile_hash=sha(profile_path) if profile_path else None
    profile=read_rotation_profile(profile_path) if profile_path else {}
    population_path=args.population_profile.resolve() if args.population_profile else None
    population_hash=sha(population_path) if population_path else None
    population=read_population_profile(population_path) if population_path else None
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
    design_assembly=dict(assembly)
    assembly,population_exclusions=apply_population(assembly,population)
    exclusions+=population_exclusions
    if population_path:
        need(sha(population_path)==population_hash,'Population profile changed during export')
        (out/'population-profile.json').write_bytes(population_path.read_bytes())
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
    write_json(out/'assembly-audit.json',dict(assembly=assembly,design_assembly=design_assembly,
        population_profile=population,exclusions=exclusions,explicit_part_changes=changes,
        supplier_rotation_profile=rotation_audit,
        removed_prior_selected=sorted(set(selected)-set(fps),key=natural),bom_and_cpl_refs_identical=True,
        previous_selected_source_sha256=sha(SELECTED),historical_pcb_sha256=sha(old_pcb),historical_pcb_commit=OLD_REV,historical_cpl_sha256=sha(OLD_CPL)))
    run('gerbers',[CLI,'pcb','export','gerbers','--layers','F.Cu,B.Cu,F.Mask,B.Mask,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,Edge.Cuts','--output',str(gerbers),str(pcb)])
    if population:
        # Keep the full-design paste as evidence, but use the deliberate DNP
        # stencil in the fabrication ZIP supplied with this pilot BOM/CPL.
        fullpaste=native/'full-design-paste';fullpaste.mkdir()
        stencil=native/'stencil';stencil.mkdir();stencilpcb=stencil/(stem+'.kicad_pcb')
        for suffix in ('F_Paste.gtp','B_Paste.gbp'):
            shutil.copyfile(gerbers/(stem+'-'+suffix),fullpaste/(stem+'-'+suffix))
        stencil_proof=stencil_variant(pcb,stencilpcb,population['omit'])
        stencilplots=stencil/'gerbers';stencilplots.mkdir()
        run('pilot-stencil',[CLI,'pcb','export','gerbers','--layers','F.Paste,B.Paste','--output',str(stencilplots),str(stencilpcb)])
        stencil_proof['paste_files']={}
        for suffix in ('F_Paste.gtp','B_Paste.gbp'):
            name=stem+'-'+suffix
            shutil.copyfile(stencilplots/name,gerbers/name)
            stencil_proof['paste_files'][name]=dict(full_design_sha256=sha(fullpaste/name),pilot_sha256=sha(gerbers/name))
        write_json(out/'stencil-population-proof.json',stencil_proof)
    run('drill',[CLI,'pcb','export','drill','--format','excellon','--drill-origin','absolute','--excellon-units','mm','--excellon-separate-th','--generate-report','--report-path',str(native/'drill-report.txt'),'--output',str(gerbers),str(pcb)])
    mask=(green_finish_proof(board,gerbers,stem) if args.finish=='green-mask-no-silk' else mask_proof(board,gerbers,stem))
    write_json(out/('finish-proof.json' if args.finish=='green-mask-no-silk' else 'no-mask-proof.json'),mask)
    expected={stem+'-'+name+'.'+ext for name,ext in [('F_Cu','gtl'),('B_Cu','gbl'),('F_Paste','gtp'),('B_Paste','gbp'),('F_Mask','gts'),('B_Mask','gbs'),('F_Silkscreen','gto'),('B_Silkscreen','gbo'),('Edge_Cuts','gm1')]}
    expected|={stem+'-PTH.drl',stem+'-NPTH.drl',stem+'-job.gbrjob'}
    need(expected<={p.name for p in gerbers.iterdir()},'Missing required named manufacturing export')
    with zipfile.ZipFile(out/'fabrication-review.zip','w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(gerbers.iterdir()):z.write(p,p.name)
    finish_instructions = (
        'Order/process instructions: **GREEN SOLDER MASK BOTH SIDES, ENIG, NO SILKSCREEN.** '
        'Selective mask openings expose component and solar soldering lands. Ordinary-via tenting and local apertures '
        'must match the reviewed native design; do not substitute automatic aperture expansion. '
        'Both legend Gerbers are deliberately empty because the native board and footprint artwork contain no silkscreen. '
        'Confirm preservation of the supplied mask geometry in supplier CAM review.'
        if args.finish=='green-mask-no-silk' else
        'Historical bare-board instructions: **NO SOLDER MASK ON EITHER FACE, NO VIA TENTING.** '
        'Both mask Gerbers contain whole-board openings with edge overrun; stackup mask thickness is zero. '
        'Do not interpret empty mask data as a no-mask instruction. Silkscreen follows the historical source.'
    )
    readme=f'''# Manufacturing review package for engineering review\n\nSource: `{source}`\nPCB SHA-256: `{hashes[stem+'.kicad_pcb']}`\n\n{len(assembly)} assembly references; BOM and CPL populations match. Explicit manual/DNP exclusions are in `assembly-audit.json`. Original native KiCad position CSV and netlist are under `native/`.\n\n{finish_instructions} Board nominal thickness is {mask['board_thickness_mm']} mm. Preserve copper, paste, outline and separate plated/nonplated drills. Final supplier CAM acceptance remains pending.\n\nCPL: millimeters, absolute board coordinates, Y negated, X not mirrored on the bottom. Placement centers are placement-side SMD copper-pad bounding centers (not footprint graphics/text); U2's corner anchor needs a substantial center correction. Retained package centers and bottom rotation `(180-native_angle) mod 360` reproduce the repository v1 production INPUT CPL, not a verified JLC post-CAM file. Supplier-model rotations require actual preview evidence for old and new parts alike. This export applies {len(rotation_overrides)} explicit supplier rotation overrides; base/override angles, exact orderables, reasons and evidence are recorded in `assembly-audit.json` and the manifest. When supplied, the exact profile is copied to `supplier-rotation-profile.json`. It changes only CPL angles, not native CAD, centers, sides, population or BOM identity. No rotation is guessed from a footprint filename. New non-centered packages require explicit local Placement Offset X/Y metadata.\n\nNo global paste reduction is performed. The F/B paste geometry preserves the native design, including the U7-specific reduction, except for explicitly documented DNP pad omissions when a population profile is supplied. Stencil thickness and any CAM-applied aperture reduction are supplier process decisions requiring the U5/U7 assembly review and, for a future populated UV build, the AS7331 aperture review. Do not silently apply a second global reduction.\n\nThis generator does not qualify electrical operation, DRC exceptions, fabrication tolerances, new-part stock, supplier rotation libraries, or stencil process capability. It creates auditable files for review and performs no upload or order.\n'''
    (out/'README.md').write_text(readme)
    if population:
        with (out/'README.md').open('a') as f:
            f.write('\n## Assembly population: '+population['name']+'\n\n')
            f.write('The native PCB and schematic describe the complete populated circuit. This pilot BOM/CPL intentionally omits '+', '.join(population['omit'])+'. Exact part identities and reasons are in `population-profile.json`. Do not treat this pilot population as the complete design BOM. No UV measurements are available from a UV-DNP pilot.\n')
            f.write('Pilot F/B.Paste files deliberately omit the DNP pad apertures. The complete design paste remains under `native/full-design-paste/`; the export-only stencil PCB and its plots are under `native/stencil/`. `stencil-population-proof.json` records exact pad/layer omissions. Fabrication copper, mask, drills and outline still come directly from the complete canonical PCB. Never use this pilot stencil for a later fully populated UV build.\n')
    # CLI export can create editor defaults beside the disposable stencil PCB.
    # They are not fabrication inputs and .kicad_prl is ignored by Git. Remove
    # only these generated companions before freezing the portable package.
    for suffix in ('.kicad_prl', '.kicad_pro'):
        (native/'stencil'/(stem+suffix)).unlink(missing_ok=True)
    after={str(p.relative_to(source)):sha(p) for p in sourcefiles};need(after==hashes,'SOURCE FILES CHANGED during export')
    if profile_path:need(sha(profile_path)==profile_hash==sha(out/'supplier-rotation-profile.json'),'Supplier rotation profile changed during export')
    if population_path:need(sha(population_path)==population_hash==sha(out/'population-profile.json'),'Population profile changed during export')
    manifest=dict(status='review-only; not released to manufacture',source=str(source),source_files=hashes,finish=args.finish,
        native_kicad_version=pcbnew.GetBuildVersion(),commands=commands,assembly_count=len(assembly),
        design_assembly_count=len(design_assembly),population_profile=population,
        exclusion_count=len(exclusions),no_duplicates=True,no_missing_population_refs=True,source_unchanged=True,
        historical_pcb_commit=OLD_REV,
        supplier_rotation_profile=rotation_audit,
        evidence_files={str(p):sha(p) for p in [SELECTED,OLD_CPL,old_pcb,OLD_HASHES,Path(__file__)]+([profile_path] if profile_path else [])+([population_path] if population_path else [])},
        output_files={str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()})
    write_json(out/'manifest.json',manifest)
    print(json.dumps(dict(output=str(out),pcb_sha256=hashes[stem+'.kicad_pcb'],assembly_count=len(assembly),exclusions=exclusions,source_unchanged=True),indent=2))

if __name__=='__main__':main()
