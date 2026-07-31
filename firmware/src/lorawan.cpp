/**
 * LoRaWAN driver, from first principles.
 * Manual OTAA join + ABP-style uplinks using RadioLib for radio only.
 * RAK3172 (STM32WLE5). Region selected via TTN_REGION_* in config.h.
 */
#include "lorawan.h"
#if __has_include("secrets.h") && !defined(B2B_RF_DIAG_BUILD)
#include "secrets.h"
#endif
#include "config.h"
#include "power_adc.h"
#include "power_manager.h"   /* for power_manager_kick_watchdog */
#include "ctt_decode.h"      /* CTT tag frame decode (pure logic) */
#include "ctt_queue.h"
#include "b2b.h"
#include "command.h"
#include "devnonce_store.h"
#include "crypto_aes128.h"
#include "lorawan_crypto.h"
#include "lorawan_frame.h"
#include "meshtastic_relay_mac.h"
#include <RadioLib.h>

/* Bench-soak build (env:stratolink_soak sets RELAY_SOLAR_MIN_MV=0) needs SubGhz.cpp
 * pulled into the link: a fresh env's LDF resolves RadioLib but not the framework's
 * SubGhz library, so SubGhzClass::* go undefined at link.  This shim makes a project
 * source depend on it (compiled with that env's -I) so SubGhz.cpp is built+linked.
 * The flight build (env:stratolink, RELAY_SOLAR_MIN_MV=3000) skips it entirely. */
#if defined(RELAY_SOLAR_MIN_MV) && (RELAY_SOLAR_MIN_MV == 0)
#include <SubGhz.h>
#endif

#if defined(DEBUG_ENABLE) && DEBUG_ENABLE
#define LOG(x) Serial.println(x)
#define LOGV(x,v) do { Serial.print(x); Serial.println(v); } while(0)
#else
#define LOG(x)    ((void)0)
#define LOGV(x,v) ((void)0)
#endif

static STM32WLx *radio = nullptr;
static bool radio_ready = false;
static bool _joined = false;

typedef struct {
    uint32_t begin_failures;
    uint32_t config_failures;
    uint32_t restore_attempts;
    uint32_t restore_recovered;
    uint32_t sleep_failures;
    int16_t  last_error;
    uint16_t allocation_failures;
} radio_diag_t;

/* J-Link-readable diagnostics for silent-PHY recovery. The primary v2 packet
 * carries only compact outcome fields, not these detailed counters. */
static volatile radio_diag_t s_radio_diag = {};

/* STM32duino's operator new returns malloc() directly.  The base build uses
 * -fcheck-new so GCC checks every result before invoking its constructor.
 * RadioLib's STM32WLx_Module constructor performs a second allocation for its
 * HAL; keep construction staged so every failure is observable and all
 * successfully allocated predecessors are released.  Static construction is
 * deliberately avoided: it would run before setup() arms the watchdog. */
static bool allocate_radio(void) {
    STM32WLx_Module* module = new STM32WLx_Module();
    if (!module || !module->hal) {
        if (module) delete module;
        if (s_radio_diag.allocation_failures != UINT16_MAX) {
            s_radio_diag.allocation_failures++;
        }
        s_radio_diag.last_error = RADIOLIB_ERR_MEMORY_ALLOCATION_FAILED;
        return false;
    }

    STM32WLx* candidate = new STM32WLx(module);
    if (!candidate) {
        delete module->hal;
        module->hal = nullptr;
        delete module;
        if (s_radio_diag.allocation_failures != UINT16_MAX) {
            s_radio_diag.allocation_failures++;
        }
        s_radio_diag.last_error = RADIOLIB_ERR_MEMORY_ALLOCATION_FAILED;
        return false;
    }

    radio = candidate;
    return true;
}

/* Session state (derived from OTAA join) */
static uint32_t devAddr = 0;
static uint8_t nwkSKey[16];
static uint8_t appSKey[16];
static uint32_t fCntUp = 0;
static uint32_t fCntDown = 0;      /* downlink frame counter (replay guard) */
static uint32_t s_tx_end_ms = 0;   /* millis() at end of the last uplink TX (RX-window timing) */
static uint8_t  s_tx_ch = 0;       /* channel index the last uplink used (for the RX1 downlink freq) */
static uint16_t s_last_join_devnonce = 0;
static bool s_have_join_devnonce = false;

/* OTAA credentials from secrets.h, parsed at init */
static uint8_t devEUI[8];
static uint8_t joinEUI[8];
static uint8_t appKey[16];

/* ========== Region Configuration ========== */
typedef struct {
    const float *tx_freqs;  uint8_t tx_ch_count;
    float rx2_freq;
    float rx1_base;  float rx1_step;  uint8_t rx1_mod; /* 0 = RX1 matches TX freq */
    uint8_t join_sf;  float join_bw;
    uint8_t rx1_sf;   float rx1_bw;
    uint8_t rx2_sf;   float rx2_bw;
    uint8_t rx1_dr_offset; uint8_t rx2_dr;
    float init_freq;
    uint8_t tx_sf;    float tx_bw;
} lora_region_t;

/* Uplink SF is 9 in every region (the last tx_sf field of each table).
 * Rationale (analysis/antenna/05_sf_linkbudget.md): SF9 buys +5 dB sensitivity
 * over SF7 (~2x link-budget range, past the 412 km radio horizon at 10 km), the
 * single biggest lever on a link that ran at the SF7 floor on flight-3.  Cost is
 * airtime: SF9 ToA ~329 ms for the 40-byte v2 payload, so the FULL-tier cadence
 * is 1200 s (config.h), ~23.67 s/day before the separately capped auxiliary
 * budget. JOIN SF is
 * unchanged (SF10 US/AU, SF7 EU/AS); that config is flight-proven, only uplinks
 * move to SF9.  RX1 SF matches join_sf via each region's RX1DROffset=0 mapping
 * (the previous code hardcoded rx1_sf=10 for US915/AU915 regardless of join, so
 * joins only ever succeeded via the RX2 fallback). */
static const float US915_FREQS[] = {
    903.9f, 904.1f, 904.3f, 904.5f, 904.7f, 904.9f, 905.1f, 905.3f
};
static const lora_region_t LORA_US915 = {
    /* US915 sub-band 2.  Join at DR0 (SF10/125), RX1 at DR10 (SF10/500)
     * per RP002 RX1 data-rate offset 0, this is the only join SF that
     * matches our rx1_sf without computing the DR2→DR8/DR3→DR8 cross-DR
     * mapping at runtime.  Yesterday's flight firmware ran this config
     * and joined cleanly through onethreenine gateway at -45 dBm.
     * Uplinks tx_sf=9 (DR1) for range. Class-A RX1 uses the corresponding
     * downlink data-rate mapping below. */
    US915_FREQS, 8, 923.3f, 923.3f, 0.6f, 8,
    10, 125.0f, 10, 500.0f, 12, 500.0f, 0, 8, 904.1f, 9, 125.0f
};

static const float EU868_FREQS[] = {868.1f, 868.3f, 868.5f};
static const lora_region_t LORA_EU868 = {
    EU868_FREQS, 3, 869.525f, 0, 0, 0, /* RX1 = TX freq */
    7, 125.0f, 7, 125.0f, 9, 125.0f, 0, 3, 868.1f, 9, 125.0f
};

static const float AU915_FREQS[] = {
    916.8f, 917.0f, 917.2f, 917.4f, 917.6f, 917.8f, 918.0f, 918.2f
};
static const lora_region_t LORA_AU915 = {
    /* AU915 same RP002 RX1 rule as US915, join at DR2/SF10 to match
     * RX1 DR10/SF10/500 without cross-DR offset math.  See US915
     * block above for the rationale. */
    AU915_FREQS, 8, 923.3f, 923.3f, 0.6f, 8,
    10, 125.0f, 10, 500.0f, 12, 500.0f, 0, 8, 917.0f, 9, 125.0f
};

static const float AS923_FREQS[] = {923.2f, 923.4f};
static const lora_region_t LORA_AS923 = {
    AS923_FREQS, 2, 923.2f, 0, 0, 0, /* RX1 = TX freq */
    7, 125.0f, 7, 125.0f, 10, 125.0f, 0, 2, 923.2f, 9, 125.0f
};

/* REGION is a mutable copy of one of the const tables above, switched
 * at runtime by lorawan_set_region() based on GPS-derived geofence
 * (region_manager.cpp).  Default at boot = US915, overwritten on the
 * first region check after a valid GPS fix.  Copying the struct (vs
 * a const reference) lets the same call sites work unchanged. */
static lora_region_t REGION = LORA_US915;
static lora_region_id_t REGION_ID = LORA_REGION_US915;

static uint8_t chIdx = 0;

/* RadioLib configuration calls can fail independently of transmit(). Ignoring
 * one after a Meshtastic/CTT window can produce the worst kind of outage: the
 * radio successfully emits the next "LoRaWAN" frame with the stale carrier,
 * sync word, or modulation, so tx_fail_streak never notices while every
 * gateway stays deaf. Apply each complete PHY transactionally and fail before
 * RF if any step did not reach the modem. */
static bool radio_apply_lora_phy(float frequency, uint8_t sf, float bandwidth,
                                 uint8_t sync_word, uint16_t preamble,
                                 bool crc, bool inverted_iq) {
    if (!radio) return false;
    int16_t state = radio->standby();
    if (state == RADIOLIB_ERR_NONE) state = radio->setFrequency(frequency);
    if (state == RADIOLIB_ERR_NONE) state = radio->setSpreadingFactor(sf);
    if (state == RADIOLIB_ERR_NONE) state = radio->setBandwidth(bandwidth);
    if (state == RADIOLIB_ERR_NONE) state = radio->setCodingRate(5);
    if (state == RADIOLIB_ERR_NONE) state = radio->setSyncWord(sync_word);
    if (state == RADIOLIB_ERR_NONE) state = radio->setPreambleLength(preamble);
    if (state == RADIOLIB_ERR_NONE) state = radio->setCRC(crc);
    if (state == RADIOLIB_ERR_NONE) state = radio->invertIQ(inverted_iq);
    radio_ready = (state == RADIOLIB_ERR_NONE);
    if (!radio_ready) {
        s_radio_diag.config_failures++;
        s_radio_diag.last_error = state;
    }
    return radio_ready;
}

static bool radio_apply_lorawan_tx(float frequency) {
    return radio_apply_lora_phy(frequency, REGION.tx_sf, REGION.tx_bw,
                                RADIOLIB_SX126X_SYNC_WORD_PUBLIC, 8,
                                true, false);
}

/* RF switch */
static const uint32_t rfswitch_pins[] =
    {PB8, PC13, RADIOLIB_NC, RADIOLIB_NC, RADIOLIB_NC};
static const Module::RfSwitchMode_t rfswitch_table[] = {
    {STM32WLx::MODE_IDLE,  {LOW,  LOW}},
    {STM32WLx::MODE_RX,    {HIGH, LOW}},
    {STM32WLx::MODE_TX_HP, {HIGH, HIGH}},
    END_OF_MODE_TABLE,
};

