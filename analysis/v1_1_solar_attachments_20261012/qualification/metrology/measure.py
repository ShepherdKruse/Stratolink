#!/usr/bin/env python3
"""Metric-grid metrology of a supplied primary-product photo capture.

Reads only the source PNG; writes measurements/plots beside this script.
Numbers are image estimates, not manufacturer dimensions or tolerances.
"""
from pathlib import Path
import hashlib,json
import numpy as np
from PIL import Image
from scipy.optimize import least_squares
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent/'sources/zachtek-metric-photo-browser.png'
EXPECTED='5b9faad0a61e231a8d753d6bc7bd92a68e95286597f6a25dba17d9f12d62dba3'
sha=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
assert sha==EXPECTED,'Source capture changed; review point selections before using this measurement.'
image=Image.open(SOURCE).convert('RGB');gray=np.asarray(image.convert('L'),dtype=float)

def minimum_subpixel(values,base):
    i=int(np.argmin(values));delta=0.
    if 0<i<len(values)-1:
        denominator=values[i-1]-2*values[i]+values[i+1]
        if denominator:delta=.5*(values[i-1]-values[i+1])/denominator
    return float(base+i+delta)

# Visible intersections of the 1 cm major grid. The y=100 mm row at the
# image top and x=80 mm column to the right avoid the panel-covered grid.
# Guesses select the intended major lines; local dark minima refine them.
grid=[]
for i,x in enumerate([127,177,226,276,326,376,426,476,526]):
    y=round(12-.015*x)
    yy=minimum_subpixel(gray[y-3:y+4,x-5:x+6].mean(axis=1),y-3)
    xx=minimum_subpixel(gray[max(0,y-5):y+15,x-3:x+4].mean(axis=0),x-3)
    grid.append(dict(label=f'T{i}',pixel_xy=[xx,yy],grid_mm=[i*10,100],selection_seed=[x,y]))
for y,mm_y in zip([53,103,303,353,404,454,505],[90,80,40,30,20,10,0]):
    x=round(525+.018*y)
    xx=minimum_subpixel(gray[y-6:y+7,x-3:x+4].mean(axis=0),x-3)
    yy=minimum_subpixel(gray[y-3:y+4,x-7:x+8].mean(axis=1),y-3)
    grid.append(dict(label=f'R{mm_y//10}',pixel_xy=[xx,yy],grid_mm=[80,mm_y],selection_seed=[x,y]))
xy=np.array([g['pixel_xy'] for g in grid]);mm=np.array([g['grid_mm'] for g in grid],dtype=float)

def project(H,coords):
    p=np.c_[coords,np.ones(len(coords))]@H.T
    return p[:,:2]/p[:,2,None]
def matrix(h):return np.r_[h,1.].reshape(3,3)
fit=least_squares(lambda h:(project(matrix(h),mm)-xy).ravel(),[5,0,130,0,-5,510,0,0])
H=matrix(fit.x);inverse=np.linalg.inv(H)
residual=project(H,mm)-xy
# Manual physical-boundary picks, avoiding the dark cast shadow below the
# lower terminal. The raised/glare-obscured upper edge is ambiguous.
corner_pixels=np.array([[126.,39.5],[498.5,30.5],[506.5,504.5],[132.,505.5]])
corner_names=['upper_left','upper_right','lower_right','lower_left']
corners=project(inverse,corner_pixels)
def dimensions(points):
    top=np.linalg.norm(points[1]-points[0]);right=np.linalg.norm(points[2]-points[1])
    bottom=np.linalg.norm(points[3]-points[2]);left=np.linalg.norm(points[0]-points[3])
    return dict(length_left_mm=left,length_right_mm=right,width_upper_mm=top,width_lower_mm=bottom,
                mean_length_mm=(left+right)/2,mean_width_mm=(top+bottom)/2)
dims=dimensions(corners)

