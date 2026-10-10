#include "optical_fault_policy.h"

#include <assert.h>
#include <stdint.h>
#include <stdio.h>

int main() {
    assert(!optical_fault_consume_fast_retry(nullptr, 5u));

    uint8_t retries = 0u;
    assert(!optical_fault_consume_fast_retry(&retries, 0u));
    assert(retries == 0u);

    for (uint8_t expected = 1u; expected <= 5u; ++expected) {
        assert(optical_fault_consume_fast_retry(&retries, 5u));
        assert(retries == expected);
    }
    assert(!optical_fault_consume_fast_retry(&retries, 5u));
    assert(retries == 5u);

    retries = UINT8_MAX - 1u;
    assert(optical_fault_consume_fast_retry(&retries, UINT8_MAX));
    assert(retries == UINT8_MAX);
    assert(!optical_fault_consume_fast_retry(&retries, UINT8_MAX));
    assert(retries == UINT8_MAX);

    retries = 9u;
    assert(!optical_fault_consume_fast_retry(&retries, 5u));
    assert(retries == 9u);

    puts("PASS: optical fault fast retries are bounded and cannot wrap");
    return 0;
}
