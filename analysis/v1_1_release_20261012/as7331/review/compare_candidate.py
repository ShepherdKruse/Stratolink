#!/usr/bin/env python3
"""Independent semantic, package-coordinate and scope checks of native evidence.

Use native_snapshot.py and fresh kicad-cli schematic export first. No imported
ECO builder code or expected net mapping from candidate metadata is used.
"""
from pathlib import Path
import argparse,json,math,xml.etree.ElementTree as ET
HERE=Path(__file__).resolve().parent

def netpins(path):
    root=ET.parse(path).getroot();pins={}
    for n in root.findall('./nets/net'):
        for p in n.findall('node'):pins[p.get('ref')+'.'+p.get('pin')]=n.get('name')
    return pins

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--allow-green-finish',action='store_true');args=ap.parse_args()
    def layers_same(a,b):
        # Native KiCad10 F.Mask=1 and B.Mask=3. Never waive Cu/Paste differences.
        mask=~((1<<1)|(1<<3)) if args.allow_green_finish else -1
        return int(a.replace('_',''),16)&mask==int(b.replace('_',''),16)&mask
    old=json.loads((HERE/'baseline-native.json').read_text());new=json.loads((HERE/'candidate-native.json').read_text())
    op,np=old['pads'],new['pads'];of,nf=old['footprints'],new['footprints']
    assert not of.keys()-nf.keys();assert nf.keys()-of.keys()=={'C23','R27'}
    changed_placements=[]
    for ref in of:
        if ref=='U6':continue
        a,b=of[ref],nf[ref]
        for field in ['value','footprint','layer','uuid','pads']:assert a[field]==b[field],('Retained footprint field changed',ref,field,a[field],b[field])
        if a['at']!=b['at'] or a['angle']!=b['angle']:
            assert ref in {'C14','C21'},('Unexpected component move',ref)
            if ref=='C21':assert b['at']==[69.362,34.647] and b['angle']==180.0,('C21 move exceeds reviewed 0.9mm shift',b)
            changed_placements.append(dict(ref=ref,before=a['at'],after=b['at'],before_angle=a['angle'],after_angle=b['angle']))
    retained={k for k in op if not k.startswith('U6.')}
    for k in retained:
        a,b=op[k],np[k];assert a['net']==b['net'],('Retained pad net changed',k,a['net'],b['net'])
        assert layers_same(a['layers'],b['layers']),('Retained non-mask layers changed',k)
        for field in ['size','drill','shape','uuid','effective_paste_margin_mm','paste_margin_mm']:assert a[field]==b[field],('Retained pad changed',k,field)
        assert set(a['physical'])&retained==set(b['physical'])&retained,('Physical island changed',k)
        if not k.startswith(('C14.','C21.')):
            assert a['at']==b['at'] and a['local']==b['local'] and a['angle']==b['angle'],('Retained pad moved',k)
    retained_uuids={u for u,p in old['physical_pads'].items() if not p['key'].startswith('U6.')}
    for uid in retained_uuids:
        a,b=old['physical_pads'][uid],new['physical_pads'][uid]
        assert layers_same(a['layers'],b['layers']),('Retained non-mask physical pad layers changed',a['key'])
        for field in ['net','size','drill','shape','uuid','key','effective_paste_margin_mm','paste_margin_mm']:assert a[field]==b[field],('Retained physical pad changed',a['key'],field)
        assert set(a['physical_uuids'])&retained_uuids==set(b['physical_uuids'])&retained_uuids,('Retained physical island differs',uid)
        if not a['key'].startswith(('C14.','C21.')):
            assert a['at']==b['at'] and a['local']==b['local'] and a['angle']==b['angle'],('Retained physical pad moved',a['key'])
    expected={str(n):'GND' for n in [1,2,5,6,7,8,11,14,15,16]}
    expected.update({'3':'+3.3V','10':'+3.3V','12':'SDA','13':'SCL'})
    for pin,net in expected.items():assert np['U6.'+pin]['net']==net,('Wrong AS7331 pin',pin,np['U6.'+pin]['net'],net)
    refnet=np['U6.4']['net'];ready=np['U6.9']['net']
    assert 'REXT' in refnet;assert ready.startswith('unconnected-') and 'READY' in ready
    assert set(np['U6.9']['physical'])=={'U6.9'},'READY unexpectedly electrically attached'
    assert {np['R27.1']['net'],np['R27.2']['net']}=={refnet,'GND'}
    for ref in ['C14','C23']:assert {np[ref+'.1']['net'],np[ref+'.2']['net']}=={'+3.3V','GND'}
    expected_centers={}
    for pin,x in zip([1,2,3,4],[-.75,-.25,.25,.75]):expected_centers[str(pin)]=[x,-1.575]
    for pin,x in zip([12,11,10,9],[-.75,-.25,.25,.75]):expected_centers[str(pin)]=[x,1.575]
    for pin,y in zip([16,15,14,13],[-.75,-.25,.25,.75]):expected_centers[str(pin)]=[-1.05,y]
    for pin,y in zip([5,6,7,8],[-.75,-.25,.25,.75]):expected_centers[str(pin)]=[1.05,y]
    for pin,xy in expected_centers.items():
        p=np['U6.'+pin];assert max(abs(a-b) for a,b in zip(p['local'],xy))<1e-5,('Wrong terminal center',pin,p['local'],xy)
        assert p['size']==[.35,.35] and p['effective_paste_margin_mm']==[-.025,-.025],('Unexpected land/paste sizing',pin,p)
    sch0,sch1=[netpins(HERE/name) for name in ['baseline-netlist.xml','candidate-netlist.xml']]
    retained_sch={k for k in sch0 if not k.startswith('U6.')}
    for k in retained_sch:assert sch0[k]==sch1[k],('Retained schematic pin changed',k)
    assert set(sch1)-retained_sch=={'U6.'+str(i) for i in range(1,17)}|{'C23.1','C23.2','R27.1','R27.2'}
    unchanged_native_name_escaping=[]
    for k,net in sch1.items():
        if np[k]['net']==net:continue
        # KiCad native NC pin-function names encode '/' as '{slash}', while
        # its XML netlist exporter decodes it. Permit only exact baseline NCs.
        assert k in retained and op[k]['net']==np[k]['net'] and sch0[k]==net and net.startswith('unconnected-') and np[k]['net'].replace('{slash}','/')==net,('Native schematic parity mismatch',k,np.get(k),net)
        unchanged_native_name_escaping.append(dict(pin=k,native=np[k]['net'],xml=net))
    ot,nt=old['tracks'],new['tracks'];changes=[]
    for uid in ot.keys()|nt.keys():
        if ot.get(uid)==nt.get(uid):continue
        rec=dict(uuid=uid,before=ot.get(uid),after=nt.get(uid));changes.append(rec)
        for t in [ot.get(uid),nt.get(uid)]:
            if t:assert t['net'] in {'GND','SDA','SCL','+3.3V','VSTOR','PB5',refnet},('Unrelated routed net changed',rec)
    for change in changes:
        t=change['after']
        if t and t['net'] in ['VSTOR','PB5'] and t['kind'] in ['PCB_TRACK','PCB_ARC']:assert t['width']>=.25,('Rerouted existing power/status trace narrowed',change)
    i2c_lengths={}
    for net in ['SDA','SCL']:
        def line_length(t):
            assert t['kind'] in ['PCB_TRACK','PCB_VIA'],('Unexpected I2C arc: extend length extraction',t)
            return math.dist(t['start'],t['end'])
        before=sum(line_length(t) for t in ot.values() if t['net']==net)
        after=sum(line_length(t) for t in nt.values() if t['net']==net)
        i2c_lengths[net]=dict(baseline_routed_centerline_mm=before,candidate_routed_centerline_mm=after,increase_mm=after-before)
    assert not new['unconnected_native']
    report=dict(status='PASS',finish_mask_layer_changes_authorized=args.allow_green_finish,retained_pad_mask_layer_changes=[dict(key=old['physical_pads'][u]['key'],uuid=u,before=old['physical_pads'][u]['layers'],after=new['physical_pads'][u]['layers']) for u in retained_uuids if old['physical_pads'][u]['layers']!=new['physical_pads'][u]['layers']],source=new['source'],source_hashes=new['hashes'],retained_physical_pads=len(retained_uuids),retained_distinct_ref_pad_names=len(retained),retained_schematic_pins=len(retained_sch),new_footprints=sorted(nf.keys()-of.keys()),changed_placements=changed_placements,as7331_expected_pin_map={**expected,'4':refnet,'9':ready},as7331_center_coordinates_mm=expected_centers,as7331_lands_mm=[.35,.35],as7331_paste_mm=[.3,.3],unchanged_gnss_rf_net_geometry=True,native_opens=0,i2c_routed_lengths=i2c_lengths,i2c_rc_screen=dict(pullups_ohm=4700,tR_limit_ns=300,nominal_total_bus_capacitance_budget_pF=300e-9/(.8473*4700)*1e12,note='AS7331 DS Figure39; lumped 30-70percent RC estimate. Full bus capacitance and real rise times not measured.'),route_changes=changes,limitations=['Electrical islands reflect native geometry, not measured assembly.','This comparison does not substitute for DRC, optical calibration, supplier rotation preview or factory process approval.'])
    report['unchanged_baseline_nc_name_escaping']=unchanged_native_name_escaping
    (HERE/'candidate-independent-review.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['route_changes','source_hashes','as7331_center_coordinates_mm']},indent=2))

if __name__=='__main__':main()
