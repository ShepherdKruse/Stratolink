#pragma once

#include <stdbool.h>
#include <stdint.h>

/* STM32WLE5 exposes only 20 backup registers. The session consumes words
 * 0..15, so the safety-critical region lease and diagnostic boot count each
 * use one self-checking word.
 *
 * The original lease record retained only age:
 *
 *   [31:22] legacy magic, [21:11] complemented age, [10:0] age
 *
 * The current record uses the same word and age width while binding the lease
 * to both its authority source and exact frequency plan:
 *
 *   [31:22] v2 magic, [21:14] CRC-8, [13] source,
 *   [12:11] region, [10:0] age
 *
 * A distinct magic keeps the formats unambiguous. The v2 decoder still
 * accepts a valid legacy word as GNSS-derived, but reports that its exact
 * region is absent so the caller can bind it to a separately CRC-protected
 * retained session before migrating it. */
#define TAMP_LEASE_AGE_MASK        0x7FFu
#define TAMP_LEASE_MAGIC           0x2D3u /* legacy age-only record */
#define TAMP_REGION_LEASE_MAGIC    0x16Du
#define TAMP_REGION_LEASE_PAYLOAD_MASK 0x3FFFu
#define TAMP_REGION_LEASE_INVALID_REGION 0xFFu
#define TAMP_REGION_LEASE_REGION_COUNT 4u
#define TAMP_BOOT_COUNT_MASK 0xFFFu
#define TAMP_BOOT_MAGIC      0xB4u

typedef enum {
    TAMP_REGION_AUTHORITY_GNSS = 0,
    TAMP_REGION_AUTHORITY_LAUNCH = 1
} tamp_region_authority_source_t;

typedef struct {
    uint32_t age_sec;
    uint8_t region_id;
    tamp_region_authority_source_t source;
    /* False only for a valid legacy age-only record. Such a record is not an
     * exact regional authorization by itself. */
    bool exact_region;
} tamp_region_lease_t;

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

/* CRC-8/ATM (polynomial x^8 + x^2 + x + 1) over the complete 14-bit v2
 * payload, serialized least-significant byte first. Together with the
 * versioned magic this detects every single-bit error in the 32-bit word. */
static inline uint8_t tamp_region_lease_crc8(uint16_t payload) {
    uint8_t crc = 0xA5u;
    for (uint8_t byte_index = 0; byte_index < 2; ++byte_index) {
        crc ^= (uint8_t)(payload >> (8u * byte_index));
        for (uint8_t bit = 0; bit < 8; ++bit) {
            crc = (uint8_t)((crc & 0x80u)
                ? (uint8_t)((crc << 1) ^ 0x07u)
                : (uint8_t)(crc << 1));
        }
    }
    return crc;
}

/** Encode an exact-region lease. Region IDs 0..3 intentionally match the
 * stable lora_region_id_t ordering (US915, EU868, AS923, AU915). Invalid
 * source/region/output arguments fail closed without producing a record. */
static inline bool tamp_region_lease_record_encode(
    uint32_t age_sec,
    uint8_t region_id,
    uint8_t source_id,
    uint32_t* record) {
    if (!record || region_id >= TAMP_REGION_LEASE_REGION_COUNT ||
        (source_id != TAMP_REGION_AUTHORITY_GNSS &&
         source_id != TAMP_REGION_AUTHORITY_LAUNCH)) {
        return false;
    }
    uint32_t age = age_sec > TAMP_LEASE_AGE_MASK
        ? TAMP_LEASE_AGE_MASK : age_sec;
    uint16_t payload = (uint16_t)(age |
        ((uint32_t)region_id << 11) |
        ((uint32_t)source_id << 13));
    uint8_t check = tamp_region_lease_crc8(payload);
    *record = (TAMP_REGION_LEASE_MAGIC << 22) |
              ((uint32_t)check << 14) | payload;
    return true;
}

/** Decode either the exact-region v2 record or a legacy GNSS age record.
 * Output is committed only after every structural/integrity check passes.
 * For legacy input, exact_region is false and region_id is the invalid
 * sentinel; callers must obtain the region from an independently validated
 * retained session before treating it as authorization. */
static inline bool tamp_region_lease_record_decode(
    uint32_t record, tamp_region_lease_t* lease) {
    if (!lease) return false;

    uint32_t magic = record >> 22;
    if (magic == TAMP_REGION_LEASE_MAGIC) {
        uint16_t payload = (uint16_t)(
            record & TAMP_REGION_LEASE_PAYLOAD_MASK);
        uint8_t check = (uint8_t)((record >> 14) & 0xFFu);
        if (check != tamp_region_lease_crc8(payload)) return false;

        tamp_region_lease_t decoded;
        decoded.age_sec = payload & TAMP_LEASE_AGE_MASK;
        decoded.region_id = (uint8_t)((payload >> 11) & 0x03u);
        decoded.source = (tamp_region_authority_source_t)(
            (payload >> 13) & 0x01u);
        decoded.exact_region = true;
        *lease = decoded;
        return true;
    }

    if (magic == TAMP_LEASE_MAGIC) {
        uint32_t age_sec = 0;
        if (!tamp_lease_record_decode(record, &age_sec)) return false;
        tamp_region_lease_t decoded;
        decoded.age_sec = age_sec;
        decoded.region_id = TAMP_REGION_LEASE_INVALID_REGION;
        decoded.source = TAMP_REGION_AUTHORITY_GNSS;
        decoded.exact_region = false;
        *lease = decoded;
        return true;
    }

    return false;
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
