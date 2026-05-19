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
    };
};

export type MonteCarloForecastInput = {
    deviceId: string;
    mission?: string;
    launch: { lat: number; lon: number; time_utc: string };
    gpsFixes: ForecastGpsFix[];
    observedTrackLonLat: Array<[number, number]>;
    driftSegmentLonLat?: Array<[number, number]>;
    pressureHpa: number;
    forecastHours?: number;
    nEnsemble?: number;
};
