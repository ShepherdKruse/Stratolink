#!/usr/bin/env python3
"""Comparative membrane FE screen; not a laminate/contact/failure qualification.

Units: N, mm, MPa. Frozen native KiCad outline/drills input. Circular holes use
inscribed polygons; mesh-area error, convergence, equilibrium and energy checked.
"""
from pathlib import Path
import json, math, csv
import numpy as np
from scipy.spatial import Delaunay, cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve
from shapely.geometry import Polygon, Point, box
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.tri as mtri
HERE=Path(__file__).resolve().parent
DATA=json.loads((HERE/'input.json').read_text())
CENTERS=np.array([[55.665,31.745],[74.327,31.745]])
E=20000.; NU=.17; THICK=.31
D=E/(1-NU**2)*np.array([[1,NU,0],[NU,1,0],[0,0,(1-NU)/2]])

def solve(radius, h, cut=42., height=20., plot=False, contact_half_angle_deg=60.):
    shell=Polygon(DATA['shell']).intersection(box(50,28,80,cut))
    alpha=math.atan(9.331/height)
    inward=(1+math.sin(alpha))/(2*math.cos(alpha))  # total vertical load =1 N
    resultant=[np.array([inward,-.5]),np.array([-inward,-.5])]
    boundary=[]; holes=[]; ring_ids=[]; forces=[]
    # Sample every original contour segment, including the support cut.
    for a,b in zip(list(shell.exterior.coords)[:-1],list(shell.exterior.coords)[1:]):
        a,b=np.array(a),np.array(b)
        boundary.extend(a+(b-a)*s for s in np.linspace(0,1,max(2,int(np.linalg.norm(b-a)/h)+1),endpoint=False))
    for center,load in zip(CENTERS,resultant):
        n=max(180 if contact_half_angle_deg<60 else 60,int(math.ceil(2*math.pi*radius/h/12))*12)
        theta=math.atan2(load[1],load[0])
        phi=np.linspace(-math.pi,math.pi,n,endpoint=False)
        unit=np.column_stack((np.cos(theta+phi),np.sin(theta+phi)))
        ring=center+radius*unit
        ids=np.arange(len(boundary),len(boundary)+n)
        boundary.extend(ring); holes.append(Polygon(ring));ring_ids.append(ids)
        # Distributed radial pressure over +/-60 deg, rather than point load.
        weight=np.where(abs(phi)<math.radians(contact_half_angle_deg)+1e-9,np.cos(phi),0)
        f=weight[:,None]*unit
        f*=np.linalg.norm(load)/np.dot(f.sum(axis=0),load/np.linalg.norm(load))
        assert np.allclose(f.sum(axis=0),load,atol=1e-10)
        forces.append(f)
    used_drills=0
    for drill in DATA['drills']:
        c=np.array(drill['at']); dia=drill['diameter']
        if not(29.397<c[1]<cut):continue
        assert abs(dia[0]-dia[1])<1e-8,'Noncircular drill requires explicit geometry'
        r=dia[0]/2
        n=max(16,int(math.ceil(2*math.pi*r/h)))
        ring=c+r*np.column_stack((np.cos(np.arange(n)*2*math.pi/n),np.sin(np.arange(n)*2*math.pi/n)))
        hole=Polygon(ring)
        if not shell.contains(hole):continue
        boundary.extend(ring);holes.append(hole);used_drills+=1
    domain=shell
    for hole in holes:domain=domain.difference(hole)
    boundary=np.array(boundary)
    xx,yy=np.meshgrid(np.arange(shell.bounds[0]+h/2,shell.bounds[2],h),np.arange(shell.bounds[1]+h/2,cut,h))
    grid=np.column_stack((xx.ravel(),yy.ravel()))
    grid=grid[np.array([domain.contains(Point(p)) for p in grid])]
    grid=grid[cKDTree(boundary).query(grid)[0]>.32*h]
    xy=np.vstack((boundary,grid))
    tri=Delaunay(xy).simplices
    # Enforce domain membership of whole triangles, not just their centroids.
    expanded=domain.buffer(1e-8)
    tri=tri[np.array([expanded.covers(Polygon(xy[t])) and Polygon(xy[t]).area>1e-12 for t in tri])]
    active=np.unique(tri)
    remap=np.full(len(xy),-1,dtype=int);remap[active]=np.arange(len(active))
    assert all(np.all(remap[ids]>=0) for ids in ring_ids),'Missing loaded boundary node'
    f=np.zeros((len(xy),2))
    for ids,values in zip(ring_ids,forces):f[ids]+=values
    f=f[active].ravel();xy=xy[active];tri=remap[tri]
    p=xy[tri];twice=(p[:,1,0]-p[:,0,0])*(p[:,2,1]-p[:,0,1])-(p[:,2,0]-p[:,0,0])*(p[:,1,1]-p[:,0,1])
    area=abs(twice)/2
    assert np.min(area)>1e-12
    area_error=abs(area.sum()-domain.area)/domain.area
    assert area_error<.001,('Mesh gap',area_error)
    b=np.stack((p[:,1,1]-p[:,2,1],p[:,2,1]-p[:,0,1],p[:,0,1]-p[:,1,1]),axis=1)/twice[:,None]
    c=np.stack((p[:,2,0]-p[:,1,0],p[:,0,0]-p[:,2,0],p[:,1,0]-p[:,0,0]),axis=1)/twice[:,None]
    B=np.zeros((len(tri),3,6));B[:,0,0::2]=b;B[:,1,1::2]=c;B[:,2,0::2]=c;B[:,2,1::2]=b
    ke=THICK*area[:,None,None]*np.einsum('nki,kl,nlj->nij',B,D,B)
    dof=np.stack((tri*2,tri*2+1),axis=-1).reshape(-1,6)
    rows=np.broadcast_to(dof[:,:,None],ke.shape);cols=np.broadcast_to(dof[:,None,:],ke.shape)
    K=coo_matrix((ke.ravel(),(rows.ravel(),cols.ravel())),shape=(len(f),len(f))).tocsr()
    fixed=np.repeat(np.isclose(xy[:,1],cut,atol=1e-7),2);free=~fixed
    u=np.zeros(len(f));u[free]=spsolve(K[free][:,free],f[free]);assert np.isfinite(u).all()
    residual=K@u-f
    assert np.max(abs(residual[free]))<1e-8
    reactions=residual.reshape(-1,2).sum(axis=0)
    assert np.allclose(reactions+f.reshape(-1,2).sum(axis=0),0,atol=1e-8)
    total=f.reshape(-1,2)+residual.reshape(-1,2)
    moment=np.sum((xy[:,0]-65)*total[:,1]-(xy[:,1]-32)*total[:,0])
    assert abs(moment)<1e-8
    stress=np.einsum('ij,njk,nk->ni',D,B,u[dof]);sx,sy,tau=stress.T
    vm=np.sqrt(sx*sx-sx*sy+sy*sy+3*tau*tau)
    cent=p.mean(axis=1)
    distance=np.min(np.linalg.norm(cent[:,None,:]-CENTERS[None,:,:],axis=2),axis=1)-radius
    band=(distance>=.2)&(distance<=.8)
    energy=.5*u@(K@u);work=f@u
    assert np.isclose(energy,.5*work,rtol=1e-9)
    # Linear affine displacement must recover exactly uniform strain in every element.
    affine=np.column_stack((.002*xy[:,0]+.001*xy[:,1],-.003*xy[:,1])).ravel()
    assert np.allclose(np.einsum('nij,nj->ni',B,affine[dof]),[.002,-.003,.001],atol=1e-12)
    result=dict(substrate_bore_radius_mm=radius,spacing_mm=h,cut_y_mm=cut,apex_height_mm=height,contact_half_angle_deg=contact_half_angle_deg,nodes=len(xy),triangles=len(tri),retained_other_drills=used_drills,mesh_area_error_fraction=float(area_error),load_total_vertical_N=1,each_hole_inward_N=inward,compliance_mm_per_N=float(work),strain_energy_Nmm=float(energy),max_displacement_um=float(np.max(np.linalg.norm(u.reshape(-1,2),axis=1))*1000),band_area_mm2=float(area[band].sum()),band_average_von_mises_MPa=float(np.sum(vm[band]*area[band])/area[band].sum()),free_residual_N=float(max(abs(residual[free]))),moment_residual_Nmm=float(moment))
    if plot:return result,(xy,tri,vm)
    return result