/* ========== Hex parsing ========== */
static void hexToBytes(const char *h, uint8_t *o, size_t n) {
    for (size_t i=0;i<n;i++) {
        uint8_t b=0;
        for (size_t j=0;j<2;j++) { b<<=4; char c=h[i*2+j];
            if(c>='0'&&c<='9') b|=c-'0'; else if(c>='A'&&c<='F') b|=c-'A'+10; else if(c>='a'&&c<='f') b|=c-'a'+10;
        } o[i]=b;
    }
}

static bool exactHex(const char* h, size_t chars) {
    if (!h) return false;
    for (size_t i = 0; i < chars; i++) {
        char c = h[i];
        bool hex = (c >= '0' && c <= '9') ||
                   (c >= 'A' && c <= 'F') ||
                   (c >= 'a' && c <= 'f');
        if (!hex) return false;
    }
    return h[chars] == '\0';
}


/* Network-assigned RECEIVE_DELAY1 in seconds, learned from the join accept.
 * TTN currently assigns 5 s for these devices. It is persisted with the
 * session: reverting to a compiled assumption after a watchdog reset would
 * leave a valid restored uplink session with a silently deaf command channel
 * if any cluster or future network assignment differs. */
static uint8_t s_rx_delay_s = 5;

/* Radio service can leave the MCU waiting from milliseconds to almost the
 * complete 20-minute cadence. The framework's default weak yield() is empty,
 * so these paths historically busy-spun. The application now also supplies a
 * shallow-WFI yield for ordinary delays, but radio waits keep this dedicated
 * helper because they own explicit deadlines, watchdog service, and freefall
 * preemption. SysTick remains enabled, so millis() and RF deadlines advance
 * with <=1 ms wake granularity. This is CPU SLEEP, not STOP; radio and system
 * clocks remain live. */
static void radio_idle_until_interrupt(void) {
#if defined(ARDUINO_ARCH_STM32)
    /* HAL's STOP1 exit currently clears SLEEPDEEP, but make this helper's
     * shallow-sleep contract self-contained rather than inheriting a prior
     * power-mode bit. The radio, SysTick, and EXTI must remain clocked. */
    SCB->SCR &= ~SCB_SCR_SLEEPDEEP_Msk;
    __DSB();
    __WFI();
    __ISB();
#else
    delay(1);
#endif
}

/* Wait to an absolute offset from a TX while remaining freefall- and
 * watchdog-responsive. False means the recovery mission preempted this
 * optional receive opportunity. */
static bool radio_wait_until(uint32_t anchor_ms, uint32_t offset_ms) {
    uint32_t last_kick = millis();
    while ((int32_t)(millis() - anchor_ms) < (int32_t)offset_ms) {
        if (power_manager_freefall_pending()) return false;
        uint32_t now = millis();
        if (now - last_kick >= 1000u) {
            power_manager_kick_watchdog();
            last_kick = now;
        }
        radio_idle_until_interrupt();
    }
    return true;
}

/* A bounded asynchronous join window. RadioLib's blocking receive(data, 33)
 * derives its default timeout as five times the maximum packet airtime. When
 * RX1 is empty that can run past JOIN_ACCEPT_DELAY2, making the nominal RX2
 * fallback deaf. RxDone is interrupt-driven here and an empty window is
 * stopped at the caller's absolute deadline. */
static volatile bool s_join_rx = false;
static void join_rx_isr(void) { s_join_rx = true; }
static size_t join_rx_window(uint8_t* buf, size_t maxlen,
                             uint32_t deadline_ms,
                             bool* mission_aborted) {
    if (mission_aborted) *mission_aborted = false;
    s_join_rx = false;
    radio->setPacketReceivedAction(join_rx_isr);
    int16_t state = radio->startReceive();
    if (state != RADIOLIB_ERR_NONE) {
        radio->clearPacketReceivedAction();
        radio->standby();
        return 0;
    }
    uint32_t last_kick = millis();
    while ((int32_t)(millis() - deadline_ms) < 0) {
        if (s_join_rx) break;
        if (power_manager_freefall_pending()) {
            if (mission_aborted) *mission_aborted = true;
            break;
        }
        uint32_t now = millis();
        if (now - last_kick >= 1000u) {
            power_manager_kick_watchdog();
            last_kick = now;
        }
        radio_idle_until_interrupt();
    }
    radio->clearPacketReceivedAction();
    size_t n = 0;
    if (s_join_rx) {
        n = radio->getPacketLength();
        if (n > maxlen || radio->readData(buf, n) != RADIOLIB_ERR_NONE) {
            n = 0;
        }
    }
    if (radio->standby() != RADIOLIB_ERR_NONE) {
        radio_ready = false;
        return 0;
    }
    return n;
}

/* ========== OTAA Join ========== */
static bool otaa_join(void) {
    /* Build join request: MHDR(1) + JoinEUI(8,LE) + DevEUI(8,LE) + DevNonce(2,LE) + MIC(4) = 23 bytes */
    uint8_t pkt[23];
    pkt[0] = 0x00; /* MHDR: join request */

    /* JoinEUI and DevEUI in LITTLE ENDIAN (reversed from display order) */
    for (int i=0;i<8;i++) pkt[1+i] = joinEUI[7-i];
    for (int i=0;i<8;i++) pkt[9+i] = devEUI[7-i];

    /* Configure the complete join TX PHY before allocating a durable nonce.
     * A modem configuration failure must neither emit on stale settings nor
     * consume finite flash-journal capacity. */
    uint8_t ch = chIdx % REGION.tx_ch_count;
    chIdx++;
    if (!radio_apply_lora_phy(
            REGION.tx_freqs[ch], REGION.join_sf, REGION.join_bw,
            RADIOLIB_SX126X_SYNC_WORD_PUBLIC, 8, true, false)) {
        radio_ready = false;
        return false;
    }

    /* Allocate and durably journal BEFORE transmit. A reset during the join
     * exchange therefore burns a nonce instead of replaying it. LoRaWAN
     * rejects reused DevNonce values; micros() repeated readily after reboot. */
    uint16_t devNonce = 0;
    if (!devnonce_next(&devNonce)) {
        LOG("[OTAA] DevNonce journal exhausted or unavailable");
        return false;
    }
    s_last_join_devnonce = devNonce;
    s_have_join_devnonce = true;
    pkt[17] = (uint8_t)(devNonce & 0xFFu);
    pkt[18] = (uint8_t)((devNonce >> 8) & 0xFFu);

    /* MIC over MHDR|JoinEUI|DevEUI|DevNonce using AppKey */
    (void)lorawan_crypto_cmac4(appKey, pkt, 19, &pkt[19]);

    int16_t state = radio->transmit(pkt, 23);
    if (state != RADIOLIB_ERR_NONE) {
        LOGV("[OTAA] TX fail: ", state);
        return false;
    }
    LOG("[OTAA] Join request sent");
    unsigned long txEnd = millis();

    /* Ensure radio is fully back in standby before configuring RX */
    if (radio->standby() != RADIOLIB_ERR_NONE) {
        radio_ready = false;
        return false;
    }
    delay(5);

    uint8_t rxBuf[64];
    uint8_t dec[33] = {};
    size_t rxLen = 0;
    bool received = false;
    bool mission_aborted = false;

    /* Join-accept windows are fixed by LoRaWAN at 5 s and 6 s after TX.
     * Start 250 ms early to absorb host/radio cleanup jitter. RX1 ends at
     * +5.5 s, leaving 250 ms to retune before RX2; current regional RX1
     * mappings (SF10/500 or SF7/125) complete a maximum 33-byte accept well
     * inside that bound. */
    power_manager_kick_watchdog();
    float rx1Freq = REGION.rx1_mod
        ? (REGION.rx1_base + (ch % REGION.rx1_mod) * REGION.rx1_step)
        : REGION.tx_freqs[ch];
    if (!radio_apply_lora_phy(
            rx1Freq, REGION.rx1_sf, REGION.rx1_bw,
            RADIOLIB_SX126X_SYNC_WORD_PUBLIC, 8, false, true)) {
        radio_ready = false;
        return false;
    }

    if (!radio_wait_until(txEnd, 4750u)) {
        mission_aborted = true;
    }
    const uint32_t join_rx1_deadline = txEnd + 5500u;
    while (!received && !mission_aborted &&
           (int32_t)(millis() - join_rx1_deadline) < 0) {
        rxLen = join_rx_window(
            rxBuf, sizeof(rxBuf), join_rx1_deadline, &mission_aborted);
        if (mission_aborted) break;
        if (!rxLen) {
            if (s_join_rx) continue;  /* oversize/read-failed IRQ: stay bounded */
            break;                    /* true deadline or arm failure */
        }
        received = lorawan_frame_decode_join_accept(
            appKey, rxBuf, rxLen, dec);
        /* Re-arm within the same absolute window after unrelated or malformed
         * traffic. A nuisance packet before the network transmission must not
         * preempt either the remainder of RX1 or the RX2 fallback. */
    }
    if (received) LOG("[OTAA] Authenticated join-accept in RX1!");
    else rxLen = 0;

    /* RX2: 6 s after TX. The slowest implemented mapping is AS923
     * SF10/125; +740 ms accommodates the complete 33-byte maximum. */
    if (!received && !mission_aborted &&
        (int32_t)(millis() - (txEnd + 7000u)) < 0) {
        if (!radio_apply_lora_phy(
                REGION.rx2_freq, REGION.rx2_sf, REGION.rx2_bw,
                RADIOLIB_SX126X_SYNC_WORD_PUBLIC, 8, false, true)) {
            radio_ready = false;
            return false;
        }

        if (!radio_wait_until(txEnd, 5750u)) {
            mission_aborted = true;
        }
        const uint32_t join_rx2_deadline = txEnd + 6740u;
        while (!received && !mission_aborted &&
               (int32_t)(millis() - join_rx2_deadline) < 0) {
            rxLen = join_rx_window(
                rxBuf, sizeof(rxBuf), join_rx2_deadline, &mission_aborted);
            if (mission_aborted) break;
            if (!rxLen) {
                if (s_join_rx) continue;
                break;
            }
            received = lorawan_frame_decode_join_accept(
                appKey, rxBuf, rxLen, dec);
        }
        if (received) LOG("[OTAA] Authenticated join-accept in RX2!");
        else rxLen = 0;
    }

    /* Restore the complete TX config from the active region. A partial
     * restore after RX2 is a silent-success failure: transmit() can return OK
     * while gateways hear the wrong IQ/sync/DR. */
    if (!radio_apply_lorawan_tx(REGION.init_freq)) {
        radio_ready = false;
        return false;
    }

    if (mission_aborted) return false;

    if (!received) {
        LOG("[OTAA] No join-accept");
        return false;
    }
    LOGV("[OTAA] Received ", (int)rxLen);

    LOG("[OTAA] Join-accept verified!");

    /* Parse join-accept: MHDR(1) + AppNonce(3) + NetID(3) + DevAddr(4) + DLSettings(1) + RxDelay(1) [+ CFList] + MIC(4) */
    uint8_t rx1_offset = (uint8_t)((dec[11] >> 4) & 0x07u);
    uint8_t rx2_dr = (uint8_t)(dec[11] & 0x0Fu);
    if ((dec[11] & 0x80u) != 0 ||
        rx1_offset != REGION.rx1_dr_offset || rx2_dr != REGION.rx2_dr) {
        /* This compact stack implements one audited RX mapping per region.
         * Silently accepting a different network assignment would produce a
         * joined-but-deaf command channel, so fail the join explicitly. */
        LOG("[OTAA] unsupported DLSettings");
        return false;
    }
    uint8_t appNonce[3] = {dec[1], dec[2], dec[3]};
    /* uint8_t netID[3] = {dec[4], dec[5], dec[6]}; */
    devAddr = (uint32_t)dec[7] | ((uint32_t)dec[8]<<8) | ((uint32_t)dec[9]<<16) | ((uint32_t)dec[10]<<24);

    /* RxDelay (dec[12], low nibble) is the network's RECEIVE_DELAY1 in seconds,
     * where 0 means 1 s.  It MUST be honoured: TTN assigns 5 s for these
     * devices (verified in the network-server record), while the LoRaWAN spec
     * default is 1 s.  Opening the windows at the spec default made the
     * Class-A command channel deaf, since the gateway transmits four seconds
     * after our windows have already closed. */
    s_rx_delay_s = (uint8_t)(dec[12] & 0x0F);
    if (s_rx_delay_s == 0) s_rx_delay_s = 1;
    LOGV("[OTAA] RxDelay (s): ", s_rx_delay_s);

    LOGV("[OTAA] DevAddr: 0x", devAddr);

    /* Derive session keys (LoRaWAN 1.0.x) */
    /* NwkSKey = aes128_encrypt(AppKey, 0x01|AppNonce|NetID|DevNonce|pad) */
    /* AppSKey = aes128_encrypt(AppKey, 0x02|AppNonce|NetID|DevNonce|pad) */
    (void)lorawan_crypto_session_key(appKey, 1, appNonce, &dec[4],
                                     devNonce, nwkSKey);
    (void)lorawan_crypto_session_key(appKey, 2, appNonce, &dec[4],
                                     devNonce, appSKey);

    fCntUp = 0;
    fCntDown = 0;
    LOG("[OTAA] Session keys derived");
    return true;
}

