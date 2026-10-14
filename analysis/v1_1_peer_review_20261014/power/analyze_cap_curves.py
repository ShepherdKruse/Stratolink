#!/usr/bin/env python3
"""Extract manufacturer's public typical capacitance curves and compute explicit screens.

These curves are typical design-reference data, not guaranteed operating minima.
Do not multiply isolated temperature/bias curves and call it a manufacturer guarantee.
"""
from pathlib import Path
import json,hashlib
HERE=Path(__file__).resolve().parent
NOM={'CL10A106KP8NNN':10,'CL21A226MAYNNN':22,'CL10A475KP8NNN':4.7,'CL05A106MQ5NUN':10,'CL10A226MP8NUN':22,'CL10A106KA8NRN':10,'CL21A476MPYNNN':47,'CL10A106KO8NQN':10}
def interp(points,x):
    p=sorted((float(d['x']),float(d['y'])) for d in points)
    if x<p[0][0] or x>p[-1][0]:return None
    for (x1,y1),(x2,y2) in zip(p,p[1:]):
        if x1<=x<=x2:return y1+(y2-y1)*(x-x1)/(x2-x1)
    return p[-1][1]
results={}
for part,nom in NOM.items():
    path=HERE/'sources'/f'{part}.html';s=path.read_text()
    start=s.index('var datasheetData =')+len('var datasheetData =')
    curves,_=json.JSONDecoder().raw_decode(s[start:].lstrip())
    data={}
    for curve in curves:
        for p in curve.get('selectPartsList',[]):
            for c in p.get('chartList',[]):
                typ=c.get('graphSubType',curve['graphType'])
                if typ in ['DCBias','TCC','BiasTCC']:
                    xs=[1.8,3.3,4.0,5.0,5.041] if typ=='DCBias' else [-55,-40,-20,25,85]
                    vals={str(x):interp(c['data'],x) for x in xs}
                    data[typ]={'conditions':{k:v for k,v in p.items() if k!='chartList'},'deltaC_percent':vals,'typical_uF':{k:None if v is None else nom*(1+v/100) for k,v in vals.items()},'raw_points':c['data']}
    results[part]={'source_url':'https://product.samsungsem.com/mlcc/'+part+'.do','source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'nominal_uF':nom,'curves':data,'warning':'Typical manufacturer reference curves only, not guaranteed limits. TCC and bias values are separate measurements unless BiasTCC.'}
(HERE/'capacitor-curves.json').write_text(json.dumps(results,indent=2)+'\n')
for part,r in results.items():
    print(part,json.dumps({k:{q:v for q,v in c.items() if q!='raw_points'} for k,c in r['curves'].items()}))