# Explicit metal-band picks at several stations. The upper band is partly
# raised/glare-obscured; it should not be treated as a uniform tolerance.
bands=[]
for label,stations in [
    ('upper',[(150,40.5,63.5),(250,40.5,63.5),(350,40.,62.5),(450,30.5,60.5),(490,30.,60.5)]),
    ('lower',[(150,480.5,505.5),(250,480.0,504.5),(350,479.5,504.0),(450,479.5,505.0),(490,479.5,505.5)])]:
    for x,y1,y2 in stations:
        endpoints=np.array([[x,y1],[x,y2]]);physical=project(inverse,endpoints)
        bands.append(dict(terminal=label,pixel_endpoints=endpoints.tolist(),grid_endpoints_mm=physical.tolist(),width_mm=float(np.linalg.norm(physical[1]-physical[0]))))

# Coordinate-picking sensitivity only. It excludes grid-print accuracy,
# nonplanarity, film curl, camera distortion, physical edge interpretation,
# and solderable coating uncertainty; the reported engineering ranges are
# intentionally wider than this Monte Carlo interval.
def linear_homography(src,dst):
    rows=[];rhs=[]
    for (x,y),(u,v) in zip(src,dst):
        rows += [[x,y,1,0,0,0,-u*x,-u*y],[0,0,0,x,y,1,-v*x,-v*y]]
        rhs += [u,v]
    return matrix(np.linalg.lstsq(np.array(rows),np.array(rhs),rcond=None)[0])
rng=np.random.default_rng(20261012);sensitivity=[]
for _ in range(2000):
    noisy_grid=xy+rng.uniform(-.75,.75,size=xy.shape)
    noisy_corners=corner_pixels+rng.uniform(-2,2,size=corner_pixels.shape)
    noisyH=linear_homography(mm,noisy_grid)
    d=dimensions(project(np.linalg.inv(noisyH),noisy_corners))
    sensitivity.append([d['mean_length_mm'],d['mean_width_mm']])
sensitivity=np.array(sensitivity)
# Affine fit is a model sensitivity, not an alternative measured ruler.
affine=np.linalg.lstsq(np.c_[mm,np.ones(len(mm))],xy,rcond=None)[0].T
affineH=np.vstack([affine,[0,0,1]])
affine_dimensions=dimensions(project(np.linalg.inv(affineH),corner_pixels))

report=dict(
 source=dict(path=str(SOURCE.relative_to(HERE.parent)),sha256=sha,size_pixels=list(image.size),
             provenance='Primary ZachTek product metric-grid photo captured in the in-app browser and supplied by the parent task; page provenance is maintained by the parent research.'),
 conventions=dict(pixel_origin='top-left of the 1280x1102 capture',pixel_axes='x right, y down',grid_origin='printed 0 cm / 0 cm intersection',grid_axes='x right, y up',grid_units='mm',major_grid_spacing_mm=10),
 calibration=dict(points=grid,homography_grid_mm_to_capture_pixels=H.tolist(),homography_capture_pixels_to_grid_mm=inverse.tolist(),coordinate_rms_residual_px=float(np.sqrt(np.mean(residual**2))),maximum_point_residual_px=float(np.linalg.norm(residual,axis=1).max()),pixel_residuals=residual.tolist()),
 panel=dict(corners=[dict(label=n,pixel_xy=p.tolist(),grid_mm=q.tolist()) for n,p,q in zip(corner_names,corner_pixels,corners)],**{k:float(v) for k,v in dims.items()}),
 terminal_band_stations=bands,
 sensitivity=dict(seed=20261012,trials=2000,grid_coordinate_uniform_noise_px=[-.75,.75],panel_corner_uniform_noise_px=[-2,2],
                  picking_only_length_2p5_97p5_mm=np.quantile(sensitivity[:,0],[.025,.975]).tolist(),
                  picking_only_width_2p5_97p5_mm=np.quantile(sensitivity[:,1],[.025,.975]).tolist(),
                  affine_dimensions_mm={k:float(v) for k,v in affine_dimensions.items()},
                  note='These are picking/model sensitivity calculations, not confidence intervals for the manufactured panel.'),
 engineering_assumptions=dict(nominal_panel_mm=[94,75],conservative_photo_only_length_mm=[92,96],conservative_photo_only_width_mm=[73.5,76.5],nominal_terminal_strip_mm=5,conservative_photo_only_terminal_width_mm=[4,6.5],manufacturer_tolerance_established=False,terminal_thickness_measurable=False,wettable_scraped_patch_measurable=False),
 limitations=['The grid is planar; the panel is visibly raised/curling at the upper end, so its silhouette need not lie in that calibration plane.',
              'The upper terminal edge is partly shadowed and glared; selecting the dark outside shadow instead adds roughly 1–2 mm to apparent length.',
              'The lower metal band is clearly about 5 mm; upper-band width varies in the photograph and cannot establish a uniform minimum wettable width.',
              'Product thickness, conductor thickness, coating thickness, solderable area after scraping, bending radius, and manufacturing tolerance cannot be inferred from this image.',
              'All dimensions are photo-derived engineering estimates and must not be attributed as manufacturer specifications.'])
