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
/* Floor abort for the GPS acquisition window.  A full 30 s no-fix acquisition
 * at ~25 mA costs roughly 4 J, which is about half the nominal 1 F / 5.36 V
 * model's 8.86 J (and a larger fraction at the exact part's 0.8 F minimum),
 * so starting one on a marginal rail can drive the board through the
 * the Flight-3 reported ~3.32 V dropout plateau mid-poll. That plateau was not
 * actual VSTOR/BOR metrology; every other long window (relay, CTT) aborts at
 * 1 Hz on VSTOR; this one did not, which left acquisition as the only
 * unguarded high-current path.  Set above the NO_GPS tier edge (3.0 V) with
 * headroom for the acquisition's own sag. */
#define GPS_ACQ_FLOOR_MV 3600u
/* SparkFun defaults each UBX configuration transaction to 1100 ms. A failed
 * read/set/read model attempt could therefore cost 3.3 s; three attempts plus
 * one RESET_N recovery would spend ~20 s at GNSS current before acquisition.
 * UART1 at 9600 baud completes these short frames comfortably inside 300 ms,
 * matching the independently bounded standby-configuration transactions. */
#define GPS_DYNMODEL_MAX_WAIT_MS 300u
/* Pin the SparkFun v3 serial-begin wait instead of inheriting a library
 * default. This keeps the GNSS reset/recovery energy bound source-visible. */
#define GPS_BEGIN_MAX_WAIT_MS 1100u

#define GPS_STALE_RECOVERY_SEC 1500u   /* ~25 min of silence before a PA0 reset */
#define GPS_STALE_RECOVERY_CYCLES \
    ((GPS_STALE_RECOVERY_SEC + SLEEP_INTERVAL_FULL_SEC - 1u) / SLEEP_INTERVAL_FULL_SEC)

// Power Management. Cadence is coupled to the uplink SF (lorawan.cpp tx_sf=9):
// at SF9 the 40-byte v2 payload is ~329 ms ToA, so FULL=1200s keeps primary
// airtime at ~23.67 s/day = 78.9% of the TTN 30 s/day guideline. Lower tiers
// at 1800s extend battery further and stay well under FUP.  If SF or payload
// change, re-check airtime: keep FULL-tier uplinks/day * ToA < 30 s.
#define POWER_SAVE_MODE true
#define TRANSMIT_INTERVAL_SEC 1200
#define SLEEP_INTERVAL_FULL_SEC      1200
#define SLEEP_INTERVAL_REDUCED_SEC   1800
#define SLEEP_INTERVAL_NO_GPS_SEC    1800
#define SLEEP_INTERVAL_EMERGENCY_SEC 1800
/* If an enabled I2C sensor cannot prove standby, retry bus recovery promptly
 * without repeating the normal GPS/TX cycle at that same short cadence.
 * A permanent non-critical optical fault must not suppress tracking forever:
 * after the bounded fast attempts, resume the normal primary cadence with
 * LTR390 reads and every auxiliary service disabled. */
#define SENSOR_QUIESCE_RETRY_SLEEP_MS 60000u
#define SENSOR_QUIESCE_FAST_RETRIES   5u

#define BURST_GPS_TIMEOUT_MS  10000
#define BURST_SLEEP_SEC       10

// Burst-mode runaway guard.  Burst (freefall-triggered 10 s rapid beaconing for
// payload recovery) self-clears as drag restores measured acceleration or the
// payload lands: the accelerometer reads >= 0.5 g and is_freefall_cleared
// returns true. A real transient should therefore exit naturally. The hazard is
// a FAULT: a
// stuck/chattering INT1, unavailable sensor sample, or persistent <0.5 g trapping burst in
// 10 s beaconing; at SF9 that's ~308 ms airtime / 10 s, blowing the daily TTN
// FUP in ~16 min and draining the cap.  Guard: cap a burst at BURST_MAX_CYCLES,
// then force-exit and require BURST_COOLDOWN_CYCLES *consecutive freefall-free*
// wakes before re-arming. Any freefall wake during cooldown restarts it, so a
// persistently stuck/chattering pin never re-arms. Six SF9 frames cost at most
// ~1.85 s airtime, keeping even the fault path inside the remaining daily
// margin in the common 17-byte-aux case. RX windows and OTAA are suppressed in
// burst mode, so the cap is also a bounded energy cost.
#define BURST_MAX_CYCLES      6
#define BURST_COOLDOWN_CYCLES 3    /* consecutive freefall-free wakes required to re-arm */
#define SPURIOUS_WAKE_BACKOFF_SEC 60u /* confirmed ~1 g INT1 wake: no GPS/TX; retry after 1 min */

