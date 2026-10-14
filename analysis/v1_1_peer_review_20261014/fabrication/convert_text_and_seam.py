#!/usr/bin/env python3
"""Preserve exact native text outlines on copper and editable sources on F.Fab."""
from pathlib import Path
import pcbnew,wx,json,uuid,sys,hashlib
app=wx.App(False);p=Path(sys.argv[1]).resolve();assert '/ai-working/scratch/' in str(p)
b=pcbnew.LoadBoard(str(p));source=hashlib.sha256(p.read_bytes()).hexdigest();ledger=[];ids={}
def stable(n):return str(uuid.uuid5(uuid.NAMESPACE_URL,'stratolink-text-copper-20261014/'+n))
def identify(item,n):u=stable(n);ids[item.m_Uuid.AsString()]=u;return u
texts={'c73a59a2-31c0-4945-990c-2704a1c497e5','5e350471-61a4-4077-9186-34d0a4e791c3'}
fillets=json.loads((p.parent/'fillet-changes.json').read_text())['changes']
for text in list(b.GetDrawings()):
 if text.m_Uuid.AsString() not in texts:continue
 key=text.m_Uuid.AsString();poly=pcbnew.SHAPE_POLY_SET();text.TransformTextToPolySet(poly,0,1000,pcbnew.ERROR_OUTSIDE);poly.Simplify()
 group=pcbnew.PCB_GROUP(b);group.SetName('Copper label: '+text.GetText());gu=identify(group,'group/'+key);b.Add(group)
 glyphs=[]
 # Native fracture retains holes as contour bridges for KiCad's filled graphic format.
 poly.Fracture()
 for i in range(poly.OutlineCount()):
  single=pcbnew.SHAPE_POLY_SET();single.AddOutline(poly.Outline(i))
  shape=pcbnew.PCB_SHAPE(b);shape.SetShape(pcbnew.SHAPE_T_POLY);shape.SetLayer(pcbnew.F_Cu);shape.SetWidth(0);shape.SetFilled(True);shape.SetPolyShape(single)
  u=identify(shape,key+'/'+str(i));b.Add(shape);group.AddItem(shape);glyphs.append(u)
 text.SetLayer(pcbnew.F_Fab);group.AddItem(text)
 patchids=[]
 for q in fillets:
  if q.get('net')=='ART:'+key:
   for g in b.GetDrawings():
    if g.m_Uuid.AsString()==q['uuid']:group.AddItem(g);patchids.append(q['uuid'])
 ledger.append(dict(action='native_text_to_copper_outlines',text_uuid=key,text=text.GetText(),source_layer_before='F.Cu',source_layer_after='F.Fab',glyph_uuids=glyphs,fillet_uuids=patchids,group_uuid=gu))
# Remove a numerical near-collinear seam where native tessellations differed.
t=pcbnew.PCB_TRACK(b);t.SetLayer(pcbnew.B_Cu);t.SetNet(b.FindNet('GND'));t.SetWidth(150000);t.SetStart(pcbnew.VECTOR2I(64170000,32865000));t.SetEnd(pcbnew.VECTOR2I(64380000,32867000));u=identify(t,'back-ground-numerical-seam');b.Add(t);ledger.append(dict(action='add_track',uuid=u,net='GND',layer='B.Cu',start_mm=[64.17,32.865],end_mm=[64.38,32.867],width_mm=.15))
pcbnew.SaveBoard(str(p),b);s=p.read_text()
for old,new in ids.items():s=s.replace(old,new)
p.write_text(s);(p.parent/'text-and-seam-changes.json').write_text(json.dumps(dict(source_sha256=source,pcb_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),changes=ledger),indent=2)+'\n');print(json.dumps(ledger,indent=2))
