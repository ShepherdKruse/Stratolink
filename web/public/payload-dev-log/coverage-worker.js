// Equal-area Fibonacci sphere sample. Each target counts at most once.
const rad=Math.PI/180,targets=[];
for(let k=0;k<6000;k++){const z=1-2*(k+.5)/6000,lon=k*Math.PI*(3-Math.sqrt(5)),r=Math.sqrt(1-z*z);targets.push([r*Math.cos(lon),r*Math.sin(lon),z]);}
self.onmessage=({data:d})=>{const threshold=Math.cos(d.radius/6371),vectors=d.positions.map(([lat,lon])=>{lat*=rad;lon*=rad;return[Math.cos(lat)*Math.cos(lon),Math.cos(lat)*Math.sin(lon),Math.sin(lat)];});let total=0,north=0;for(const x of targets){for(const y of vectors){if(x[0]*y[0]+x[1]*y[1]+x[2]*y[2]>=threshold){total++;if(x[2]>0)north++;break;}}}self.postMessage({id:d.id,hour:d.hour,global:total/6000*100,north:north/3000*100,south:(total-north)/3000*100});};
