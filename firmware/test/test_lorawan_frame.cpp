#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "lorawan_crypto.h"
#include "lorawan_frame.h"

static void from_hex(const char* hex, uint8_t* out, size_t length) {
    for (size_t i = 0; i < length; ++i) {
        unsigned value = 0;
        assert(sscanf(hex + i * 2, "%2x", &value) == 1);
        out[i] = (uint8_t)value;
    }
}

static size_t make_downlink(const uint8_t nwk[16], const uint8_t app[16],
                            uint32_t addr, uint32_t counter,
                            uint8_t* frame) {
    const uint8_t clear[] = {0x12, 0x34, 0x56, 0x78, 0x9a};
    size_t i = 0;
    frame[i++] = 0x60;
    frame[i++] = (uint8_t)addr;
    frame[i++] = (uint8_t)(addr >> 8);
    frame[i++] = (uint8_t)(addr >> 16);
    frame[i++] = (uint8_t)(addr >> 24);
    frame[i++] = 0x02;                 /* two bytes of FOpts */
    frame[i++] = (uint8_t)counter;
    frame[i++] = (uint8_t)(counter >> 8);
    frame[i++] = 0x03; frame[i++] = 0x04;
    frame[i++] = 10;
    memcpy(frame + i, clear, sizeof(clear));
    assert(lorawan_crypto_payload(app, addr, counter, 1,
                                  frame + i, sizeof(clear)));
    i += sizeof(clear);
    uint8_t mic[4];
    assert(lorawan_crypto_mic(nwk, addr, counter, 1, frame, i, mic));
    memcpy(frame + i, mic, sizeof(mic));
    return i + sizeof(mic);
}

