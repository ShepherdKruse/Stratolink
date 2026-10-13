#!/usr/bin/env python3
"""Build a bare-board mask candidate from a Git-pinned baseline, scratch only."""
from pathlib import Path
import hashlib,json,subprocess,sys,uuid

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
BASE='41027a4'
OUT=Path.home()/'Repositories/ai-working/scratch/stratolink-bare-finish-20261012/mask'
sys.path.insert(0,str(ROOT/'analysis/v1_1_ground_20261012'))
from build_candidate import spans,replace,cad

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(name):return subprocess.check_output(['git','show',BASE+':hardware/pcb/'+name],cwd=ROOT)

def make_candidate():
    canonical=ROOT/'hardware/pcb'
    names=['stratolink.kicad_pcb','stratolink.kicad_sch','stratolink.kicad_pro','fp-lib-table','sym-lib-table']
    libnames=subprocess.check_output(['git','ls-tree','-r','--name-only',BASE+':hardware/pcb/lib'],cwd=ROOT,text=True).splitlines()
    allnames=names+['lib/'+n for n in libnames]
    protected={n:digest(canonical/n) for n in allnames}
    for directory in [OUT/'baseline',OUT/'candidate']:
        directory.mkdir(parents=True,exist_ok=True)
        for n in allnames:
            p=directory/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(git(n))
    p=OUT/'candidate/stratolink.kicad_pcb';text=p.read_text()
    initial=cad.parse(text)
    old_setup=next(x for x in cad.nodes(initial,'setup'))
    patches=[]
    for start,end,depth in spans(text):
        if depth!=1:continue
        node=cad.parse(text[start:end])
        if node[0]!='setup':continue
        block=text[start:end]
        assert block.count('(thickness 0.01)')==2
        assert block.count('(thickness 0.31)')==1
        block=block.replace('(thickness 0.01)','(thickness 0)')
        block=block.replace('(thickness 0.31)','(thickness 0.33)')
        tent='(tenting\n\t\t\t(front yes)\n\t\t\t(back yes)\n\t\t)'
        assert block.count(tent)==1
        block=block.replace(tent,'(tenting\n\t\t\t(front no)\n\t\t\t(back no)\n\t\t)')
        patches.append((start,end,block))
    assert len(patches)==1
    text=replace(text,patches)
    additions=[]
    for layer in ['F.Mask','B.Mask']:
        uid=str(uuid.uuid5(uuid.NAMESPACE_URL,'stratolink-v1.1-no-solder-mask-20261012/'+layer))
        additions.append(dict(uuid=uid,layer=layer,start_mm=[52,28],end_mm=[78,88],filled=True,locked=True,stroke_width_mm=0))
        graphic='\t(gr_rect\n\t\t(start 52 28)\n\t\t(end 78 88)\n\t\t(stroke\n\t\t\t(width 0)\n\t\t\t(type default)\n\t\t)\n\t\t(fill yes)\n\t\t(locked yes)\n\t\t(layer "'+layer+'")\n\t\t(uuid "'+uid+'")\n\t)\n'
        end=text.rfind(')');text=text[:end]+graphic+text[end:]
    p.write_text(text)
    current=cad.parse(text)
    # Raw S-expression equality proves every existing object outside setup is preserved.
    def exclude(tree,keys):return [x for x in tree if not(isinstance(x,list) and x[0] in keys)]
    rect_ids={v['uuid'] for v in additions}
    restored=[x for x in current if not(isinstance(x,list) and x[0]=='gr_rect' and cad.scalar(x,'uuid') in rect_ids)]
    assert exclude(initial,{'setup'})==exclude(restored,{'setup'})
    for n,h in protected.items():assert digest(canonical/n)==h,('Canonical changed while building',n)
    manifest=dict(baseline_commit=subprocess.check_output(['git','rev-parse',BASE],cwd=ROOT,text=True).strip(),
      candidate=str(OUT/'candidate'),baseline=str(OUT/'baseline'),
      added_mask_rectangles=additions,setup_changes=dict(mask_thickness_mm=[.01,0],core_thickness_mm=[.31,.33],via_tenting_front=['yes','no'],via_tenting_back=['yes','no']),
      unchanged_nominal_board_thickness_mm=.4,unchanged_copper_thickness_each_mm=.035,
      stackup_note='Metadata selection to retain nominal 0.40 mm after removing two nominal 0.01 mm mask films; not a measurement of flown material or a fabrication stackup guarantee.',
      files={n:digest(OUT/'candidate'/n) for n in allnames},baseline_hashes={n:digest(OUT/'baseline'/n) for n in allnames},
      scope=dict(existing_copper_drills_paste_silkscreen_footprints_zones_preserved_exactly=True,schematic_and_project_and_libraries_preserved_exactly=True))
    (HERE/'candidate.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({k:v for k,v in manifest.items() if k not in ['files','baseline_hashes']},indent=2))
    print('PCB SHA256',digest(p))

if __name__=='__main__':make_candidate()
