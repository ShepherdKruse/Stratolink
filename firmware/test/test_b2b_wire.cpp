#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "b2b.h"

int main(void) {
    static const uint8_t auth_key[16] = {
        0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
        0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F,
    };
    b2b_t state = {};
    b2b_reset(&state, 0x0002);
    b2b_add_airtime(&state, UINT32_MAX);
    assert(state.airtime_budget_ms == B2B_AIRTIME_CAP_MS);
    state.airtime_budget_ms = 1;
    b2b_add_airtime(&state, UINT32_MAX);
    assert(state.airtime_budget_ms == B2B_AIRTIME_CAP_MS);
    state.airtime_budget_ms = 0;

    /* At the datasheet-fastest 34 kHz LSI, 3,825 nominal RTC seconds are the
     * first value that proves 60 real minutes elapsed. The scheduler must use
     * this lower wall-time bound, preserve long missions, and survive wrap. */
    assert(b2b_interval_due(false, 0u, 0u, 60u));
    assert(!b2b_interval_due(true, 1000u + 3824u, 1000u, 60u));
    assert(b2b_interval_due(true, 1000u + 3825u, 1000u, 60u));
    assert(b2b_interval_due(true, 1000u + 65536u, 1000u, 60u));
    assert(!b2b_interval_due(
        true, 2823u, UINT32_MAX - 1000u, 60u));
    assert(b2b_interval_due(
        true, 2824u, UINT32_MAX - 1000u, 60u));

    /* Freshness takes the opposite bound. At 29.5 kHz, 3,318 raw seconds can
     * already represent 60 real minutes; one more raw tick proves >60. */
    assert(b2b_age_upper_minutes(0u) == 0u);
    assert(b2b_age_upper_minutes(3318u) == 60u);
    assert(b2b_age_upper_minutes(3319u) == 61u);
    assert(b2b_elapsed_lower_minutes(3824u) == 59u);
    assert(b2b_elapsed_lower_minutes(3825u) == 60u);
    /* Integer-oracle sweep: upper is the least whole minute not below the
     * slow-LSI wall time; lower is the greatest whole minute not above the
     * fast-LSI wall time. This proves both rounding directions and monotonicity
     * across more than two days of raw ticks without floating point. */
    uint32_t previous_upper = 0, previous_lower = 0;
    for (uint32_t delta = 0; delta <= 200000u; ++delta) {
        uint32_t upper = b2b_age_upper_minutes(delta);
        uint32_t lower = b2b_elapsed_lower_minutes(delta);
        uint64_t scaled = (uint64_t)delta * B2B_RTC_CONFIGURED_LSI_HZ;
        uint64_t slow_den = (uint64_t)B2B_RTC_MIN_LSI_HZ * 60u;
        uint64_t fast_den = (uint64_t)B2B_RTC_MAX_LSI_HZ * 60u;
        assert((uint64_t)upper * slow_den >= scaled);
        assert(upper == 0u ||
               (uint64_t)(upper - 1u) * slow_den < scaled);
        assert((uint64_t)lower * fast_den <= scaled);
        assert((uint64_t)(lower + 1u) * fast_den > scaled);
        assert(upper >= previous_upper && lower >= previous_lower);
        previous_upper = upper;
        previous_lower = lower;
    }

    b2b_crumb_t crumb = {3745, -12242, 180, 3};
    uint8_t payload[B2B_CRUMB_LEN + B2B_AUTH_TAG_LEN] = {};
    b2b_crumb_pack(&crumb, payload);
    memset(payload + B2B_CRUMB_LEN, 0xA5, B2B_AUTH_TAG_LEN);

    b2b_frame_t frame = {};
    memset(frame.payload, 0xFF, sizeof(frame.payload));
    assert(b2b_make(&state, B2B_TYPE_CRUMB, payload, sizeof(payload), &frame));
    assert(state.next_msg_id == 1);
    uint8_t tag[B2B_AUTH_TAG_LEN];
    assert(b2b_auth_tag(auth_key, &frame, tag));
    static const uint8_t openssl_expected[B2B_AUTH_TAG_LEN] = {
        0xC1, 0x67, 0xEB, 0x8C, 0xE4, 0x7F, 0x19, 0x3D,
    };
    assert(memcmp(tag, openssl_expected, sizeof(tag)) == 0);
    memcpy(frame.payload + B2B_CRUMB_LEN, tag, sizeof(tag));
    assert(b2b_auth_verify(auth_key, &frame));

    /* Queue residence is part of position freshness. A relay must advance the
     * coarse age, saturate instead of wrapping, and renew the CMAC without
     * changing the origin identity. */
    b2b_frame_t aged = frame;
    aged.queued_rtc_sec = 1000;
    assert(b2b_refresh_authenticated_age(auth_key, &aged, 4318));
    b2b_crumb_t aged_crumb = {};
    b2b_crumb_unpack(aged.payload, &aged_crumb);
    assert(aged_crumb.age_min == 63);
    assert(aged.src == frame.src && aged.msg_id == frame.msg_id &&
           aged.ttl == frame.ttl && aged.queued_rtc_sec == 4318);
    assert(b2b_auth_verify(auth_key, &aged));
    assert(b2b_refresh_authenticated_age(auth_key, &aged, 70000));
    b2b_crumb_unpack(aged.payload, &aged_crumb);
    assert(aged_crumb.age_min == 255);
    assert(b2b_auth_verify(auth_key, &aged));

    uint8_t wrong_age_key[16];
    memcpy(wrong_age_key, auth_key, sizeof(wrong_age_key));
    wrong_age_key[0] ^= 1;
    b2b_frame_t rejected_age = frame;
    rejected_age.queued_rtc_sec = 1000;
    assert(!b2b_refresh_authenticated_age(
        wrong_age_key, &rejected_age, 4318));
    assert(rejected_age.payload[B2B_CRUMB_LEN - 1] == 3 &&
           rejected_age.queued_rtc_sec == 1000);

    b2b_t age_forward = {};
    b2b_reset(&age_forward, 0x0003);
    b2b_add_airtime(&age_forward, 1000);
    assert(b2b_ingest(&age_forward, &frame, 1000) == B2B_FORWARD);
    b2b_frame_t forwarded_age = {};
    assert(b2b_next_forward_fresh(
        &age_forward, &forwarded_age, 100, auth_key, 4318));
    b2b_crumb_unpack(forwarded_age.payload, &aged_crumb);
    assert(aged_crumb.age_min == 63 &&
           b2b_auth_verify(auth_key, &forwarded_age));

    /* The raw uint32 RTC-second epoch remains wrap-safe and a frame heard
     * 65,536 nominal seconds later is well beyond the retention horizon. */
    b2b_t long_flight = {};
    b2b_reset(&long_flight, 0x0003);
    b2b_add_airtime(&long_flight, 1000);
    assert(b2b_ingest(&long_flight, &frame, 1000) == B2B_FORWARD);
    b2b_frame_t drained = {};
    assert(b2b_next_forward(&long_flight, &drained, 100));
    assert(b2b_ingest(&long_flight, &frame, 1000u + 65536u) ==
           B2B_FORWARD);

    /* Security boundary, not a success claim: dedup is volatile and expires.
     * At the 34 kHz fast corner it cannot expire before 240 real minutes, but
     * the exact same authenticated frame is accepted after that horizon and
     * immediately after a receiver reset. Pin this explicitly so launch
     * documentation cannot mistake wire-v3 CMAC for durable replay defense.
     * Current single-balloon flight is unaffected; a replay-robust fleet wire
     * needs authenticated origin time or durable per-source high-water state. */
    b2b_t replay_horizon = {};
    b2b_reset(&replay_horizon, 0x0003);
    b2b_add_airtime(&replay_horizon, 1000);
    assert(b2b_ingest(&replay_horizon, &frame, 1000) == B2B_FORWARD);
    assert(b2b_next_forward(&replay_horizon, &drained, 100));
    assert(b2b_ingest(&replay_horizon, &frame,
                      1000 + 15300u) == B2B_DUP);
    assert(b2b_ingest(&replay_horizon, &frame,
                      1000 + 15364u) == B2B_FORWARD);
    b2b_reset(&replay_horizon, 0x0003);
    assert(b2b_ingest(&replay_horizon, &frame, 1002) == B2B_FORWARD);

    /* All immutable origin/body/tag bits are bound. TTL alone remains mutable
     * so a legitimate store-and-forward hop can decrement it. */
    for (unsigned bit = 0; bit < 16; ++bit) {
        b2b_frame_t changed = frame;
        changed.src ^= (uint16_t)(1u << bit);
        assert(!b2b_auth_verify(auth_key, &changed));
    }
    for (unsigned bit = 0; bit < 8; ++bit) {
        b2b_frame_t changed = frame;
        changed.msg_id ^= (uint8_t)(1u << bit);
        assert(!b2b_auth_verify(auth_key, &changed));
    }
    for (unsigned byte = 0; byte < frame.len; ++byte) {
        for (unsigned bit = 0; bit < 8; ++bit) {
            b2b_frame_t changed = frame;
            changed.payload[byte] ^= (uint8_t)(1u << bit);
            assert(!b2b_auth_verify(auth_key, &changed));
        }
    }
    b2b_frame_t relayed = frame;
    relayed.ttl--;
    assert(b2b_auth_verify(auth_key, &relayed));
    uint8_t wrong_key[16];
    memcpy(wrong_key, auth_key, sizeof(wrong_key));
    wrong_key[0] ^= 1;
    assert(!b2b_auth_verify(wrong_key, &frame));
    assert(!b2b_auth_tag(nullptr, &frame, tag));
    assert(!b2b_auth_verify(nullptr, &frame));

    uint8_t wire[B2B_FRAME_MAX] = {};
    int len = b2b_encode(&frame, wire, sizeof(wire));
    assert(len == B2B_HDR_LEN + B2B_CRUMB_LEN + B2B_AUTH_TAG_LEN);
    assert(wire[0] == B2B_MAGIC_0 && wire[1] == B2B_MAGIC_1);
    assert(wire[2] == B2B_WIRE_VERSION);

    b2b_frame_t decoded = {};
    assert(b2b_parse(wire, len, &decoded));
    assert(decoded.src == 0x0002 && decoded.type == B2B_TYPE_CRUMB);
    assert(decoded.len == B2B_CRUMB_LEN + B2B_AUTH_TAG_LEN);
    assert(memcmp(decoded.payload, payload, B2B_CRUMB_LEN) == 0);
    assert(b2b_auth_verify(auth_key, &decoded));
    assert(b2b_is_namespaced(wire, len));

    wire[0] ^= 1;
    assert(!b2b_parse(wire, len, &decoded));
    wire[0] ^= 1;
    wire[2]++;
    /* Future/unknown StratoLink versions must remain reserved rather than
     * falling through into the ordinary Meshtastic relay path. */
    assert(b2b_is_namespaced(wire, len));
    assert(!b2b_parse(wire, len, &decoded));
    wire[2] = B2B_WIRE_VERSION;
    wire[2] = 2; /* unauthenticated-crumb wire version */
    assert(!b2b_parse(wire, len, &decoded));
    wire[2] = B2B_WIRE_VERSION;
    wire[7] |= 0x80;
    assert(!b2b_parse(wire, len, &decoded));
    wire[7] &= 0x03;
    wire[6] = B2B_TTL_DEFAULT + 1;
    assert(!b2b_parse(wire, len, &decoded));
    wire[6] = B2B_TTL_DEFAULT;
    wire[3] = 0xFF;
    wire[4] = 0xFF;
    assert(!b2b_parse(wire, len, &decoded));
    wire[3] = 0x00;
    wire[4] = 0x02;
    assert(!b2b_is_namespaced(nullptr, 0));
    const uint8_t ordinary_mesh[] = {0x01, 0x02};
    assert(!b2b_is_namespaced(ordinary_mesh, sizeof(ordinary_mesh)));

    /* Authenticated control frames carry an 8-byte transport tag. The local
     * command parser must receive only the original exact-length body. */
    b2b_frame_t command = {};
    command.type = B2B_TYPE_COMMAND;
    command.len = 4 + B2B_AUTH_TAG_LEN;
    assert(b2b_authenticated_body_len(&command) == 4);
    command.src = 0x1234;
    command.msg_id = 9;
    command.ttl = 2;
    command.payload[0] = 0;
    command.payload[1] = 2;
    command.payload[2] = 1;
    command.payload[3] = 7;
    assert(b2b_auth_tag(auth_key, &command, tag));
    memcpy(command.payload + 4, tag, sizeof(tag));
    b2b_frame_t queued_command = command;
    queued_command.queued_rtc_sec = 50;
    assert(b2b_refresh_authenticated_age(
        auth_key, &queued_command, 50000));
    assert(queued_command.queued_rtc_sec == 50000 &&
           memcmp(queued_command.payload, command.payload, command.len) == 0);
    assert(!b2b_refresh_authenticated_age(
        wrong_key, &queued_command, 50001));
    command.type = B2B_TYPE_ACK;
    command.len = 3 + B2B_AUTH_TAG_LEN;
    assert(b2b_authenticated_body_len(&command) == 3);
    command.type = B2B_TYPE_CRUMB;
    command.len = B2B_CRUMB_LEN + B2B_AUTH_TAG_LEN;
    assert(b2b_authenticated_body_len(&command) == B2B_CRUMB_LEN);

    /* Shape validation remains defense in depth behind wire-v3 authentication:
     * impossible coordinates die before relay/TTN queue use. */
    b2b_frame_t impossible = {};
    impossible.type = B2B_TYPE_CRUMB;
    impossible.len = B2B_CRUMB_LEN + B2B_AUTH_TAG_LEN;
    impossible.payload[0] = 0x23; /* 9001 centidegrees latitude */
    impossible.payload[1] = 0x29;
    impossible.payload[2] = 0;
    impossible.payload[3] = 0;
    impossible.ttl = B2B_TTL_DEFAULT;
    impossible.src = 7;
    b2b_t receiver = {};
    b2b_reset(&receiver, 2);
    assert(b2b_ingest(&receiver, &impossible, 0) == B2B_MALFORMED);

    /* Origin validation must inspect the caller's payload, not stale bytes in
     * the reusable output frame, and failures must not burn a message ID. */
    uint8_t impossible_payload[B2B_CRUMB_LEN + B2B_AUTH_TAG_LEN] = {
        0x23, 0x29, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
    };
    uint8_t msg_id_before = state.next_msg_id;
    assert(!b2b_make(&state, B2B_TYPE_CRUMB, impossible_payload,
                     sizeof(impossible_payload), &frame));
    assert(state.next_msg_id == msg_id_before);

    b2b_frame_t broadcast_source = frame;
    broadcast_source.src = B2B_ID_BROADCAST;
    assert(!b2b_auth_tag(auth_key, &broadcast_source, tag));
    assert(b2b_ingest(&receiver, &broadcast_source, 0) == B2B_MALFORMED);
    assert(b2b_encode(&broadcast_source, wire, sizeof(wire)) == 0);
    b2b_t invalid_origin = {};
    b2b_reset(&invalid_origin, B2B_ID_BROADCAST);
    assert(!b2b_make(&invalid_origin, B2B_TYPE_CRUMB, payload,
                     sizeof(payload), &broadcast_source));
    assert(invalid_origin.next_msg_id == 0);
    assert(!b2b_make(&state, B2B_TYPE_CRUMB, nullptr,
                     B2B_CRUMB_LEN, &frame));
    assert(state.next_msg_id == msg_id_before);

    /* The complete tunneled frame must fit US915 DR1's 53-byte application
     * ceiling. The maximum control payload succeeds exactly at that boundary;
     * one byte beyond the B2B contract fails without consuming an ID. */
    static_assert(B2B_FRAME_MAX == 53, "LoRaWAN DR1 envelope regressed");
    uint8_t max_payload[B2B_PAYLOAD_MAX] = {};
    assert(b2b_make(&state, B2B_TYPE_COMMAND, max_payload,
                    sizeof(max_payload), &frame));
    len = b2b_encode(&frame, wire, sizeof(wire));
    assert(len == B2B_FRAME_MAX);
    msg_id_before = state.next_msg_id;
    uint8_t oversized[B2B_PAYLOAD_MAX + 1] = {};
    assert(!b2b_make(&state, B2B_TYPE_COMMAND, oversized,
                     sizeof(oversized), &frame));
    assert(state.next_msg_id == msg_id_before);

    puts("B2B wire: namespace/version/round-trip/auth/age/origin/coordinate/DR1 and explicit volatile-replay-horizon cases passed");
    return 0;
}
