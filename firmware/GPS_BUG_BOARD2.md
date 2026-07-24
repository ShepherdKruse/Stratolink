# GPS Stale-Fix Bug — fix for board #2 / #3

## Symptom observed on Stratolink-3 flight 2026-05-17

From 18:20 UTC onwards (~30 min sequence), every uplink carries bit-identical GPS values:

- `lat = 36.615955°, lon = -121.571856°, alt = 6924 m`
- `gps_speed = 31.27 m/s, gps_heading = 22.24°`
- `gps_satellites = 32` (sentinel)

Meanwhile pressure dropped 425 → 325 hPa (balloon climbed ~1.8 km) and temperature dropped from -1°C to -18°C — proving the balloon was *still ascending*, GPS reporting was just frozen.

Other sensors (TMP117, MS5611, LTR390, MEMS, battery/solar ADC) and LoRa all continued reporting fresh values. So this is GPS-subsystem-specific, not a general firmware hang.

## Root cause

[`firmware/src/gps_ublox.cpp`](src/gps_ublox.cpp) line 37-49:

```c
static void fill_fix_from_gnss(gps_fix_t* fix) {
    fix->lat_e7      = gnss.getLatitude();
    fix->lon_e7      = gnss.getLongitude();
    fix->altitude_m  = gnss.getAltitude() / 1000;
    ...
    fix->satellites  = (uint8_t)gnss.getSIV();
    fix->valid       = gnss.getGnssFixOk() && fix->satellites >= 4;
}
```

The SparkFun u-blox library `getLatitude()`, `getGnssFixOk()`, etc. all return values from an internal cached PVT struct. When the u-blox module stops sending fresh PVT messages (e.g. fix lost at altitude, cold thermal drift on the TCXO, antenna issue, signal geometry), `checkUblox()` doesn't update the cache but the cache still reports the *last* `fixOK = true`. So `fill_fix_from_gnss()` happily reports a valid fix with stale lat/lon.

`getSIV()` returning 32 is the smoking gun — that's "satellites in view" from the last good PVT (plausible at altitude where the receiver can see the full GPS+Galileo+GLONASS+BeiDou constellation when it was tracking) — it's frozen with the rest of the cache.

`gnss.getGnssFixOk()` doesn't tell us if the fix is *fresh*; it tells us if the *last* PVT had its fix-OK flag set.

## Fix

Verify the PVT is fresh on every call. Two options:

### Option A: epoch-based freshness check (preferred)

```c
static uint32_t last_pvt_epoch = 0;

static void fill_fix_from_gnss(gps_fix_t* fix) {
    if (!fix) return;
    uint32_t epoch = gnss.getUnixEpoch();  // SparkFun helper
    if (epoch == last_pvt_epoch) {
        fix->valid = false;                 // PVT hasn't advanced
        return;
    }
    last_pvt_epoch = epoch;

    fix->lat_e7      = gnss.getLatitude();
    fix->lon_e7      = gnss.getLongitude();
    fix->altitude_m  = gnss.getAltitude() / 1000;
    ...
    fix->satellites  = (uint8_t)gnss.getSIV();
    fix->valid       = gnss.getGnssFixOk() && fix->satellites >= 4;
}
```

### Option B: explicit getPVT() return-value check

`gnss.getPVT()` returns `true` only when a *new* PVT was received during the call. Use it as the gate instead of polling cached accessors.

```c
bool gps_ublox_get_fix(gps_fix_t* fix, uint32_t timeout_ms) {
    ...
    while (millis() < deadline) {
        if (gnss.getPVT()) {  // <-- only returns true on fresh PVT
            fill_fix_from_gnss(&last_fix);
            if (last_fix.valid) {
                *fix = last_fix;
                return true;
            }
        }
        if (millis() - last_kick >= 5000) {
            power_manager_kick_watchdog();
            last_kick = millis();
        }
        delay(100);
    }
    *fix = last_fix;
    fix->valid = false;
    return false;
}
```

`getPVT()` blocks until either a new PVT arrives or a per-call timeout fires; the outer `delay(100)` should be removed if we use this pattern.

### Recovery: power-cycle GPS after N consecutive stale fixes

If 5+ consecutive cycles return stale PVTs, power-cycle the u-blox module via its enable line:

```c
if (consecutive_stale >= 5) {
    gps_power_cycle();  // assert enable low, wait 100 ms, high
    consecutive_stale = 0;
    delay(2000);  // give it time to re-acquire
}
```

The MAX-M10S cold-start TTFF is ~30 s, warm-start ~3 s, so a 5-cycle (25 min) wait before recycle is reasonable. Aim is not to interrupt valid acquisition by being too aggressive.

## Validation criteria

Before re-flying, validate the fix by:

1. Block the GPS antenna with foil during bench test. Within 1 telemetry cycle, `gps_satellites` should drop to 0 and `lat/lon/alt` should be reported as null (NOGPS).
2. Unblock the antenna. Within ~30 s, fresh fix should resume.
3. Power-cycle the GPS module manually. Confirm cold-start recovery.

## Severity

- **Flight #1 (current)**: position tracking degraded. Pressure-based altitude still works; satellite anchor for ozone retrieval works since we know lat/lon roughly. Trajectory prediction can dead-reckon from last known position + GFS winds.
- **For science**: not breaking — pressure → altitude is fine for ozone profile retrieval. Satellite collocation can use last-known lat/lon ± a 100-km uncertainty box.
- **For board #2/#3**: high priority. Fix before next flight.
