"""
FastAPI app for the Stratolink trajectory predictor.

``POST /predict``
    Body: a telemetry packet (field naming matches the Supabase
    ``telemetry`` schema) plus optional balloon physical params.
    Returns: median trajectory + 1σ/2σ uncertainty radii at each
    sample, plus CEP at requested horizons (default 3 h, 6 h, 10 h).

``GET /health``
    Liveness check.

Dependency injection
--------------------
The wind-field source and the device → balloon-params lookup are both
:func:`fastapi.Depends`-style factories. Tests override them with
synthetic stand-ins via ``app.dependency_overrides[...]``. Production
wiring (HRRR / GFS for wind, Supabase ``devices`` row for params) is
slotted in by the deployment layer — keeping it out of the API module
keeps the request handler pure-Python and testable without network.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, List, Optional

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from predictor.buoyancy.float_solver import LiftGas, compute_float_altitude
from predictor.trajectory.ensemble import (
    DEFAULT_N_MEMBERS,
    cep_radius_km,
    run_ensemble,
)
from predictor.trajectory.integrator import GeodeticPosition
from predictor.weather.wind_factory import (
    WindFieldMetadata,
    build_wind_field,
)
from predictor.weather.wind_field import WindField


# A WindFieldBuilder takes (target_time, duration_hours, lat, lon, altitude_m)
# and returns (WindField, WindFieldMetadata). It's a factory because the wind
# field depends on the request — different telemetry packets need different
# HRRR/GFS cycles, regions, and level subsets.
WindFieldBuilder = Callable[
    [datetime, float, float, float, float],
    "tuple[WindField, WindFieldMetadata]",
]


# Per the approved plan, these are the fallbacks when a row on the
# ``devices`` table has NULLs for the balloon-physical columns.
DEFAULT_ENVELOPE_VOLUME_M3 = 0.5
DEFAULT_SYSTEM_MASS_KG = 0.012
DEFAULT_LIFT_GAS: LiftGas = "H2"
DEFAULT_GAS_MASS_KG = 0.002


# -------------------- Request models --------------------


class BalloonParams(BaseModel):
    """Balloon physical parameters.

    All fields optional. Resolution order (each layer wins over the next):
    1. This request body (inline override for A/B fills).
    2. The ``devices`` row looked up by ``device_id``.
    3. The pico-balloon defaults above.
    """

    envelope_volume_m3: Optional[float] = Field(default=None, gt=0.0,
                                                description="Rigid envelope volume in m^3.")
    system_mass_kg: Optional[float] = Field(default=None, ge=0.0,
                                            description="Non-gas system mass (payload + envelope + battery) in kg.")
    lift_gas: Optional[LiftGas] = Field(default=None,
                                        description="Lift gas: 'H2' or 'He'.")
    gas_mass_kg: Optional[float] = Field(default=None, ge=0.0,
                                         description="Lift-gas mass in kg.")


class TelemetryPacket(BaseModel):
    """One telemetry packet, field naming matched to the Supabase schema."""

    device_id: str
    time: datetime
    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude in degrees.")
    lon: float = Field(..., ge=-180.0, le=180.0, description="Longitude in degrees.")
    altitude_m: Optional[float] = Field(
        default=None,
        description=(
            "Altitude in metres above sea level. If omitted, the float "
            "altitude is computed from balloon physical parameters."
        ),
    )


class PredictRequest(BaseModel):
    telemetry: TelemetryPacket
    balloon_params: Optional[BalloonParams] = None
    duration_hours: float = Field(default=10.0, gt=0.0, le=48.0)
    n_ensemble: int = Field(default=DEFAULT_N_MEMBERS, ge=2, le=500)
    horizons_hours: List[float] = Field(default=[3.0, 6.0, 10.0])
    seed: Optional[int] = Field(
        default=None,
        description="Master RNG seed for reproducibility (omit for time-based randomness).",
    )


# -------------------- Response models --------------------


class TrajectoryPointDTO(BaseModel):
    t_offset_s: float = Field(..., description="Seconds since the start time.")
    time: datetime = Field(..., description="Absolute valid time (UTC).")
    lat: float
    lon: float
    altitude_m: float
    sigma1_radius_km: float = Field(..., description="Great-circle 1σ position spread (km).")
    sigma2_radius_km: float = Field(..., description="Great-circle 2σ position spread (km).")


class CEPHorizonDTO(BaseModel):
    horizon_hours: float
    cep_km: float = Field(..., description="1σ great-circle position spread at this horizon.")
    cep_2sigma_km: float = Field(..., description="2σ great-circle position spread at this horizon.")


class BalloonParamsDTO(BaseModel):
    envelope_volume_m3: float
    system_mass_kg: float
    lift_gas: LiftGas
    gas_mass_kg: float


class WindSourceDTO(BaseModel):
    """Provenance for the NWP data backing this prediction."""

    source: str = Field(..., description="'hrrr', 'gfs', or 'constant'.")
    cycle: Optional[datetime] = Field(None, description="Model cycle init time (UTC).")
    fxx_start: Optional[int] = Field(None, description="First forecast hour included.")
    fxx_end: Optional[int] = Field(None, description="Last forecast hour included.")
    levels_hpa: List[float] = Field(default_factory=list, description="Loaded pressure-level subset (hPa).")
    region: str = Field("global", description="'conus' or 'global'.")


class PredictResponse(BaseModel):
    device_id: str
    issued_at: datetime
    valid_from: datetime
    float_altitude_m: float
    n_ensemble: int
    balloon_params: BalloonParamsDTO
    trajectory: List[TrajectoryPointDTO]
    horizons: List[CEPHorizonDTO]
    wind_source: WindSourceDTO


# -------------------- DI factories --------------------


def get_wind_field_builder() -> WindFieldBuilder:
    """Default wind-field builder: real HRRR/GFS via the orchestrator.

    Tests override this with a stub that returns a deterministic
    :class:`ConstantWindField` (or any other :class:`WindField`) and
    an arbitrary :class:`WindFieldMetadata`.

    Production deployments can override this to pin a specific cache
    directory or to bias source selection (e.g. force GFS-only).
    """

    def _builder(
        target_time: datetime,
        duration_hours: float,
        lat: float,
        lon: float,
        altitude_m: float,
    ) -> "tuple[WindField, WindFieldMetadata]":
        result = build_wind_field(
            target_time=target_time,
            duration_hours=duration_hours,
            lat=lat,
            lon=lon,
            altitude_m=altitude_m,
        )
        return result.wind_field, result.metadata

    return _builder


def get_balloon_lookup() -> Callable[[str], Optional[BalloonParams]]:
    """Default device → balloon-params lookup factory.

    v1 returns a no-op lookup; production overrides this with a
    Supabase client that selects the row on ``devices`` for
    ``device_id`` and maps the balloon columns to :class:`BalloonParams`.
    """

    def _lookup(_device_id: str) -> Optional[BalloonParams]:
        return None

    return _lookup


# -------------------- Param resolution --------------------


def _resolve_balloon_params(
    inline_override: Optional[BalloonParams],
    db_value: Optional[BalloonParams],
) -> BalloonParams:
    """Merge inline body, DB row, and defaults.

    Inline > DB > defaults.
    """
    merged = {
        "envelope_volume_m3": DEFAULT_ENVELOPE_VOLUME_M3,
        "system_mass_kg": DEFAULT_SYSTEM_MASS_KG,
        "lift_gas": DEFAULT_LIFT_GAS,
        "gas_mass_kg": DEFAULT_GAS_MASS_KG,
    }
    if db_value is not None:
        for k, v in db_value.model_dump(exclude_none=True).items():
            merged[k] = v
    if inline_override is not None:
        for k, v in inline_override.model_dump(exclude_none=True).items():
            merged[k] = v
    return BalloonParams(**merged)


# -------------------- App factory --------------------


def create_app() -> FastAPI:
    app = FastAPI(
        title="Stratolink Predictor",
        version="0.1.0",
        description="Pico-balloon trajectory + uncertainty prediction API.",
    )

    @app.post("/predict", response_model=PredictResponse)
    def predict(
        req: PredictRequest,
        wind_field_builder: WindFieldBuilder = Depends(get_wind_field_builder),
        balloon_lookup=Depends(get_balloon_lookup),
    ) -> PredictResponse:
        # 1. Resolve balloon physical parameters
        db_row = balloon_lookup(req.telemetry.device_id)
        params = _resolve_balloon_params(req.balloon_params, db_row)

        # 2. Determine float altitude: telemetry's altitude wins if present
        if req.telemetry.altitude_m is not None:
            float_alt_m = req.telemetry.altitude_m
        else:
            try:
                fr = compute_float_altitude(
                    envelope_volume_m3=params.envelope_volume_m3,
                    system_mass_kg=params.system_mass_kg,
                    lift_gas=params.lift_gas,
                    gas_mass_kg=params.gas_mass_kg,
                )
                float_alt_m = fr.altitude_m
            except ValueError as e:
                raise HTTPException(status_code=422, detail=f"Float altitude unsolvable: {e}")

        # 3. Normalize telemetry timestamp to UTC
        start_time = req.telemetry.time
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        else:
            start_time = start_time.astimezone(timezone.utc)

        # 4. Build the wind field for this request's spacetime context
        try:
            wind_field, wind_meta = wind_field_builder(
                start_time,
                req.duration_hours,
                req.telemetry.lat,
                req.telemetry.lon,
                float_alt_m,
            )
        except FileNotFoundError as e:
            raise HTTPException(status_code=503, detail=f"Weather data unavailable: {e}")

        # 5. Run the ensemble
        result = run_ensemble(
            initial_position=GeodeticPosition(
                lat_deg=req.telemetry.lat,
                lon_deg=req.telemetry.lon,
                altitude_m=float_alt_m,
            ),
            wind_field=wind_field,
            duration_hours=req.duration_hours,
            start_time=start_time,
            n_members=req.n_ensemble,
            seed=req.seed,
        )

        # 5. Marshal response
        traj_dtos = [
            TrajectoryPointDTO(
                t_offset_s=p.t_offset_s,
                time=p.time,
                lat=p.lat_deg,
                lon=p.lon_deg,
                altitude_m=p.altitude_m,
                sigma1_radius_km=p.sigma1_radius_km,
                sigma2_radius_km=p.sigma2_radius_km,
            )
            for p in result.summary
        ]
        sigma1_series = [p.sigma1_radius_km for p in result.summary]
        sigma2_series = [p.sigma2_radius_km for p in result.summary]
        cep1 = cep_radius_km(sigma1_series, req.horizons_hours)
        cep2 = cep_radius_km(sigma2_series, req.horizons_hours)
        horizons = [
            CEPHorizonDTO(
                horizon_hours=h,
                cep_km=cep1[h],
                cep_2sigma_km=cep2[h],
            )
            for h in req.horizons_hours
        ]

        return PredictResponse(
            device_id=req.telemetry.device_id,
            issued_at=datetime.now(timezone.utc),
            valid_from=start_time,
            float_altitude_m=float_alt_m,
            n_ensemble=req.n_ensemble,
            balloon_params=BalloonParamsDTO(
                envelope_volume_m3=params.envelope_volume_m3,
                system_mass_kg=params.system_mass_kg,
                lift_gas=params.lift_gas,
                gas_mass_kg=params.gas_mass_kg,
            ),
            trajectory=traj_dtos,
            horizons=horizons,
            wind_source=WindSourceDTO(
                source=wind_meta.source,
                cycle=wind_meta.cycle,
                fxx_start=wind_meta.fxx_start,
                fxx_end=wind_meta.fxx_end,
                levels_hpa=list(wind_meta.levels_hpa),
                region=wind_meta.region,
            ),
        )

    @app.get("/health")
    def health():
        return {"status": "ok", "version": "0.1.0"}

    return app


# Module-level app instance for `uvicorn predictor.api.predict:app`
app = create_app()
