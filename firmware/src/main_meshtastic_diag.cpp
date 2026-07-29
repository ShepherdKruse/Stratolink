/**
 * Meshtastic-relay bench diagnostic (env: meshtastic_relay_diag).
 *
 * Puts the RAK3172's SX1262 into Meshtastic **LongFast** mode (SF11/BW250/CR4-5,
 * 16-symbol preamble, sync 0x2B, explicit header + CRC) and runs an AUTOMATIC,
 * self-sequencing test battery so the board can be flashed, powered, and left to
 * run with zero interaction. All state is exposed in the global `mrd` RAM struct,
 * read over J-Link (mirrors the gps_diag `gd` pattern); a human-readable line is
 * also printed to Serial each phase.
 *
 * Bench context (stratolink-2, 2026-06-02): powered VSTOR/GND from a PSU at 4.8 V
 * (NO supercap yet), solar attached. So relay-listen current is read directly off
 * the PSU per labelled phase (the cap-decay method needs the cap, deferred).
 *
 * Phases (each held PHASE_MS so PSU current can be read per phase):
 *   SLEEP    radio sleep            -> baseline current
 *   STANDBY  radio standby          -> standby current
 *   RX       continuous receive     -> RELAY-LISTEN current (key #) + RX any ambient
 *                                      LongFast frames (parse header -> mrd.last_*)
 *   TXBEACON emit a LongFast frame  -> TX current + SDR off-air presence/wire-shape
 *   RELAY    RX + dedup + hop-1 + re-TX (opaque) -> the header-only relay logic
 *   MODESW   N× LoRaWAN<->Meshtastic radio reconfig, timed -> coexistence cost
 *   BW500    LongTurbo SF11/BW500   -> §15.247 A/B: ToA + presence (no default interop)
 * then loops back to RX (the steady-state relay listen).
 *
 * Manual override: set `mrd.cmd` over J-Link (gdb `set var mrd.cmd=<PhaseId>`); the
 * sequencer honours it for one phase, then resumes auto.
 *
 * Bench courtesy: TX power is low (MESH_TX_DBM) and the beacon uses a PRIVATE channel
 * hash so we don't inject into the live public LongFast mesh while characterising.
 */
#include <Arduino.h>
#include <RadioLib.h>
#include <SubGhz.h>   // force the LDF to compile+link the bundled STM32WL SubGhz lib
                      // that RadioLib's STM32WLx HAL needs (minimal-source-set LDF gap)
#include "config.h"
#include "power_adc.h"

// ---- Meshtastic LongFast (US default slot 19 = 906.875 MHz; EU = 869.525) -------
#define MESH_FREQ_US   906.875f
#define MESH_FREQ_EU   869.525f
#define MESH_FREQ      MESH_FREQ_US      // bench is in the US
#define MESH_SF        11
#define MESH_BW        250.0f
#define MESH_CR        5                 // 4/5
#define MESH_PREAMBLE  16
#define MESH_SYNC      0x2B
#define MESH_TX_DBM    2                 // low power for bench courtesy
#define TCXO_V         1.7f

// LongTurbo (BW500), the §15.247-clean A/B candidate (T11)
#define BW500          500.0f

// our LoRaWAN uplink config, for the mode-switch timing test (T6)
#define LW_FREQ        904.1f
#define LW_SF          9
#define LW_BW          125.0f
#define LW_SYNC        RADIOLIB_SX126X_SYNC_WORD_PUBLIC   // 0x34
#define LW_PREAMBLE    8

#define PHASE_MS       20000u            // hold each phase 20 s for a clean PSU read
#define DEDUP_N        16
#define MAX_PKT        255

/* RF switch, identical to lorawan.cpp (RAK3172 / STM32WLx) */
static const uint32_t rfswitch_pins[] = {PB8, PC13, RADIOLIB_NC, RADIOLIB_NC, RADIOLIB_NC};
static const Module::RfSwitchMode_t rfswitch_table[] = {
    {STM32WLx::MODE_IDLE,  {LOW,  LOW}},
    {STM32WLx::MODE_RX,    {HIGH, LOW}},
    {STM32WLx::MODE_TX_HP, {HIGH, HIGH}},
    END_OF_MODE_TABLE,
};

