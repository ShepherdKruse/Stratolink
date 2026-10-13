#!/usr/bin/env python3
"""Adversarial tests of the real manufacturing population parser/filter.

Run with KiCad's bundled Python. --package additionally verifies an exported
AS7331 pilot package and all source/output hashes; requires approved identity.
"""
from pathlib import Path
import argparse
import copy
import csv
import hashlib
import importlib.util
import json
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
GENERATOR = ROOT/'analysis/v1_1_release_20261012/manufacturing/generate.py'
SCRATCH = Path('/Users/twarn/Repositories/ai-working/scratch/stratolink-release-20261012/as7331/manufacturing')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_generator():
    spec = importlib.util.spec_from_file_location('manufacturing_generator', GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_unit_tests(generator):
    # Synthetic part identities exercise this generic filter, not procurement.
    design = {
        'U6': {'ref':'U6','mpn':'AS7331-AQFM','lcsc':'C20482877','footprint':'OLGA16',
               'center_mm':[69.0,41.0],'side':'top','rotation_deg':90},
        'R27':{'ref':'R27','mpn':'REFERENCE-RESISTOR','lcsc':'C123456','footprint':'R0805',
               'center_mm':[66.0,42.0],'side':'top','rotation_deg':0},
        'C23':{'ref':'C23','mpn':'BYPASS-CAPACITOR','lcsc':'C1525','footprint':'C0402',
               'center_mm':[67.0,42.0],'side':'top','rotation_deg':180},
    }
    profile = {'name':'AS7331 pilot, U6 absent', 'omit':{
        'U6':{'mpn':'AS7331-AQFM','lcsc':'C20482877','reason':'Pilot U6 stock unavailable'}}}
    frozen_design=copy.deepcopy(design)
    frozen_profile=copy.deepcopy(profile)
    full, records = generator.apply_population(design, None)
    assert full == design and records == []
    pilot, records = generator.apply_population(design, profile)
    assert set(pilot) == {'R27','C23'} and len(records)==1 and records[0]['ref']=='U6'
    assert pilot == {ref:row for ref,row in design.items() if ref != 'U6'}
    assert design == frozen_design and profile == frozen_profile
    passed = ['no_profile_preserves_full_population', 'omit_U6_preserves_every_other_row',
              'inputs_unchanged']
    cases = []
    def variant(name, change):
        modified=copy.deepcopy(profile); change(modified); cases.append((name, modified, design))
    variant('wrong_MPN',lambda p:p['omit']['U6'].__setitem__('mpn','AS7331-AQFT'))
    variant('wrong_LCSC',lambda p:p['omit']['U6'].__setitem__('lcsc','C999999'))
    variant('missing_identity',lambda p:p['omit']['U6'].pop('mpn'))
    variant('numeric_identity',lambda p:p['omit']['U6'].__setitem__('lcsc',20482877))
    variant('blank_reason',lambda p:p['omit']['U6'].__setitem__('reason',' '))
    variant('missing_reason',lambda p:p['omit']['U6'].pop('reason'))
    variant('extra_identity_field',lambda p:p['omit']['U6'].__setitem__('quantity',0))
    variant('blank_name',lambda p:p.__setitem__('name',' '))
    variant('non_string_name',lambda p:p.__setitem__('name',False))
    variant('empty_omit',lambda p:p.__setitem__('omit',{}))
    variant('array_omit',lambda p:p.__setitem__('omit',['U6']))
    variant('extra_top_level_field',lambda p:p.__setitem__('override',True))
    variant('unknown_reference',lambda p:p['omit'].__setitem__('U66',p['omit'].pop('U6')))
    variant('lowercase_reference',lambda p:p['omit'].__setitem__('u6',p['omit'].pop('U6')))
    variant('whitespace_reference',lambda p:p['omit'].__setitem__(' U6 ',p['omit'].pop('U6')))
    stale=copy.deepcopy(design); stale['U6'].update(mpn='LTR-390UV-01',lcsc='C276079')
    cases.append(('stale_profile_for_legacy_U6', profile, stale))
    cases.append(('stale_profile_U6_removed_or_native_DNP', profile, {r:v for r,v in design.items() if r!='U6'}))
    remove_all={'name':'bad all-DNP','omit':{ref:{'mpn':row['mpn'],'lcsc':row['lcsc'],'reason':'test'} for ref,row in design.items()}}
    cases.append(('remove_every_assembly_reference',remove_all,design))
    for name,candidate,assembly in cases:
        a=copy.deepcopy(assembly); p=copy.deepcopy(candidate)
        try:
            generator.apply_population(assembly,candidate)
        except ValueError:
            passed.append(name)
        else:
            raise AssertionError('Invalid population accepted: '+name)
        assert a==assembly and p==candidate, 'Rejected profile mutated inputs: '+name

    rejected_json = {
        'explicit_null_profile':'null', 'empty_object_profile':'{}',
        'array_profile':'[]', 'boolean_profile':'false', 'string_profile':'"profile"',
        'malformed_json':'{"name":',
        'duplicate_top_name':'{"name":"first","name":"second","omit":{}}',
        'duplicate_top_omit':'{"name":"pilot","omit":{},"omit":{"U6":{"mpn":"AS7331-AQFM","lcsc":"C20482877","reason":"omit"}}}',
        'duplicate_U6_reference':'{"name":"pilot","omit":{"U6":{"mpn":"WRONG","lcsc":"C9","reason":"bad"},"U6":{"mpn":"AS7331-AQFM","lcsc":"C20482877","reason":"omit"}}}',
        'duplicate_MPN':'{"name":"pilot","omit":{"U6":{"mpn":"WRONG","mpn":"AS7331-AQFM","lcsc":"C20482877","reason":"omit"}}}',
        'duplicate_LCSC':'{"name":"pilot","omit":{"U6":{"mpn":"AS7331-AQFM","lcsc":"C9","lcsc":"C20482877","reason":"omit"}}}',
        'duplicate_reason':'{"name":"pilot","omit":{"U6":{"mpn":"AS7331-AQFM","lcsc":"C20482877","reason":"","reason":"omit"}}}',
    }
    SCRATCH.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='profiles-',dir=SCRATCH) as temp:
        path=Path(temp)/'profile.json'
        for name,raw in rejected_json.items():
            path.write_text(raw); before=sha(path)
            try:
                generator.read_population_profile(path)
            except ValueError:
                passed.append(name)
            else:
                raise AssertionError('Invalid JSON profile accepted: '+name)
            assert sha(path)==before
        path.write_text(json.dumps(profile)); before=sha(path)
        loaded=generator.read_population_profile(path)
        assert loaded==profile and sha(path)==before
        loaded_result,_=generator.apply_population(design,loaded)
        assert loaded_result==pilot
        passed.append('valid_profile_round_trip_and_hash_preserved')
    return passed


