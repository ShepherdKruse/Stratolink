"""Reproduce lower wire-hole position screens against current source."""
import contextlib,io,json
with contextlib.redirect_stdout(io.StringIO()):
 import study as m
results=[]
for y in [76.5,77,77.5,78,78.5,79,79.5,80,80.5,81,81.5,82]:
 for xl,xr in [(54.8,74.6),(54.5,75.5)]:results += m.screen('lower_positive',[(xl,y),(xr,y)],(1.6,1.6),'+SOLAR')
(m.HERE/'lower_positive_screen.json').write_text(json.dumps(results,indent=2)+'\n')
results=[]
for size in [1.3,1.4,1.5,1.6]:
 for y in [76.4,76.5,76.6,76.7,77.0,78.5,79,80,81.5,82]:results += m.screen('lower_positive',[(54.3,y),(75.7,y)],(size,size),'+SOLAR')
(m.HERE/'lower_positive_edge_screen.json').write_text(json.dumps(results,indent=2)+'\n')
for r in results:
 if r['pad_size_mm']==(1.4,1.4) and r['center_mm'][1]==76.5:print(r['side'],r['center_mm'],'pad conflicts',r['pad_conflicts'],'courtyard conflicts',[(c['ref'],c['layer']) for c in r['courtyard_nearby']])
