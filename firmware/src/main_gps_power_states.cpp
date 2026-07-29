/*
 * MAX-M10S power-state characterization for the PPK2 bench.
 *
 * The u-blox data sheet specifies software-standby current, but does not
 * specify current while RESET_N is held low. Flight firmware therefore must
 * not assume that reset-held is a safe terminal containment state until the
 * actual payload has been measured.
 *
 * The program produces four equal, fixed-duration phases after a short boot
 * settle. It never initializes or transmits with the sub-GHz radio:
 *
 *   1. GPS awake, RESET_N released
 *   2. GPS requested into software standby
 *   3. GPS explicitly woken and left awake (failed-standby model)
 *   4. GPS RESET_N held low
 *
 * MCU activity is deliberately identical (`delay`) in all four phases, so
 * phase-to-phase PPK2 current deltas isolate the GNSS state. The cycle then
 * releases RESET_N and repeats. `gps_power_state_diag` is volatile so J-Link
 * can verify phase sequencing after the PPK capture; do not attach J-Link
 * during the current trace because halting would disturb the load.
 */

#include <Arduino.h>
#include "config.h"
#include "stratolink_pins.h"

#if __has_include(<SparkFun_u-blox_GNSS_v3.h>)
#include <SparkFun_u-blox_GNSS_v3.h>
static SFE_UBLOX_GNSS_SERIAL gnss;
#else
#include <SparkFun_u-blox_GNSS_Arduino_Library.h>
static SFE_UBLOX_GNSS gnss;
#endif

static constexpr uint32_t BOOT_SETTLE_MS = 5000;
static constexpr uint32_t PHASE_MS = 15000;

enum gps_power_phase_t : uint32_t {
    GPS_POWER_BOOT_SETTLE = 0,
    GPS_POWER_AWAKE = 1,
    GPS_POWER_SOFTWARE_STANDBY = 2,
    GPS_POWER_FAILED_STANDBY_AWAKE = 3,
    GPS_POWER_RESET_HELD = 4,
};

typedef struct {
    uint32_t magic;       /* "GPSP" */
    uint32_t cycle;
    uint32_t phase;
    uint32_t begin_ok;
    uint32_t pmreq_sent;
    uint32_t uptime_ms;
} gps_power_state_diag_t;

volatile gps_power_state_diag_t gps_power_state_diag = {
    0x47505350u, 0, GPS_POWER_BOOT_SETTLE, 0, 0, 0
};

static void set_phase(gps_power_phase_t phase) {
    gps_power_state_diag.phase = (uint32_t)phase;
    gps_power_state_diag.uptime_ms = millis();
}

static void wake_gps_uart(void) {
    GPS_SERIAL.write((uint8_t)0xFF);
    GPS_SERIAL.write((uint8_t)0xFF);
    GPS_SERIAL.flush();
    delay(10);
}

void setup() {
    pinMode(PIN_GPS_RESET_N, INPUT);
    GPS_SERIAL.begin(GPS_BAUD);
    wake_gps_uart();
    gps_power_state_diag.begin_ok = gnss.begin(GPS_SERIAL) ? 1u : 0u;
    delay(BOOT_SETTLE_MS);
}

void loop() {
    gps_power_state_diag.cycle++;

    pinMode(PIN_GPS_RESET_N, INPUT);
    wake_gps_uart();
    set_phase(GPS_POWER_AWAKE);
    delay(PHASE_MS);

    /* maxWait=0 sends the complete frame and returns without pretending that
     * the input-only PMREQ command has a positive ACK. TX flush below proves
     * the host UART shifted the complete request before timing the phase. */
    (void)gnss.powerOffWithInterrupt(
        0, VAL_RXM_PMREQ_WAKEUPSOURCE_UARTRX, true, 0);
    GPS_SERIAL.flush();
    gps_power_state_diag.pmreq_sent++;
    set_phase(GPS_POWER_SOFTWARE_STANDBY);
    delay(PHASE_MS);

    wake_gps_uart();
    set_phase(GPS_POWER_FAILED_STANDBY_AWAKE);
    delay(PHASE_MS);

    pinMode(PIN_GPS_RESET_N, OUTPUT);
    digitalWrite(PIN_GPS_RESET_N, LOW);
    set_phase(GPS_POWER_RESET_HELD);
    delay(PHASE_MS);

    /* Never leave the receiver held in reset if the diagnostic is halted
     * between complete cycles. The next iteration re-establishes the UART
     * command path from a normal cold start. */
    pinMode(PIN_GPS_RESET_N, INPUT);
    delay(1000);
    (void)gnss.begin(GPS_SERIAL);
}