static STM32WLx* radio = nullptr;

/* Keep the bench diagnostic subject to the same allocation contract as the
 * flight driver.  In particular, do not allocate during static construction:
 * a failed RadioLib HAL allocation must remain observable after setup starts. */
static bool allocate_diag_radio(void) {
    STM32WLx_Module* module = new STM32WLx_Module();
    if (!module || !module->hal) {
        if (module) delete module;
        return false;
    }
    STM32WLx* candidate = new STM32WLx(module);
    if (!candidate) {
        delete module->hal;
        module->hal = nullptr;
        delete module;
        return false;
    }
    radio = candidate;
    return true;
}

enum Phase : uint8_t { P_SLEEP=0, P_STANDBY, P_RX, P_TXBEACON, P_RELAY, P_MODESW, P_BW500, P_NPHASES, P_AUTO=255 };
static const char *PNAME[P_NPHASES] = {"SLEEP","STANDBY","RX","TXBEACON","RELAY","MODESW","BW500"};

/* Diagnostic struct, read over J-Link (gdb: `print mrd`). */
struct MeshRelayDiag {
    uint32_t magic;            // 0x4D524431 "MRD1"
    uint32_t uptime_s;
    uint8_t  phase;            // current Phase
    uint8_t  cmd;              // J-Link override: set to a Phase to force it once (else P_AUTO)
    uint16_t vstor_mv;         // rail (PSU) voltage as the ADC sees it
    uint16_t solar_mv;
    int16_t  radio_begin_state;// RadioLib begin() result (0 = OK)
    // RX / relay
    uint32_t rx_count;         // valid LongFast frames received
    uint32_t rx_crc_err;
    uint32_t relay_fwd;        // packets we re-transmitted
    uint32_t relay_dedup;      // dropped as duplicate
    uint32_t relay_hop0;       // dropped, hop exhausted
    // last received frame (parsed 16-byte header)
    uint32_t last_to, last_from, last_id;
    uint8_t  last_flags, last_hop, last_chan, last_len;
    int16_t  last_rssi;        // dBm
    int16_t  last_snr_cdb;     // SNR ×100
    // TX / timing
    uint32_t tx_count;
    uint32_t last_toa_us;      // measured time-on-air of our last TX
    uint32_t modeswitch_us;    // mean LoRaWAN<->Meshtastic reconfig time
    uint32_t bw500_toa_us;     // ToA of a LongTurbo BW500 frame (vs LongFast)
};
__attribute__((used)) volatile MeshRelayDiag mrd;

static volatile bool rxFlag = false;
static void onRx(void) { rxFlag = true; }

static uint8_t  rxbuf[MAX_PKT];
static uint32_t dedup_from[DEDUP_N], dedup_id[DEDUP_N];
static uint8_t  dedup_head = 0;

#if defined(DEBUG_ENABLE) && DEBUG_ENABLE
#define LOG(x)    Serial.println(x)
#define LOGV(a,b) do{ Serial.print(a); Serial.println(b);}while(0)
#else
#define LOG(x) ((void)0)
#define LOGV(a,b) ((void)0)
#endif

static inline uint32_t rd_u32(const uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1]<<8) | ((uint32_t)p[2]<<16) | ((uint32_t)p[3]<<24);
}
static bool seen(uint32_t from, uint32_t id) {
    for (uint8_t i=0;i<DEDUP_N;i++) if (dedup_from[i]==from && dedup_id[i]==id) return true;
    return false;
}
static void mark_seen(uint32_t from, uint32_t id) {
    dedup_from[dedup_head]=from; dedup_id[dedup_head]=id; dedup_head=(dedup_head+1)%DEDUP_N;
}

