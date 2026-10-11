/** Pre-computed Monte Carlo forecast blob (matches stratolink_forecast module schema). */

export type ForecastGpsFix = {
    lat: number;
    lon: number;
    time_utc: string;
    alt_m?: number;
    /** Barometric pressure (hPa) reported with the fix, when it is a plausible
     *  float reading (80–400 hPa); anchors the long-gap smoother's per-particle
     *  pressure at the gap's ends. */
    pressure_hpa?: number;
    note?: string | null;
};

export type ForecastEllipse = {
    center: [number, number];
    semi_a_km: number;
    semi_b_km: number;
    theta_deg: number;
    polygon: Array<[number, number]>;
};

export type ForecastEllipseSlice = {
    t_hours: number;
    e50: ForecastEllipse;
    e90: ForecastEllipse;
    mean: [number, number];
};

export type StratolinkForecast = {
    generated_at: string;
    forecast_horizon_h: number;
    level_hpa: number;
    forecast_origin: {
        lat: number;
        lon: number;
        alt_m?: number;
        time_utc: string;
    };
    /** Present when last GPS fix was stale and we dead-reckoned to an implied "now". */
    stale_gps?: {
        gap_hours: number;
        last_fix_time_utc: string;
        wind_field_time_utc: string;
        wind_mode?: string;
        /** True when the dead-reckon ran out of wind-cube coverage before reaching
         *  "now" — the origin is the last modeled point, position now is unknown. */
        coverage_limited?: boolean;
        /** Hours of dead-reckon actually modeled before coverage ran out. */
        modeled_hours?: number;
    };
    /** Set when the forecast was terminated early because the ensemble's RMS spread
     *  crossed the predictability threshold — the drawn path ends here and the UI
     *  anchors a "forecast ends — paths diverge" notice at `lonlat`. */
    divergence?: {
        limited: true;
        lonlat: [number, number];
        time_utc: string;
        spread_km: number;
        threshold_km: number;
    };
    /** Wind-integrated "predicted hindcast" — the curved path from the last GPS
     *  fix to "now" (analysis winds). Present only when the last fix was stale;
     *  the forward forecast begins at its final point. Drawn instead of a
     *  straight last-fix→now connector. */
    predicted_hindcast?: {
        path: Array<[number, number]>;
        last_fix_lonlat: [number, number];
        now_lonlat: [number, number];
        /** Index in `path` where analysis winds hand off to forecast winds
         *  (= the final point for a fix→now hindcast). */
        analysis_boundary_idx: number;
        analysis_boundary_time_utc: string;
    };
    nominal_path: Array<[number, number]>;
    ensemble: Array<Array<[number, number]>>;
    ellipses: ForecastEllipseSlice[];
    endpoint: {
        lat: number;
        lon: number;
        wind: { speed_mps: number; dir_deg: number };
    };
    bias_correction: {
        speed_factor: number;
        direction_offset_deg: number;
        n_samples: number;
        capped: boolean;
        raw_speed_factor: number;
        raw_direction_offset_deg: number;
    };
    observed: {
        mission?: string;
        device_id: string;
        launch: { lat: number; lon: number; time_utc: string };
        gps_fixes: ForecastGpsFix[];
        track: Array<[number, number]>;
        drift_segment: Array<[number, number]>;
        /** Particle-smoother path through GPS-dark segments (stitched). */
        reconstructed_path?: Array<[number, number]>;
        /** Reconstructed path with UTC time at each point (timeline scrub). */
        reconstructed_track?: Array<{ lon: number; lat: number; time_utc: string }>;
        /** Per-gap bridge segments (non-trivial gaps only). */
        gap_bridges?: Array<Array<[number, number]>>;
        /** Hash of the reconstruction inputs (fixes + level) — lets the cache
         *  reuse an unchanged hindcast instead of recomputing it. */
        reconstruction_input_hash?: string;
        /** Per-gap scalar metadata. The corridor occupancy footprint and ellipse
         *  rings stay in the hindcast cache; they are not stored in the forecast. */
        reconstruction_gaps?: Array<{
            from_idx: number;
            to_idx: number;
            dt_hours: number;
            measured_altitude: boolean;
            /** Raw smoother closure error (long gaps: forward/backward posterior
             *  mismatch at the meeting step; the bridge itself ends at the fix). */
            endpoint_miss_km: number;
            /** Mid-gap 90 % ellipse semi-major axis; posterior-weighted for long gaps. */
            mid_gap_90_km: number;
            confidence: string;
            short: boolean;
            mode?: 'line' | 'corridor';
            /** Long gaps: effective number of matched forward×backward particle pairs. */
            n_eff?: number;
            directness?: number;
            net_speed_ms?: number;
            /** Fraction of the bridge's wind samples outside the cube's slice boxes. */
            outside_cube_frac?: number;
            /** Long gaps: the same, weighted by posterior particle weight. */
            outside_cube_frac_weighted?: number;
            /** Long gaps: the winds cannot connect the two fixes (clouds never
             *  met, or closure > 300 km) — a low-confidence corridor. */
            unexplained?: boolean;
            /** How the drawn bridge was formed ('trimmed-local-mean' | 'straight'). */
            line_method?: string;
        }>;
    };
    metadata: {
        n_ensemble: number;
        step_hours: number;
        speed_sigma: number;
        dir_sigma_deg: number;
        alt_sigma_hpa: number;
        compute_ms: number;
        reconstruction_ms?: number;
        /** `gfs_cube` — the stale-GPS gap is dead-reckoned through the shared GFS cube. */
        gap_wind_mode?: string;
        /** Resolution (deg) of the forecast wind cube (the forward forecast + ensemble). */
        grid_step_deg?: number;
        /** Resolution (deg) of the full-mission reconstruction wind cube. */
        recon_grid_step_deg?: number;
        /** Where the winds came from: 'gfs' (the GFS cube) or 'gefs-ensemble' (per-member cubes). */
        wind_source?: string;
        /** ISO time the GFS wind cube was ingested (staleness indicator). */
        wind_cube_generated_at?: string;
        /** True when the reconstruction ran out of call budget and left some gaps
         *  as straight-line placeholders — recompute soon to fill them in. */
        reconstruction_partial?: boolean;
        /** Ensemble member cubes the compute found per source (`gefs` = physics
         *  GEFS, `aigefs` = GraphCast AI). Stamped by the worker (compute_forecasts). */
        members?: Record<string, number>;
        /** Members each source was configured to build (from the ingest manifest);
         *  fewer `members` than this means the ingest step was cut short. */
        members_expected?: Record<string, number>;
    };
};

export type MonteCarloForecastInput = {
    deviceId: string;
    mission?: string;
    launch: { lat: number; lon: number; time_utc: string };
    gpsFixes: ForecastGpsFix[];
    observedTrackLonLat: Array<[number, number]>;
    driftSegmentLonLat?: Array<[number, number]>;
    /** Pressure/altitude samples during GPS gaps (baro continued). */
    baroSamples?: Array<{ time_utc: string; alt_m: number }>;
    pressureHpa: number;
    forecastHours?: number;
    nEnsemble?: number;
};
