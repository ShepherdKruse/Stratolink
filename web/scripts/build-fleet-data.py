"""Reproduce article tracks from Caleb's solver and a NOAA 300 hPa subset.

uv run --with numpy --with xarray --with netCDF4 python scripts/build-fleet-data.py \
  --wind-dir /path/to/wind

The directory must contain uwnd.2024.nc and vwnd.2024.nc, subset to
2024-05-17 00:00 through 2024-05-31 00:00 UTC, all latitudes/longitudes.
NOAA endpoint: https://psl.noaa.gov/thredds/ncss/grid/Datasets/ncep.reanalysis2/pressure/uwnd.2024.nc
Query: var=uwnd&north=90&west=-180&east=180&south=-90&horizStride=1&time_start=2024-05-17T00:00:00Z&time_end=2024-05-31T00:00:00Z&vertCoord=300&accept=netcdf3
Use vwnd for the second file. The large source files are not site assets.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import numpy as np

WEB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WEB.parent / 'simulation'))
from balloon_sim.wind import WindField
from balloon_sim.trajectory import TrajectoryComputer

parser = argparse.ArgumentParser()
parser.add_argument('--wind-dir', type=Path, required=True)
args = parser.parse_args()
wind = WindField(str(args.wind_dir), pressure_level=300, interpolation='linear')
assert wind.times[0] == np.datetime64('2024-05-17T00:00:00')
assert wind.times[-1] == np.datetime64('2024-05-31T00:00:00')
assert len(wind.times) == 57
solver = TrajectoryComputer(wind)
out = WEB / 'public/assets/payload-dev-log'
meta = json.loads((out / 'fleet.json').read_text())
for mode, seed, sign, filename in [('north', 20261008, 1, 'fleet-tracks.bin'), ('south', 20261009, -1, 'fleet-south.bin')]:
    rng = np.random.default_rng(seed)
    lats = sign * np.degrees(np.arcsin(rng.uniform(0, 1, 500)))
    lons = rng.uniform(-180, 180, 500)
    tracks = np.empty((500, 337, 2), dtype='<f4')
    for k in range(500):
        lat, lon = solver.compute_trajectory_arrays(float(lats[k]), float(lons[k]), 336)
        tracks[k, :, 0] = lat
        tracks[k, :, 1] = lon
    assert np.isfinite(tracks).all() and np.abs(tracks[:, :, 0]).max() <= 90
    if mode == 'north':
        assert np.array_equal(np.fromfile(out / filename, dtype='<f4').reshape(tracks.shape), tracks), 'Original northern trajectories changed'
    else:
        tracks.tofile(out / filename)
    print(mode, tracks.shape, hashlib.sha256(tracks.tobytes()).hexdigest(), flush=True)
meta['distributions'] = {
    'north': '500 uniform-by-area northern seeds, RNG 20261008',
    'south': '500 uniform-by-area southern seeds, RNG 20261009',
    'world': 'Alternate independent northern and southern tracks; 250 from each at count 500',
}
meta['track_hashes'] = {name: hashlib.sha256((out / name).read_bytes()).hexdigest() for name in ['fleet-tracks.bin', 'fleet-south.bin']}
(out / 'fleet.json').write_text(json.dumps(meta, indent=2) + '\n')
