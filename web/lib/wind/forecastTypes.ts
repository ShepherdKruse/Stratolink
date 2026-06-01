/** Pre-computed Monte Carlo forecast blob (matches stratolink_forecast module schema). */

export type ForecastGpsFix = {
    lat: number;
    lon: number;
    time_utc: string;
    alt_m?: number;
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
        reconstruction_gaps?: Array<{
            from_idx: number;
            to_idx: number;
            dt_hours: number;
            measured_altitude: boolean;
            endpoint_miss_km: number;
            mid_gap_90_km: number;
            confidence: string;
            short: boolean;
            mode?: 'line' | 'corridor';
            n_eff?: number;
            directness?: number;
            net_speed_ms?: number;
            occupancy?: {
                lat0: number;
                lon0: number;
                dLat: number;
                dLon: number;
                nLat: number;
                nLon: number;
                cells: Array<{ i: number; j: number; d: number }>;
            } | null;
            ellipses?: Array<{
                frac: number;
                t_hours: number;
                e50: { semi_a_km: number; polygon: Array<[number, number]> };
                e90: { semi_a_km: number; polygon: Array<[number, number]> };
            }>;
        }>;
    };
    wind_field: {
        lat0: number;
        dLat: number;
        nLat: number;
        lon0: number;
        dLon: number;
        nLon: number;
        U: number[];
        V: number[];
    };
    metadata: {
        n_ensemble: number;
        step_hours: number;
        speed_sigma: number;
        dir_sigma_deg: number;
        alt_sigma_hpa: number;
        compute_ms: number;
        reconstruction_ms?: number;
        /** `hourly_series` when stale-GPS gap used time-varying past+hourly winds. */
        gap_wind_mode?: string;
        /** Resolution (deg) of the shared space-time wind field for this compute. */
        grid_step_deg?: number;
        /** True when the reconstruction ran out of call budget and left some gaps
         *  as straight-line placeholders — recompute soon to fill them in. */
        reconstruction_partial?: boolean;
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
