"""
NOAA GFS client — anonymous S3 access to ``s3://noaa-gfs-bdp-pds``.

Mirror of :mod:`predictor.weather.hrrr_client` for global, longer-range
forecasts. Used (a) outside CONUS (HRRR doesn't cover the rest of the
world) and (b) beyond HRRR's 18 h/48 h horizon. GFS runs four times a
day at 00/06/12/18Z out to 384 h.

The GFS pressure-level product used here is ``pgrb2.0p25`` (0.25°
regular lat/lon grid) — easier to interpolate than HRRR's Lambert
Conformal mesh, at the cost of coarser horizontal resolution.

Layout (as documented in NOAA NCEP's product description; verify
against the live bucket when implementing partial-fetch byte ranges)::

    s3://noaa-gfs-bdp-pds/gfs.YYYYMMDD/HH/atmos/gfs.tHHz.pgrb2.0p25.fFFF
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from predictor.weather.hrrr_client import (
    _ByteRangeFetcher,
    _compute_byte_ranges,
    parse_idx,
    select_uv_pressure_records,
)

logger = logging.getLogger(__name__)

S3_BUCKET = "noaa-gfs-bdp-pds"
S3_HTTPS_BASE = f"https://{S3_BUCKET}.s3.amazonaws.com"

# GFS cycles every 6 hours
GFS_CYCLES_UTC = (0, 6, 12, 18)
GFS_MAX_FXX = 384


@dataclass(frozen=True)
class GFSCycle:
    """A GFS model cycle on AWS Open Data."""

    cycle_dt: datetime

    def __post_init__(self) -> None:
        if self.cycle_dt.tzinfo is None or self.cycle_dt.tzinfo.utcoffset(self.cycle_dt) != timedelta(0):
            raise ValueError("cycle_dt must be timezone-aware UTC.")
        if self.cycle_dt.hour not in GFS_CYCLES_UTC:
            raise ValueError(
                f"GFS cycles are 00/06/12/18Z; got {self.cycle_dt.hour:02d}Z."
            )
        if self.cycle_dt.minute or self.cycle_dt.second or self.cycle_dt.microsecond:
            raise ValueError("cycle_dt must be hour-aligned.")

    @property
    def s3_prefix(self) -> str:
        return f"gfs.{self.cycle_dt:%Y%m%d}/{self.cycle_dt:%H}/atmos/"

    def key(self, fxx: int, resolution: str = "0p25") -> str:
        return f"{self.s3_prefix}gfs.t{self.cycle_dt:%H}z.pgrb2.{resolution}.f{fxx:03d}"

    def url(self, fxx: int, resolution: str = "0p25") -> str:
        return f"{S3_HTTPS_BASE}/{self.key(fxx, resolution)}"

    def max_fxx(self) -> int:
        return GFS_MAX_FXX


def download_uv_pressure_levels(
    cycle: GFSCycle,
    fxx: int,
    cache_dir: Path,
    levels_mb: list[int] | None = None,
    fetcher: _ByteRangeFetcher | None = None,
    resolution: str = "0p25",
) -> Path:
    """Download u/v pressure-level messages for one GFS cycle/fxx.

    Same partial-fetch strategy as the HRRR client: parse the ``.idx``,
    select isobaric ``UGRD``/``VGRD``, byte-range fetch.

    Notes
    -----
    GFS ``.idx`` is the same wgrib2 format as HRRR's, which is why we
    reuse the parser from :mod:`predictor.weather.hrrr_client`.
    """
    if fxx < 0 or fxx > GFS_MAX_FXX:
        raise ValueError(f"fxx={fxx} outside GFS range [0, {GFS_MAX_FXX}].")

    cache_dir = Path(cache_dir)
    cycle_part = cycle.cycle_dt.strftime("%Y%m%dT%HZ")
    lv_key = "all" if levels_mb is None else "_".join(str(lv) for lv in sorted(levels_mb))
    out_path = cache_dir / "gfs" / cycle_part / f"f{fxx:03d}_uv_{lv_key}.grib2"
    if out_path.exists() and out_path.stat().st_size > 0:
        return out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fetcher = fetcher or _ByteRangeFetcher()
    grib_url = cycle.url(fxx, resolution=resolution)
    idx_url = grib_url + ".idx"

    idx_text = fetcher.get_text(idx_url)
    if idx_text is None:
        raise FileNotFoundError(f"GFS idx not found: {idx_url}")
    records = parse_idx(idx_text)
    selected = select_uv_pressure_records(records, levels_mb=levels_mb)
    if not selected:
        raise RuntimeError(f"No u/v pressure-level records in {idx_url}")

    file_length = fetcher.head_length(grib_url)
    byte_ranges = _compute_byte_ranges(selected, records, file_length)
    with open(out_path, "wb") as fh:
        for start, end in byte_ranges:
            fh.write(fetcher.get_range(grib_url, start, end))
    return out_path


def open_pressure_levels(grib_path: Path, indexpath: str = ""):
    """Open a GFS pressure-level GRIB2 file as an :class:`xarray.Dataset`.

    Mirrors :func:`predictor.weather.hrrr_client.open_pressure_levels`;
    GFS uses the same wgrib2/cfgrib conventions and the same
    ``filter_by_keys`` selection for isobaric u/v.
    """
    import xarray as xr

    return xr.open_dataset(
        str(grib_path),
        engine="cfgrib",
        backend_kwargs={
            "filter_by_keys": {
                "typeOfLevel": "isobaricInhPa",
                "shortName": ["u", "v"],
            },
            "indexpath": indexpath,
        },
    )


def latest_cycle_before(now_utc: datetime, latency_padding_h: float = 4.0) -> GFSCycle:
    """Most-recent GFS cycle that should be fully uploaded by now.

    GFS f000 typically appears ~3h45m after cycle time; we pad to 4 h.
    """
    if now_utc.tzinfo is None or now_utc.tzinfo.utcoffset(now_utc) != timedelta(0):
        raise ValueError("now_utc must be timezone-aware UTC.")
    safe = now_utc - timedelta(hours=latency_padding_h)
    # Floor to the nearest GFS cycle hour
    h = (safe.hour // 6) * 6
    return GFSCycle(cycle_dt=safe.replace(hour=h, minute=0, second=0, microsecond=0))
