#!/usr/bin/env python3
"""Compare current hardware power connectivity against the last v1 CAD commit."""
from pathlib import Path
import hashlib,json,subprocess,sys
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'analysis/v1_1_solar_attachments_20261012/review'));import check_solar_attachments as a

def rows(text):
 b=a.parse(text);result={}
 for f in a.nodes(b,'footprint'):
  ref=a.prop(f,'Reference');pins={}
  for p in a.nodes(f,'pad'):
   net=a.nodes(p,'net');pins.setdefault(p[1],set()).add(net[0][-1] if net else None)
  result[ref]=dict(value=a.prop(f,'Value'),pads={k:sorted(v,key=str) for k,v in pins.items()})
 return result

def main():
 old=subprocess.check_output(['git','show','9bdd19e:hardware/pcb/stratolink.kicad_pcb'],cwd=ROOT,text=True);new=(ROOT/'hardware/pcb/stratolink.kicad_pcb').read_text();o,n=rows(old),rows(new)
 refs=['U1','U2','U3','U4','U6','U7','C5','FB1','L1','L2']+[f'R{i}' for i in list(range(1,17))+[18,19,21,22,23]]+[f'C{i}' for i in [1,2,3,4,6,7,8,9,10,11,12,14,15,16,17,19,20,21]]
 differences=[]
 for ref in refs:
  before,after=o[ref]['pads'],n[ref]['pads']
  if ref=='U2':
   for pin in ['31','32']:before.pop(pin);after.pop(pin)
  assert before==after,(ref,before,after)
  assert o[ref]['value']==n[ref]['value'],ref
 result=dict(v1_revision=subprocess.check_output(['git','rev-parse','9bdd19e'],cwd=ROOT,text=True).strip(),current_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),current_pcb_sha256=hashlib.sha256(new.encode()).hexdigest(),references_compared=refs,pad_net_and_value_differences=[],U2_excluded_pins=['31','32'],reason_for_excluded_pins='Intentional microphone removal; these pins are now NC.',interpretation='All compared power, harvester, storage, GNSS and remaining peripheral pad-net assignments and values are identical to the last v1 CAD commit. This preserves the proven topology but does not close pre-existing rating or component-identity issues.')
 (HERE/'v1-topology-comparison.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