/* ========== Uplink MIC ========== */
static void compute_mic(const uint8_t *msg, size_t msgLen, uint8_t *mic) {
    (void)lorawan_crypto_mic(nwkSKey, devAddr, fCntUp, 0,
                             msg, msgLen, mic);
}

/* ========== Public API ========== */
/* ========== Per-region OTAA credentials ==========
 *
 * TTN community network enforces globally-unique DevEUIs across all
 * clusters (nam1, eu1).  To get telemetry in multiple LoRaWAN regions
 * during a circumnavigation, each frequency plan needs its own
 * (DevEUI, AppKey) pair registered on the appropriate cluster.  The
 * flight firmware switches credentials when lorawan_set_region fires
 * a transition, so the next OTAA join uses the right identity for
 * the gateway listening below.
 *
 * Empty string = no creds for that region → lorawan_join returns
 * false immediately (firmware still respects geofence spectrum rules
 * via the SILENT/region-table channels, just won't transmit OTAA
 * traffic without valid credentials).
 *
 * JoinEUI is shared (TTN convention 00...00) and loaded once in
 * lorawan_init from LORAWAN_APP_EUI.
 *
 * Backward compatibility: older secrets files (secrets_board1.h,
 * secrets_board2.h) only define the legacy LORAWAN_DEV_EUI /
 * LORAWAN_APP_KEY pair.  The #ifndef guards below let those builds
 * succeed by mapping the legacy pair into the US915 slot and leaving
 * EU/AS/AU empty, single-region behaviour, same as before. */
#ifndef LORAWAN_DEV_EUI_US
#define LORAWAN_DEV_EUI_US LORAWAN_DEV_EUI
#endif
#ifndef LORAWAN_APP_KEY_US
#define LORAWAN_APP_KEY_US LORAWAN_APP_KEY
#endif
#ifndef LORAWAN_DEV_EUI_EU
#define LORAWAN_DEV_EUI_EU ""
#endif
#ifndef LORAWAN_APP_KEY_EU
#define LORAWAN_APP_KEY_EU ""
#endif
#ifndef LORAWAN_DEV_EUI_AS
#define LORAWAN_DEV_EUI_AS ""
#endif
#ifndef LORAWAN_APP_KEY_AS
#define LORAWAN_APP_KEY_AS ""
#endif
#ifndef LORAWAN_DEV_EUI_AU
#define LORAWAN_DEV_EUI_AU ""
#endif
#ifndef LORAWAN_APP_KEY_AU
#define LORAWAN_APP_KEY_AU ""
#endif

typedef struct {
    const char* dev_eui_hex;
    const char* app_key_hex;
} region_creds_t;

static const region_creds_t REGION_CREDS[LORA_REGION_COUNT] = {
    /* Indexed by lora_region_id_t.  Order must match the enum in
     * lorawan.h: US915=0, EU868=1, AS923=2, AU915=3, SILENT=4. */
    { LORAWAN_DEV_EUI_US, LORAWAN_APP_KEY_US },
    { LORAWAN_DEV_EUI_EU, LORAWAN_APP_KEY_EU },
    { LORAWAN_DEV_EUI_AS, LORAWAN_APP_KEY_AS },
    { LORAWAN_DEV_EUI_AU, LORAWAN_APP_KEY_AU },
    { "",                  ""                  },  /* SILENT */
};

static bool creds_loaded = false;

static void load_creds_for_current_region(void) {
    creds_loaded = false;
    if (REGION_ID >= LORA_REGION_SILENT) return;
    const region_creds_t* c = &REGION_CREDS[REGION_ID];
    if (!exactHex(LORAWAN_APP_EUI, 16) ||
        !exactHex(c->dev_eui_hex, 16) ||
        !exactHex(c->app_key_hex, 32)) return;
    hexToBytes(c->dev_eui_hex, devEUI, 8);
    hexToBytes(c->app_key_hex, appKey, 16);
    creds_loaded = true;
}

bool lorawan_creds_loaded(void) { return creds_loaded; }
void lorawan_get_dev_eui(uint8_t* out) { if (out) memcpy(out, devEUI, 8); }

bool lorawan_init(void) {
    HAL_ResumeTick();
    if (!radio && !allocate_radio()) return false;
    radio->setRfSwitchTable(rfswitch_pins, rfswitch_table);

    radio_ready = false;
    int16_t state = RADIOLIB_ERR_UNKNOWN;
    for (uint8_t attempt = 0; attempt < 3; ++attempt) {
        state = radio->begin(REGION.init_freq, REGION.tx_bw, 9, 7,
                             RADIOLIB_SX126X_SYNC_WORD_PUBLIC,
                             14, 8, 1.7f, false);
        if (state == RADIOLIB_ERR_NONE) {
            radio_ready = true;
            break;
        }
        s_radio_diag.begin_failures++;
        s_radio_diag.last_error = state;
        power_manager_kick_watchdog();
        delay(20);
    }
    LOGV("[LoRaWAN] radio.begin: ", state);
    if (!radio_ready) return false;

    if (!radio_apply_lorawan_tx(REGION.init_freq)) {
        radio_ready = false;
        return false;
    }

    /* JoinEUI is shared across regions; DevEUI + AppKey are loaded
     * per-region by load_creds_for_current_region (called below and
     * also from lorawan_set_region on every transition). */
    if (exactHex(LORAWAN_APP_EUI, 16)) {
        hexToBytes(LORAWAN_APP_EUI, joinEUI, 8);
    } else {
        memset(joinEUI, 0, sizeof(joinEUI));
    }
    load_creds_for_current_region();

    LOG("[LoRaWAN] init OK");
    return true;
}

bool lorawan_join(uint32_t timeout_ms) {
    if (REGION_ID == LORA_REGION_SILENT) return false;  /* off-plan zone */
    /* A transient boot-time begin failure must not strand a restored session
     * or a never-joined payload forever. Re-run the bounded hardware init at
     * the next mission TX opportunity. Session keys/counters live outside the
     * radio object and remain intact. */
    if (!radio_ready && !lorawan_init()) return false;
    if (!creds_loaded) {
        LOG("[LoRaWAN] no OTAA creds for current region, skipping join");
        return false;
    }

    /* Skip the join if VSTOR is too low to reliably support +14 dBm TX
     * peaks (~50 mA bursts).  Below ~3.0 V the buck is in dropout and
     * Vdd droops hard during TX, failed joins burn the supercap fast
     * (the IWDG-reset-then-rejoin spiral observed empirically drains
     * 1.7 V in 4-5 minutes).  Returning false here lets loop() proceed
     * to a normal cycle which then sleeps; setup() retries join on the
     * next cold boot, by which point either solar has recharged the cap
     * or the chip browns out gracefully and waits. */
    if (power_adc_read_vSTOR_mv() < 3000) {
        LOG("[LoRaWAN] vstor too low to join");
        return false;
    }

    /* Wake the SX1262 from SLEEP retention (set by lorawan_sleep() on
     * the previous cycle) before any join-request TX.  Without this
     * the setFrequency()/transmit() calls in otaa_join() run against a
     * sleeping radio and the join silently fails forever, matches
     * lorawan_send_uplink()'s explicit standby() pattern. */
    if (!radio_apply_lorawan_tx(REGION.init_freq)) {
        radio_ready = false;
        return false;
    }

    /* One complete exchange can occupy the radio through RX2 at +6.74 s.
     * Never start a retry that cannot finish inside the caller's budget, and
     * recheck VSTOR before every nonce allocation/TX. Previously a retry could
     * begin at ~14 s in a nominal 15 s call and stretch active draw past 20 s.
     * Flight's 15 s call now performs one deliberate attempt; later attempts
     * use main.cpp's energy-aware 1/2/4-cycle backoff. */
    static constexpr uint32_t JOIN_ATTEMPT_BUDGET_MS = 7000u;
    unsigned long start = millis();
    while (millis() - start < timeout_ms) {
        uint32_t elapsed = millis() - start;
        uint32_t remaining = timeout_ms - elapsed;
        if (remaining < JOIN_ATTEMPT_BUDGET_MS) break;
        if (power_adc_read_vSTOR_mv() < 3000) {
            LOG("[LoRaWAN] vstor fell below join floor");
            break;
        }
        if (otaa_join()) {
            _joined = true;
            LOG("[LoRaWAN] OTAA joined!");
            return true;
        }
        elapsed = millis() - start;
        if (elapsed >= timeout_ms) break;
        uint32_t retry_delay = 3000u + (millis() & 0xFFFu);
        remaining = timeout_ms - elapsed;
        if (remaining <= JOIN_ATTEMPT_BUDGET_MS ||
            retry_delay > remaining - JOIN_ATTEMPT_BUDGET_MS) break;
        delay(retry_delay);
    }
    LOG("[LoRaWAN] join timeout");
    return false;
}

