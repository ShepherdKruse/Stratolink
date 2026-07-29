# Stratolink-3 signal characterization

Source: TTN webhook -> Supabase `public.telemetry` (project iazmnyyfsobucndqncgw), devices `stratolink-3` (US915/nam1) and `stratolink-3-eu` (EU868/eu1).
Per-reception rows are exploded from the `gateways` JSONB column (one entry per gateway that decoded the uplink).
Time span: 2026-05-15 14:00:30.323000+00:00 -> 2026-05-29 19:45:04.098429+00:00 (UTC).

**Geometry caveat:** only a subset of `gateways[]` entries carry lat/lon. Coordinates come from BOTH named gateways (e.g. niharramikrotik, italr0005, meceiot-*, cdtic-multitech-4, tef-mls-01) AND Packet-Broker (`gateway_id='packetbroker'`) entries; the rest (cicytex, mtcdtip, ext-sg50, mjv-*, ...) report null coords. All distance/angle stats below are over the geolocated receptions only; RSSI/SNR/SF stats use every reception.

## Counts
- Uplinks total: **458** (US 316, EU 142)
- Receptions (uplink x gateway): **3693**
- Unique NAMED gateways: **149**; packetbroker-anonymized receptions: **617**
- Receptions with usable gateway coords (geometry): **1226** (of which 908 from named gateways, 318 from packetbroker)

## RSSI / SNR (per reception)

| region | n | RSSI min | RSSI med | RSSI max | SNR min | SNR med | SNR max |
| --- | --- | --- | --- | --- | --- | --- | --- |
| US | 646 | -128.0 | -111.0 | -43.0 | -10.5 | -1.4 | 12.2 |
| EU | 3047 | -129.0 | -115.0 | -98.0 | -11.0 | -4.2 | 9.5 |
| ALL | 3693 | -129.0 | -114.0 | -43.0 | -11.0 | -4.0 | 12.2 |

## Spreading factor and frequency
- SF usage (receptions): SF7: 3520, SF10: 34
- SF usage (uplinks): SF7: 285, SF10: 34
- Frequencies seen (MHz): [868.1, 868.3, 868.5, 903.9, 904.1, 904.3, 904.5, 904.7, 904.9, 905.1, 905.3]

## Distance reached (geolocated receptions)
- Great-circle: median 107.2 km, max 433.2 km
- Slant range: median 107.6 km, max 433.4 km

Longest-range successful reception:
- slant 433.4 km (great-circle 433.2 km), RSSI -113.0 dBm, SNR -5.2 dB, SF7, balloon alt 6924 m, region US, elev -1.0 deg, at 2026-05-17 22:41:36.546770+00:00

## Look angles (geolocated receptions)
- Gateway elevation above horizon (deg): min -1.0, p25 3.2, median 4.7, p75 7.5, max 35.0
- Balloon depression below local horizontal (0=side, 90=nadir): min 2.6, median 5.7, max 35.1
- Gateway elevation-angle histogram: (-0.001, 1.0]deg: 97, (1.0, 2.0]deg: 74, (2.0, 5.0]deg: 471, (5.0, 10.0]deg: 407, (10.0, 20.0]deg: 116, (20.0, 40.0]deg: 61, (40.0, 90.0]deg: 0

## RSSI vs distance (path-loss fit)
- Fit RSSI ~= A - 10*n*log10(d_km): A = -104.9 dBm, n = **0.44** (free space = 2.0), R^2 = 0.09, n_points = 1226.
- Interpretation: n below 2 means the link beats free space along the as-the-crow-flies distance: at altitude the longest links go to high-elevation / overhead gateways with the clearest path, so RSSI falls slower than 1/d^2 -- expect heavy scatter (R^2 low) because the balloon antenna pattern and orientation, not distance, dominate.

## Altitude vs reception
- Balloon altitude at receptions: min -36 m, median 10009 m, max 10041 m
- Receptions by altitude band: -100-1000m: 112, 1000-5000m: 15, 5000-10000m: 402, 10000-12000m: 2990, 12000-13000m: 0, 13000-14000m: 0, 14000-100000m: 0
- Uplink altitude: min -36 m, median 6924 m, max 10041 m (n=366 uplinks w/ altitude)

## RSSI vs time-of-day (UTC)
- Median RSSI by UTC hour: 00h:-82, 01h:-114, 02h:-114, 07h:-113, 08h:-114, 09h:-114, 10h:-115, 11h:-114, 12h:-115, 13h:-115, 14h:-115, 15h:-114, 16h:-115, 17h:-114, 18h:-114, 19h:-115, 20h:-110, 21h:-111, 22h:-113, 23h:-52
- (Flight crossed ~8 timezones SF->Spain; local-solar effects are confounded with longitude/phase, so read this as indicative only.)
