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
// Region is selected at runtime from GPS lat/lon — see region_manager.cpp
// and lorawan_set_region().  Cold-boot default is US915 (see lorawan.cpp);
// overridden on the first valid GPS fix.

// GNSS Configuration
#define GNSS_ENABLE true
#define GNSS_UPDATE_INTERVAL_MS 30000

// Power Management — FULL=300s keeps daily airtime at SF7/35-byte to
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