bool lorawan_send_uplink_port(uint8_t fport, const uint8_t* payload, uint8_t payload_len) {
    if (!_joined || !payload || fport == 0 ||
        payload_len > LORAWAN_PAYLOAD_MAX ||
        fCntUp == UINT32_MAX) return false;
    if (REGION_ID == LORA_REGION_SILENT) return false;  /* off-plan zone */
    if (!radio_ready && !lorawan_init()) return false;

    /* MHDR(1) + FHDR without FOpts(7) + FPort(1) + payload + MIC(4).
     * Derive the storage from the public payload ceiling so a future ceiling
     * edit cannot silently outgrow a stale magic-sized local buffer. */
    static constexpr size_t UPLINK_FIXED_BYTES = 13u;
    static constexpr size_t UPLINK_FRAME_BYTES =
        UPLINK_FIXED_BYTES + LORAWAN_PAYLOAD_MAX;
    static_assert(UPLINK_FRAME_BYTES <= UINT8_MAX,
                  "uplink frame length no longer fits the packet index");
    uint8_t pkt[UPLINK_FRAME_BYTES]; uint8_t idx = 0;
    pkt[idx++] = 0x40;
    pkt[idx++]=(uint8_t)(devAddr & 0xFFu);
    pkt[idx++]=(uint8_t)((devAddr >> 8) & 0xFFu);
    pkt[idx++]=(uint8_t)((devAddr >> 16) & 0xFFu);
    pkt[idx++]=(uint8_t)((devAddr >> 24) & 0xFFu);
    pkt[idx++]=0x00;
    pkt[idx++]=(uint8_t)(fCntUp & 0xFFu);
    pkt[idx++]=(uint8_t)((fCntUp >> 8) & 0xFFu);
    pkt[idx++]=fport;
    memcpy(&pkt[idx], payload, payload_len);
    (void)lorawan_crypto_payload(appSKey, devAddr, fCntUp, 0,
                                 &pkt[idx], payload_len);
    idx += payload_len;
    uint8_t mic[4]; compute_mic(pkt, idx, mic);
    memcpy(&pkt[idx], mic, 4); idx += 4;

    s_tx_ch = (uint8_t)(chIdx % REGION.tx_ch_count);
    float freq = REGION.tx_freqs[s_tx_ch]; chIdx++;
    /* This complete checked transaction wakes SLEEP retention and prevents a
     * stale relay/CTT PHY from masquerading as a successful LoRaWAN TX. */
    if (!radio_apply_lorawan_tx(freq)) {
        radio_ready = false;
        return false;
    }

    /* Reserve the counter durably BEFORE RF. A supercap brownout can occur
     * during or immediately after the TX peak; persisting only after transmit
     * left a reset window where the next boot restored and replayed the frame
     * counter TTN had already accepted. Counter gaps after a failed TX are
     * legal, while counter reuse is not, so advance RAM and atomically commit
     * the next value before handing the frame to the radio. The packet above
     * was already encrypted/MICed with the pre-increment value. */
    fCntUp++;
    lorawan_session_t reserved;
    lorawan_export_session(&reserved);
    if (!power_manager_save_session(&reserved)) {
        LOG("[LoRaWAN] FCntUp reservation failed");
        return false;
    }

    int16_t state = radio->transmit(pkt, idx);
    LOGV("[LoRaWAN] uplink: ", state);
    if (state == RADIOLIB_ERR_NONE) {
        s_tx_end_ms = millis();  /* RX windows anchor to the last SUCCESSFUL TX */
        return true;
    }
    return false;
}

bool lorawan_send_uplink(const uint8_t* payload, uint8_t payload_len) {
    return lorawan_send_uplink_port(1, payload, payload_len);
}

bool lorawan_joined(void) { return _joined; }

void lorawan_sleep(void) {
    /* SX1262 SLEEP w/ retention. ~3 µA. Next transmit() implicitly wakes it
     * (RadioLib calls setStandby before configuring TX). Without this, the
    * radio stays in STDBY_RC across STOP1, which kills the energy budget.
    * The older STOP2 path also hard-reset the RAK3172 during entry. */
    int16_t sleep_state = RADIOLIB_ERR_UNKNOWN;
    if (radio_ready) {
        sleep_state = radio->sleep(true);
        if (sleep_state == RADIOLIB_ERR_NONE) return;
        s_radio_diag.last_error = sleep_state;
    }
    /* A failed sleep can strand the modem in STDBY_RC at ~600 uA for the
     * entire 20-30 minute interval. `radio_ready == false` is not proof of a
     * sleeping modem either: a failed post-relay restore or partial PHY update
     * can leave the hardware awake even though software correctly refuses RF.
     * Rebuild the PHY once and demand a confirmed sleep on both paths; reset
     * only if the radio cannot be made quiescent. */
    s_radio_diag.sleep_failures++;
    radio_ready = false;
    int16_t retry_state = RADIOLIB_ERR_NONE;
    if (!lorawan_init() ||
        (retry_state = radio->sleep(true)) != RADIOLIB_ERR_NONE) {
        if (retry_state != RADIOLIB_ERR_NONE) {
            s_radio_diag.sleep_failures++;
            s_radio_diag.last_error = retry_state;
        }
        NVIC_SystemReset();
    }
}

/* ========== Meshtastic open-relay (mission-subordinate, power-gated) ==========
 *
 * A header-only, KEYLESS LongFast repeater that runs on the SHARED SX1262 in the
 * idle time between TTN cycles, ONLY when the caller says power allows.  The
 * 16-byte Meshtastic PacketHeader is plaintext, so we forward real traffic
 * (dedup + hop-decrement + airtime cap) WITHOUT any channel PSK, "relay what we
 * hear, register nothing."  Validated on a live mesh 2026-06-03 (RESULTS.md).
 *
 * SAFETY (defense in depth): the caller (main.cpp) gates entry on FULL tier +
 * solar + !burst; this window additionally (a) self-aborts the instant
 * VSTOR < floor_mv, (b) caps its own TX airtime, (c) yields by max_ms so the next
 * TTN cycle is on time, and (d) on EVERY exit restores the EXACT post-init
 * LoRaWAN TX PHY (SF9/BW125/CR5/sync-PUBLIC/preamble-8/CRC) that send_uplink()
 * depends on.  The LoRaWAN session (DevAddr/keys/FCnt) is never touched. */

/* Meshtastic LongFast default-channel centre per region.  0 => not relay-eligible
 * (we only TX Meshtastic where the frequency is validated + practically legal). */
static float meshtastic_longfast_freq(lora_region_id_t id) {
    switch (id) {
        case LORA_REGION_US915: return 906.875f;  /* US LongFast slot 19 */
        case LORA_REGION_EU868: return 869.525f;  /* EU LongFast */
        /* The two LoRaWAN common channels (923.2/923.4) overlap the TTN
         * AS_920_923 and AS_923_925 plans, but Meshtastic's 923.125 MHz
         * BW250 LongFast channel extends below the latter plan's 923.2 MHz
         * lower edge. A single coarse AS region cannot prove that relay/B2B
         * carrier legal, so keep it receive/TX-ineligible until the geofence
         * distinguishes the AS sub-plan. */
        case LORA_REGION_AS923: return 0.0f;
        case LORA_REGION_AU915: return 919.875f;  /* ANZ LongFast slot 19 */
        default:                return 0.0f;       /* SILENT: disabled */
    }
}

/* Forwarded-frame dedup ring (managed-flood good-citizen: never re-forward the
 * same (from,id) twice).  Persists across windows for stronger suppression. */
