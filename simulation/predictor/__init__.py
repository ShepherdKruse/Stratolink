"""
Stratolink short-range trajectory predictor.

A physics-based predictor for pico-balloon position with CEP precision targets
of <5 km at 3 h, <15 km at 6 h, and <40 km at 10 h. Combines U.S. Standard
Atmosphere 1976, hydrostatic float-altitude solving, Lagrangian trajectory
integration against NOAA HRRR/GFS winds, and a 50-member ensemble for
uncertainty quantification.

Scope boundary vs. ``balloon_sim``: this package is for operational short-range
prediction of a specific in-flight balloon. ``balloon_sim`` answers fleet-design
questions ("how many balloons do we need for coverage?") against coarse
hourly reanalysis winds and is intentionally not used here.

See ``predictor/README.md`` for build phases and module layout.
"""

__version__ = "0.1.0"
