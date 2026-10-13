from PIL import Image,ImageDraw,ImageFont
import json,math,sys
r=json.load(open(sys.argv[1]));side=sys.argv[3] if len(sys.argv)>3 else 'F';im=Image.new('RGB',(1800,1400),'#10151b');d=ImageDraw.Draw(im);scale=70;origin=(53,30);font=ImageFont.truetype('/System/Library/Fonts/Menlo.ttc',12)
def p(pt):return tuple(int((pt[i]-origin[i])*scale)+40 for i in range(2))
colors={'GND':'#738090','+3.3V':'#ee6655','SDA':'#66e5ac','SCL':'#eece56'}
for x in range(53,78):d.line([p((x,30)),p((x,48))],fill='#293038');d.text(p((x,30)),str(x),font=font)
for y in range(30,49):d.line([p((53,y)),p((77,y))],fill='#293038');d.text(p((53,y)),str(y),font=font)
for t in r['tracks']:
 if not t['side'].startswith(side) and not t['via']:continue
 col=colors.get(t['net'],'#9988dd');d.line([p(t['s']),p(t['e'])],fill=col,width=max(1,int(scale*t['width'])))
 if t['via']:
  x,y=p(t['s']);a=scale*t['width']/2;d.ellipse((x-a,y-a,x+a,y+a),fill=col);d.ellipse((x-5,y-5,x+5,y+5),fill='#111111')
for q in r['pads']:
 if not q['side'].startswith(side) and not q['pth']:continue
 x,y=q['at'];w,h=q['size'];rad=math.radians(q['angle']);cs=math.cos(rad);sn=math.sin(rad)
 pts=[p((x+u*cs+v*sn,y-u*sn+v*cs)) for u,v in [(-w/2,-h/2),(w/2,-h/2),(w/2,h/2),(-w/2,h/2)]]
 d.polygon(pts,fill=colors.get(q['net'],'#9988dd'));d.text(p((x,y)),q['ref']+'.'+q['n'],fill='white',font=font)
for l in r['lines']:
 if l['side'].startswith(side):d.line([p(l['s']),p(l['e'])],fill='white',width=1)
im.save(sys.argv[2])