int main(void) {
    uint8_t app[16], nwk[16];
    from_hex("000102030405060708090a0b0c0d0e0f", app, sizeof(app));
    from_hex("2b7e151628aed2a6abf7158809cf4f3c", nwk, sizeof(nwk));
    const uint32_t addr = 0x26011BDAu;
    uint8_t frame[64] = {};
    size_t frame_len = make_downlink(nwk, app, addr, 0x00010003u, frame);

    lorawan_decoded_downlink_t decoded;
    uint8_t reject = 0xFF;
    assert(lorawan_frame_decode_downlink(
        nwk, app, addr, 0x00010003u, frame, frame_len, &decoded, &reject));
    assert(reject == LORAWAN_FRAME_REJECT_NONE);
    assert(decoded.frame_counter == 0x00010003u);
    assert(decoded.fport == 10 && decoded.len == 5);
    const uint8_t expected[] = {0x12, 0x34, 0x56, 0x78, 0x9a};
    assert(memcmp(decoded.data, expected, sizeof(expected)) == 0);

    uint8_t changed[64];
    memcpy(changed, frame, frame_len);
    changed[1] ^= 1u;
    assert(!lorawan_frame_decode_downlink(
        nwk, app, addr, 0x00010003u, changed, frame_len, &decoded, &reject));
    assert(reject == LORAWAN_FRAME_REJECT_DEVADDR);
    memcpy(changed, frame, frame_len);
    changed[0] = 0x40;
    assert(!lorawan_frame_decode_downlink(
        nwk, app, addr, 0x00010003u, changed, frame_len, &decoded, &reject));
    assert(reject == LORAWAN_FRAME_REJECT_MHDR);
    memcpy(changed, frame, frame_len);
    changed[0] = 0x61;                /* unsupported Major/RFU bits */
    assert(!lorawan_frame_decode_downlink(
        nwk, app, addr, 0x00010003u, changed, frame_len, &decoded, &reject));
    assert(reject == LORAWAN_FRAME_REJECT_MHDR);
    memcpy(changed, frame, frame_len);
    changed[frame_len - 1] ^= 1u;
    assert(!lorawan_frame_decode_downlink(
        nwk, app, addr, 0x00010003u, changed, frame_len, &decoded, &reject));
    assert(reject == LORAWAN_FRAME_REJECT_MIC);
    assert(!lorawan_frame_decode_downlink(
        nwk, app, addr, 0x00010004u, frame, frame_len, &decoded, &reject));
    assert(reject == LORAWAN_FRAME_REJECT_COUNTER);
    assert(!lorawan_frame_decode_downlink(
        nwk, app, addr, 0x00010003u, frame, 11, &decoded, &reject));
    assert(reject == LORAWAN_FRAME_REJECT_LENGTH);
    assert(!lorawan_frame_decode_downlink(
        nullptr, app, addr, 0x00010003u, frame, frame_len,
        &decoded, &reject));
    assert(!lorawan_frame_decode_downlink(
        nwk, app, addr, 0x00010003u, frame, frame_len,
        nullptr, &reject));
    for (size_t byte = 0; byte < frame_len; ++byte) {
        for (uint8_t bit = 0; bit < 8; ++bit) {
            memcpy(changed, frame, frame_len);
            changed[byte] ^= (uint8_t)(1u << bit);
            assert(!lorawan_frame_decode_downlink(
                nwk, app, addr, 0x00010003u, changed, frame_len,
                &decoded, &reject));
        }
    }

    /* Synthetic join-accept generated independently by
     * generate_lorawan_crypto_vectors.mjs with Node/OpenSSL. The clear body is
     * AppNonce 010203, NetID 040506, DevAddr 26011BDA (LE), DLSettings 00,
     * RxDelay 05, followed by its AppKey CMAC. */
    uint8_t join[17];
    from_hex("20436b0eb787e358149bd659c26d57ec43", join, sizeof(join));
    uint8_t plain[33];
    assert(lorawan_frame_decode_join_accept(app, join, sizeof(join), plain));
    assert(plain[0] == 0x20);
    const uint8_t join_fields[] = {
        0x01,0x02,0x03,0x04,0x05,0x06,0xda,0x1b,0x01,0x26,0x00,0x05
    };
    assert(memcmp(plain + 1, join_fields, sizeof(join_fields)) == 0);
    assert(!lorawan_frame_decode_join_accept(
        nullptr, join, sizeof(join), plain));
    assert(!lorawan_frame_decode_join_accept(
        app, join, sizeof(join), nullptr));
    assert(!lorawan_frame_decode_join_accept(app, join, 16, plain));
    uint8_t valid_join[sizeof(join)];
    memcpy(valid_join, join, sizeof(join));
    for (size_t byte = 0; byte < sizeof(join); ++byte) {
        for (uint8_t bit = 0; bit < 8; ++bit) {
            memcpy(join, valid_join, sizeof(join));
            join[byte] ^= (uint8_t)(1u << bit);
            assert(!lorawan_frame_decode_join_accept(
                app, join, sizeof(join), plain));
        }
    }
    memcpy(join, valid_join, sizeof(join));
    join[4] ^= 1u;
    assert(!lorawan_frame_decode_join_accept(app, join, sizeof(join), plain));
    join[4] ^= 1u;
    join[0] = 0x60;
    assert(!lorawan_frame_decode_join_accept(app, join, sizeof(join), plain));
    join[0] = 0x21;
    assert(!lorawan_frame_decode_join_accept(app, join, sizeof(join), plain));

    uint8_t join_cf[33];
    from_hex(
        "202c0645afd2cc1374073728f44afffdf2"
        "e4f213d4508d1c8dd536804cef5c42e5",
        join_cf, sizeof(join_cf));
    assert(lorawan_frame_decode_join_accept(
        app, join_cf, sizeof(join_cf), plain));
    assert(memcmp(plain + 1, join_fields, sizeof(join_fields)) == 0);
    uint8_t cf_list[16];
    from_hex("0102030405060708090a0b0c0d0e0f00",
             cf_list, sizeof(cf_list));
    assert(memcmp(plain + 13, cf_list, sizeof(cf_list)) == 0);
    uint8_t changed_join_cf[sizeof(join_cf)];
    for (size_t byte = 0; byte < sizeof(join_cf); ++byte) {
        for (uint8_t bit = 0; bit < 8; ++bit) {
            memcpy(changed_join_cf, join_cf, sizeof(join_cf));
            changed_join_cf[byte] ^= (uint8_t)(1u << bit);
            assert(!lorawan_frame_decode_join_accept(
                app, changed_join_cf, sizeof(changed_join_cf), plain));
        }
    }

    puts("LoRaWAN receive frames: authenticated RX1/RX2 gate cases passed");
    return 0;
}
