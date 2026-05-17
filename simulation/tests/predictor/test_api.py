"""Phase 5 verification: round-trip sample telemetry packets through the API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from predictor.api.predict import (
    DEFAULT_ENVELOPE_VOLUME_M3,
    DEFAULT_GAS_MASS_KG,
    DEFAULT_LIFT_GAS,
    DEFAULT_SYSTEM_MASS_KG,
    create_app,
    get_wind_field_builder,
)
from predictor.weather.wind_factory import WindFieldMetadata
from predictor.weather.wind_field import ConstantWindField


def _build_app(u: float = 10.0, v: float = 0.0):
    """Build an app whose wind field is a deterministic constant — tests
    must not depend on live HRRR/GFS S3 reachability."""
    app = create_app()

    def _stub_builder():
        def _builder(target_time, duration_hours, lat, lon, altitude_m):
            wf = ConstantWindField(u_m_s=u, v_m_s=v)
            meta = WindFieldMetadata(
                source="constant",
                cycle=None,
                fxx_start=None,
                fxx_end=None,
                levels_hpa=(),
                region="test",
                grid_extent=None,
            )
            return wf, meta
        return _builder

    app.dependency_overrides[get_wind_field_builder] = _stub_builder
    return app


def test_round_trip_sample_telemetry_packet():
    """Phase 5 verification gate: a realistic telemetry payload goes in,
    a well-shaped trajectory+uncertainty response comes out."""
    app = _build_app(u=10.0, v=0.0)
    client = TestClient(app)
    payload = {
        "telemetry": {
            "device_id": "test-balloon-001",
            "time": "2026-05-17T12:00:00+00:00",
            "lat": 40.0,
            "lon": -105.0,
            "altitude_m": 20000.0,
        },
        "duration_hours": 6.0,
        "n_ensemble": 30,
        "horizons_hours": [3.0, 6.0],
        "seed": 7,
    }
    r = client.post("/predict", json=payload)
    assert r.status_code == 200, r.text
    data = r.json()

    # Identity
    assert data["device_id"] == "test-balloon-001"
    assert data["float_altitude_m"] == 20000.0
    assert data["n_ensemble"] == 30
    assert data["valid_from"].startswith("2026-05-17T12:00:00")

    # Trajectory shape: 6 h × 12 samples/h + 1 (inclusive endpoints) = 73
    assert len(data["trajectory"]) == 73
    assert data["trajectory"][0]["t_offset_s"] == 0.0
    assert data["trajectory"][-1]["t_offset_s"] == 21600.0

    # Each trajectory point has the expected unit-bearing fields
    p = data["trajectory"][0]
    for key in ("t_offset_s", "time", "lat", "lon", "altitude_m",
                "sigma1_radius_km", "sigma2_radius_km"):
        assert key in p, f"missing field {key}"

    # Uncertainty cones widen with time (Phase 4 √t behavior survives the API path)
    s_start = data["trajectory"][0]["sigma1_radius_km"]
    s_end = data["trajectory"][-1]["sigma1_radius_km"]
    assert s_end > s_start

    # CEP horizons
    horizons_map = {h["horizon_hours"]: h for h in data["horizons"]}
    assert set(horizons_map.keys()) == {3.0, 6.0}
    assert horizons_map[6.0]["cep_km"] > horizons_map[3.0]["cep_km"]
    assert horizons_map[3.0]["cep_2sigma_km"] >= horizons_map[3.0]["cep_km"]


def test_altitude_derived_from_balloon_params_when_telemetry_alt_missing():
    """Field 'altitude_m' is optional; when omitted, float_solver fills it
    from the (defaulted or overridden) balloon physical params."""
    app = _build_app()
    client = TestClient(app)
    payload = {
        "telemetry": {
            "device_id": "alt-derived",
            "time": "2026-05-17T12:00:00+00:00",
            "lat": 40.0,
            "lon": -105.0,
        },
        "duration_hours": 3.0,
        "n_ensemble": 10,
        "seed": 1,
    }
    r = client.post("/predict", json=payload)
    assert r.status_code == 200, r.text
    data = r.json()
    # Default balloon (0.5 m³, 12 g + 2 g H2) floats in the stratosphere
    assert 20000.0 < data["float_altitude_m"] < 32000.0
    bp = data["balloon_params"]
    assert bp["envelope_volume_m3"] == DEFAULT_ENVELOPE_VOLUME_M3
    assert bp["system_mass_kg"] == DEFAULT_SYSTEM_MASS_KG
    assert bp["lift_gas"] == DEFAULT_LIFT_GAS
    assert bp["gas_mass_kg"] == DEFAULT_GAS_MASS_KG


def test_inline_balloon_params_override_defaults():
    """Body-level balloon_params must win over the defaults (DB lookup is
    mocked to return None in this app instance)."""
    app = _build_app()
    client = TestClient(app)
    payload = {
        "telemetry": {
            "device_id": "override-test",
            "time": "2026-05-17T12:00:00+00:00",
            "lat": 40.0,
            "lon": -105.0,
        },
        "balloon_params": {
            "envelope_volume_m3": 1.0,
            "system_mass_kg": 0.020,
            "lift_gas": "He",
            "gas_mass_kg": 0.005,
        },
        "duration_hours": 1.0,
        "n_ensemble": 5,
    }
    r = client.post("/predict", json=payload)
    assert r.status_code == 200, r.text
    bp = r.json()["balloon_params"]
    assert bp["envelope_volume_m3"] == 1.0
    assert bp["system_mass_kg"] == 0.020
    assert bp["lift_gas"] == "He"
    assert bp["gas_mass_kg"] == 0.005


def test_reproducible_with_seed():
    app = _build_app()
    client = TestClient(app)
    payload = {
        "telemetry": {
            "device_id": "seed-test",
            "time": "2026-05-17T12:00:00+00:00",
            "lat": 40.0,
            "lon": -105.0,
            "altitude_m": 20000.0,
        },
        "duration_hours": 3.0,
        "n_ensemble": 20,
        "seed": 99,
    }
    a = client.post("/predict", json=payload).json()
    b = client.post("/predict", json=payload).json()
    # issued_at will differ across requests but trajectory must be deterministic
    assert a["trajectory"] == b["trajectory"]
    assert a["horizons"] == b["horizons"]


def test_validation_rejects_bad_inputs():
    app = _build_app()
    client = TestClient(app)
    base = {
        "telemetry": {
            "device_id": "x",
            "time": "2026-05-17T12:00:00+00:00",
            "lat": 40.0,
            "lon": -105.0,
            "altitude_m": 20000.0,
        },
        "duration_hours": 1.0,
        "n_ensemble": 5,
    }

    bad = dict(base)
    bad["duration_hours"] = 0.0
    assert client.post("/predict", json=bad).status_code == 422

    bad = dict(base)
    bad["n_ensemble"] = 1
    assert client.post("/predict", json=bad).status_code == 422

    bad = dict(base)
    bad["telemetry"] = dict(base["telemetry"])
    bad["telemetry"]["lat"] = 100.0
    assert client.post("/predict", json=bad).status_code == 422


def test_unsolvable_balloon_returns_422():
    """A balloon too heavy to lift returns a clean 422, not a 500."""
    app = _build_app()
    client = TestClient(app)
    payload = {
        "telemetry": {
            "device_id": "too-heavy",
            "time": "2026-05-17T12:00:00+00:00",
            "lat": 40.0,
            "lon": -105.0,
            # No altitude → solver path
        },
        "balloon_params": {
            "envelope_volume_m3": 0.1,
            "system_mass_kg": 100.0,  # absurdly heavy for 0.1 m^3 envelope
            "lift_gas": "H2",
            "gas_mass_kg": 0.002,
        },
        "duration_hours": 1.0,
        "n_ensemble": 5,
    }
    r = client.post("/predict", json=payload)
    assert r.status_code == 422
    assert "unsolvable" in r.json()["detail"].lower() or "too heavy" in r.json()["detail"].lower()


def test_health_endpoint():
    client = TestClient(_build_app())
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert "version" in r.json()


def test_naive_timestamp_treated_as_utc():
    """Telemetry timestamps without timezone info are assumed to be UTC."""
    app = _build_app()
    client = TestClient(app)
    payload = {
        "telemetry": {
            "device_id": "naive-time",
            "time": "2026-05-17T12:00:00",  # no tz
            "lat": 40.0,
            "lon": -105.0,
            "altitude_m": 20000.0,
        },
        "duration_hours": 1.0,
        "n_ensemble": 5,
        "seed": 1,
    }
    r = client.post("/predict", json=payload)
    assert r.status_code == 200, r.text
    valid_from = r.json()["valid_from"]
    assert valid_from.endswith("+00:00") or valid_from.endswith("Z")
