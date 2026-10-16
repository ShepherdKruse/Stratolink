from pathlib import Path
import argparse,hashlib,json,sys
import pcbnew,wx
p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--pcb',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
sys.path.insert(0,str(a.repo/'analysis/v1_1_solar_attachments_20261012/materials'));from extract_native import contours
raw=a.pcb.read_bytes();app=wx.App(False);b=pcbnew.LoadBoard(str(a.pcb));r=[]
for item in b.GetDrawings():
 if isinstance(item,pcbnew.PCB_TEXT)and item.GetLayer()in[pcbnew.F_Mask,pcbnew.B_Mask]:
  poly=pcbnew.SHAPE_POLY_SET();item.TransformTextToPolySet(poly,0,2000,pcbnew.ERROR_OUTSIDE)
  r.append({'text':item.GetText(),'uuid':item.m_Uuid.AsString(),'position':[item.GetPosition().x/1e6,item.GetPosition().y/1e6],'layer':item.GetLayerName(),'polygons':contours(poly)})
assert raw==a.pcb.read_bytes();a.output.write_text(json.dumps({'pcb_sha256':hashlib.sha256(raw).hexdigest(),'items':r},indent=2)+'\n')