def main():
    results=[]
    for cut,height,h in [(42,20,.22),(42,20,.15),(42,20,.10),(40,20,.15),(46,20,.15),(42,10,.15),(42,80,.15)]:
        for label,r in [('current',1.35050694185554),('selected',1.018)]:
            row=solve(r,h,cut,height);row['variant']=label;results.append(row);print(label,h,cut,height,row['compliance_mm_per_N'],flush=True)
    for contact in ['20deg', '0p6mm_arc']:
        for label,r in [('current',1.35050694185554),('selected',1.018)]:
            angle=20 if contact=='20deg' else math.degrees(.3/r)
            row=solve(r,.10,42,20,contact_half_angle_deg=angle);row['variant']=label;results.append(row)
    with (HERE/'results.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(results[0]));writer.writeheader();writer.writerows(results)
    fig,ax=plt.subplots(1,2,figsize=(11,5),layout='constrained')
    for a,(label,r) in zip(ax,[('Current 2.701 mm unplated cutout',1.35050694185554),('Selected 2.0 mm finished PTH',1.018)]):
        result,(xy,tri,vm)=solve(r,.10,42,20,True)
        plot=a.tripcolor(mtri.Triangulation(xy[:,0],xy[:,1],tri),facecolors=vm,vmin=0,vmax=3,cmap='viridis',rasterized=True)
        a.set_aspect('equal');a.set_ylim(38,28.8);a.set_title(label);a.set_xlabel('Board x (mm)');a.set_ylabel('Board y (mm)')
    fig.colorbar(plot,ax=ax,label='Membrane von Mises stress (MPa); color clipped at 3')
    fig.suptitle('Geometry comparison: 1 N total vertical load; continuous triangle, 20 mm apex\n0.31 mm isotropic core; copper reinforcement omitted; no failure prediction')
    fig.savefig(HERE/'comparison.png',dpi=180);plt.close(fig)
    ratios=[]
    for a,b in zip(results[0::2],results[1::2]):
        ratios.append(dict(spacing_mm=a['spacing_mm'],cut_y_mm=a['cut_y_mm'],apex_height_mm=a['apex_height_mm'],current_contact_half_angle_deg=a['contact_half_angle_deg'],selected_contact_half_angle_deg=b['contact_half_angle_deg'],compliance_ratio_selected_current=b['compliance_mm_per_N']/a['compliance_mm_per_N'],band_stress_ratio_selected_current=b['band_average_von_mises_MPa']/a['band_average_von_mises_MPa']))
    (HERE/'summary.json').write_text(json.dumps(dict(source_board_sha256=DATA['board_sha256'],E_MPa=E,poisson=NU,core_thickness_mm=THICK,ratios=ratios,limitations=['Isotropic plane stress membrane; no laminate anisotropy, copper, plating, wear, cold, solder, or nonlinear string contact.','Fixed lower cut is a sensitivity assumption; the assembled load distribution is unmeasured.','Smooth +/-60 degree bore contact loading; local peaks are not strength allowables.','Other fully contained upper drill holes retained; holes intersecting the artificial support cut omitted; copper routing omitted.','Source KiCad faceted outline and polygonized holes; comparative compliance only.']),indent=2)+'\n')

if __name__=='__main__':main()
