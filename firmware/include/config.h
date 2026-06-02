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
// Hardware-reset the GPS via PA0 after this many consecutive cycles in which the
// module was truly SILENT (getPVT never answered), to un-stick a wedged module.
// Counted in GPS-POLLED cycles (only when power_adc_can_use_gps()), not wall-clock:
// ~25 min at the 300 s FULL cadence, less in burst.  NOTE: cadence is coupled to
// the LoRaWAN spreading factor (SF9 -> ~15 min -> 5 cycles = ~75 min); when SF/
// cadence is finalized, make this a wall-clock budget.  See GPS_HANDOFF.md.
#define GPS_STALE_RECOVERY_CYCLES 5

// Power Management, FULL=300s keeps daily airtime at SF7/35-byte to
// ~28 s/day across every region, inside the TTN 30 s Fair-Use Policy.
// Lower tiers extend further; both NO_GPS and EMERGENCY already cover
// the cold/dark cycle.
#define POWER_SAVE_MODE true
#define TRANSMIT_INTERVAL_SEC 300
#define SLEEP_INTERVAL_FULL_SEC      300
#define SLEEP_INTERVAL_REDUCED_SEC   600
#define SLEEP_INTERVAL_NO_GPS_SEC    900
#define SLEEP_INTERVAL_EMERGENCY_SEC 600

#define BURST_GPS_TIMEOUT_MS  10000
#define BURST_SLEEP_SEC       10

// Debug Configuration
#define DEBUG_ENABLE true
#define DEBUG_SERIAL_BAUD 115200

#endif // CONFIG_H
