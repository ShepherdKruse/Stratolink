#!/usr/bin/env python3
"""Native extraction or Shapely screen wrapper. Run each mode in its own runtime."""
from pathlib import Path
import importlib.util,argparse,json
p=argparse.ArgumentParser();p.add_argument('mode',choices=['extract','screen']);p.add_argument('--repo',type=Path,required=True);p.add_argument('--pcb',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();folder=a.repo/'analysis/v1_1_peer_review_20261014/fabrication'
file=folder/('extract_geometry.py' if a.mode=='extract' else 'screen_geometry.py');spec=importlib.util.spec_from_file_location('screen_helper',file);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
if a.mode=='extract':
 import wx
 app=wx.App(False);r=m.extract(a.pcb);(a.output/'final-geometry.json').write_text(json.dumps(r,separators=(',',':'))+'\n');print(r['sha256'])
else:
 m.HERE=a.output;r=m.screen('final');(a.output/'final-screen.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({l:{k:len(v) for k,v in q.items() if isinstance(v,list)} for l,q in r['layers'].items()},indent=2))
