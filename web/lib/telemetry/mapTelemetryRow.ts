import { altitudeFromPressureHpa } from '@/lib/atmosphere/isa';
import type { TelemetryRow } from '@/components/dashboard-v2/atoms';
import type { RawTelemetryRecord } from './fetchMergedTelemetry';

export function rawToTelemetry(raw: RawTelemetryRecord): TelemetryRow {
    const presHpa = (raw.pressure ?? null) as number | null;
    return {
        t: new Date(raw.time as string).getTime(),
        lat: (raw.lat ?? null) as number | null,
        lon: (raw.lon ?? null) as number | null,
        alt: (raw.altitude_m ?? null) as number | null,
        temp: (raw.temperature ?? null) as number | null,
        pres: presHpa,
        presAlt: altitudeFromPressureHpa(presHpa),
        batt: (raw.battery_voltage ?? null) as number | null,
        sol: (raw.solar_voltage ?? null) as number | null,
        rssi: (raw.rssi ?? null) as number | null,
        snr: (raw.snr ?? null) as number | null,
        sats: (raw.gps_satellites ?? null) as number | null,
        lux: (raw.ambient_lux ?? null) as number | null,
        uv: (raw.uv_index ?? null) as number | null,
        spd: (raw.gps_speed ?? null) as number | null,
        hdg: (raw.gps_heading ?? null) as number | null,
        ax: (raw.mems_accel_x ?? null) as number | null,
        ay: (raw.mems_accel_y ?? null) as number | null,
        az: (raw.mems_accel_z ?? null) as number | null,
        vx: (raw.velocity_x ?? null) as number | null,
        vy: (raw.velocity_y ?? null) as number | null,
        firmware_version: (raw.firmware_version ?? null) as string | null,
        uptime_s: (raw.uptime_s ?? null) as number | null,
        tx_count: (raw.tx_count ?? null) as number | null,
        hdop: (raw.hdop ?? null) as number | null,
        power_mode: (raw.power_mode ?? null) as string | null,
        sleep_ms: (raw.sleep_ms ?? null) as number | null,
        lora_sf: (raw.lora_sf ?? null) as number | null,
        lora_bw: (raw.lora_bw ?? null) as number | null,
        frequency_hz: (raw.frequency_hz ?? null) as number | null,
        gateways: Array.isArray(raw.gateways) ? raw.gateways : null,
    };
}
