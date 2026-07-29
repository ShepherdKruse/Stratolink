#pragma once

#include <stdbool.h>
#include <stdint.h>

/* STM32WLE5 exposes only 20 backup registers. The session consumes words
 * 0..15, so the safety-critical region lease and diagnostic boot count each
 * use one self-checking word. */
#define TAMP_LEASE_AGE_MASK  0x7FFu
#define TAMP_LEASE_MAGIC     0x2D3u
#define TAMP_BOOT_COUNT_MASK 0xFFFu
#define TAMP_BOOT_MAGIC      0xB4u

static inline uint32_t tamp_lease_record_encode(uint32_t age_sec) {
    uint32_t age = age_sec > TAMP_LEASE_AGE_MASK
        ? TAMP_LEASE_AGE_MASK : age_sec;
    uint32_t check = (~age) & TAMP_LEASE_AGE_MASK;
    return (TAMP_LEASE_MAGIC << 22) | (check << 11) | age;
}

static inline bool tamp_lease_record_decode(
    uint32_t record, uint32_t* age_sec) {
    if (!age_sec || (record >> 22) != TAMP_LEASE_MAGIC) return false;
    uint32_t age = record & TAMP_LEASE_AGE_MASK;
    uint32_t check = (record >> 11) & TAMP_LEASE_AGE_MASK;
    if (check != ((~age) & TAMP_LEASE_AGE_MASK)) return false;
    *age_sec = age;
    return true;
}

static inline uint32_t tamp_boot_record_encode(uint32_t count) {
    uint32_t value = count > TAMP_BOOT_COUNT_MASK
        ? TAMP_BOOT_COUNT_MASK : count;
    uint32_t check = (~value) & TAMP_BOOT_COUNT_MASK;
    return (TAMP_BOOT_MAGIC << 24) | (check << 12) | value;
}

static inline bool tamp_boot_record_decode(
    uint32_t record, uint32_t* count) {
    if (!count || (record >> 24) != TAMP_BOOT_MAGIC) return false;
    uint32_t value = record & TAMP_BOOT_COUNT_MASK;
    uint32_t check = (record >> 12) & TAMP_BOOT_COUNT_MASK;
    if (check != ((~value) & TAMP_BOOT_COUNT_MASK)) return false;
    *count = value;
    return true;
}
