"""Shared helpers for the Stratolink-3 antenna analysis pipeline.

Credentials are read from the environment (source ~/.config/stratolink/env first):
  SUPABASE_URL              https://iazmnyyfsobucndqncgw.supabase.co
  SBKEY                     Supabase service-role key (preferred name)
  SUPABASE_SERVICE_ROLE_KEY alternate name the webhook uses

Table: public.telemetry  (FLAT schema, one row per uplink).
Per-gateway reception lives in the `gateways` JSONB column:
  [{gateway_id, lat, lon, alt, rssi, snr}, ...]
Only entries with gateway_id == "packetbroker" carry coordinates (Packet Broker
keeps a coarsened lat/lon but strips the real gateway id); NAMED gateways have
null lat/lon. So geometry is computable exactly on the packetbroker receptions.

Position columns: lat, lon, altitude_m.  Timestamp column: `time`.
Device IDs: stratolink-3 (US915/nam1), stratolink-3-eu (EU868/eu1).
(stratolink-2 also present = an earlier board; excluded from flight-3 analysis.)
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
FIGS = HERE / "figs"
DATA.mkdir(exist_ok=True)
FIGS.mkdir(exist_ok=True)

DEVICE_IDS = ["stratolink-3", "stratolink-3-eu"]
REGION_BY_DEVICE = {"stratolink-3": "US", "stratolink-3-eu": "EU"}

# Packet-Broker-anonymized gateway id.
ANON_GATEWAY_IDS = {"packetbroker"}


def get_creds() -> tuple[str, str]:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SBKEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not url or not key:
        sys.stderr.write(
            "ERROR: missing credentials. Set SUPABASE_URL and SBKEY.\n"
            "  set -a; source ~/.config/stratolink/env; set +a\n"
        )
        sys.exit(2)
    return url, key


def rest_headers(key: str) -> dict:
    return {"apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json"}


def is_anonymized(gateway_id) -> bool:
    return gateway_id is None or str(gateway_id).lower() in ANON_GATEWAY_IDS


# ---------------------------------------------------------------------------
# Geometry (spherical Earth, R = 6371.0088 km)
# ---------------------------------------------------------------------------
EARTH_R_KM = 6371.0088


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    """Great-circle surface distance (km) between two lat/lon points (deg)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_R_KM * math.asin(min(1.0, math.sqrt(a)))


def slant_range_km(gc_km: float, alt_balloon_m: float, alt_gw_m: float = 0.0) -> float:
    """Straight-line 3-D range (km), gateway->balloon. Law of cosines on the two
    radii (R+h) with central angle theta = gc/R."""
    R = EARTH_R_KM
    r1 = R + alt_gw_m / 1000.0
    r2 = R + alt_balloon_m / 1000.0
    theta = gc_km / R
    chord_sq = r1 * r1 + r2 * r2 - 2 * r1 * r2 * math.cos(theta)
    return math.sqrt(max(0.0, chord_sq))


def elevation_angle_deg(gc_km: float, alt_balloon_m: float, alt_gw_m: float = 0.0) -> float:
    """Elevation (look-up) angle (deg) at the GATEWAY toward the balloon, above
    the gateway's local horizontal.  elev = atan2(r2*cos(th)-r1, r2*sin(th)),
    th = gc/R.  Negative => geometrically below horizon."""
    R = EARTH_R_KM
    r1 = R + alt_gw_m / 1000.0
    r2 = R + alt_balloon_m / 1000.0
    theta = gc_km / R
    return math.degrees(math.atan2(r2 * math.cos(theta) - r1, r2 * math.sin(theta)))


def depression_angle_deg(gc_km: float, alt_balloon_m: float, alt_gw_m: float = 0.0) -> float:
    """Depression (look-down) angle (deg) at the BALLOON toward the gateway,
    below the balloon's local horizontal. This is the angle the balloon's own
    antenna sees: 0 deg = out to the side / local horizon, 90 deg = straight
    down (nadir).  depr = atan2(r2-r1*cos(th), r1*sin(th)),  th = gc/R."""
    R = EARTH_R_KM
    r1 = R + alt_gw_m / 1000.0
    r2 = R + alt_balloon_m / 1000.0
    theta = gc_km / R
    return math.degrees(math.atan2(r2 - r1 * math.cos(theta), r1 * math.sin(theta)))