def verify_package(path, expected_mpn, expected_lcsc):
    path=path.resolve()
    audit=json.loads((path/'assembly-audit.json').read_text())
    manifest=json.loads((path/'manifest.json').read_text())
    design=audit['design_assembly']; pilot=audit['assembly']; profile=audit['population_profile']
    assert set(profile['omit'])=={'U6'}, 'This release only authorizes U6 omission'
    assert {'R27','C23'} <= set(pilot), 'AS7331 reference resistor and added bypass must remain fitted'
    assert design['U6']['mpn']==expected_mpn and design['U6']['lcsc']==expected_lcsc
    assert profile['omit']['U6']['mpn']==expected_mpn and profile['omit']['U6']['lcsc']==expected_lcsc
    assert pilot=={ref:row for ref,row in design.items() if ref!='U6'}
    population_records=[r for r in audit['exclusions'] if r['reason'].startswith('Assembly variant DNP: ')]
    assert len(population_records)==1 and population_records[0]['ref']=='U6'
    assert manifest['assembly_count']==len(pilot)
    assert manifest['design_assembly_count']==len(design)==len(pilot)+1
    assert manifest['population_profile']==profile
    assert json.loads((path/'population-profile.json').read_text())==profile
    bom=list(csv.DictReader((path/'BOM-stratolink.csv').open()))
    cpl=list(csv.DictReader((path/'CPL-stratolink.csv').open()))
    assert len(bom)==len(cpl)==len(pilot)
    assert {r['Designator'] for r in bom}=={r['Designator'] for r in cpl}==set(pilot)
    for row in bom:
        native=design[row['Designator']]
        assert row=={'Comment':native['mpn'],'Designator':native['ref'],
                     'Footprint':native['footprint'],'LCSC Part #':native['lcsc']}
    for row in cpl:
        native=design[row['Designator']]
        assert row=={'Designator':native['ref'],'Mid X':f"{native['center_mm'][0]:.6f}",
                     'Mid Y':f"{-native['center_mm'][1]:.6f}",'Layer':native['side'],
                     'Rotation':f"{native['rotation_deg']:.6f}"}
    for relative,digest in manifest['output_files'].items():
        assert sha(path/relative)==digest, 'Output hash mismatch: '+relative
    actual={str(p.relative_to(path)) for p in path.rglob('*') if p.is_file() and p.relative_to(path)!=Path('manifest.json')}
    assert actual==set(manifest['output_files']), 'Manifest omitted or invented an output'
    source=Path(manifest['source'])
    for relative,digest in manifest['source_files'].items():
        assert sha(source/relative)==digest, 'Source hash mismatch: '+relative
    for name,digest in manifest['evidence_files'].items():
        assert sha(Path(name))==digest, 'Evidence hash mismatch: '+name
    # An exact copy is guaranteed by the original profile's manifest hash,
    # not merely equivalent parsed JSON with changed contents/whitespace.
    originals=[name for name in manifest['evidence_files'] if sha(Path(name))==sha(path/'population-profile.json')]
    assert originals, 'No source population profile with the copied byte hash'
    from test_stencil import verify_package as verify_stencil_package
    stencil=verify_stencil_package(path)
    return {'package':str(path),'stencil':stencil,'assembly_count':len(pilot),'design_assembly_count':len(design),
            'only_omitted_reference':'U6','approved_mpn':expected_mpn,'approved_lcsc':expected_lcsc,
            'all_retained_assembly_BOM_CPL_fields_match':True,
            'source_hash_count':len(manifest['source_files']),
            'output_hash_count':len(manifest['output_files']),
            'all_source_output_evidence_hashes_valid':True,'population_profile_byte_copy_valid':True}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package',type=Path)
    parser.add_argument('--expected-mpn')
    parser.add_argument('--expected-lcsc')
    args=parser.parse_args()
    if args.package and not (args.expected_mpn and args.expected_lcsc):
        parser.error('--package requires --expected-mpn and --expected-lcsc')
    tests=run_unit_tests(load_generator())
    report={'generator_sha256':sha(GENERATOR),'passed_case_count':len(tests),'passed_cases':tests,
            'package':verify_package(args.package,args.expected_mpn,args.expected_lcsc) if args.package else None}
    destination=HERE/('package-verification.json' if args.package else 'population-test.json')
    destination.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    main()
