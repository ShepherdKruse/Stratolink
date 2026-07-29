#!/usr/bin/env python3
"""Bound Flight-3 geometric darkness against StratoLink-2 reserve screens.

This is deliberately not an endurance qualification.  It reconstructs the
direct-sun horizon along the already cached Flight-3 mean path, then compares
that clear-sky duration with the minimum-capacitance *baseline-only* reserve
screens.  Clouds, panel attitude, frost, cold capacitance/ESR, active work,
conversion loss, and load-step sag can only make the electrical problem worse.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Iterable

import numpy as np


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DEFAULT_TELEMETRY = ROOT / "analysis/antenna/data/telemetry_raw.csv"
DEFAULT_RECONSTRUCTION = (
    Path.home() / ".cache/stratolink/reconstructed_path.npz"
)
DEFAULT_RESERVE = (
    HERE / "logs/stratolink2_supercap_night_reserve_20260726.json"
)
EARTH_RADIUS_KM = 6371.0
SPEED_CAP_MPS = 80.0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def record(path: Path) -> dict[str, object]:
    return {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("telemetry timestamp must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def haversine_m(
    lat_a: float, lon_a: float, lat_b: float, lon_b: float
) -> float:
    phi_a = math.radians(lat_a)
    phi_b = math.radians(lat_b)
    d_phi = phi_b - phi_a
    d_lam = math.radians(lon_b - lon_a)
    term = (
        math.sin(d_phi / 2.0) ** 2
        + math.cos(phi_a) * math.cos(phi_b) * math.sin(d_lam / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS_KM * 1000.0 * math.asin(math.sqrt(term))


def load_waypoints(path: Path) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            try:
                when = parse_time(row["time"])
                lat = float(row["lat"])
                lon = float(row["lon"])
                altitude_m = float(row["altitude_m"])
            except (KeyError, TypeError, ValueError):
                continue
            if not (
                -90.0 <= lat <= 90.0
                and -180.0 <= lon <= 180.0
                and altitude_m > 1000.0
            ):
                continue
            candidates.append(
                {
                    "time": when,
                    "lat": lat,
                    "lon": lon,
                    "altitude_m": altitude_m,
                }
            )
    candidates.sort(key=lambda row: row["time"])

    # Match the reconstruction's stale-tuple filter exactly.
    distinct: list[dict[str, object]] = []
    prior: tuple[float, float, int] | None = None
    for row in candidates:
        key = (
            round(float(row["lat"]), 6),
            round(float(row["lon"]), 6),
            int(float(row["altitude_m"])),
        )
        if key == prior:
            continue
        distinct.append(row)
        prior = key

    accepted: list[dict[str, object]] = []
    for row in distinct:
        if accepted:
            previous = accepted[-1]
            dt_s = (
                row["time"] - previous["time"]
            ).total_seconds()  # type: ignore[operator]
            if dt_s <= 0:
                continue
            speed = haversine_m(
                float(previous["lat"]),
                float(previous["lon"]),
                float(row["lat"]),
                float(row["lon"]),
            ) / dt_s
            if speed > SPEED_CAP_MPS:
                continue
        accepted.append(row)
    if len(accepted) < 2:
        raise ValueError("fewer than two usable Flight-3 waypoints")
    return accepted


def load_timed_path(
    path: Path, waypoints: list[dict[str, object]]
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    cache = np.load(path)
    required = {"full_lon", "full_lat", "way_lons", "way_lats"}
    if set(cache.files) != required:
        raise ValueError("reconstruction cache has unexpected arrays")
    full_lon = np.asarray(cache["full_lon"], dtype=float)
    full_lat = np.asarray(cache["full_lat"], dtype=float)
    way_lon = np.asarray(cache["way_lons"], dtype=float)
    way_lat = np.asarray(cache["way_lats"], dtype=float)
    if not (
        full_lon.ndim == full_lat.ndim == way_lon.ndim == way_lat.ndim == 1
        and len(full_lon) == len(full_lat)
        and len(way_lon) == len(way_lat) == len(waypoints)
        and len(full_lon) >= len(way_lon)
        and np.isfinite(full_lon).all()
        and np.isfinite(full_lat).all()
    ):
        raise ValueError("reconstruction cache shapes or values are invalid")

    observed_lon = np.asarray([float(row["lon"]) for row in waypoints])
    observed_lat = np.asarray([float(row["lat"]) for row in waypoints])
    if not (
        np.allclose(way_lon, observed_lon, rtol=0.0, atol=1e-9)
        and np.allclose(way_lat, observed_lat, rtol=0.0, atol=1e-9)
    ):
        raise ValueError("cached path is not bound to the supplied telemetry")

    anchor_indices: list[int] = []
    start = 0
    for lon, lat in zip(way_lon, way_lat):
        distance = np.hypot(full_lon[start:] - lon, full_lat[start:] - lat)
        relative = int(np.argmin(distance))
        if float(distance[relative]) > 1e-9:
            raise ValueError("a cached waypoint is absent from the full path")
        index = start + relative
        if anchor_indices and index <= anchor_indices[-1]:
            raise ValueError("cached waypoint order is not strictly increasing")
        anchor_indices.append(index)
        start = index + 1
    if anchor_indices[0] != 0 or anchor_indices[-1] != len(full_lon) - 1:
        raise ValueError("full cached path is not endpoint-anchored")

    anchor_t = np.asarray(
        [row["time"].timestamp() for row in waypoints], dtype=float  # type: ignore[union-attr]
    )
    anchor_alt = np.asarray(
        [float(row["altitude_m"]) for row in waypoints], dtype=float
    )
    full_t = np.interp(np.arange(len(full_lon)), anchor_indices, anchor_t)
    full_alt = np.interp(np.arange(len(full_lon)), anchor_indices, anchor_alt)
    if not np.all(np.diff(full_t) > 0):
        raise ValueError("reconstructed timestamps are not strictly increasing")
    return full_t, full_lat, full_lon, full_alt


def solar_elevation_deg(
    unix_s: np.ndarray, lat_deg: np.ndarray, lon_deg: np.ndarray
) -> np.ndarray:
    jd = unix_s / 86400.0 + 2440587.5
    n = jd - 2451545.0
    anomaly = np.radians(np.mod(357.528 + 0.9856003 * n, 360.0))
    mean_lon = np.mod(280.460 + 0.9856474 * n, 360.0)
    ecliptic_lon = np.radians(
        np.mod(
            mean_lon
            + 1.915 * np.sin(anomaly)
            + 0.020 * np.sin(2.0 * anomaly),
            360.0,
        )
    )
    obliquity = np.radians(23.439 - 3.6e-7 * n)
    declination = np.arcsin(np.sin(obliquity) * np.sin(ecliptic_lon))
    right_ascension = np.degrees(
        np.arctan2(
            np.cos(obliquity) * np.sin(ecliptic_lon),
            np.cos(ecliptic_lon),
        )
    )
    gmst = np.mod(280.46061837 + 360.98564736629 * n, 360.0)
    subsolar_lon = np.mod(right_ascension - gmst + 180.0, 360.0) - 180.0
    hour_angle = np.radians(lon_deg - subsolar_lon)
    latitude = np.radians(lat_deg)
    return np.degrees(
        np.arcsin(
            np.sin(latitude) * np.sin(declination)
            + np.cos(latitude) * np.cos(declination) * np.cos(hour_angle)
        )
    )


def horizon_dip_deg(altitude_m: np.ndarray) -> np.ndarray:
    altitude_km = np.maximum(altitude_m, 0.0) / 1000.0
    return np.degrees(
        np.arccos(EARTH_RADIUS_KM / (EARTH_RADIUS_KM + altitude_km))
    )


def dark_intervals(
    unix_s: np.ndarray, sun_margin_deg: np.ndarray
) -> list[tuple[float, float]]:
    if len(unix_s) != len(sun_margin_deg) or len(unix_s) < 2:
        raise ValueError("darkness series is invalid")
    if not np.all(np.diff(unix_s) > 0):
        raise ValueError("darkness timestamps must be strictly increasing")

    intervals: list[tuple[float, float]] = []
    open_start: float | None = float(unix_s[0]) if sun_margin_deg[0] <= 0 else None
    for index in range(1, len(unix_s)):
        earlier = float(sun_margin_deg[index - 1])
        later = float(sun_margin_deg[index])
        if (earlier <= 0) == (later <= 0):
            continue
        fraction = abs(earlier) / (abs(earlier) + abs(later))
        crossing = float(unix_s[index - 1]) + fraction * float(
            unix_s[index] - unix_s[index - 1]
        )
        if earlier > 0 and later <= 0:
            open_start = crossing
        elif open_start is not None:
            intervals.append((open_start, crossing))
            open_start = None
    if open_start is not None:
        intervals.append((open_start, float(unix_s[-1])))
    return intervals


def iso(unix_s: float) -> str:
    return datetime.fromtimestamp(unix_s, tz=timezone.utc).isoformat(
        timespec="seconds"
    )


def build_audit(
    telemetry: Path,
    reconstruction: Path,
    reserve_path: Path,
    *,
    sample_seconds: int = 60,
) -> dict[str, object]:
    if not 10 <= sample_seconds <= 300:
        raise ValueError("sample period must be 10-300 seconds")
    waypoints = load_waypoints(telemetry)
    path_t, path_lat, path_lon, path_alt = load_timed_path(
        reconstruction, waypoints
    )
    sample_t = np.arange(
        path_t[0], path_t[-1] + sample_seconds, sample_seconds, dtype=float
    )
    if sample_t[-1] > path_t[-1]:
        sample_t[-1] = path_t[-1]
    sample_lat = np.interp(sample_t, path_t, path_lat)
    sample_lon = np.interp(sample_t, path_t, path_lon)
    sample_alt = np.interp(sample_t, path_t, path_alt)
    elevation = solar_elevation_deg(sample_t, sample_lat, sample_lon)
    dip = horizon_dip_deg(sample_alt)
    margin = elevation + dip
    intervals = dark_intervals(sample_t, margin)
    completed = [
        {
            "start_utc": iso(start),
            "end_utc": iso(end),
            "hours": round((end - start) / 3600.0, 3),
        }
        for start, end in intervals
        if start > sample_t[0] and end < sample_t[-1]
    ]
    if not completed:
        raise ValueError("reconstruction contains no complete darkness interval")
    longest = max(completed, key=lambda item: float(item["hours"]))

    reserve = json.loads(reserve_path.read_text(encoding="utf-8"))
    runtime: dict[str, float] = {}
    for option in reserve["divider_options"]:
        top = f"{float(option['top_mohm']):.2f}Mohm"
        runtime[top] = float(
            option["baseline_only_runtime_h"]["35uA_plus_6uA_room_leakage"]
        )
    selected = {
        key: {
            "baseline_only_hours": runtime[key],
            "margin_over_longest_geometric_darkness_hours": round(
                runtime[key] - float(longest["hours"]), 3
            ),
        }
        for key in ("8.25Mohm", "7.50Mohm", "7.32Mohm")
    }

    return {
        "passed": False,
        "status": "BLOCKED_PENDING_EXACT_FITTED_CAP_DARKNESS_HIL",
        "scope": (
            "clear-sky direct-sun geometry along the cached Flight-3 mean "
            "reconstruction; not electrical darkness or endurance qualification"
        ),
        "provenance": {
            "telemetry": record(telemetry),
            "reconstructed_mean_path": record(reconstruction),
            "night_reserve_screen": record(reserve_path),
        },
        "method": {
            "accepted_waypoints": len(waypoints),
            "reconstructed_points": len(path_t),
            "sample_seconds": sample_seconds,
            "samples": len(sample_t),
            "speed_rejection_ceiling_mps": SPEED_CAP_MPS,
            "sunlit_rule": "solar elevation > negative geometric horizon dip",
            "altitude_range_m": [
                round(float(sample_alt.min()), 3),
                round(float(sample_alt.max()), 3),
            ],
            "latitude_range_deg": [
                round(float(sample_lat.min()), 6),
                round(float(sample_lat.max()), 6),
            ],
        },
        "geometric_darkness": {
            "complete_intervals": completed,
            "complete_interval_count": len(completed),
            "longest": longest,
            "minimum_solar_margin_deg": round(float(margin.min()), 6),
        },
        "baseline_comparison": selected,
        "gates": {
            "current_divider_baseline_exceeds_reconstructed_geometric_night": (
                selected["8.25Mohm"][
                    "margin_over_longest_geometric_darkness_hours"
                ]
                > 0
            ),
            "safer_7v32_divider_baseline_exceeds_reconstructed_geometric_night": (
                selected["7.32Mohm"][
                    "margin_over_longest_geometric_darkness_hours"
                ]
                > 0
            ),
            "active_cycle_energy_included": False,
            "cloud_and_attitude_outages_bounded": False,
            "cold_capacitance_esr_and_leakage_bounded": False,
            "fitted_capacitance_and_esr_measured": False,
            "actual_brownout_and_sunrise_recovery_measured": False,
        },
        "interpretation": (
            "The reconstructed direct-sun interval is a lower bound on the "
            "electrical darkness the payload must survive. Positive baseline "
            "margin cannot establish launch readiness because it excludes every "
            "GPS, sensor, LoRa TX/RX, watchdog wake, balancer, conversion, cold, "
            "cloud, attitude, aging, and load-step term. The Atlantic interval "
            "also follows a modeled mean path rather than received telemetry. "
            "Use this result only to size the fitted-cap darkness HIL duration; "
            "the audit therefore fails closed."
        ),
        "required_hil": (
            "After charge ceiling and midpoint balancing are resolved, start "
            "from the independently measured worst-case ceiling and run the "
            "exact final assembly in darkness for at least the longest modeled "
            "geometric night plus a cloud/attitude reserve, through real active "
            "cycles, tier crossings, actual BOR, and verified sunrise recovery; "
            "repeat at the cold envelope."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--telemetry", type=Path, default=DEFAULT_TELEMETRY)
    parser.add_argument(
        "--reconstruction", type=Path, default=DEFAULT_RECONSTRUCTION
    )
    parser.add_argument("--night-reserve", type=Path, default=DEFAULT_RESERVE)
    parser.add_argument("--sample-seconds", type=int, default=60)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--allow-blocked", action="store_true")
    args = parser.parse_args()
    audit = build_audit(
        args.telemetry,
        args.reconstruction,
        args.night_reserve,
        sample_seconds=args.sample_seconds,
    )
    encoded = json.dumps(audit, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        if args.output.exists():
            raise SystemExit(
                f"refusing to overwrite darkness evidence: {args.output}"
            )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    if not audit["passed"] and not args.allow_blocked:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
