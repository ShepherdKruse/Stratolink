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
#define TTN_REGION_US915
// Alternative regions: EU868, AS923, AU915, IN865, KR920

// GNSS Configuration
#define GNSS_ENABLE true
#define GNSS_UPDATE_INTERVAL_MS 30000

// Power Management
#define POWER_SAVE_MODE true
#define TRANSMIT_INTERVAL_SEC 60
#define SLEEP_INTERVAL_FULL_SEC      60
#define SLEEP_INTERVAL_REDUCED_SEC  120
#define SLEEP_INTERVAL_NO_GPS_SEC   300
#define SLEEP_INTERVAL_EMERGENCY_SEC 120

#define BURST_GPS_TIMEOUT_MS  10000
#define BURST_SLEEP_SEC       10

// Debug Configuration
#define DEBUG_ENABLE true
#define DEBUG_SERIAL_BAUD 115200

#endif // CONFIG_H
