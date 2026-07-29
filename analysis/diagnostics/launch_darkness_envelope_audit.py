#!/usr/bin/env python3
"""Project clear-sky night growth after the planned 2026-07-31 launch."""

from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta, timezone
import json
from pathlib import Path

import numpy as np

from flight3_darkness_audit import (
    DEFAULT_RESERVE,
    dark_intervals,
    horizon_dip_deg,
    record,
    solar_elevation_deg,
)


DEFAULT_LAUNCH_DATE = date(2026, 7, 31)
# Bound to the prior flight's accepted reconstructed corridor rather than
# pretending the next trajectory is known.
FLIGHT3_MAX_LATITUDE_DEG = 45.995252
FLIGHT3_MAX_ALTITUDE_M = 10040.999


def geometric_nights(
    launch_date: date,
    days: int,
    latitude_deg: float,
    altitude_m: float,
    *,
    sample_seconds: int = 60,
) -> list[dict[str, object]]:
    if not 1 <= days <= 366:
        raise ValueError("mission duration must be 1-366 days")
    if not -90.0 <= latitude_deg <= 90.0:
        raise ValueError("latitude is invalid")
    if not 0.0 <= altitude_m <= 60_000.0:
        raise ValueError("altitude is invalid")
    if not 10 <= sample_seconds <= 300:
        raise ValueError("sample period must be 10-300 seconds")

    start = datetime.combine(
        launch_date - timedelta(days=1), time.min, tzinfo=timezone.utc
    ).timestamp()
    end = datetime.combine(
        launch_date + timedelta(days=days + 2),
        time.min,
        tzinfo=timezone.utc,
    ).timestamp()
    unix_s = np.arange(start, end + sample_seconds, sample_seconds, dtype=float)
    latitude = np.full_like(unix_s, latitude_deg)
    longitude = np.zeros_like(unix_s)
    altitude = np.full_like(unix_s, altitude_m)
    margin = (
        solar_elevation_deg(unix_s, latitude, longitude)
        + horizon_dip_deg(altitude)
    )
    intervals = dark_intervals(unix_s, margin)
    mission_end = launch_date + timedelta(days=days)
    result: list[dict[str, object]] = []
    for dark_start, dark_end in intervals:
        start_date = datetime.fromtimestamp(
            dark_start, tz=timezone.utc
        ).date()
        midpoint = datetime.fromtimestamp(
            (dark_start + dark_end) / 2.0, tz=timezone.utc
        ).date()
        # At Greenwich the equation of time can move solar midnight across
        # 00:00 UTC, making midpoint-date selection return 89 or 91 nights.
        # Sunset/start date is unambiguous and gives one complete night per
        # mission day.
        if not launch_date <= start_date < mission_end:
            continue
        result.append(
            {
                "start_date": start_date.isoformat(),
                "midpoint_date": midpoint.isoformat(),
                "start_utc": datetime.fromtimestamp(
                    dark_start, tz=timezone.utc
                ).isoformat(timespec="seconds"),
                "end_utc": datetime.fromtimestamp(
                    dark_end, tz=timezone.utc
                ).isoformat(timespec="seconds"),
                "hours": round((dark_end - dark_start) / 3600.0, 3),
            }
        )
    if len(result) != days:
        raise ValueError(
            f"expected {days} complete nights, reconstructed {len(result)}"
        )
    return result


def first_exceedance(
    nights: list[dict[str, object]], reserve_hours: float
) -> dict[str, object] | None:
    for night in nights:
        if float(night["hours"]) > reserve_hours:
            return {
                "midpoint_date": night["midpoint_date"],
                "night_hours": night["hours"],
                "baseline_hours": reserve_hours,
                "deficit_hours": round(
                    float(night["hours"]) - reserve_hours, 3
                ),
            }
    return None


