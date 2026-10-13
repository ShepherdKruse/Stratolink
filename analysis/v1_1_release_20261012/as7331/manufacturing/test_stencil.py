#!/usr/bin/env python3
"""Independently prove the native U6-only stencil variant and Gerber artwork.

Run with KiCad Python. --candidate runs on a frozen temporary PCB snapshot;
--package verifies the actual release source/copy/full/pilot artifacts.
"""
from pathlib import Path
import argparse
import collections
import copy
import hashlib
import importlib.util
import json
import re
import subprocess
import tempfile
import uuid
import zipfile

import pcbnew
import wx

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
GENERATOR=ROOT/'analysis/v1_1_release_20261012/manufacturing/generate.py'
SCRATCH=Path('/Users/twarn/Repositories/ai-working/scratch/stratolink-release-20261012/as7331/manufacturing')
CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def nodes(obj, key): return [item for item in obj if isinstance(item,list) and item and item[0]==key]
def prop(obj, name): return next(item[2] for item in nodes(obj,'property') if item[1]==name)
def scalar(obj, name): return nodes(obj,name)[0][1]


def parse(text):
    stack=[]; roots=[]
    for token in re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+',text):
        if token=='(':
            item=[]
            (stack[-1] if stack else roots).append(item);stack.append(item)
        elif token==')':
            assert stack,'Unbalanced s-expression';stack.pop()
        else:
            assert stack,'Token outside s-expression'
            stack[-1].append(json.loads(token) if token.startswith('"') else token)
    assert not stack and len(roots)==1
    return roots[0]


def stable_object_order(node):
    """Native save may reorder UUID-tagged objects; geometry point order stays exact."""
    if not isinstance(node,list):return node
    children=[stable_object_order(item) for item in node]
    keyed=[item for item in children if isinstance(item,list) and nodes(item,'uuid')]
    others=[item for item in children if not (isinstance(item,list) and nodes(item,'uuid'))]
    return others+sorted(keyed,key=lambda item:(item[0],scalar(item,'uuid')))


def verify_native(source, pilot):
    original=parse(source.read_text()); exported=parse(pilot.read_text())
    expected=copy.deepcopy(original)
    u6=next(f for f in nodes(expected,'footprint') if prop(f,'Reference')=='U6')
    pads=nodes(u6,'pad');assert len(pads)==16
    assert {p[1] for p in pads}=={str(i) for i in range(1,17)}
    changes=[]
    for pad in pads:
        layers=nodes(pad,'layers')[0]
        removed=[layer for layer in layers[1:] if layer in {'F.Paste','B.Paste'}]
        assert removed==['F.Paste'], 'Each source U6 land must have exactly front paste'
        layers[:]=[layer for layer in layers if layer not in {'F.Paste','B.Paste'}]
        changes.append({'ref':'U6','pad':pad[1],'uuid':scalar(pad,'uuid'),'removed_layers':removed})
    # Entire parsed native PCB equality after the sole approved layer removal:
    # all other layers, pad sizes/paste reductions, routing, zones, graphics,
    # copper and source metadata remain exact, not merely visually similar.
    assert stable_object_order(expected)==stable_object_order(exported),'Stencil PCB changed something besides the 16 U6 F.Paste flags or UUID object order'
    return changes


def gerber_artwork(path):
    text=path.read_text()
    for token in ('%FSLAX46Y46*%','%MOMM*%','%LPD*%','%TF.FilePolarity,Positive*%'):
        assert token in text, 'Unexpected Gerber convention: '+token
    assert '%LPC*%' not in text, 'Clear polarity needs a boolean artwork review'
    assert not re.search(r'G0?[23]\*',text),'Arc interpolation needs explicit normalization'
    macros={m[1]:m[2] for m in re.finditer(r'%AM([^*]+)\*(.*?)\*%',text,re.S)}
    text=re.sub(r'%AM[^*]+\*.*?\*%','',text,flags=re.S)
    apertures={m[1]:m[2] for m in re.finditer(r'%ADD(\d+)([^%]+)%',text)}
    # Parse relevant drawing commands into semantic records. D-code numbers
    # are local labels, so compare their actual shape parameters and macros.
    selected=None; component=None; records=[]; paint_counts=collections.Counter()
    for raw in text.splitlines():
        line=raw.strip()
        if not line or line.startswith('G04 ') or line.startswith('%ADD'):
            continue
        match=re.fullmatch(r'D(\d+)\*',line)
        if match:
            assert match[1] in apertures,'Undefined aperture select'
            selected=apertures[match[1]]
            continue
        match=re.fullmatch(r'%TO.C,([^*]+)\*%',line)
        if match:
            component=match[1];continue
        if line=='%TD*%':component=None;continue
        if line.startswith('%TF.') or line in {'%FSLAX46Y46*%','%MOMM*%','%LPD*%','G01*','M02*'}:
            continue
        if line.startswith('X') or line in {'G36*','G37*','G75*'}:
            assert selected is not None,'Drawing without an aperture'
            macro_name=selected.split(',',1)[0]
            record=(component,selected,macros.get(macro_name),line)
            records.append(record)
            if line.endswith('D03*') or line=='G36*':paint_counts[component]+=1
            continue
        raise AssertionError('Unrecognized Gerber command: '+line)
    return records,paint_counts


