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
        /** Reachability hulls for under-determined long gaps (corridor mode). */
        gap_reach_hulls?: Array<Array<[number, number]>>;
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
            reach_hull?: Array<[number, number]> | null;
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