#define RELAY_DEDUP_N 32
static uint32_t s_dd_from[RELAY_DEDUP_N];
static uint32_t s_dd_id[RELAY_DEDUP_N];
static uint8_t  s_dd_head = 0;
static bool relay_dd_seen(uint32_t f, uint32_t i) {
    for (uint8_t k = 0; k < RELAY_DEDUP_N; k++)
        if (s_dd_from[k] == f && s_dd_id[k] == i) return true;
    return false;
}
static void relay_dd_mark(uint32_t f, uint32_t i) {
    s_dd_from[s_dd_head] = f; s_dd_id[s_dd_head] = i;
    s_dd_head = (uint8_t)((s_dd_head + 1) % RELAY_DEDUP_N);
}
static inline uint32_t relay_rd_u32le(const uint8_t* p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static volatile bool s_relay_rx = false;
static void relay_rx_isr(void) { s_relay_rx = true; }
static lorawan_relay_stats_t s_relay = {};
static uint8_t s_relay_buf[256];
static mesh_relay_mac_t s_relay_mac;

static bool relay_arm_receive(void) {
    s_relay_rx = false;
    int16_t state = radio->startReceive();
    if (state == RADIOLIB_ERR_NONE) return true;
    s_relay.rx_arm_fail++;
    s_radio_diag.last_error = state;
    return false;
}

/* B2B shares this exact LongFast PHY but is unambiguously separated from
 * Meshtastic by its "SB"/version prefix.  State survives STOP cycles in RAM. */
static b2b_t s_b2b;
static bool s_b2b_initialized = false;
static b2b_crumb_t s_b2b_latest_crumb;
static bool s_b2b_crumb_pending = false;
static bool s_b2b_crumb_frame_ready = false;
static b2b_frame_t s_b2b_crumb_frame;
static uint32_t s_b2b_latest_crumb_rtc_sec = 0;
static uint32_t s_b2b_last_crumb_rtc_sec = 0;
static bool s_b2b_ever_sent_crumb = false;

#define B2B_ORIGIN_N 4
static b2b_frame_t s_b2b_origin[B2B_ORIGIN_N];
static uint8_t s_b2b_origin_head = 0, s_b2b_origin_tail = 0, s_b2b_origin_n = 0;

#define B2B_UPLINK_N 8
static b2b_frame_t s_b2b_uplink[B2B_UPLINK_N];
static uint8_t s_b2b_uplink_head = 0, s_b2b_uplink_tail = 0, s_b2b_uplink_n = 0;
static uint8_t s_b2b_fleet_key[16];
static bool s_b2b_auth_ready = false;
static bool s_b2b_origin_id_ready = false;
static_assert(B2B_FRAME_MAX <= LORAWAN_PAYLOAD_MAX,
              "B2B tunnel exceeds the common regional uplink ceiling");
static_assert(CMD_BROADCAST == B2B_ID_BROADCAST,
              "command and B2B broadcast namespaces must agree");
static_assert(CMD_BALLOON_ID != B2B_ID_BROADCAST,
              "a balloon origin ID cannot use the broadcast target");

static void b2b_prepare_origin_id(void) {
    if (s_b2b_origin_id_ready) return;

    uint8_t retained = 0;
    if (power_manager_load_b2b_msg_id(&retained)) {
        s_b2b.next_msg_id = retained;
    } else {
        /* A true backup-domain loss also destroys the LoRaWAN session and
         * forces a new durable DevNonce before the first B2B-capable relay
         * window. Fold that nonce, the new DevAddr, and the already reserved
         * FCntUp into a non-constant cold-start seed. A one-time upgrade over
         * a retained legacy session still gets a session/counter-derived
         * seed, then every successor is retained before RF. */
        uint32_t mix = devAddr ^ (fCntUp * 0x9E3779B9u);
        if (s_have_join_devnonce) {
            mix ^= (uint32_t)s_last_join_devnonce * 0x045D9F3Bu;
        }
        mix ^= mix >> 16;
        mix ^= mix >> 8;
        s_b2b.next_msg_id = (uint8_t)mix;
    }
    s_b2b_origin_id_ready = true;
}

static bool b2b_make_authenticated(b2b_type_t type, const uint8_t* body,
                                   uint8_t body_len, b2b_frame_t* out) {
    if (!s_b2b_auth_ready || !out ||
        (body_len && !body) ||
        body_len > B2B_PAYLOAD_MAX - B2B_AUTH_TAG_LEN) return false;
    uint8_t payload[B2B_PAYLOAD_MAX] = {};
    if (body_len && body) memcpy(payload, body, body_len);
    b2b_prepare_origin_id();
    if (!b2b_make(&s_b2b, type, payload,
                  (uint8_t)(body_len + B2B_AUTH_TAG_LEN), out)) return false;
    uint8_t tag[B2B_AUTH_TAG_LEN];
    if (!b2b_auth_tag(s_b2b_fleet_key, out, tag)) return false;
    memcpy(out->payload + body_len, tag, sizeof(tag));
    /* Commit the successor before the caller can queue or transmit this
     * frame. A reset may burn an ID, which is safe; it must never reuse one. */
    return power_manager_save_b2b_msg_id(s_b2b.next_msg_id);
}

static void b2b_init_once(void) {
    if (s_b2b_initialized) return;
    b2b_reset(&s_b2b, CMD_BALLOON_ID);
    s_b2b_auth_ready = exactHex(B2B_FLEET_KEY, 32);
    if (s_b2b_auth_ready) hexToBytes(B2B_FLEET_KEY, s_b2b_fleet_key, 16);
    s_b2b_initialized = true;
}

static uint32_t b2b_now_rtc_sec(void) {
    /* millis() freezes in STOP1. Preserve the raw 32-bit RTC-second domain so
     * b2b.cpp can apply the opposite datasheet LSI bounds required by sample
     * freshness versus minimum replay retention/origin spacing. */
    return power_manager_monotonic_seconds();
}

void lorawan_b2b_set_local_crumb(int32_t lat_e7, int32_t lon_e7, int32_t altitude_m) {
    b2b_init_once();
    int32_t lat_cd = lat_e7 / 100000;
    int32_t lon_cd = lon_e7 / 100000;
    if (lat_cd < -9000) lat_cd = -9000;
    if (lat_cd >  9000) lat_cd =  9000;
    if (lon_cd < -18000) lon_cd = -18000;
    if (lon_cd >  18000) lon_cd =  18000;
    int32_t alt_hm = altitude_m / 100;
    if (alt_hm < 0) alt_hm = 0;
    if (alt_hm > 255) alt_hm = 255;
    s_b2b_latest_crumb.lat_cd = (int16_t)lat_cd;
    s_b2b_latest_crumb.lon_cd = (int16_t)lon_cd;
    s_b2b_latest_crumb.alt_hm = (uint8_t)alt_hm;
    s_b2b_latest_crumb.age_min = 0;
    s_b2b_latest_crumb_rtc_sec = b2b_now_rtc_sec();

    uint32_t now_rtc_sec = b2b_now_rtc_sec();
    if (b2b_interval_due(s_b2b_ever_sent_crumb, now_rtc_sec,
                         s_b2b_last_crumb_rtc_sec,
                         B2B_CRUMB_INTERVAL_MIN)) {
        /* If an earlier due crumb has not transmitted yet, replace it with the
         * newest fix—the freshest position is always more useful. */
        s_b2b_crumb_pending = true;
        s_b2b_crumb_frame_ready = false;
    }
}

static bool b2b_origin_push(const b2b_frame_t* frame) {
    if (s_b2b_origin_n >= B2B_ORIGIN_N) return false;
    s_b2b_origin[s_b2b_origin_tail] = *frame;
    s_b2b_origin_tail = (uint8_t)((s_b2b_origin_tail + 1) % B2B_ORIGIN_N);
    s_b2b_origin_n++;
    return true;
}

/* ACKs close the store-and-forward control loop, so insert them at the head
 * instead of behind operator commands already waiting for the next solar
 * window. Ring invariants still hold: on the empty queue, decrementing head
 * leaves tail as the next free slot. */
static bool b2b_origin_push_priority(const b2b_frame_t* frame) {
    if (s_b2b_origin_n >= B2B_ORIGIN_N) return false;
    s_b2b_origin_head =
        (uint8_t)((s_b2b_origin_head + B2B_ORIGIN_N - 1) % B2B_ORIGIN_N);
    s_b2b_origin[s_b2b_origin_head] = *frame;
    s_b2b_origin_n++;
    return true;
}

bool lorawan_b2b_queue_command(const lorawan_downlink_t* command) {
    b2b_init_once();
    if (!command_validate_wire(command)) return false;
    uint16_t target =
        (uint16_t)(((uint16_t)command->data[0] << 8) | command->data[1]);
    if (target == CMD_BALLOON_ID) return false; /* local command, no mesh hop */
    /* Capacity is part of the transaction. b2b_make() allocates a message ID
     * only after validating the frame; do not allocate one when the origin
     * queue cannot accept the result. */
    /* Reserve one slot for a command ACK generated while these commands wait.
     * Without this, a full operator queue can suppress the only proof that a
     * remote command reached its target. */
    if (s_b2b_origin_n >= B2B_ORIGIN_N - 1) return false;
    b2b_frame_t frame;
    if (!b2b_make_authenticated(B2B_TYPE_COMMAND, command->data, command->len,
                                &frame)) return false;
    return b2b_origin_push(&frame);
}

static void b2b_queue_ttn(const b2b_frame_t* frame) {
    if (s_b2b_uplink_n >= B2B_UPLINK_N) {
        s_b2b.stats.ttn_drop++;
        return;
    }
    s_b2b_uplink[s_b2b_uplink_tail] = *frame;
    s_b2b_uplink[s_b2b_uplink_tail].queued_rtc_sec = b2b_now_rtc_sec();
    s_b2b_uplink_tail = (uint8_t)((s_b2b_uplink_tail + 1) % B2B_UPLINK_N);
    s_b2b_uplink_n++;
}

bool lorawan_b2b_peek_pending_uplink(
    uint8_t* out, uint8_t capacity, uint8_t* len) {
    if (!out || !len || capacity < B2B_FRAME_MAX) return false;
    while (s_b2b_uplink_n) {
        b2b_frame_t* frame = &s_b2b_uplink[s_b2b_uplink_head];
        if (b2b_refresh_authenticated_age(
                s_b2b_fleet_key, frame, b2b_now_rtc_sec())) {
            int encoded = b2b_encode(frame, out, capacity);
            if (encoded > 0) {
                *len = (uint8_t)encoded;
                return true;
            }
        }
        /* A queue entry that can no longer authenticate or encode is not
         * retryable; dropping it fails closed and prevents permanent head-of-
         * line blockage of later evidence. */
        s_b2b.stats.ttn_drop++;
        s_b2b_uplink_head =
            (uint8_t)((s_b2b_uplink_head + 1) % B2B_UPLINK_N);
        s_b2b_uplink_n--;
    }
    return false;
}
void lorawan_b2b_ack_pending_uplink(void) {
    if (s_b2b_uplink_n == 0) return;
    s_b2b_uplink_head = (uint8_t)((s_b2b_uplink_head + 1) % B2B_UPLINK_N);
    s_b2b_uplink_n--;
}
uint8_t lorawan_b2b_pending_uplink_count(void) { return s_b2b_uplink_n; }

void lorawan_relay_get_stats(lorawan_relay_stats_t* out) { if (out) *out = s_relay; }

/* Restore the exact post-init LoRaWAN TX PHY that send_uplink()/join depend on.
 * Frequency is restored too (TTN paths set it per-TX, but this honors the
 * "post-init state" contract and removes the off-channel trap of leaving the
 * radio tuned to the Meshtastic frequency). */
static bool relay_restore_lorawan_phy(void) {
    return radio_apply_lorawan_tx(REGION.init_freq);
}

static void restore_lorawan_or_reset(void) {
    if (relay_restore_lorawan_phy()) return;
    s_radio_diag.restore_attempts++;
    /* A partial restore can transmit successfully but be undecodable. Force a
     * full three-attempt begin() now; if the modem still cannot be placed in a
     * known LoRaWAN state, reset rather than enter STOP with silent corruption. */
    radio_ready = false;
    if (!lorawan_init()) NVIC_SystemReset();
    s_radio_diag.restore_recovered++;
}

static uint32_t relay_toa_ms(size_t len) {
    uint32_t us = (uint32_t)radio->getTimeOnAir(len);
    return (us + 999u) / 1000u;
}

static bool relay_airtime_allows(uint32_t used_ms, uint32_t start_ms,
                                 uint32_t next_ms) {
    uint32_t elapsed = millis() - start_ms;
    /* Preserve one bootstrapping forward: at the instant a frame arrives the
     * elapsed denominator can be tiny. Thereafter charge projected airtime,
     * not merely the already-spent total, so a single large packet cannot
     * jump past the cap unnoticed. */
    if (used_ms == 0) return true;
    return (used_ms + next_ms) * 100u <=
           (uint32_t)RELAY_AIRTIME_CAP_PCT * elapsed;
}

static bool relay_send_b2b_frame(
    const b2b_frame_t* frame, uint32_t start_ms, uint32_t max_ms,
    uint32_t* used_ms) {
    uint8_t wire[B2B_FRAME_MAX];
    int len = b2b_encode(frame, wire, sizeof(wire));
    if (len <= 0) return false;
    uint32_t toa = relay_toa_ms((size_t)len);
    if (!relay_airtime_allows(*used_ms, start_ms, toa)) return false;
    /* CAD plus a short guard prevents a final B2B hand-off from extending
     * beyond the mission-owned relay window and delaying the next TTN cycle. */
    if ((millis() - start_ms) + toa + 100u >= max_ms) {
        s_b2b.stats.window_block++;
        return false;
    }
    int16_t cad = radio->scanChannel();
    if (cad == RADIOLIB_LORA_DETECTED ||
        cad == RADIOLIB_PREAMBLE_DETECTED) {
        s_b2b.stats.cad_busy++;
        return false;
    }
    if (cad != RADIOLIB_CHANNEL_FREE) {
        s_b2b.stats.cad_error++;
        s_radio_diag.last_error = cad;
        return false;
    }
    int16_t state = radio->transmit(wire, (size_t)len);
    if (state == RADIOLIB_ERR_NONE) {
        *used_ms += toa;
    } else {
        s_b2b.stats.tx_error++;
        s_radio_diag.last_error = state;
    }
    return state == RADIOLIB_ERR_NONE;
}

uint32_t lorawan_relay_window(
    uint32_t max_ms, uint16_t floor_mv, bool meshtastic_enabled) {
    if (!radio_ready) return 0;
    float freq = meshtastic_longfast_freq(REGION_ID);
    if (freq <= 0.0f) return 0;                    /* region not relay-eligible */

    uint32_t start = millis();

    /* Switch the shared radio to Meshtastic LongFast (SF11/BW250/CR4-5,
     * sync 0x2B, 16-symbol preamble, explicit header + CRC, non-inverted IQ). */
    if (!radio_apply_lora_phy(freq, 11, 250.0, 0x2B, 16, true, false)) {
        restore_lorawan_or_reset();
        return millis() - start;
    }

    b2b_init_once();
    /* A queued forward is useful only inside the current solar-surplus
     * listening window. Never carry a several-minute-old public frame into a
     * later window. */
    mesh_relay_mac_init(&s_relay_mac);
    /* Store-and-forward receives a bounded share of this same combined TX
     * budget. b2b_next_forward applies its own capped bank, while every actual
     * radio hand-off also passes the relay-wide 5% cap below. */
    b2b_add_airtime(&s_b2b,
        ((uint32_t)RELAY_AIRTIME_CAP_PCT * max_ms) / 100u);

    s_relay_rx = false;
    radio->setPacketReceivedAction(relay_rx_isr);
    if (!relay_arm_receive()) {
        radio->clearPacketReceivedAction();
        restore_lorawan_or_reset();
        return millis() - start;
    }

    uint32_t tx_airtime_ms = 0;
    uint32_t last_hk = start;
    uint32_t b2b_attempt_seq = 0;
    uint32_t next_b2b_try = start + mesh_relay_mac_delay_ms(
        0, micros(), CMD_BALLOON_ID, b2b_attempt_seq++);
    while (millis() - start < max_ms) {
        if (s_relay_rx) {
            s_relay_rx = false;
            size_t len = radio->getPacketLength();
            if (len >= B2B_HDR_LEN && len <= sizeof(s_relay_buf) &&
                radio->readData(s_relay_buf, len) == RADIOLIB_ERR_NONE) {
                int16_t heard_rssi = (int16_t)radio->getRSSI();
                /* Reserve the complete "SB" namespace before inspecting the
                 * version. Requiring version==current in the classifier made
                 * an unknown/future B2B version fall through and get mutated
                 * and forwarded as an ordinary Meshtastic header. The strict
                 * parser below owns version rejection. */
                bool b2b_prefix =
                    b2b_is_namespaced(s_relay_buf, (int)len);
                if (b2b_prefix) {
                    b2b_frame_t frame;
                    if (!b2b_parse(s_relay_buf, (int)len, &frame)) {
                        s_b2b.stats.malformed++;
                    } else if (!s_b2b_auth_ready ||
                               !b2b_auth_verify(s_b2b_fleet_key, &frame)) {
                        /* Public LongFast is untrusted. Never route, tunnel,
                         * apply, or ACK a forged control-plane frame. */
                        s_b2b.stats.auth_fail++;
                    } else {
                        b2b_result_t result = b2b_ingest(
                            &s_b2b, &frame, b2b_now_rtc_sec());
                        bool fresh = result == B2B_FORWARD ||
                                     result == B2B_LOCAL ||
                                     result == B2B_LOCAL_FORWARD ||
                                     result == B2B_LOCAL_BLOCKED ||
                                     result == B2B_EXPIRED;
                        if (fresh) b2b_queue_ttn(&frame);

                        bool local = result == B2B_LOCAL ||
                                     result == B2B_LOCAL_FORWARD ||
                                     result == B2B_LOCAL_BLOCKED;
                        if (local && frame.type == B2B_TYPE_COMMAND) {
                            lorawan_downlink_t command = {};
                            command.fport = CMD_FPORT;
                            /* The B2B carrier appends its CMAC tag to the
                             * command body. Authentication has already
                             * succeeded above; strip that transport trailer
                             * before handing the original
                             * [target,opcode,seq,args] wire command to the
                             * exact-length command parser. Passing frame.len
                             * here made every authenticated command verify
                             * and then fail closed as "too long". */
                            command.len =
                                b2b_authenticated_body_len(&frame);
                            memcpy(command.data, frame.payload, command.len);
                            bool applied = command_handle(&command);
                            /* If an ACK was lost, an exact authenticated retry
                             * can arrive after B2B dedup ages or RAM resets.
                             * Re-ACK the durably current sequence without
                             * applying its effect twice. */
                            bool acknowledge = applied ||
                                (command_validate_wire(&command) &&
                                 command_sequence_is_current(
                                     frame.payload[3]));
                            if (acknowledge) {
                                uint8_t ack_payload[3] = {
                                    (uint8_t)(frame.src >> 8),
                                    (uint8_t)frame.src,
                                    frame.payload[3],
                                };
                                b2b_frame_t ack;
                                if (s_b2b_origin_n >= B2B_ORIGIN_N ||
                                    !b2b_make_authenticated(
                                        B2B_TYPE_ACK, ack_payload,
                                        sizeof(ack_payload), &ack) ||
                                    !b2b_origin_push_priority(&ack)) {
                                    s_b2b.stats.ack_drop++;
                                }
                            }
                        }
                        (void)heard_rssi; /* retained for debugger inspection at RX */
                    }
                } else if (meshtastic_enabled && len >= 16) {
                    /*
                     * Ordinary Meshtastic packet. Queue it into a native-like
                     * ROUTER_LATE contention window; never transmit directly
                     * from RxDone. The pure MAC changes only hop_limit,
                     * next_hop and relay_node, leaving ciphertext opaque.
                     */
                    s_relay.rx_count++;
                    s_relay.last_rssi = heard_rssi;
                    uint32_t from  = relay_rd_u32le(s_relay_buf + 4);
                    uint32_t id    = relay_rd_u32le(s_relay_buf + 8);
                    s_relay.last_from = from;
                    if (relay_dd_seen(from, id)) {
                        s_relay.dedup++;
                    } else if (mesh_relay_mac_cancel(
                                   &s_relay_mac, from, id)) {
                        /* Another node won the managed-flood contention while
                         * our ROUTER_LATE copy was pending. Cancel our copy and
                         * commit the key: the network already carried it, so a
                         * later repeat must not re-open the same forward. */
                        relay_dd_mark(from, id);
                        s_relay.dedup++;
                        s_relay.pending_dup++;
                    } else {
                        int16_t heard_snr = (int16_t)radio->getSNR();
                        mesh_relay_queue_result_t queued =
                            mesh_relay_mac_enqueue(
                                &s_relay_mac, s_relay_buf, len, heard_snr,
                                millis(), micros());
                        switch (queued) {
                            case MESH_RELAY_QUEUE_OK:
                                s_relay.queued++;
                                break;
                            case MESH_RELAY_DROP_HOP_ZERO:
                                s_relay.hop0++;
                                break;
                            case MESH_RELAY_DROP_DIRECTED_NEXT_HOP:
                                s_relay.next_hop_skip++;
                                break;
                            case MESH_RELAY_DROP_PENDING_DUPLICATE:
                                /* Defensive only: the explicit cancel above
                                 * owns the single-threaded receive path. */
                                s_relay.dedup++;
                                s_relay.pending_dup++;
                                break;
                            case MESH_RELAY_DROP_QUEUE_FULL:
                                s_relay.queue_full++;
                                break;
                            default:
                                s_relay.invalid++;
                                break;
                        }
                    }
                }
            }
            if (!relay_arm_receive()) break;
        }

        /*
         * A due public relay first performs LoRa CAD. RadioLib's blocking
         * scanChannel() implements the SX1262 two-symbol detector and leaves
         * the modem out of continuous RX, so every outcome explicitly rearms
         * receive. Failed/busy scans repeat the randomized late contention
         * delay; successful TX alone commits the long-lived dedup record.
         */
        uint32_t now = millis();
        bool mesh_serviced = false;
        int8_t due_slot = mesh_relay_mac_due(&s_relay_mac, now);
        if (due_slot >= 0) {
            mesh_serviced = true;
            mesh_relay_pending_t* pending =
                &s_relay_mac.pending[(uint8_t)due_slot];
            uint32_t toa = relay_toa_ms(pending->len);
            uint32_t elapsed = now - start;
            if (elapsed + toa + 100u >= max_ms) {
                s_relay.window_skip++;
                mesh_relay_mac_remove(&s_relay_mac, (uint8_t)due_slot);
            } else if (!relay_airtime_allows(
                           tx_airtime_ms, start, toa)) {
                s_relay.cap_skip++;
                mesh_relay_mac_remove(&s_relay_mac, (uint8_t)due_slot);
            } else {
                int16_t cad = radio->scanChannel();
                if (cad == RADIOLIB_CHANNEL_FREE) {
                    if (radio->transmit(pending->frame, pending->len) ==
                        RADIOLIB_ERR_NONE) {
                        relay_dd_mark(pending->from, pending->id);
                        s_relay.fwd++;
                        tx_airtime_ms += toa;
                        mesh_relay_mac_remove(
                            &s_relay_mac, (uint8_t)due_slot);
                    } else {
                        s_relay.tx_error++;
                        mesh_relay_mac_reschedule(
                            &s_relay_mac, (uint8_t)due_slot, millis(),
                            micros());
                    }
                } else if (cad == RADIOLIB_LORA_DETECTED ||
                           cad == RADIOLIB_PREAMBLE_DETECTED) {
                    s_relay.cad_busy++;
                    mesh_relay_mac_reschedule(
                        &s_relay_mac, (uint8_t)due_slot, millis(), micros());
                } else {
                    s_relay.cad_error++;
                    s_radio_diag.last_error = cad;
                    mesh_relay_mac_reschedule(
                        &s_relay_mac, (uint8_t)due_slot, millis(), micros());
                }
            }
            if (!relay_arm_receive()) break;
        }

        /* One randomized, CAD-guarded B2B hand-off per contention deadline.
         * ACKs have priority, then our
         * newest hourly crumb, then store-and-forward traffic. Failed TX keeps
         * the exact frame queued for a later retry. */
        now = millis();
        if (!mesh_serviced &&
            (int32_t)(now - next_b2b_try) >= 0) {
            next_b2b_try = now + mesh_relay_mac_delay_ms(
                0, micros(), CMD_BALLOON_ID, b2b_attempt_seq++);
            bool attempted = false;
            if (s_b2b_origin_n) {
                b2b_frame_t* frame = &s_b2b_origin[s_b2b_origin_head];
                attempted = true;
                if (relay_send_b2b_frame(
                        frame, start, max_ms, &tx_airtime_ms)) {
                    s_b2b_origin_head =
                        (uint8_t)((s_b2b_origin_head + 1) % B2B_ORIGIN_N);
                    s_b2b_origin_n--;
                }
            } else if (s_b2b_crumb_pending) {
                if (!s_b2b_crumb_frame_ready) {
                    uint32_t prepared_rtc_sec = b2b_now_rtc_sec();
                    uint32_t age = b2b_age_upper_minutes(
                        prepared_rtc_sec - s_b2b_latest_crumb_rtc_sec);
                    s_b2b_latest_crumb.age_min =
                        age > 255u ? 255u : (uint8_t)age;
                    uint8_t crumb[B2B_CRUMB_LEN];
                    b2b_crumb_pack(&s_b2b_latest_crumb, crumb);
                    b2b_prepare_origin_id();
                    if (b2b_make_authenticated(
                            B2B_TYPE_CRUMB, crumb, sizeof(crumb),
                            &s_b2b_crumb_frame)) {
                        s_b2b_crumb_frame.queued_rtc_sec = prepared_rtc_sec;
                        s_b2b_crumb_frame_ready = true;
                    }
                }
                if (s_b2b_crumb_frame_ready) {
                    attempted = true;
                    if (!b2b_refresh_authenticated_age(
                            s_b2b_fleet_key, &s_b2b_crumb_frame,
                            b2b_now_rtc_sec())) {
                        /* Deterministic RAM/auth corruption is not retryable
                         * as the same frame. Burned IDs are safe; rebuild the
                         * newest crumb under a fresh ID on the next attempt. */
                        s_b2b.stats.auth_fail++;
                        s_b2b_crumb_frame_ready = false;
                    } else if (relay_send_b2b_frame(
                                   &s_b2b_crumb_frame, start, max_ms,
                                   &tx_airtime_ms)) {
                    s_b2b_crumb_pending = false;
                    s_b2b_crumb_frame_ready = false;
                    s_b2b_ever_sent_crumb = true;
                    s_b2b_last_crumb_rtc_sec = b2b_now_rtc_sec();
                    }
                }
            } else {
                const b2b_frame_t* head = b2b_peek_forward(&s_b2b);
                if (head) {
                    uint8_t wire[B2B_FRAME_MAX];
                    int wire_len = b2b_encode(head, wire, sizeof(wire));
                    uint32_t toa = wire_len > 0
                        ? relay_toa_ms((size_t)wire_len) : 0;
                    if (toa && relay_airtime_allows(tx_airtime_ms, start, toa)) {
                        b2b_frame_t frame;
                        if (b2b_next_forward_fresh(
                                &s_b2b, &frame, toa, s_b2b_fleet_key,
                                b2b_now_rtc_sec())) {
                            attempted = true;
                            if (!relay_send_b2b_frame(
                                    &frame, start, max_ms, &tx_airtime_ms)) {
                                b2b_refund(&s_b2b, &frame, toa);
                            }
                        }
                    }
                }
            }
            /*
             * scanChannel() leaves continuous RX even when CAD is busy or
             * errors. Rearm after every attempt, not only successful TX.
             */
            if (attempted) {
                if (!relay_arm_receive()) break;
            }
        }

        now = millis();
        if (now - last_hk >= 1000) {                        /* housekeeping ~1 Hz */
            last_hk = now;
            power_manager_kick_watchdog();
            if (power_adc_read_vSTOR_mv() < floor_mv) break; /* floor-abort: protect mission reserve */
            if (power_manager_freefall_pending()) break;    /* freefall: yield to burst NOW, not at window end */
            if (power_adc_read_solar_mv() < RELAY_SOLAR_MIN_MV) break; /* sunset/cloud mid-window: the
                * relay only runs on solar surplus, and a 20 min window can outlive
                * the daylight that justified opening it */
        }
        /* Continuous RX remains armed while the CPU sleeps shallowly. Radio
         * DIO, SysTick, or freefall INT1 wakes this service loop. */
        radio_idle_until_interrupt();
    }

    for (uint8_t i = 0; i < MESH_RELAY_PENDING_N; ++i) {
        if (s_relay_mac.pending[i].used) s_relay.window_skip++;
    }
    mesh_relay_mac_init(&s_relay_mac);
    radio->clearPacketReceivedAction();
    restore_lorawan_or_reset();
    return millis() - start;
}

/* ===== CTT wildlife-tag listener (RX-only 434 MHz FSK window) =====
 *
 * Listens for CTT LifeTag/PowerTag/HybridTag beacons (the Motus network's
 * 434 MHz tags on birds/bats) in the solar-surplus idle window and logs
 * decoded tag ids.  RX-only: transmits nothing, registers nowhere.  PHY per
 * the rtl_433 decoder + CTT's own RadioLib test-tag firmware: 2-FSK 25 kbps,
 * +-25 kHz deviation, no shaping, sync D3 91, fixed 5-byte payload (4 id
 * bytes from a 32-symbol dictionary + CRC-8), one ~3 ms beep every 2-15 s.
 *
 * This exact board fits RAK3172-9-SM-NI, RAK's 9xx-MHz SKU for
 * US915/AU915/KR920/AS923; RAK assigns EU868 and 434 MHz to different ordering
 * codes. Successful beginFSK()
 * therefore proves only SX1262 configuration, not usable sensitivity through
 * the fitted matching network and antenna. A real compatible-tag HIL is a hard
 * qualification gate before this listener can be called operational.
 *
 * Same subordination contract as the relay window: the caller gates entry,
 * the 1 Hz housekeeping aborts on VSTOR floor, solar loss, or a pending
 * freefall, and the exact LoRaWAN PHY is restored on every exit.  Note the
 * digital decoder is vector-proven, but absolute 434 MHz sensitivity and
 * end-to-end reception remain unmeasured until a compatible physical
 * transmitter is available. */

static volatile bool s_ctt_rx = false;
static void ctt_rx_isr(void) { s_ctt_rx = true; }
static lorawan_ctt_stats_t s_ctt = {};
static ctt_queue_t s_ctt_queue = {};

void lorawan_ctt_get_stats(lorawan_ctt_stats_t* out) { if (out) *out = s_ctt; }
uint8_t lorawan_ctt_get_log(ctt_detection_t* out) {
    return ctt_queue_get_log(&s_ctt_queue, out);
}
bool lorawan_ctt_peek_pending(ctt_detection_t* out) {
    return ctt_queue_peek(&s_ctt_queue, out);
}
void lorawan_ctt_ack_pending(void) {
    ctt_queue_ack(&s_ctt_queue);
}
uint8_t lorawan_ctt_pending_count(void) {
    return ctt_queue_count(&s_ctt_queue);
}

/* Log a decoded frame, aggregating repeat beeps of the same tag within one
 * window (a LifeTag beeps every ~5 s; a pass would otherwise flood the ring). */
static void ctt_log_frame(uint32_t id_raw, uint32_t id_motus, uint8_t motus_valid,
                          int16_t rssi, uint16_t window_idx) {
    ctt_detection_t detection = {};
    detection.id_raw = id_raw;
    detection.id_motus = id_motus;
    detection.rssi_best = rssi;
    detection.hits = 1;
    detection.motus_valid = motus_valid;
    detection.window_idx = window_idx;
    detection.queued_min = power_manager_monotonic_seconds() / 60u;
    ctt_queue_result_t result = ctt_queue_record(&s_ctt_queue, &detection);
    if (result != CTT_QUEUE_REPEAT) s_ctt.tags_seen++;
    if (result == CTT_QUEUE_NEW_DROPPED) s_ctt.pending_drop++;
}

/* Return the shared radio from FSK to the exact post-init LoRaWAN state.
 * beginFSK() switched the SX126x packet type, so a full LoRa begin() is
 * required before the parameter-level restore. */
static void ctt_restore_lorawan(void) {
    /* A failed restore leaves the radio in FSK mode and silences the mission
     * with nothing able to detect it (tx_fail_streak counts LoRaWAN send
     * failures, which never happen if the modem is simply wrong).  Retry once,
     * then reset so lorawan_init() rebuilds the radio from scratch. */
    int16_t rst = radio->begin(REGION.init_freq, REGION.tx_bw, 9, 7,
                               RADIOLIB_SX126X_SYNC_WORD_PUBLIC, 14, 8, 1.7f, false);
    if (rst != RADIOLIB_ERR_NONE) {
        s_radio_diag.begin_failures++;
        s_radio_diag.last_error = rst;
        rst = radio->begin(REGION.init_freq, REGION.tx_bw, 9, 7,
                           RADIOLIB_SX126X_SYNC_WORD_PUBLIC, 14, 8, 1.7f, false);
        if (rst != RADIOLIB_ERR_NONE) {
            s_radio_diag.begin_failures++;
            s_radio_diag.last_error = rst;
            NVIC_SystemReset();
        }
    }
    radio_ready = true;
    restore_lorawan_or_reset();
}

uint32_t lorawan_ctt_window(uint32_t max_ms, uint16_t floor_mv) {
    if (!radio_ready) return 0;
    uint32_t start = millis();

    radio->standby();
    /* rxBw must be one of the SX126x DSB values; 50.0 is not one of them, so
     * beginFSK rejected it and every CTT window aborted before the radio was
     * ever tuned to 434 MHz.  Carson bandwidth for 25 kbps at +-25 kHz dev is
     * ~75 kHz, so 93.8 kHz is the smallest legal setting with margin for the
     * tag's crystal tolerance. */
    int16_t st = radio->beginFSK(
        (float)CTT_FREQ_MHZ, 25.0f, 25.0f, 93.8f, 0, 16);
    if (st == RADIOLIB_ERR_NONE) st = radio->setDataShaping(RADIOLIB_SHAPING_NONE);
    uint8_t ctt_sync[2] = {0xD3, 0x91};
    if (st == RADIOLIB_ERR_NONE) st = radio->setSyncWord(ctt_sync, 2);
    if (st == RADIOLIB_ERR_NONE) st = radio->fixedPacketLengthMode(5);
    if (st == RADIOLIB_ERR_NONE) st = radio->setCRC(0);  /* tag CRC-8 checked in software */
    if (st != RADIOLIB_ERR_NONE) {
        ctt_restore_lorawan();
        return millis() - start;
    }

    s_ctt.windows++;
    uint16_t widx = (uint16_t)s_ctt.windows;
    s_ctt_rx = false;
    radio->setPacketReceivedAction(ctt_rx_isr);
    int16_t rx_state = radio->startReceive();
    if (rx_state != RADIOLIB_ERR_NONE) {
        s_ctt.rx_arm_fail++;
        s_radio_diag.last_error = rx_state;
        radio->clearPacketReceivedAction();
        ctt_restore_lorawan();
        return millis() - start;
    }

    uint32_t last_hk = start;
    while (millis() - start < max_ms) {
        if (s_ctt_rx) {
            s_ctt_rx = false;
            uint8_t buf[5];
            if (radio->readData(buf, 5) == RADIOLIB_ERR_NONE) {
                s_ctt.frames_rx++;
                ctt_frame_t f;
                if (ctt_decode(buf, &f)) {
                    int16_t rssi = (int16_t)radio->getRSSI();
                    s_ctt.last_id   = f.id_raw;
                    s_ctt.last_rssi = rssi;
                    ctt_log_frame(f.id_raw, f.id_motus, f.motus_valid ? 1 : 0, rssi, widx);
                } else {
                    s_ctt.crc_fail++;
                }
            }
            s_ctt_rx = false;
            rx_state = radio->startReceive();
            if (rx_state != RADIOLIB_ERR_NONE) {
                s_ctt.rx_arm_fail++;
                s_radio_diag.last_error = rx_state;
                break;  /* re-arm failed: bail, don't busy-loop deaf */
            }
        }
        uint32_t now = millis();
        if (now - last_hk >= 1000) {                    /* housekeeping ~1 Hz */
            last_hk = now;
            power_manager_kick_watchdog();
            if (power_adc_read_vSTOR_mv() < floor_mv) break;
            if (power_manager_freefall_pending()) break;
            if (power_adc_read_solar_mv() < RELAY_SOLAR_MIN_MV) break;
        }
        /* Diagnostic-only CTT listening must not busy-spin for its complete
         * window even though the StratoLink-2 flight image disables CTT. */
        radio_idle_until_interrupt();
    }

    radio->clearPacketReceivedAction();
    ctt_restore_lorawan();
    return millis() - start;
}

/* ========== Class-A downlink (command channel) ========== */

/* One bounded RX window: arm RX, poll for RxDone until deadline_ms, read it. Bounded
 * so a slow-DR RX1 cannot block past the RX2 window. Caller sets the PHY first. */
static volatile bool s_dl_rx = false;
static lorawan_downlink_stats_t s_dl_stats = {};
static void dl_rx_isr(void) {
    s_dl_rx = true;
    s_dl_stats.irq_count++;
}
void lorawan_downlink_get_stats(lorawan_downlink_stats_t* out) {
    if (out) *out = s_dl_stats;
}

static size_t rx_window(uint8_t* buf, size_t maxlen, uint32_t deadline_ms,
                        int16_t* start_state, bool* mission_aborted) {
    if (mission_aborted) *mission_aborted = false;
    s_dl_rx = false;
    radio->setPacketReceivedAction(dl_rx_isr);
    int16_t state = radio->startReceive();
    if (start_state) *start_state = state;
    if (state != RADIOLIB_ERR_NONE) {
        radio->clearPacketReceivedAction(); radio->standby(); return 0;
    }
    uint32_t last_kick = millis();
    while ((int32_t)(millis() - deadline_ms) < 0) {
        if (s_dl_rx) break;
        if (power_manager_freefall_pending()) {
            if (mission_aborted) *mission_aborted = true;
            break;
        }
        uint32_t now = millis();
        if (now - last_kick >= 1000u) {
            power_manager_kick_watchdog();
            last_kick = now;
        }
        radio_idle_until_interrupt();
    }
    radio->clearPacketReceivedAction();
    size_t n = 0;
    if (s_dl_rx) {
        n = radio->getPacketLength();
        /* Authenticate exactly the radio frame that arrived. Truncating an
         * oversized frame to the caller buffer would make the decoder verify
         * only a prefix and silently ignore trailing on-air bytes. Join RX
         * already fails closed at this boundary; keep data-down identical. */
        if (n > maxlen || radio->readData(buf, n) != RADIOLIB_ERR_NONE) {
            n = 0;
        }
        if (n) s_dl_stats.frame_count++;
    }
    radio->standby();
    return n;
}

bool lorawan_receive_downlink(lorawan_downlink_t* out) {
    if (!radio_ready || !_joined || !out) return false;
    memset(out, 0, sizeof(*out));
    s_dl_stats.calls++;
    s_dl_stats.last_window = 0;
    s_dl_stats.last_len = 0;
    s_dl_stats.last_mhdr = 0;
    s_dl_stats.last_reject = 0;
    float rx1f = REGION.rx1_mod
        ? (REGION.rx1_base + (s_tx_ch % REGION.rx1_mod) * REGION.rx1_step)
        : REGION.tx_freqs[s_tx_ch % REGION.tx_ch_count];

    uint8_t rx[64]; size_t rxLen = 0;
    bool saw_frame = false;
    bool authenticated = false;
    bool mission_aborted = false;
    lorawan_decoded_downlink_t decoded = {};

    /* Windows are driven by the NETWORK-assigned RxDelay, not the spec default.
     * RX1 opens at rx_delay, RX2 one second later (LoRaWAN defines
     * RECEIVE_DELAY2 = RECEIVE_DELAY1 + 1 s). RadioLib's blocking transmit()
     * returns after TX-done cleanup, so s_tx_end_ms can lag the actual RF end
     * by tens of milliseconds. The previous 40 ms pre-open was marginal:
     * TTN reported successful +5 s transmissions but the board saw no DIO IRQ.
     * Start 250 ms early; the extra RX energy is ~5 mJ/cycle and the RX1
     * deadline still leaves 250 ms of quiet reconfiguration before RX2. */
    const uint32_t rx1_at = (uint32_t)s_rx_delay_s * 1000u;
    const uint32_t rx2_at = rx1_at + 1000u;
    const uint32_t preopen_ms = 250u;

    if (!radio_wait_until(s_tx_end_ms, rx1_at - preopen_ms)) {
        return false;
    }
    if (!radio_apply_lora_phy(
            rx1f, REGION.tx_sf, REGION.rx1_bw,
            RADIOLIB_SX126X_SYNC_WORD_PUBLIC, 8, false, true)) {
        s_dl_stats.last_reject = 8;
        restore_lorawan_or_reset();
        return false;
    }
    s_dl_stats.last_rx1_start_offset_ms =
        (int32_t)(millis() - s_tx_end_ms);
    s_dl_stats.rx1_armed++;
    const uint32_t rx1_deadline = s_tx_end_ms + rx1_at + 500u;
    do {
        rxLen = rx_window(rx, sizeof(rx), rx1_deadline,
                          &s_dl_stats.last_rx1_start_state,
                          &mission_aborted);
        if (mission_aborted) {
            restore_lorawan_or_reset();
            return false;
        }
        if (!rxLen) {
            if (s_dl_rx) continue;    /* malformed/read-failed IRQ */
            break;
        }
        saw_frame = true;
        s_dl_stats.last_window = 1;
        s_dl_stats.last_len = (uint8_t)rxLen;
        s_dl_stats.last_mhdr = rx[0];
        authenticated = lorawan_frame_decode_downlink(
            nwkSKey, appSKey, devAddr, fCntDown, rx, rxLen,
            &decoded, &s_dl_stats.last_reject);
        /* Keep listening until the logical RX1 deadline after an unauthenticated
         * frame. An early nuisance packet must not preempt the scheduled frame
         * later in the same window. */
    } while (!authenticated && (int32_t)(millis() - rx1_deadline) < 0);

    /* A merely present RX1 frame is not ours. Wrong-address, malformed,
     * replayed, or bad-MIC traffic must leave RX2 available for the network's
     * authenticated fallback. */
    if (!authenticated) {
        if (!radio_wait_until(s_tx_end_ms, rx2_at - preopen_ms)) {
            restore_lorawan_or_reset();
            return false;
        }
        if (!radio_apply_lora_phy(
                REGION.rx2_freq, REGION.rx2_sf, REGION.rx2_bw,
                RADIOLIB_SX126X_SYNC_WORD_PUBLIC, 8, false, true)) {
            s_dl_stats.last_reject = 8;
            restore_lorawan_or_reset();
            return false;
        }
        s_dl_stats.last_rx2_start_offset_ms =
            (int32_t)(millis() - s_tx_end_ms);
        s_dl_stats.rx2_armed++;
        const uint32_t rx2_deadline = s_tx_end_ms + rx2_at + 740u;
        do {
            rxLen = rx_window(rx, sizeof(rx), rx2_deadline,
                              &s_dl_stats.last_rx2_start_state,
                              &mission_aborted);
            if (mission_aborted) {
                restore_lorawan_or_reset();
                return false;
            }
            if (!rxLen) {
                if (s_dl_rx) continue;
                break;
            }
            saw_frame = true;
            s_dl_stats.last_window = 2;
            s_dl_stats.last_len = (uint8_t)rxLen;
            s_dl_stats.last_mhdr = rx[0];
            authenticated = lorawan_frame_decode_downlink(
                nwkSKey, appSKey, devAddr, fCntDown, rx, rxLen,
                &decoded, &s_dl_stats.last_reject);
        } while (!authenticated &&
                 (int32_t)(millis() - rx2_deadline) < 0);
    }

    restore_lorawan_or_reset();       /* leave radio ready for the next uplink */
    if (!authenticated) {
        if (!saw_frame) s_dl_stats.last_reject = LORAWAN_FRAME_REJECT_LENGTH;
        return false;
    }

    /* Consume and atomically persist the authenticated counter BEFORE the
     * application can observe or dispatch the command. A reset after MIC
     * validation must never restore the previous value and replay the same
     * control frame. This deliberately gives commands at-most-once delivery:
     * a reset after this commit but before dispatch can lose the command, so a
     * controller must retry with a newer application sequence number. */
    fCntDown = decoded.frame_counter + 1u;
    lorawan_session_t reserved;
    lorawan_export_session(&reserved);
    if (!power_manager_save_session(&reserved)) {
        s_dl_stats.last_reject = 7;
        return false;
    }

    out->fport = decoded.fport;
    out->len = decoded.len;
    memcpy(out->data, decoded.data, decoded.len);
    s_dl_stats.last_reject = 0;
    return true;
}

/* ========== Runtime region switching ========== */

void lorawan_set_region(lora_region_id_t id) {
    if (id == REGION_ID) return;  /* no-op: same plan */

    /* Any region change invalidates the LoRaWAN session, TTN clusters
     * (nam1, eu1) are independent, DevAddr / NwkSKey / AppSKey from the
     * old region won't authenticate against the new gateway, and
     * fCntUp must reset to 0 (per-session replay protection).  Done
     * up-front so the SILENT branch below gets the same invalidation
     * as a "normal" region switch, caught by the hardware trajectory
     * test which flagged "fCntUp not reset on AS923->SILENT". */
    _joined = false;
    fCntUp  = 0;
    fCntDown = 0;
    chIdx   = 0;

    switch (id) {
        case LORA_REGION_US915: REGION = LORA_US915; break;
        case LORA_REGION_EU868: REGION = LORA_EU868; break;
        case LORA_REGION_AS923: REGION = LORA_AS923; break;
        case LORA_REGION_AU915: REGION = LORA_AU915; break;
        case LORA_REGION_SILENT:
        default:
            REGION_ID = LORA_REGION_SILENT;
            creds_loaded = false;
            return;  /* skip radio reconfig, SILENT keeps prev band */
    }

    REGION_ID = id;
    load_creds_for_current_region();  /* swap DevEUI/AppKey for new band */

    /* Reconfigure the radio for the new region's TX defaults so any
     * subsequent join attempt fires on the right band. */
    if (radio_ready) {
        (void)radio_apply_lorawan_tx(REGION.init_freq);
    }
}

lora_region_id_t lorawan_current_region(void) { return REGION_ID; }

/* ========== Session persistence ========== */

void lorawan_export_session(lorawan_session_t* out) {
    if (!out) return;
    out->magic     = 0;  /* save layer fills magic + version */
    out->version   = 0;
    out->region_id = (uint32_t)REGION_ID;
    out->devAddr   = devAddr;
    out->fCntUp    = fCntUp;
    out->fCntDown  = fCntDown;
    out->rxDelaySec = s_rx_delay_s;
    memcpy(out->nwkSKey, nwkSKey, 16);
    memcpy(out->appSKey, appSKey, 16);
}

bool lorawan_import_session(const lorawan_session_t* in) {
    if (!in) return false;
    if (in->region_id >= (uint32_t)LORA_REGION_SILENT) return false;
    if (in->rxDelaySec < 1u || in->rxDelaySec > 15u) return false;

    /* Apply region first so the radio is configured before the next
     * uplink attempt.  set_region clears _joined + fCntUp, then we
     * restore the saved session state on top. */
    REGION_ID = (lora_region_id_t)in->region_id;
    switch (REGION_ID) {
        case LORA_REGION_US915: REGION = LORA_US915; break;
        case LORA_REGION_EU868: REGION = LORA_EU868; break;
        case LORA_REGION_AS923: REGION = LORA_AS923; break;
        case LORA_REGION_AU915: REGION = LORA_AU915; break;
        default: return false;
    }
    devAddr = in->devAddr;
    fCntUp  = in->fCntUp;
    fCntDown = in->fCntDown;
    s_rx_delay_s = (uint8_t)in->rxDelaySec;
    memcpy(nwkSKey, in->nwkSKey, 16);
    memcpy(appSKey, in->appSKey, 16);
    _joined = true;

    /* Also refresh DevEUI/AppKey for the restored region.  Uplinks
     * use session keys (NwkSKey/AppSKey), but if the session ever
     * gets invalidated (region switch, replay collision, etc.) we
     * need creds available for the rejoin.  No-op if the region has
     * no creds in secrets, uplinks still work with the restored
     * session keys, just any future rejoin will fail. */
    load_creds_for_current_region();

    if (radio_ready) {
        (void)radio_apply_lorawan_tx(REGION.init_freq);
    }
    return true;
}
