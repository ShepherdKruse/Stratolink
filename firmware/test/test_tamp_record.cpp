#include <assert.h>
#include <stdint.h>
#include <stdio.h>

#include "tamp_record.h"

static void prove_lease(void) {
    for (uint32_t age = 0; age <= TAMP_LEASE_AGE_MASK; ++age) {
        uint32_t record = tamp_lease_record_encode(age);
        uint32_t decoded = UINT32_MAX;
        assert(tamp_lease_record_decode(record, &decoded));
        assert(decoded == age);
        for (uint8_t bit = 0; bit < 32; ++bit) {
            decoded = UINT32_MAX;
            assert(!tamp_lease_record_decode(record ^ (1u << bit), &decoded));
            assert(decoded == UINT32_MAX);
        }
    }
    uint32_t decoded = 0;
    assert(tamp_lease_record_decode(
        tamp_lease_record_encode(UINT32_MAX), &decoded));
    assert(decoded == TAMP_LEASE_AGE_MASK);
    assert(!tamp_lease_record_decode(0, &decoded));
    assert(!tamp_lease_record_decode(tamp_lease_record_encode(1), nullptr));
}

static void prove_region_authority_lease(void) {
    for (uint8_t region = 0;
         region < TAMP_REGION_LEASE_REGION_COUNT;
         ++region) {
        for (uint8_t source_value = TAMP_REGION_AUTHORITY_GNSS;
             source_value <= TAMP_REGION_AUTHORITY_LAUNCH;
             ++source_value) {
            tamp_region_authority_source_t source =
                (tamp_region_authority_source_t)source_value;
            for (uint32_t age = 0; age <= TAMP_LEASE_AGE_MASK; ++age) {
                uint32_t record = UINT32_MAX;
                assert(tamp_region_lease_record_encode(
                    age, region, source, &record));
                assert((record >> 22) == TAMP_REGION_LEASE_MAGIC);

                tamp_region_lease_t decoded = {
                    UINT32_MAX,
                    TAMP_REGION_LEASE_INVALID_REGION,
                    TAMP_REGION_AUTHORITY_GNSS,
                    false,
                };
                assert(tamp_region_lease_record_decode(record, &decoded));
                assert(decoded.age_sec == age);
                assert(decoded.region_id == region);
                assert(decoded.source == source);
                assert(decoded.exact_region);

                /* Magic protects its field and CRC-8 protects every payload
                 * and check bit. Every possible one-bit corruption of the
                 * complete retained word must therefore fail closed. */
                for (uint8_t bit = 0; bit < 32; ++bit) {
                    tamp_region_lease_t corrupt = {
                        UINT32_MAX,
                        TAMP_REGION_LEASE_INVALID_REGION,
                        TAMP_REGION_AUTHORITY_GNSS,
                        false,
                    };
                    assert(!tamp_region_lease_record_decode(
                        record ^ (1u << bit), &corrupt));
                    assert(corrupt.age_sec == UINT32_MAX);
                    assert(corrupt.region_id ==
                           TAMP_REGION_LEASE_INVALID_REGION);
                    assert(corrupt.source == TAMP_REGION_AUTHORITY_GNSS);
                    assert(!corrupt.exact_region);
                }
            }
        }
    }

    uint32_t saturated_record = 0;
    assert(tamp_region_lease_record_encode(
        UINT32_MAX, 3u, TAMP_REGION_AUTHORITY_LAUNCH,
        &saturated_record));
    tamp_region_lease_t saturated = {};
    assert(tamp_region_lease_record_decode(saturated_record, &saturated));
    assert(saturated.age_sec == TAMP_LEASE_AGE_MASK);
    assert(saturated.region_id == 3u);
    assert(saturated.source == TAMP_REGION_AUTHORITY_LAUNCH);
    assert(saturated.exact_region);

    uint32_t untouched = 0x12345678u;
    assert(!tamp_region_lease_record_encode(
        0u, TAMP_REGION_LEASE_REGION_COUNT,
        TAMP_REGION_AUTHORITY_GNSS, &untouched));
    assert(untouched == 0x12345678u);
    assert(!tamp_region_lease_record_encode(
        0u, 0u, 2u, &untouched));
    assert(untouched == 0x12345678u);
    assert(!tamp_region_lease_record_encode(
        0u, 0u, TAMP_REGION_AUTHORITY_GNSS, nullptr));

    tamp_region_lease_t invalid = {};
    assert(!tamp_region_lease_record_decode(0u, &invalid));
    assert(!tamp_region_lease_record_decode(saturated_record, nullptr));
}

static void prove_legacy_region_lease_migration(void) {
    for (uint32_t age = 0; age <= TAMP_LEASE_AGE_MASK; ++age) {
        uint32_t record = tamp_lease_record_encode(age);
        tamp_region_lease_t decoded = {};
        assert(tamp_region_lease_record_decode(record, &decoded));
        assert(decoded.age_sec == age);
        assert(decoded.region_id == TAMP_REGION_LEASE_INVALID_REGION);
        assert(decoded.source == TAMP_REGION_AUTHORITY_GNSS);
        assert(!decoded.exact_region);

        for (uint8_t bit = 0; bit < 32; ++bit) {
            tamp_region_lease_t corrupt = {
                UINT32_MAX,
                TAMP_REGION_LEASE_INVALID_REGION,
                TAMP_REGION_AUTHORITY_GNSS,
                false,
            };
            assert(!tamp_region_lease_record_decode(
                record ^ (1u << bit), &corrupt));
            assert(corrupt.age_sec == UINT32_MAX);
        }
    }
}

static void prove_boot(void) {
    for (uint32_t count = 0; count <= TAMP_BOOT_COUNT_MASK; ++count) {
        uint32_t record = tamp_boot_record_encode(count);
        uint32_t decoded = UINT32_MAX;
        assert(tamp_boot_record_decode(record, &decoded));
        assert(decoded == count);
        for (uint8_t bit = 0; bit < 32; ++bit) {
            decoded = UINT32_MAX;
            assert(!tamp_boot_record_decode(record ^ (1u << bit), &decoded));
            assert(decoded == UINT32_MAX);
        }
    }
    uint32_t decoded = 0;
    assert(tamp_boot_record_decode(
        tamp_boot_record_encode(UINT32_MAX), &decoded));
    assert(decoded == TAMP_BOOT_COUNT_MASK);
    assert(!tamp_boot_record_decode(0, &decoded));
    assert(!tamp_boot_record_decode(tamp_boot_record_encode(1), nullptr));
}

int main(void) {
    prove_lease();
    prove_region_authority_lease();
    prove_legacy_region_lease_migration();
    prove_boot();
    puts("TAMP packed records: legacy/v2 exhaustive round-trip and one-bit rejection passed");
    return 0;
}
