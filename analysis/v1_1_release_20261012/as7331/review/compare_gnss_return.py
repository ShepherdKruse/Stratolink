#!/usr/bin/env python3
"""Compare source-hashed native GNSS back-ground samples; not an RF field solver."""
from pathlib import Path
import base64,json
HERE=Path(__file__).resolve().parent

def main():
    before=json.loads((HERE/'baseline-gnss-return.json').read_text());after=json.loads((HERE/'candidate-gnss-return.json').read_text());assert before['grid']==after['grid'];g=before['grid']
    old=base64.b64decode(before['samples_base64']);new=base64.b64decode(after['samples_base64']);assert len(old)==len(new)
    def points(indices):return [[round(g['xmin']+(i%g['nx']+.5)*g['step'],6),round(g['ymin']+(i//g['nx']+.5)*g['step'],6)] for i in indices]
    lost=[i for i,(a,b) in enumerate(zip(old,new)) if a and not b];gained=[i for i,(a,b) in enumerate(zip(old,new)) if b and not a]
    cl=[]
    for a,b in zip(before['vertical_feed_centerline'],after['vertical_feed_centerline']):
        assert a[:2]==b[:2]
        if a[2]!=b[2]:cl.append(dict(position=a[:2],before=a[2],after=b[2]))
    r=dict(status='IDENTICAL_SAMPLED_GROUND' if not lost and not gained else 'CHANGED_SAMPLED_GROUND_REVIEW_REQUIRED',baseline_sha256=before['pcb_sha256'],candidate_sha256=after['pcb_sha256'],grid=g,samples=len(old),lost_count=len(lost),gained_count=len(gained),lost_points_mm=points(lost),gained_points_mm=points(gained),feed_centerline_changes=cl,limitations=['50um samples can miss smaller slivers; actual conductor geometry review supplements this.','Filled back GND zones only. Ground pads/traces may additionally carry return.','Does not establish RF impedance, antenna matching, or equivalence after adding green mask.'])
    (HERE/'gnss-return-comparison.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k not in ['lost_points_mm','gained_points_mm']},indent=2))
if __name__=='__main__':main()