def verify_paste(full, pilot):
    before,counts_before=gerber_artwork(full)
    after,counts_after=gerber_artwork(pilot)
    expected=[r for r in before if r[0]!='U6']
    assert after==expected,'A retained paste shape/position/command changed'
    assert counts_after.get('U6',0)==0
    assert not any(r[0]=='U6' for r in after)
    expected_count=16 if 'F_Paste' in full.name else 0
    assert counts_before.get('U6',0)==expected_count
    return {'full_U6_apertures':counts_before.get('U6',0),
            'pilot_U6_apertures':counts_after.get('U6',0),
            'retained_artwork_commands':len(after),
            'all_retained_paste_artwork_identical':True}


def verify_package(path):
    manifest=json.loads((path/'manifest.json').read_text())
    source=Path(manifest['source'])/'stratolink.kicad_pcb'
    assert sha(source)==manifest['source_files']['stratolink.kicad_pcb']
    pilot=path/'native/stencil/stratolink.kicad_pcb'
    changes=verify_native(source,pilot)
    proof=json.loads((path/'stencil-population-proof.json').read_text())
    assert proof['source_pcb_sha256']==sha(source)
    assert proof['stencil_pcb_sha256']==sha(pilot)
    assert proof['omitted_refs']==['U6']
    byuuid=lambda rows:{row['uuid']:row for row in rows}
    assert len(proof['pad_changes'])==16 and byuuid(proof['pad_changes'])==byuuid(changes)
    sides={}
    with zipfile.ZipFile(path/'fabrication-review.zip') as archive:
        for suffix in ('F_Paste.gtp','B_Paste.gbp'):
            name='stratolink-'+suffix
            full=path/'native/full-design-paste'/name
            final=path/'gerbers'/name
            native_pilot=path/'native/stencil/gerbers'/name
            assert final.read_bytes()==native_pilot.read_bytes()==archive.read(name)
            assert proof['paste_files'][name]=={'full_design_sha256':sha(full),'pilot_sha256':sha(final)}
            sides[name]=verify_paste(full,final)
    return {'package':str(path),'changed_U6_pad_paste_flags':len(changes),
            'whole_native_PCB_exact_except_U6_paste':True,
            'paste':sides,'pilot_ZIP_paste_bytes_verified':True}


def run_candidate(candidate):
    spec=importlib.util.spec_from_file_location('generator_stencil',GENERATOR)
    generator=importlib.util.module_from_spec(spec);spec.loader.exec_module(generator)
    SCRATCH.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='stencil-',dir=SCRATCH) as temp:
        temp=Path(temp);full=temp/'full';pilot=temp/'pilot';full.mkdir();pilot.mkdir()
        source=full/'stratolink.kicad_pcb';source.write_bytes((candidate/'stratolink.kicad_pcb').read_bytes())
        snapshot_original=sha(source)
        # Normalize only the temporary fixture, never the source candidate.
        # Final package mode requires its actual canonical source already saved.
        pcbnew.SaveBoard(str(source),pcbnew.LoadBoard(str(source)))
        initial=sha(source);dest=pilot/'stratolink.kicad_pcb'
        evidence=generator.stencil_variant(source,dest,{'U6'})
        assert sha(source)==initial
        changes=verify_native(source,dest)
        assert len(evidence['pad_changes'])==len(changes)==16
        for folder in (full,pilot):
            result=subprocess.run([CLI,'pcb','export','gerbers','--layers','F.Paste,B.Paste',
                       '--output',str(folder/'gerbers'),str(folder/'stratolink.kicad_pcb')],
                       capture_output=True,text=True)
            assert result.returncode==0,result.stdout+result.stderr
        sides={suffix:verify_paste(full/'gerbers'/('stratolink-'+suffix),pilot/'gerbers'/('stratolink-'+suffix))
               for suffix in ('F_Paste.gtp','B_Paste.gbp')}
        negative=[]
        for name,pcb,omit in [('missing_reference',source,{'U999'}),
                              ('empty_omission',source,set()),
                              ('already_suppressed_noop',dest,{'U6'})]:
            output=temp/(name+'.kicad_pcb')
            try:generator.stencil_variant(pcb,output,omit)
            except ValueError:negative.append(name)
            else:raise AssertionError('Invalid stencil request accepted: '+name)
            assert not output.exists()
        board=pcbnew.LoadBoard(str(source));fp=next(f for f in board.GetFootprints() if f.GetReference()=='U6')
        graphic=pcbnew.PCB_SHAPE(fp);graphic.SetShape(pcbnew.SHAPE_T_SEGMENT)
        graphic.SetLayer(pcbnew.F_Paste);graphic.SetStart(pcbnew.VECTOR2I(1000000,1000000))
        graphic.SetEnd(pcbnew.VECTOR2I(2000000,1000000));graphic.SetWidth(100000);fp.Add(graphic)
        bad=temp/'custom-paste.kicad_pcb';pcbnew.SaveBoard(str(bad),board)
        output=temp/'custom-paste-output.kicad_pcb'
        try:generator.stencil_variant(bad,output,{'U6'})
        except ValueError:negative.append('explicit_footprint_paste_graphic')
        else:raise AssertionError('Custom paste graphic was silently retained')
        assert not output.exists() and sha(source)==initial
        return {'candidate_snapshot_sha256':snapshot_original,'normalized_fixture_sha256':initial,
                'changed_U6_pad_paste_flags':16,
                'whole_native_PCB_exact_except_U6_paste':True,'paste':sides,
                'negative_cases_rejected':negative,'source_hash_preserved':True}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--candidate',type=Path);group.add_argument('--package',type=Path)
    args=parser.parse_args();app=wx.App(False)
    report=verify_package(args.package.resolve()) if args.package else run_candidate(args.candidate.resolve())
    report['generator_sha256']=sha(GENERATOR)
    (HERE/('stencil-package-verification.json' if args.package else 'stencil-test.json')).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
