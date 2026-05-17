"""End-to-end verification: hit the API with a realistic packet and use real NWP.

Spins up a TestClient against ``predictor.api.predict.create_app()`` with
the **default** wind-field builder (no dependency override), so the
request flows through :func:`predictor.weather.wind_factory.build_wind_field`
and pulls real GFS or HRRR data from S3.

Run from ``simulation/``::

    python -m scripts.verify_phase6_api_live
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from predictor.api.predict import create_app


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    app = create_app()
    client = TestClient(app)

    # Use a launch ~12 h in the past so the relevant cycle is definitely uploaded.
    t0 = (datetime.now(timezone.utc) - timedelta(hours=12)).replace(
        minute=0, second=0, microsecond=0
    )

    payload = {
        "telemetry": {
            "device_id": "verify-phase6-001",
            "time": t0.isoformat(),
            "lat": 40.015,
            "lon": -105.27,    # Boulder, CO — inside HRRR's CONUS
            # No altitude_m → solved from the default pico-balloon params
        },
        "duration_hours": 6.0,
        "n_ensemble": 30,
        "horizons_hours": [3.0, 6.0],
        "seed": 0,
    }

    print(f"POST /predict   target_time={t0.isoformat()}")
    print(f"               lat={payload['telemetry']['lat']}  lon={payload['telemetry']['lon']}")
    print()

    r = client.post("/predict", json=payload)
    if r.status_code != 200:
        print(f"FAIL: HTTP {r.status_code}", file=sys.stderr)
        print(r.text, file=sys.stderr)
        return 1
    data = r.json()

    ws = data["wind_source"]
    print(f"Wind source: {ws['source'].upper()}")
    if ws["cycle"]:
        print(f"  cycle  : {ws['cycle']}")
        print(f"  fxx    : {ws['fxx_start']} → {ws['fxx_end']}")
    print(f"  levels : {ws['levels_hpa']} hPa")
    print(f"  region : {ws['region']}")
    print()

    print(f"Float altitude  : {data['float_altitude_m']:.0f} m")
    bp = data["balloon_params"]
    print(
        f"Balloon         : env={bp['envelope_volume_m3']} m^3  "
        f"sys={bp['system_mass_kg']} kg  gas={bp['lift_gas']}/{bp['gas_mass_kg']} kg"
    )
    print(f"Trajectory      : {len(data['trajectory'])} samples")
    p0 = data["trajectory"][0]
    pN = data["trajectory"][-1]
    print(
        f"  t=0     lat={p0['lat']:.3f}  lon={p0['lon']:.3f}  σ1={p0['sigma1_radius_km']:.2f} km"
    )
    print(
        f"  t=end   lat={pN['lat']:.3f}  lon={pN['lon']:.3f}  σ1={pN['sigma1_radius_km']:.2f} km"
    )
    print()
    print("CEP horizons:")
    for h in data["horizons"]:
        print(
            f"  {h['horizon_hours']} h  σ1={h['cep_km']:.2f} km   σ2={h['cep_2sigma_km']:.2f} km"
        )

    print()
    print("Phase 6 (real-NWP API) verification: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
