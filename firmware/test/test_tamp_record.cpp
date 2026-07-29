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
    prove_boot();
    puts("TAMP packed records: exhaustive round-trip and one-bit rejection passed");
    return 0;
}