/* Apply the Meshtastic LongFast PHY (used at boot and after the mode-switch test). */
static int16_t cfg_meshtastic(float bw = MESH_BW) {
    radio->standby();
    int16_t s = radio->setFrequency(MESH_FREQ);
    s |= radio->setSpreadingFactor(MESH_SF);
    s |= radio->setBandwidth(bw);
    s |= radio->setCodingRate(MESH_CR);
    s |= radio->setPreambleLength(MESH_PREAMBLE);
    s |= radio->setSyncWord(MESH_SYNC);
    s |= radio->setCRC(true);
    s |= radio->setOutputPower(MESH_TX_DBM);
    return s;
}
/* Apply our LoRaWAN uplink PHY (for the mode-switch timing test). */
static int16_t cfg_lorawan(void) {
    radio->standby();
    int16_t s = radio->setFrequency(LW_FREQ);
    s |= radio->setSpreadingFactor(LW_SF);
    s |= radio->setBandwidth(LW_BW);
    s |= radio->setPreambleLength(LW_PREAMBLE);
    s |= radio->setSyncWord(LW_SYNC);
    return s;
}

/* Build a minimal LongFast frame: 16-byte plaintext header + a few opaque bytes.
 * to=broadcast, from=our fake node, id=counter, flags=hop_limit(3), channel=private
 * hash (so we don't hit the live default mesh), next_hop/relay_node=0. */
static uint8_t build_beacon(uint8_t *p, uint32_t id) {
    uint32_t from = 0x57524431;               // "WRD1" fake node id
    uint32_t to   = 0xFFFFFFFF;               // broadcast
    p[0]=to; p[1]=to>>8; p[2]=to>>16; p[3]=to>>24;
    p[4]=from; p[5]=from>>8; p[6]=from>>16; p[7]=from>>24;
    p[8]=id; p[9]=id>>8; p[10]=id>>16; p[11]=id>>24;
    p[12]= 3 | (3<<5);                          // hop_limit=3, hop_start=3
    p[13]= 0x7F;                                // private channel hash (NOT default LongFast)
    p[14]= 0; p[15]= 0;                          // next_hop, relay_node
    const char *tag = "STRATOLINK-BENCH";       // opaque "payload" (not real ciphertext)
    uint8_t n=16; for (const char *c=tag; *c; c++) p[n++]=*c;
    return n;
}

static void handle_rx(bool relay) {
    size_t len = radio->getPacketLength();
    int16_t st = radio->readData(rxbuf, len);
    if (st != RADIOLIB_ERR_NONE) { mrd.rx_crc_err++; radio->startReceive(); return; }
    if (len < 16) { radio->startReceive(); return; }
    mrd.rx_count++;
    uint32_t to=rd_u32(rxbuf), from=rd_u32(rxbuf+4), id=rd_u32(rxbuf+8);
    uint8_t flags=rxbuf[12]; uint8_t hop=flags & 0x07;
    mrd.last_to=to; mrd.last_from=from; mrd.last_id=id; mrd.last_flags=flags;
    mrd.last_hop=hop; mrd.last_chan=rxbuf[13]; mrd.last_len=(uint8_t)len;
    mrd.last_rssi=(int16_t)radio->getRSSI(); mrd.last_snr_cdb=(int16_t)(radio->getSNR()*100);
    LOGV("RX from=", from); LOGV("  id=", id); LOGV("  hop=", hop); LOGV("  rssi=", mrd.last_rssi);
    if (relay) {
        if (hop == 0) { mrd.relay_hop0++; }
        else if (seen(from,id)) { mrd.relay_dedup++; }
        else {
            mark_seen(from,id);
            rxbuf[12] = (flags & ~0x07) | (hop-1);   // decrement hop_limit
            rxbuf[15] = 0xD1;                          // relay_node = our last byte (marker)
            radio->transmit(rxbuf, len);              // opaque re-TX, no decrypt/PSK
            mrd.relay_fwd++; mrd.tx_count++;
            LOG("  -> FORWARDED (hop-1)");
        }
    }
    radio->startReceive();
}

