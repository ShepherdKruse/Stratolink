from pathlib import Path
import pcbnew,wx,re,json,hashlib,sys
app=wx.App(False);p=Path(sys.argv[1]).resolve().parent;b=pcbnew.LoadBoard(str(p/'stratolink.kicad_pcb'));f=next(f for f in b.GetFootprints() if f.GetReference()=='C5');properties={q.GetName():q.GetText() for q in f.GetFields()};lib=p/'lib/Stratolink_v1p1_C5_DMF4B5R5G105M3DTA0.kicad_mod';s=lib.read_text();changes=[]
for k in ['Description','Assembly_Note']:
 pattern=r'(\(property "'+k+r'" ")([^"]*)(")';m=re.search(pattern,s);assert m;old=m.group(2);new=properties[k];s=s[:m.start(2)]+new+s[m.end(2):];changes.append(dict(field=k,before=old,after=new))
lib.write_text(s);(p/'library-metadata-ledger.json').write_text(json.dumps(changes,indent=2)+'\n');print(json.dumps(changes,indent=2))