def build_audit(
    reserve_path: Path,
    *,
    launch_date: date = DEFAULT_LAUNCH_DATE,
    days: int = 90,
    latitude_deg: float = FLIGHT3_MAX_LATITUDE_DEG,
    altitude_m: float = FLIGHT3_MAX_ALTITUDE_M,
    sample_seconds: int = 60,
) -> dict[str, object]:
    nights = geometric_nights(
        launch_date,
        days,
        latitude_deg,
        altitude_m,
        sample_seconds=sample_seconds,
    )
    reserve = json.loads(reserve_path.read_text(encoding="utf-8"))
    runtime: dict[str, float] = {}
    for option in reserve["divider_options"]:
        key = f"{float(option['top_mohm']):.2f}Mohm"
        runtime[key] = float(
            option["baseline_only_runtime_h"]["35uA_plus_6uA_room_leakage"]
        )
    selected = {}
    for key in ("8.25Mohm", "7.50Mohm", "7.32Mohm"):
        selected[key] = {
            "baseline_only_hours": runtime[key],
            "launch_night_margin_hours": round(
                runtime[key] - float(nights[0]["hours"]), 3
            ),
            "first_clear_sky_night_exceedance": first_exceedance(
                nights, runtime[key]
            ),
        }

    first_30 = nights[: min(30, len(nights))]
    longest_30 = max(first_30, key=lambda row: float(row["hours"]))
    longest_all = max(nights, key=lambda row: float(row["hours"]))
    return {
        "passed": False,
        "status": "BLOCKED_PENDING_MISSION_ENERGY_ARCHITECTURE_AND_HIL",
        "scope": (
            "stationary clear-sky geometry at Flight-3's maximum accepted "
            "latitude and altitude; not a next-flight trajectory or electrical "
            "darkness/endurance prediction"
        ),
        "provenance": {"night_reserve_screen": record(reserve_path)},
        "inputs": {
            "launch_date": launch_date.isoformat(),
            "mission_days": days,
            "latitude_deg": latitude_deg,
            "altitude_m": altitude_m,
            "sample_seconds": sample_seconds,
            "latitude_altitude_basis": (
                "maximum accepted values on the Flight-3 cached mean reconstruction"
            ),
        },
        "geometric_darkness": {
            "launch_night": nights[0],
            "longest_first_30_days": longest_30,
            "longest_modeled": longest_all,
            "nights": nights,
        },
        "baseline_comparison": selected,
        "gates": {
            "next_trajectory_latitude_bounded": False,
            "cloud_and_attitude_outages_bounded": False,
            "active_cycle_energy_included": False,
            "cold_and_aging_included": False,
            "fitted_cap_darkness_hil_passed": False,
        },
        "interpretation": (
            "Night length grows after the planned July 31 launch. A reserve "
            "that merely covers launch night is not adequate for a long-duration "
            "balloon. Clear-sky geometric exceedance is itself a hard baseline "
            "failure; a later or absent exceedance is not a pass because active "
            "loads, clouds, panel attitude, cold, conversion, balancing, aging, "
            "and trajectory uncertainty are excluded."
        ),
        "required_resolution": (
            "Choose and qualify an energy architecture and voltage-safe charge "
            "ceiling that covers the intended mission season and latitude, then "
            "run exact-assembly darkness/cold HIL with real duty cycles through "
            "BOR and sunrise recovery."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--night-reserve", type=Path, default=DEFAULT_RESERVE)
    parser.add_argument(
        "--launch-date", type=date.fromisoformat, default=DEFAULT_LAUNCH_DATE
    )
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument(
        "--latitude-deg", type=float, default=FLIGHT3_MAX_LATITUDE_DEG
    )
    parser.add_argument(
        "--altitude-m", type=float, default=FLIGHT3_MAX_ALTITUDE_M
    )
    parser.add_argument("--sample-seconds", type=int, default=60)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--allow-blocked", action="store_true")
    args = parser.parse_args()
    audit = build_audit(
        args.night_reserve,
        launch_date=args.launch_date,
        days=args.days,
        latitude_deg=args.latitude_deg,
        altitude_m=args.altitude_m,
        sample_seconds=args.sample_seconds,
    )
    payload = json.dumps(audit, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        if args.output.exists():
            raise SystemExit(
                f"refusing to overwrite launch-darkness evidence: {args.output}"
            )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    if not audit["passed"] and not args.allow_blocked:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