void setup() {
#if defined(DEBUG_ENABLE) && DEBUG_ENABLE
    Serial.begin(DEBUG_SERIAL_BAUD);
#endif
    power_adc_init();
    mrd.magic = 0x4D524431; mrd.cmd = P_AUTO;
    if (!allocate_diag_radio()) {
        mrd.radio_begin_state = RADIOLIB_ERR_MEMORY_ALLOCATION_FAILED;
        LOG("[mrd] RadioLib allocation failed");
        return;
    }
    radio->setRfSwitchTable(rfswitch_pins, rfswitch_table);
    int16_t st = radio->begin(MESH_FREQ, MESH_BW, MESH_SF, MESH_CR, MESH_SYNC,
                              MESH_TX_DBM, MESH_PREAMBLE, TCXO_V, false);
    mrd.radio_begin_state = st;
    LOGV("[mrd] radio.begin = ", st);
    radio->setCRC(true);
    radio->setPacketReceivedAction(onRx);
    LOG("[mrd] Meshtastic LongFast diag up");
}

static uint8_t  cur_phase = P_RX;
static uint32_t phase_start = 0;
static uint32_t beacon_id = 1;

static void enter_phase(uint8_t ph) {
    cur_phase = ph; mrd.phase = ph; phase_start = millis();
    LOGV("PHASE: ", PNAME[ph % P_NPHASES]);
    switch (ph) {
        case P_SLEEP:   radio->sleep();   break;
        case P_STANDBY: radio->standby(); break;
        case P_RX:
        case P_RELAY:   cfg_meshtastic(); rxFlag=false; radio->startReceive(); break;
        case P_TXBEACON: cfg_meshtastic(); break;
        case P_BW500:   cfg_meshtastic(BW500); break;
        case P_MODESW:  break;
    }
}

void loop() {
    mrd.uptime_s = millis()/1000;
    mrd.vstor_mv = power_adc_read_vSTOR_mv();
    mrd.solar_mv = power_adc_read_solar_mv();
    if (!radio) {
        delay(1000);
        return;
    }

    // RX-driven phases: service received frames
    if ((cur_phase==P_RX || cur_phase==P_RELAY) && rxFlag) { rxFlag=false; handle_rx(cur_phase==P_RELAY); }

    // periodic action within a phase
    if (cur_phase==P_TXBEACON && (millis()-phase_start)%4000 < 50) {
        uint8_t n = build_beacon(rxbuf, beacon_id++);
        uint32_t t0=micros(); radio->transmit(rxbuf, n); mrd.last_toa_us=micros()-t0;
        mrd.tx_count++; LOGV("TXBEACON toa_us=", mrd.last_toa_us);
        delay(60);
    }
    if (cur_phase==P_MODESW && (millis()-phase_start) < 200) {
        uint32_t t0=micros();
        for (int i=0;i<10;i++){ cfg_lorawan(); cfg_meshtastic(); }
        mrd.modeswitch_us = (micros()-t0)/20;     // mean of 20 reconfigs
        LOGV("MODESW mean_us=", mrd.modeswitch_us);
        radio->startReceive();                    // leave it listening
        phase_start = millis() - PHASE_MS + 3000; // short phase, move on
    }
    if (cur_phase==P_BW500 && (millis()-phase_start)%4000 < 50) {
        uint8_t n = build_beacon(rxbuf, beacon_id++);
        uint32_t t0=micros(); radio->transmit(rxbuf, n); mrd.bw500_toa_us=micros()-t0;
        LOGV("BW500 toa_us=", mrd.bw500_toa_us); delay(60);
    }

    // phase advance
    if (millis() - phase_start >= PHASE_MS) {
        uint8_t next;
        if (mrd.cmd != P_AUTO) { next = mrd.cmd; mrd.cmd = P_AUTO; }
        else next = (cur_phase==P_BW500) ? P_RX : (uint8_t)(cur_phase+1);  // loop steady-state at RX
        enter_phase(next);
    }
    delay(5);
}
