"""
NOAA HRRR client — anonymous S3 access to ``s3://noaa-hrrr-bdp-pds``.

The HRRR (3 km Lambert Conformal CONUS) runs hourly; cycles at 00/06/12/18Z
are extended to 48 h forecast, the other cycles to 18 h. We pull the
**pressure-level** product ``wrfprsfFF.grib2`` because it carries
``UGRD``/``VGRD`` on a fixed set of isobaric surfaces.

Two fetch modes:

- **Partial** (default): parse the ``.idx`` sidecar in the bucket and
  issue HTTP byte-range GETs against ``noaa-hrrr-bdp-pds.s3.amazonaws.com``
  for only the u/v messages we want. ~10 MB per cycle vs. ~150 MB for
  the full file. The concatenated bytes are a valid mini-GRIB2 that
  cfgrib opens normally.

- **Full**: plain anonymous HTTP GET of the entire ``.grib2``.

Forecast-hour availability and latency are documented inline in
:func:`list_available_cycles`. Cached files live under a caller-supplied
directory and are keyed by (cycle, product, fxx, vars-hash).

See ``predictor/weather/README.md`` (recon doc) for the GRIB2 message
layout and the cfgrib filter dict used in :func:`open_pressure_levels`.
"""

from __future__ import annotations

import hashlib
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)

S3_BUCKET = "noaa-hrrr-bdp-pds"
S3_HTTPS_BASE = f"https://{S3_BUCKET}.s3.amazonaws.com"

# Domains supported by HRRR on AWS Open Data
DOMAIN_CONUS = "conus"
DOMAIN_ALASKA = "alaska"

# Cycles with extended (48 h) forecast horizon
EXTENDED_CYCLES_UTC = (0, 6, 12, 18)


@dataclass(frozen=True)
class HRRRCycle:
    """An HRRR model cycle on AWS Open Data.

    Attributes
    ----------
    cycle_dt : datetime
        Cycle initialization time. Must be UTC and hour-aligned
        (minute, second, microsecond all zero).
    domain : str
        ``"conus"`` (default) or ``"alaska"``.
    """

    cycle_dt: datetime
    domain: str = DOMAIN_CONUS

    def __post_init__(self) -> None:
        if self.cycle_dt.tzinfo is None or self.cycle_dt.tzinfo.utcoffset(self.cycle_dt) != timedelta(0):
            raise ValueError("cycle_dt must be timezone-aware UTC.")
        if self.cycle_dt.minute or self.cycle_dt.second or self.cycle_dt.microsecond:
            raise ValueError("cycle_dt must be hour-aligned.")
        if self.domain not in (DOMAIN_CONUS, DOMAIN_ALASKA):
            raise ValueError(f"Unknown HRRR domain: {self.domain!r}")

    @property
    def s3_prefix(self) -> str:
        return f"hrrr.{self.cycle_dt:%Y%m%d}/{self.domain}/"

    def key(self, product: str, fxx: int) -> str:
        """S3 key for a given product + forecast hour."""
        return f"{self.s3_prefix}hrrr.t{self.cycle_dt:%H}z.{product}f{fxx:02d}.grib2"

    def url(self, product: str, fxx: int) -> str:
        return f"{S3_HTTPS_BASE}/{self.key(product, fxx)}"

    def max_fxx(self) -> int:
        return 48 if self.cycle_dt.hour in EXTENDED_CYCLES_UTC else 18


@dataclass(frozen=True)
class _IdxRecord:
    """One row from the wgrib2-style ``.idx`` sidecar."""

    msg_no: int        # message number within the GRIB2 file
    byte_start: int    # byte offset in the file
    short_name: str    # e.g. "UGRD", "VGRD"
    level: str         # e.g. "500 mb", "10 m above ground"
    fcst: str          # e.g. "anl", "1 hour fcst"