(HERE/'measurement.json').write_text(json.dumps(report,indent=2)+'\n')

plt.rcParams.update({'font.size':10})
fig,axs=plt.subplots(1,2,figsize=(12,7),layout='constrained')
ax=axs[0];ax.imshow(image);ax.set_xlim(105,562);ax.set_ylim(524,-3);ax.scatter(xy[:,0],xy[:,1],s=25,facecolors='none',edgecolors='#00dcff',linewidths=1.3)
for g in grid:
    x,y=g['pixel_xy'];ax.text(x+3,y+11,g['label'],color='#00dcff',fontsize=7)
closed=np.vstack([corner_pixels,corner_pixels[0]])
ax.plot(closed[:,0],closed[:,1],color='#ffae19',lw=1.3);ax.scatter(corner_pixels[:,0],corner_pixels[:,1],s=22,color='#ffae19')
ax.set_title('Source pixels and selected metric-grid intersections');ax.set_xlabel('Capture X (pixels)');ax.set_ylabel('Capture Y (pixels)')
ax=axs[1];c=np.vstack([corners,corners[0]])
ax.fill(c[:,0],c[:,1],color='#f2eee4');ax.plot(c[:,0],c[:,1],color='#b57000',lw=2)
for b in bands:
    p=np.array(b['grid_endpoints_mm']);ax.plot(p[:,0],p[:,1],color='#837661',lw=3)
ax.set_aspect('equal');ax.set_xlim(-7,85);ax.set_ylim(-4,101);ax.set_xticks(np.arange(0,81,10));ax.set_yticks(np.arange(0,101,10));ax.grid(alpha=.25)
ax.text(37,49,f'{dims["mean_length_mm"]:.1f} × {dims["mean_width_mm"]:.1f} mm\nphoto-derived point estimate',ha='center',va='center',fontsize=13)
ax.text(37,40,'Use 94 ± 2 × 75 ± 1.5 mm\nfor engineering sensitivity',ha='center',va='center',fontsize=10)
ax.set_title('Coordinates after planar perspective correction');ax.set_xlabel('Printed grid X (mm)');ax.set_ylabel('Printed grid Y (mm)')
fig.suptitle('ZachTek panel: metric-photo estimate, not a manufacturer drawing',fontsize=14)
fig.savefig(HERE/'measurement.png',dpi=180);plt.close(fig)
for title,xlim,ylim,filename in [('Upper terminal: edge/glare ambiguity',(110,510),(90,20),'top_detail.png'),('Lower terminal: clear ≈5 mm metal band',(115,540),(520,455),'bottom_detail.png')]:
    fig,ax=plt.subplots(figsize=(13,5),layout='constrained');ax.imshow(image);ax.set_xlim(*xlim);ax.set_ylim(*ylim);ax.set_xticks(np.arange(125,xlim[1]+1,25));ax.set_yticks(np.arange(min(ylim),max(ylim)+1,5));ax.grid(alpha=.3);ax.set_title(title);ax.set_xlabel('Capture X (pixels)');ax.set_ylabel('Capture Y (pixels)');fig.savefig(HERE/filename,dpi=140);plt.close(fig)
print(json.dumps({'panel_mm':dims,'grid_rms_px':report['calibration']['coordinate_rms_residual_px'],'picking_sensitivity':report['sensitivity'],'terminal_widths_mm':[round(b['width_mm'],3) for b in bands]},indent=2))
