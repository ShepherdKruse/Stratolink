/**
 * LoRaWAN stub for Phase 1.
 * Replace with STM32LoRaWAN (stm32duino/STM32LoRaWAN) or AT command driver
 * when integrating with RAK3172 radio.
 */
#include "lorawan.h"
#include "config.h"
#include <Arduino.h>

static bool joined = false;
static bool inited = false;

bool lorawan_init(void) {
    (void)inited;
    joined = false;
    inited = true;
#ifdef DEBUG_ENABLE
    if (DEBUG_ENABLE) {
        Serial.println("[LoRaWAN] stub init");
    }
#endif
    return true;
}

bool lorawan_join(uint32_t timeout_ms) {
    (void)timeout_ms;
    joined = true;
#ifdef DEBUG_ENABLE
    if (DEBUG_ENABLE) {
        Serial.println("[LoRaWAN] stub join OK");
    }
#endif
    return true;
}

bool lorawan_send_uplink(const uint8_t* payload, uint8_t payload_len) {
    if (!payload || payload_len > LORAWAN_PAYLOAD_MAX) return false;
#ifdef DEBUG_ENABLE
    if (DEBUG_ENABLE) {
        Serial.print("[LoRaWAN] stub uplink ");
        Serial.print(payload_len);
        Serial.println(" bytes");
    }
#endif
    (void)payload;
    return joined;
}

bool lorawan_joined(void) {
    return joined;
}
