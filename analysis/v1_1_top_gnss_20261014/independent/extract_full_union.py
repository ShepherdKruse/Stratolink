#!/usr/bin/env python3
"""Read-only native full-copper export with an explicit destination."""
from pathlib import Path
import argparse,importlib.util,json
import wx
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--repo',type=Path,required=True);p.add_argument('--pcb',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
a=p.parse_args();assert not a.output.exists(),a.output
s=importlib.util.spec_from_file_location('native_copper_export',a.repo/'analysis/v1_1_peer_review_20261014/fabrication/extract_geometry.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
app=wx.App(False);result=m.extract(a.pcb)
a.output.write_text(json.dumps(result,separators=(',',':'))+'\n')
print(result['sha256'])
