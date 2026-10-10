/**
 * NOT FLIGHT FIRMWARE: finite CTT/Motus 434 MHz test-tag emulator.
 *
 * This image exists only to make a second StratoLink board provide controlled
 * physical stimulus for the flight receiver. Both available boards use the
 * high-band RAK3172-9 RF path, so reception proves the digital decoder,
 * aggregation, queue, event uplink, and LoRaWAN restore path; it does not
 * qualify absolute 434 MHz sensitivity or airborne range.
 *
 * RF safety contract:
 *   - HP-only board routing fixes output at the RadioLib minimum, -9 dBm.
 *   - Exactly CTT_TX_FRAME_COUNT frames are attempted once per boot.
 *   - Every transmission is followed by at least ten seconds of silence.
 *   - Any configuration failure prevents all RF transmission.
 *   - The radio enters standby permanently after the finite sequence.
 *
 * Use only in a shielded/controlled bench arrangement with a suitable load or
 * antenna. Build explicitly with `pio run -e ctt_tx_diag`; this source is
 * excluded from every flight and receiver-diagnostic environment.
 */
#ifndef CTT_TX_DIAG_BUILD
#error "main_ctt_tx_diag.cpp is diagnostic-only; use env:ctt_tx_diag"
#endif

#include <Arduino.h>
#include <RadioLib.h>
#include <SubGhz.h>

#include "ctt_test_tag.h"

static constexpr float CTT_TX_FREQ_MHZ = 434.0f;
static constexpr float CTT_TX_BITRATE_KBPS = 25.0f;
static constexpr float CTT_TX_DEVIATION_KHZ = 25.0f;
static constexpr float CTT_TX_RX_BW_KHZ = 93.8f;
static constexpr int8_t CTT_TX_POWER_DBM = -9;  // minimum of the HP-only path
static constexpr uint16_t CTT_TX_PREAMBLE_BITS = 24;
static constexpr uint32_t CTT_TX_SILENT_MS = 10000u;
static constexpr uint8_t CTT_TX_FRAME_COUNT = 24;
static_assert(CTT_TX_POWER_DBM == -9, "do not raise diagnostic RF power");
static_assert(CTT_TX_SILENT_MS >= 10000u, "retain the RF quiet interval");

static const uint32_t rfswitch_pins[] = {
    PB8, PC13, RADIOLIB_NC, RADIOLIB_NC, RADIOLIB_NC,
};
static const Module::RfSwitchMode_t rfswitch_table[] = {
    {STM32WLx::MODE_IDLE,  {LOW,  LOW}},
    {STM32WLx::MODE_RX,    {HIGH, LOW}},
    {STM32WLx::MODE_TX_HP, {HIGH, HIGH}},
    END_OF_MODE_TABLE,
};

static STM32WLx* radio = nullptr;

enum CttTxVectorKind : uint8_t {
    CTT_TX_VALID = 0,
    CTT_TX_BAD_CRC = 1,
    CTT_TX_NON_DICTIONARY = 2,
};

struct CttTxDiagState {
    uint32_t magic;              // "CTX1"
    uint32_t uptime_ms;
    uint32_t last_raw_id;
    uint32_t tx_attempts;
    uint32_t tx_success;
    uint32_t tx_fail;
    int16_t config_state;
    int16_t last_tx_state;
    int8_t power_dbm;
    uint8_t frame_index;
    uint8_t frame_count;
    uint8_t vector_kind;
    uint8_t last_frame[5];
    uint8_t configured;
    uint8_t complete;
    uint8_t reserved[2];
};

volatile CttTxDiagState ctt_tx_diag_state = {
    0x43545831u, 0, 0, 0, 0, 0, RADIOLIB_ERR_UNKNOWN,
    RADIOLIB_ERR_UNKNOWN, CTT_TX_POWER_DBM, 0, CTT_TX_FRAME_COUNT,
    CTT_TX_VALID, {0, 0, 0, 0, 0}, 0, 0, {0, 0},
};

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

static void record_frame(const uint8_t frame[5], uint8_t kind) {
    ctt_tx_diag_state.vector_kind = kind;
    ctt_tx_diag_state.last_raw_id =
        ((uint32_t)frame[0] << 24) | ((uint32_t)frame[1] << 16) |
        ((uint32_t)frame[2] << 8) | frame[3];
    for (uint8_t i = 0; i < 5; ++i) ctt_tx_diag_state.last_frame[i] = frame[i];
}

