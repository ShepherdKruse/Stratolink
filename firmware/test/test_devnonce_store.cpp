#include <cstdint>
#include <cstdio>

#include "devnonce_store.h"

static int failures = 0;
#define CHECK(x) do { if (!(x)) { \
    std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #x); \
    ++failures; \
} } while (0)

int main() {
    const uint16_t cases[] = {0u, 1u, 0x1234u, 0xFFFEu, 0xFFFFu};
    for (uint16_t value : cases) {
        uint64_t record = devnonce_record_encode(value);
        uint16_t decoded = 0;
        CHECK(devnonce_record_decode(record, &decoded));
        CHECK(decoded == value);
        CHECK(!devnonce_record_decode(record ^ (1ull << 37), &decoded));
    }

    uint16_t next = 99;
    CHECK(devnonce_value_next(false, 0, &next) && next == 0);
    CHECK(devnonce_value_next(true, 0, &next) && next == 1);
    CHECK(devnonce_value_next(true, 0xFFFEu, &next) && next == 0xFFFFu);
    CHECK(!devnonce_value_next(true, 0xFFFFu, &next));
    CHECK(!devnonce_value_next(false, 0, nullptr));

    if (failures) return 1;
    std::puts("DevNonce journal record/corruption/exhaustion tests passed");
    return 0;
}
