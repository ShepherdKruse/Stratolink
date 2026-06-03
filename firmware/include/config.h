#ifndef CONFIG_H
#define CONFIG_H

// Stratolink Firmware Configuration
// DO NOT COMMIT REAL KEYS TO GITHUB
// Copy this file to secrets.h and fill in actual values
// secrets.h is gitignored

// LoRaWAN Configuration
#ifndef LORAWAN_DEV_EUI
#define LORAWAN_DEV_EUI ""
#endif
#ifndef LORAWAN_APP_EUI
#define LORAWAN_APP_EUI ""
#endif
#ifndef LORAWAN_APP_KEY
#define LORAWAN_APP_KEY ""
#endif

// TTN Configuration
// Region is selected at runtime from GPS lat/lon, see region_manager.cpp
// and lorawan_set_region().  Cold-boot default is US915 (see lorawan.cpp);
// overridden on the first valid GPS fix.

// GNSS Configuration
#define GNSS_ENABLE true
#define GNSS_UPDATE_INTERVAL_MS 30000
// Hardware-reset the GPS via PA0 after ~this much CONTINUOUS module silence
// (getPVT never answered), to un-stick a wedged module.  Derived from a wall-
// clock budget so it stays ~constant as the SF-coupled cadence changes, instead
// of ballooning to ~100 min at the SF9 1200 s cadence.  millis() is frozen in
// STOP1, so we can't time it directly; deriving the cycle count from the FULL
// cadence is the clean equivalent (the recovery counter only advances on GPS-
// polled cycles, which run at ~the FULL interval).  300 s -> 5 cycles (the soak-
// validated value); 1200 s -> 2 cycles (~40 min vs the old 100).
#define GPS_STALE_RECOVERY_SEC 1500u   /* ~25 min of silence before a PA0 reset */
#define GPS_STALE_RECOVERY_CYCLES \
    ((GPS_STALE_RECOVERY_SEC + SLEEP_INTERVAL_FULL_SEC - 1u) / SLEEP_INTERVAL_FULL_SEC)

// Power Management. Cadence is coupled to the uplink SF (lorawan.cpp tx_sf=9):
// at SF9 the 35-byte payload is ~308 ms ToA, so FULL=1200s keeps daily airtime
// at ~22 s/day = 74% of the TTN 30 s/day Fair-Use Policy (comfortable margin for
// join retries + clock drift; SF9 @ 900s would be 99% = no margin).  Lower tiers
// at 1800s extend battery further and stay well under FUP.  If SF or payload
// change, re-check airtime: keep FULL-tier uplinks/day * ToA < 30 s.
#define POWER_SAVE_MODE true
#define TRANSMIT_INTERVAL_SEC 1200
#define SLEEP_INTERVAL_FULL_SEC      1200
#define SLEEP_INTERVAL_REDUCED_SEC   1800
#define SLEEP_INTERVAL_NO_GPS_SEC    1800
#define SLEEP_INTERVAL_EMERGENCY_SEC 1800

#define BURST_GPS_TIMEOUT_MS  10000
#define BURST_SLEEP_SEC       10

// Burst-mode runaway guard.  Burst (freefall-triggered 10 s rapid beaconing for
// payload recovery) self-clears the moment the payload reaches terminal velocity
// or lands: the accelerometer reads ~1g again (>= 0.5 g) and is_freefall_cleared
// returns true.  A REAL burst is therefore short (the brief weightless transient)
// and exits naturally, never hitting the cap below.  The hazard is a FAULT: a
// stuck/chattering INT1 (or a sensor reading persistent <0.5 g) trapping burst in
// 10 s beaconing; at SF9 that's ~308 ms airtime / 10 s, blowing the daily TTN
// FUP in ~16 min and draining the cap.  Guard: cap a burst at BURST_MAX_CYCLES,
// then force-exit and require BURST_COOLDOWN_CYCLES *consecutive freefall-free*
// wakes before re-arming.  Any freefall wake during cooldown restarts it, so a
// persistently stuck/chattering pin NEVER re-arms (exactly one ~9 s burst window
// total, FUP-safe), while a healthy sensor re-arms within a few normal cycles.
#define BURST_MAX_CYCLES      30   /* ~5-10 min of beacons, ~9 s airtime; >> a real freefall transient */
#define BURST_COOLDOWN_CYCLES 3    /* consecutive freefall-free wakes required to re-arm */

// Debug Configuration
#define DEBUG_ENABLE true
#define DEBUG_SERIAL_BAUD 115200

#endif // CONFIG_H