static bool make_test_frame(uint8_t index, uint8_t frame[5], uint8_t* kind) {
    if (!frame || !kind || index >= CTT_TX_FRAME_COUNT) return false;
    *kind = CTT_TX_VALID;

    if (index <= 3u) {
        /* Known public reference: raw 0x78554C33, Motus ID 0x3256E,
         * CRC 0x58. The first three copies prove same-window aggregation. */
        if (!ctt_test_tag_encode(0x3256Eu, frame)) return false;
        if (index == 3u) {
            frame[4] ^= 0x01u;
            *kind = CTT_TX_BAD_CRC;
        }
        return true;
    }

    if (index == 4u) {
        /* CRC-valid but non-dictionary raw ID: proves the receiver's explicit
         * motus_valid=false representation without manufacturing a Motus ID. */
        frame[0] = 0xDE;
        frame[1] = 0xAD;
        frame[2] = 0xBE;
        frame[3] = 0xEF;
        frame[4] = ctt_test_tag_crc8(frame, 4);
        *kind = CTT_TX_NON_DICTIONARY;
        return true;
    }

    /* Nineteen distinct valid IDs exercise FIFO order and the 16-entry
     * receiver queue's bounded overflow path after the reference event. */
    return ctt_test_tag_encode(0x12000u + (uint32_t)(index - 5u), frame);
}

static int16_t configure_radio(void) {
    if (!allocate_diag_radio()) return RADIOLIB_ERR_MEMORY_ALLOCATION_FAILED;
    radio->setRfSwitchTable(rfswitch_pins, rfswitch_table);

    int16_t state = radio->beginFSK(
        CTT_TX_FREQ_MHZ, CTT_TX_BITRATE_KBPS, CTT_TX_DEVIATION_KHZ,
        CTT_TX_RX_BW_KHZ, CTT_TX_POWER_DBM, CTT_TX_PREAMBLE_BITS, 1.7f, false);
    if (state == RADIOLIB_ERR_NONE) {
        state = radio->setDataShaping(RADIOLIB_SHAPING_NONE);
    }
    if (state == RADIOLIB_ERR_NONE) state = radio->setEncoding(RADIOLIB_ENCODING_NRZ);
    uint8_t sync[2] = {0xD3, 0x91};
    if (state == RADIOLIB_ERR_NONE) state = radio->setSyncWord(sync, 2);
    if (state == RADIOLIB_ERR_NONE) state = radio->fixedPacketLengthMode(5);
    if (state == RADIOLIB_ERR_NONE) state = radio->setCRC(0);
    return state;
}

void setup() {
    Serial.begin(115200);
    delay(100);
    Serial.println("[ctt_tx_diag] NOT FLIGHT; finite -9 dBm test sequence");

    ctt_tx_diag_state.config_state = configure_radio();
    if (ctt_tx_diag_state.config_state != RADIOLIB_ERR_NONE) {
        Serial.print("[ctt_tx_diag] configuration failed: ");
        Serial.println(ctt_tx_diag_state.config_state);
        if (radio) radio->standby();
        return;
    }
    ctt_tx_diag_state.configured = 1;
    Serial.println("[ctt_tx_diag] configured; first frame in 10 seconds");
    delay(CTT_TX_SILENT_MS);
}

void loop() {
    ctt_tx_diag_state.uptime_ms = millis();
    if (!ctt_tx_diag_state.configured || ctt_tx_diag_state.complete) {
        delay(1000);
        return;
    }

    const uint8_t index = ctt_tx_diag_state.frame_index;
    if (index >= CTT_TX_FRAME_COUNT) {
        radio->standby();
        ctt_tx_diag_state.complete = 1;
        Serial.println("[ctt_tx_diag] finite sequence complete; radio in standby");
        return;
    }

    uint8_t frame[5] = {};
    uint8_t kind = CTT_TX_VALID;
    if (!make_test_frame(index, frame, &kind)) {
        radio->standby();
        ctt_tx_diag_state.complete = 1;
        ctt_tx_diag_state.last_tx_state = RADIOLIB_ERR_UNKNOWN;
        return;
    }

    record_frame(frame, kind);
    ctt_tx_diag_state.tx_attempts++;
    const int16_t state = radio->transmit(frame, sizeof(frame));
    ctt_tx_diag_state.last_tx_state = state;
    if (state == RADIOLIB_ERR_NONE) {
        ctt_tx_diag_state.tx_success++;
    } else {
        ctt_tx_diag_state.tx_fail++;
    }
    ctt_tx_diag_state.frame_index = (uint8_t)(index + 1u);

    Serial.print("[ctt_tx_diag] frame ");
    Serial.print(index);
    Serial.print(" kind=");
    Serial.print(kind);
    Serial.print(" state=");
    Serial.println(state);

    /* Blocking transmit is about 3.2 ms; start the full quiet interval only
     * after it returns so the on-air-to-on-air silence is never shortened. */
    delay(CTT_TX_SILENT_MS);
}