@dataclass
class _ByteRangeFetcher:
    """HTTP byte-range fetcher with a small built-in retry."""

    timeout_s: float = 30.0
    retries: int = 3

    def head_length(self, url: str) -> int | None:
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                cl = resp.headers.get("Content-Length")
                return int(cl) if cl is not None else None
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise

    def get_text(self, url: str) -> str | None:
        for attempt in range(self.retries):
            try:
                with urllib.request.urlopen(url, timeout=self.timeout_s) as resp:
                    return resp.read().decode("utf-8", errors="replace")
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return None
                if attempt == self.retries - 1:
                    raise
            except urllib.error.URLError:
                if attempt == self.retries - 1:
                    raise

    def get_range(self, url: str, start: int, end_inclusive: int) -> bytes:
        req = urllib.request.Request(
            url,
            headers={"Range": f"bytes={start}-{end_inclusive}"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            return resp.read()

    def get_full(self, url: str) -> bytes:
        with urllib.request.urlopen(url, timeout=self.timeout_s) as resp:
            return resp.read()


def parse_idx(idx_text: str) -> list[_IdxRecord]:
    """Parse the wgrib2-style ``.idx`` sidecar HRRR ships next to each GRIB2.

    Format (one record per line, fields colon-delimited)::

        <msg_no>:<byte_start>:d=<YYYYMMDDHH>:<short_name>:<level>:<fcst>:

    Trailing colon and any extra metadata fields are ignored.
    """
    records: list[_IdxRecord] = []
    for raw in idx_text.splitlines():
        if not raw.strip():
            continue
        parts = raw.split(":")
        if len(parts) < 6:
            continue
        try:
            msg_no = int(parts[0])
            byte_start = int(parts[1])
        except ValueError:
            continue
        records.append(
            _IdxRecord(
                msg_no=msg_no,
                byte_start=byte_start,
                short_name=parts[3],
                level=parts[4],
                fcst=parts[5],
            )
        )
    return records


def select_uv_pressure_records(
    records: list[_IdxRecord],
    levels_mb: Iterable[int] | None = None,
) -> list[_IdxRecord]:
    """Select ``UGRD``/``VGRD`` records on isobaric ('mb') levels.

    Parameters
    ----------
    records : list[_IdxRecord]
        Parsed sidecar records.
    levels_mb : iterable of int, optional
        Restrict to these pressure levels in millibars. If ``None``,
        all isobaric u/v records are returned.

    Returns
    -------
    list[_IdxRecord]
        Filtered records, sorted by byte offset (so concatenating
        them yields a valid mini-GRIB2 file).
    """
    wanted_vars = {"UGRD", "VGRD"}
    out: list[_IdxRecord] = []
    levels_set = {f"{lv} mb" for lv in levels_mb} if levels_mb is not None else None
    for r in records:
        if r.short_name not in wanted_vars:
            continue
        # Pressure-level rows look like "<NNN> mb"; surface/height-AGL rows do not.
        if not r.level.endswith(" mb"):
            continue
        if levels_set is not None and r.level not in levels_set:
            continue
        out.append(r)
    out.sort(key=lambda r: r.byte_start)
    return out


def _compute_byte_ranges(
    selected: list[_IdxRecord],
    all_records: list[_IdxRecord],
    file_length: int | None,
) -> list[tuple[int, int]]:
    """Convert a list of records to ``[(start, end_inclusive), ...]`` byte ranges.

    Each GRIB2 message ends just before the next message's byte offset
    in the file, or at EOF for the last message.
    """
    sorted_all = sorted(all_records, key=lambda r: r.byte_start)
    by_offset = {r.byte_start: i for i, r in enumerate(sorted_all)}

    ranges: list[tuple[int, int]] = []
    for r in selected:
        idx = by_offset[r.byte_start]
        if idx + 1 < len(sorted_all):
            end_exclusive = sorted_all[idx + 1].byte_start
        elif file_length is not None:
            end_exclusive = file_length
        else:
            # Fall back to a large open range; HTTP will clip at EOF
            end_exclusive = r.byte_start + 50 * 1024 * 1024
        ranges.append((r.byte_start, end_exclusive - 1))
    return ranges


def _cache_path(
    cache_dir: Path,
    cycle: HRRRCycle,
    product: str,
    fxx: int,
    levels_mb: Iterable[int] | None,
    partial: bool,
) -> Path:
    cycle_part = cycle.cycle_dt.strftime("%Y%m%dT%HZ")
    if partial:
        lv_key = "all" if levels_mb is None else "_".join(str(lv) for lv in sorted(levels_mb))
        vars_hash = hashlib.blake2b(("UGRD_VGRD|" + lv_key).encode(), digest_size=4).hexdigest()
        fname = f"{product}_f{fxx:02d}_uv_{vars_hash}.grib2"
    else:
        fname = f"{product}_f{fxx:02d}_full.grib2"
    return cache_dir / cycle.domain / cycle_part / fname


def download_uv_pressure_levels(
    cycle: HRRRCycle,
    fxx: int,
    cache_dir: Path,
    levels_mb: Iterable[int] | None = None,
    product: str = "wrfprs",
    fetcher: _ByteRangeFetcher | None = None,
) -> Path:
    """Download just the u/v pressure-level messages for one cycle/fxx.

    Uses ``.idx`` byte-range partial download for ~10× bandwidth
    savings vs. the full file. Cached files are returned as-is on
    repeat calls.

    Parameters
    ----------
    cycle : HRRRCycle
    fxx : int
        Forecast hour, 0 to ``cycle.max_fxx()``.
    cache_dir : Path
        Directory under which cached GRIB2 files are stored.
    levels_mb : iterable of int, optional
        Restrict to these pressure levels (mb). Default: all isobaric
        levels in the file (39 standard).
    product : str
        Default ``"wrfprs"`` — the pressure-level product.
    fetcher : _ByteRangeFetcher, optional
        Override for testing.

    Returns
    -------
    Path
        Local path to the cached mini-GRIB2 file.
    """
    if fxx < 0 or fxx > cycle.max_fxx():
        raise ValueError(f"fxx={fxx} out of range [0, {cycle.max_fxx()}] for cycle {cycle.cycle_dt}.")

    cache_dir = Path(cache_dir)
    out_path = _cache_path(cache_dir, cycle, product, fxx, levels_mb, partial=True)
    if out_path.exists() and out_path.stat().st_size > 0:
        logger.debug("HRRR cache hit: %s", out_path)
        return out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fetcher = fetcher or _ByteRangeFetcher()
    grib_url = cycle.url(product, fxx)
    idx_url = grib_url + ".idx"

    idx_text = fetcher.get_text(idx_url)
    if idx_text is None:
        raise FileNotFoundError(f"HRRR idx not found: {idx_url}")
    records = parse_idx(idx_text)
    selected = select_uv_pressure_records(records, levels_mb=levels_mb)
    if not selected:
        raise RuntimeError(f"No u/v pressure-level records in {idx_url}")

    file_length = fetcher.head_length(grib_url)
    byte_ranges = _compute_byte_ranges(selected, records, file_length)

    logger.info(
        "HRRR partial fetch: %d messages, %.1f MB",
        len(selected),
        sum(b - a + 1 for a, b in byte_ranges) / 1e6,
    )
    with open(out_path, "wb") as fh:
        for start, end in byte_ranges:
            fh.write(fetcher.get_range(grib_url, start, end))
    return out_path


def open_pressure_levels(
    grib_path: Path,
    indexpath: str = "",
):
    """Open a pressure-level GRIB2 file as an :class:`xarray.Dataset`.

    Uses the cfgrib engine with ``filter_by_keys`` set to the
    isobaric ``u``/``v`` subset documented in the recon report.
    ``indexpath=""`` disables cfgrib's per-file ``.idx`` cache so we
    don't try to write into read-only locations or pollute the cache
    directory with a second flavor of ``.idx``.

    Parameters
    ----------
    grib_path : Path
        Local GRIB2 file.
    indexpath : str
        Passed through to cfgrib. Empty string disables the cache.
        Set to e.g. ``"{path}.{short_hash}.idx"`` to keep a cache
        next to the source file.

    Returns
    -------
    xarray.Dataset
    """
    import xarray as xr  # local import — cfgrib + xarray are optional extras

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


@dataclass(frozen=True)
class _LatestCycle:
    cycle: HRRRCycle
    fxx: int
    valid_time: datetime


def latest_for_valid_time(
    valid_time: datetime,
    *,
    domain: str = DOMAIN_CONUS,
    max_fxx: int = 18,
    lookback_hours: int = 24,
    fetcher: _ByteRangeFetcher | None = None,
    product: str = "wrfprs",
) -> _LatestCycle:
    """Find the freshest cycle whose forecast covers ``valid_time``.

    Prefers lower forecast hours (less-stale forecast). HEAD-checks
    the bucket for the ``wrfprsfFF.grib2`` file's existence.

    Parameters
    ----------
    valid_time : datetime
        Target valid time, timezone-aware UTC.
    domain : str
        ``"conus"`` (default) or ``"alaska"``.
    max_fxx : int
        Maximum forecast hour to consider. Default 18 since every cycle
        guarantees at least 18 h; raise to 48 if you need long-range
        from the extended cycles only.
    lookback_hours : int
        How many cycle hours to walk backwards from the most recent
        cycle <= valid_time.
    fetcher : _ByteRangeFetcher, optional
    product : str

    Returns
    -------
    _LatestCycle
        (cycle, fxx, valid_time) such that ``cycle.cycle_dt + fxx*1h == valid_time``.

    Raises
    ------
    FileNotFoundError
        If no available cycle covers the requested valid time within
        the lookback window.
    """
    if valid_time.tzinfo is None or valid_time.tzinfo.utcoffset(valid_time) != timedelta(0):
        raise ValueError("valid_time must be timezone-aware UTC.")
    fetcher = fetcher or _ByteRangeFetcher()

    # Walk cycles from valid_time down to (valid_time - lookback_hours);
    # for each, the implied fxx is (valid_time - cycle_dt) in hours.
    candidates: list[tuple[HRRRCycle, int]] = []
    base = valid_time.replace(minute=0, second=0, microsecond=0)
    for h in range(0, lookback_hours + 1):
        cycle_dt = base - timedelta(hours=h)
        fxx = h
        cycle = HRRRCycle(cycle_dt=cycle_dt, domain=domain)
        if fxx > min(max_fxx, cycle.max_fxx()):
            continue
        candidates.append((cycle, fxx))

    for cycle, fxx in candidates:
        url = cycle.url(product, fxx) + ".idx"
        # idx is small; HEAD on it is the cheapest existence check
        if fetcher.head_length(url) is not None:
            return _LatestCycle(cycle=cycle, fxx=fxx, valid_time=valid_time)
    raise FileNotFoundError(
        f"No HRRR cycle in the last {lookback_hours} h covers "
        f"valid_time={valid_time.isoformat()} (domain={domain}, max_fxx={max_fxx})."
    )