// ===== Meshtastic open-relay (mission-subordinate, power-gated) =====
// In the idle time between TTN cycles the flight radio relays real Meshtastic
// LongFast traffic (header-only, KEYLESS: dedup + hop-decrement + airtime cap),
// but ONLY on surplus power and NEVER at the expense of telemetry.  Validated on
// a live mesh 2026-06-03.  See analysis/network/{04,05,06,07}*.md + bench/RESULTS.md.
//   Gate (main.cpp): FULL tier (VSTOR>=4.5V) AND solar charging AND !burst.
//   Abort (lorawan.cpp): the instant VSTOR < RELAY_FLOOR_MV.
// The 4.5V start / 4.2V abort band IS the hysteresis; 4.2V leaves a 0.9V reserve
// above the conservative 3.32 V Flight-3 reported plateau and 1.2 V above the
// 3.0 V TTN-TX floor. Exact low-rail VSTOR/VOUT/TX HIL still sets the real floor.
#define MESHTASTIC_RELAY_ENABLE   true
#ifndef RELAY_SOLAR_MIN_MV               /* overridable for the indoor bench soak (env:stratolink_soak) */
#define RELAY_SOLAR_MIN_MV        3000   /* only relay when solar is actively charging */
#endif
#define RELAY_FLOOR_MV            4200   /* abort well above the conservative 3.32 V reported plateau */
#define RELAY_AIRTIME_CAP_PCT     5      /* cap our own TX airtime to this % of the relay window */

// ===== Balloon-to-balloon store-and-forward (shares LongFast relay window) =====
#define B2B_ENABLE                 true
#define B2B_EVENT_FPORT            12     /* exact versioned B2B frame tunneled to TTN */
#define B2B_CRUMB_INTERVAL_MIN     60u    /* at most one local position crumb per hour */
#ifndef B2B_FLEET_KEY
/* 32 hex chars / 128-bit secret shared only by StratoLink fleet nodes.
 * Empty is safe: every B2B frame type fails closed. Define the real value in
 * gitignored secrets.h. */
#define B2B_FLEET_KEY              ""
#endif

/* fPort 11 wildlife events and fPort 12 B2B tunnels share ONE auxiliary
 * LoRaWAN budget. At SF9 the 40-byte primary is 328.704 ms * 72/day =
 * 23.667 s. One worst-case 53-byte auxiliary every eight successful primary
 * cycles adds 3.511 s/day, for 27.178 s/day total and 2.822 s of join/model/
 * clock margin under TTN's 30 s/day community guideline. */
#define AUX_UPLINK_INTERVAL_CYCLES 8u

// ===== CTT wildlife-tag listener (Motus 434 MHz tags: birds, bats) =====
// RX-only window in the solar-surplus idle time (same gate as the relay, runs
// first since listening is cheaper than relaying). Logs decoded tag ids to a
// J-Link-readable ring and queues exact versioned fPort-11 events under the
// shared auxiliary-uplink budget. PHY substantiated from the rtl_433 CTT
// decoder + CTT's RadioLib test-tag firmware. HARDWARE LIMIT: this payload fits
// RAK3172-9-SM-NI, the 9xx-MHz SKU for US915/AU915/KR920/AS923; RAK assigns
// EU868 and 434 MHz to different ordering codes. The
// SX1262 may accept the register setting, but reliable sensitivity through the
// module matching network and installed antenna is not a supported claim. Keep
// CTT experimental until an exact tag HIL proves it. StratoLink-2's fitted
// high-band module has no qualified 434 MHz receive path, so the flight default
// fails closed. The decoder/window and env:ctt_diag remain available for a
// future real-tag test or a board fitted with a qualified low-band receiver.
#define CTT_LISTEN_ENABLE  false
#define CTT_FREQ_MHZ       434.0
#define CTT_LISTEN_MS      60000u   /* idle-window slice for tag listening */
#define CTT_EVENT_FPORT    11       /* dedicated sparse event uplink */

// ===== Class-A downlink command channel (analysis/network/08_command_control.md) =====
// Listen in the RX1/RX2 windows after each uplink and dispatch the small,
// bounded Stage-1 set below. Stage-2 behaviour-changers (cadence/SF/GPS reset/
// safe mode/rejoin) and their commit-confirm, persistence, and dead-man revert
// are design-only. Telemetry v2 ships the bounded Stage-1 sequence ACK and
// actual retained public-relay state.
#define CMD_ENABLE        true
#define CMD_FPORT         10             /* application fPort for our command protocol */
#ifndef CMD_BALLOON_ID
#define CMD_BALLOON_ID    0x0001         /* this balloon's command address (for B2B routing) */
#endif
#define CMD_BROADCAST     0xFFFFu
#define CMD_OP_PING       0x00           /* no-op; ACK sequence appears in next primary */
#define CMD_OP_RELAY      0x02           /* args[0] = 0/1 public Meshtastic only; never B2B */
#define CMD_OP_EASTER     0x7E           /* reserved fun */

// Debug Configuration
#ifndef DEBUG_ENABLE
#define DEBUG_ENABLE 0
#endif
#define DEBUG_SERIAL_BAUD 115200

#endif // CONFIG_H
