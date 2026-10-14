"""Conditional grounded-CPW screen, not a field solve or board qualification."""
from itertools import product
import json
from math import log, pi, sqrt, tanh
from pathlib import Path

from scipy.constants import mu_0, epsilon_0
from scipy.special import ellipk


def ratio(k):
    assert 0 < k < 1
    # scipy's argument is the elliptic parameter m = k squared.
    return float(ellipk(k * k) / ellipk(1 - k * k))


def cpw(w, gap, h, er, t=0):
    """All dimensions in mm. Qucs 12.10-13 + scikit-rf thickness correction."""
    k1 = w / (w + 2 * gap)
    k3 = tanh(pi * w / (4 * h)) / tanh(pi * (w + 2 * gap) / (4 * h))
    q1, q3 = ratio(k1), ratio(k3)
    ee = 1 + (er - 1) * q3 / (q1 + q3)
    qe = q1
    if t:
        d = 1.25 * t / pi * (1 + log(4 * pi * w / t))
        ke = k1 + (1 - k1 * k1) * d / (2 * gap)
        qe = ratio(ke)
        ee -= (0.7 * (ee - 1) * t / gap) / (q1 + 0.7 * t / gap)
    return float(sqrt(mu_0 / epsilon_0) / (2 * (qe + q3) * sqrt(ee)))


def main():
    rows = [dict(width_mm=w, gap_mm=g, zero_thickness_ohm=cpw(w, g, .31, 4.5),
                 first_order_35um_ohm=cpw(w, g, .31, 4.5, .035))
            for w, g in product((.3, .4, .45, .5, .6, .75), (.15, .20, .25, .30))]
    corners = [dict(width_mm=w, gap_mm=g, core_mm=h, er=er, copper_mm=t,
                    impedance_ohm=cpw(w, g, h, er, t))
               for w, g, h, er, t in product((.425, .475), (.125, .175),
                                              (.279, .341), (4.0, 4.8), (.025, .045))]
    out = dict(
        status='conditional design screen; not manufacturer-qualified impedance',
        source_urls=['https://qucs.sourceforge.net/tech/node86.html',
                     'https://scikit-rf.readthedocs.io/en/latest/_modules/skrf/media/cpw.html'],
        nominal=dict(core_mm=.31, cad_declared_er=4.5, copper_mm=.035),
        rows=rows,
        sensitivity=dict(nominal_width_mm=.45, nominal_gap_mm=.15,
                         ranges_are_assumed_not_supplier_tolerances=True,
                         minimum_ohm=min(x['impedance_ohm'] for x in corners),
                         maximum_ohm=max(x['impedance_ohm'] for x in corners), corners=corners),
        limitations=[
            'Infinite coplanar grounds and continuous opposite plane assumed.',
            'Finite conductor correction is first order; the source itself qualifies retaining k3 unchanged.',
            'No solder-mask dielectric, copper roughness, dispersion, loss or pad/via/ESD discontinuity model.',
            'No real stackup tolerance or laminate permittivity has been qualified.',
            'Does not predict antenna match, module noise, coupling or C/N0.',
            'Cannot assign a uniform impedance to the existing interrupted-reference feed.'])
    (Path(__file__).parent / 'cpw-screen.json').write_text(json.dumps(out, indent=2) + '\n')
    print(json.dumps({'nominal_0p45_0p15_ohm':cpw(.45,.15,.31,4.5,.035),
                      'assumed_corner_range_ohm':[out['sensitivity']['minimum_ohm'],out['sensitivity']['maximum_ohm']]},indent=2))


if __name__ == '__main__':
    main()
