#!/usr/bin/env python3
"""Compare project policy and exact rule scope to captured release baseline."""
from pathlib import Path
import argparse,json,sys,copy
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'analysis/v1_1_solar_attachments_20261012/review'))
import check_solar_attachments as sx

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--candidate',type=Path,required=True);ap.add_argument('--allow-green-finish',action='store_true');a=ap.parse_args()
    old=json.loads((HERE/'baseline-project.json').read_text());new=json.loads((a.candidate/'stratolink.kicad_pro').read_text())
    desired=copy.deepcopy(old);removed=[x for x in desired['erc']['erc_exclusions'] if 'LTR-390UV' in x[1]]
    desired['erc']['erc_exclusions']=[x for x in desired['erc']['erc_exclusions'] if 'LTR-390UV' not in x[1]]
    assert len(removed)==1 and len(desired['erc']['erc_exclusions'])==2
    finish_changes={}
    if a.allow_green_finish:
        settings=desired['board']['design_settings']
        finish_changes={'solder_mask_bridge':'error','solder_mask_to_copper_clearance':.09}
        settings['rule_severities']['solder_mask_bridge']='error'
        settings['rules']['solder_mask_to_copper_clearance']=.09
    assert desired==new,'Project changed beyond exact old LTR390 exclusion removal and explicitly selected mask settings'
    def rules(text):return {n[1]:n for n in sx.nodes(sx.parse('(root '+text+')'),'rule')}
    before=rules((HERE/'baseline-rules.txt').read_text());after=rules((a.candidate/'stratolink.kicad_dru').read_text())
    oldname='U7 escape SCL to U6 SDA pad 6 - 0.12 mm';newname='U6 AS7331 fine pitch lands'
    assert before.keys()-after.keys()=={oldname};assert after.keys()-before.keys()=={newname}
    for name in before.keys()&after.keys():assert before[name]==after[name],('Retained rule changed',name)
    expected=['rule',newname,['condition',"A.Type == 'Pad' && B.Type == 'Pad' && A.memberOfFootprint('U6') && B.memberOfFootprint('U6')"],['constraint','clearance',['min','0.15mm']]]
    assert after[newname]==expected,after[newname]
    result=dict(status='PASS',remaining_erc_exclusions=new['erc']['erc_exclusions'],removed_erc_exclusion=removed[0],green_finish_project_changes=finish_changes,all_other_project_fields_identical=True,retained_rules=sorted(before.keys()&after.keys()),removed_rule=before[oldname],added_rule=after[newname])
    (HERE/'project-rule-scope.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':'PASS','retained_rules':len(result['retained_rules']),'erc_exclusions':2},indent=2))
if __name__=='__main__':main()
