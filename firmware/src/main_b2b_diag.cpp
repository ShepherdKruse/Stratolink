/**
 * B2B store-and-forward bench diagnostic and self-test.
 *
 * Exercises the b2b module logic with synthesized neighbour frames: dedup and
 * its aging, hop-count convention, local and broadcast addressing, the
 * blocked-then-retry path, the drain-time airtime governor, refund, and the
 * strict wire parse.  Pure logic, no radio needed, so it validates the
 * store-and-forward core before it is wired onto the shared SX1262.
 *
 * The case list mirrors the adversarial-review findings on the first cut of
 * this module, so a regression on any of them fails loudly here.
 *
 * Build/flash:  pio run -e b2b_diag -t upload
 * Watch:        serial at 115200; prints PASS/FAIL per case and a summary.
 */
#include <Arduino.h>
#include "b2b.h"

static int g_pass = 0, g_fail = 0;

static void check(const char* name, bool ok) {
    Serial.print(ok ? "[PASS] " : "[FAIL] ");
    Serial.println(name);
    if (ok) g_pass++; else g_fail++;
}

/* Build a neighbour crumb frame directly (not via b2b_make, which would stamp
 * OUR src) so each case controls src/msg_id/ttl. */
static b2b_frame_t crumb_frame(uint16_t src, uint8_t msg_id, uint8_t ttl) {
    b2b_frame_t f;
    f.src = src; f.msg_id = msg_id; f.ttl = ttl;
    f.type = B2B_TYPE_CRUMB;
    b2b_crumb_t c = { .lat_cd = 3745, .lon_cd = -12242, .alt_hm = 180, .age_min = 3 };
    uint8_t packed[6];
    b2b_crumb_pack(&c, packed);
    memcpy(f.payload, packed, 6); f.len = 6;
    return f;
}

static b2b_frame_t command_frame(uint16_t src, uint8_t msg_id, uint16_t target) {
    b2b_frame_t f;
    f.src = src; f.msg_id = msg_id; f.ttl = 3;
    f.type = B2B_TYPE_COMMAND; f.len = 4;
    f.payload[0] = (uint8_t)(target >> 8); f.payload[1] = (uint8_t)(target & 0xFF);
    f.payload[2] = 0x01; f.payload[3] = 0x00;   /* opcode set-cadence, seq 0 */
    return f;
}

static void run_tests() {
    g_pass = g_fail = 0;
    const uint16_t SELF = 0x0002;      /* Stratolink-2 */
    const uint32_t TOA  = 100;         /* pretend a forward costs 100 ms */
    uint16_t now = 1000;               /* coarse clock, minutes */
    b2b_frame_t out;

    b2b_t b; b2b_reset(&b, SELF); b2b_add_airtime(&b, 1000);

    /* 1. crumb pack/unpack round-trip */
    b2b_crumb_t c0 = { .lat_cd = -8999, .lon_cd = 17999, .alt_hm = 255, .age_min = 42 };
    uint8_t cp[6]; b2b_crumb_pack(&c0, cp);
    b2b_crumb_t c1; b2b_crumb_unpack(cp, &c1);
    check("crumb round-trip",
          c1.lat_cd == c0.lat_cd && c1.lon_cd == c0.lon_cd &&
          c1.alt_hm == c0.alt_hm && c1.age_min == c0.age_min);

    /* 2. frame encode/parse round-trip */
    b2b_frame_t f = crumb_frame(0x0007, 11, 3);
    uint8_t wire[B2B_FRAME_MAX];
    int n = b2b_encode(&f, wire, sizeof(wire));
    b2b_frame_t g;
    check("frame encode/parse",
          n == B2B_HDR_LEN + 6 && b2b_parse(wire, n, &g) &&
          g.src == f.src && g.msg_id == f.msg_id && g.ttl == f.ttl &&
          g.type == f.type && g.len == f.len);

    /* 3. strict parse: trailing bytes and reserved flag bits are rejected */
    check("parse rejects trailing bytes", !b2b_parse(wire, n + 2, &g));
    wire[4] |= 0x40;
    check("parse rejects reserved bits", !b2b_parse(wire, n, &g));
    wire[4] &= 0x03;

    /* 4. fresh frame forwards, ttl decremented */
    b2b_result_t r = b2b_ingest(&b, &f, now);
    bool got = b2b_next_forward(&b, &out, TOA);
    check("fresh -> FORWARD, ttl--",
          r == B2B_FORWARD && got && out.ttl == 2 && out.src == 0x0007);

    /* 5. same frame again -> DUP */
    check("replay -> DUP", b2b_ingest(&b, &f, now) == B2B_DUP);

    /* 6. hop convention: ttl==1 forwards once more as ttl==0 */
    b2b_frame_t e1 = crumb_frame(0x0009, 5, 1);
    r = b2b_ingest(&b, &e1, now);
    got = b2b_next_forward(&b, &out, TOA);
    check("ttl==1 -> FORWARD as ttl 0", r == B2B_FORWARD && got && out.ttl == 0);

    /* 7. ttl==0 on arrival -> EXPIRED, consumed, not queued */
    b2b_frame_t e0 = crumb_frame(0x0009, 6, 0);
    check("ttl==0 -> EXPIRED",
          b2b_ingest(&b, &e0, now) == B2B_EXPIRED &&
          !b2b_next_forward(&b, &out, TOA));

    /* 8. unicast command for us -> LOCAL, not forwarded */
    b2b_frame_t cmd = command_frame(0x0007, 20, SELF);
    check("command for self -> LOCAL",
          b2b_ingest(&b, &cmd, now) == B2B_LOCAL &&
          !b2b_next_forward(&b, &out, TOA));

    /* 9. unicast command for another balloon -> FORWARD */
    b2b_frame_t cmd2 = command_frame(0x0007, 21, 0x0005);
    r = b2b_ingest(&b, &cmd2, now);
    got = b2b_next_forward(&b, &out, TOA);
    check("command for other -> FORWARD", r == B2B_FORWARD && got);

    /* 10. BROADCAST command -> delivered locally AND queued for the mesh */
    b2b_frame_t bc = command_frame(0x0007, 22, B2B_ID_BROADCAST);
    r = b2b_ingest(&b, &bc, now);
    got = b2b_next_forward(&b, &out, TOA);
    check("broadcast -> LOCAL_FORWARD + queued",
          r == B2B_LOCAL_FORWARD && got && out.ttl == 2);

    /* 11. own frame heard back -> OWN (healthy), not malformed */
    b2b_frame_t mine = crumb_frame(SELF, 1, 3);
    uint32_t mal_before = b.stats.malformed;
    check("own echo -> OWN, malformed untouched",
          b2b_ingest(&b, &mine, now) == B2B_OWN &&
          b.stats.malformed == mal_before && b.stats.own_echo == 1);

    /* 12. malformed shapes die at first hearing: short command, bad ack, type 3 */
    b2b_frame_t shortcmd = command_frame(0x0007, 23, 0x0005); shortcmd.len = 1;
    b2b_frame_t badack = command_frame(0x0007, 24, 0x0005);
    badack.type = B2B_TYPE_ACK;                   /* len 4, ACK wants exactly 3 */
    check("short COMMAND / bad ACK -> MALFORMED",
          b2b_ingest(&b, &shortcmd, now) == B2B_MALFORMED &&
          b2b_ingest(&b, &badack, now) == B2B_MALFORMED);

    /* 13. queue-full -> BLOCKED, NOT marked seen; retry after drain FORWARDS */
    b2b_t b2; b2b_reset(&b2, SELF); b2b_add_airtime(&b2, 60000);
    for (uint8_t i = 0; i < B2B_FWD_N; i++) {
        b2b_frame_t fill = crumb_frame(0x0030, i, 3);
        b2b_ingest(&b2, &fill, now);
    }
    b2b_frame_t ninth = crumb_frame(0x0031, 1, 3);
    r = b2b_ingest(&b2, &ninth, now);
    while (b2b_next_forward(&b2, &out, TOA)) {}   /* drain */
    b2b_result_t retry = b2b_ingest(&b2, &ninth, now);
    check("queue-full -> BLOCKED then retry -> FORWARD",
          r == B2B_BLOCKED && b2.stats.queue_full == 1 && retry == B2B_FORWARD);

    /* 14. airtime governor at drain time: no credit -> frame STAYS queued */
    b2b_t b3; b2b_reset(&b3, SELF);               /* zero credit */
    b2b_frame_t a1 = crumb_frame(0x0010, 1, 3);
    r = b2b_ingest(&b3, &a1, now);
    bool blocked = !b2b_next_forward(&b3, &out, TOA);
    b2b_add_airtime(&b3, 1000);
    got = b2b_next_forward(&b3, &out, TOA);
    check("no credit: queued frame waits, then forwards",
          r == B2B_FORWARD && blocked && b3.stats.airtime_block == 1 && got);

    /* 15. credit is capped: a quiet leg cannot bank a TX burst */
    b2b_t b4; b2b_reset(&b4, SELF);
    for (int i = 0; i < 1000; i++) b2b_add_airtime(&b4, 60);
    check("credit capped", b4.airtime_budget_ms == B2B_AIRTIME_CAP_MS);

    /* 16. refund after failed TX: charge undone, frame re-queued */
    b2b_t b5; b2b_reset(&b5, SELF); b2b_add_airtime(&b5, 500);
    b2b_frame_t rf = crumb_frame(0x0011, 1, 3);
    b2b_ingest(&b5, &rf, now);
    b2b_next_forward(&b5, &out, TOA);
    uint32_t budget_mid = b5.airtime_budget_ms;
    b2b_refund(&b5, &out, TOA);
    check("refund restores budget + queue",
          budget_mid == 400 && b5.airtime_budget_ms == 500 &&
          b5.fwd_count == 1 && b5.stats.fwd == 0);

    /* 17. seen aging: after B2B_SEEN_TTL_MIN a wrapped msg_id is fresh again */
    b2b_t b6; b2b_reset(&b6, SELF); b2b_add_airtime(&b6, 60000);
    b2b_frame_t w = crumb_frame(0x0012, 77, 3);
    b2b_ingest(&b6, &w, now);
    b2b_result_t dup_soon = b2b_ingest(&b6, &w, now + 10);
    b2b_result_t fresh_later = b2b_ingest(&b6, &w, (uint16_t)(now + B2B_SEEN_TTL_MIN + 1));
    check("seen ages out (msg_id wrap safe)",
          dup_soon == B2B_DUP && fresh_later == B2B_FORWARD);

    Serial.print("=== b2b self-test: ");
    Serial.print(g_pass); Serial.print(" passed, ");
    Serial.print(g_fail); Serial.println(" failed ===");
}

void setup() {
    Serial.begin(115200);
    delay(200);
    Serial.println("[b2b_diag] start");
    run_tests();
}

void loop() {
    delay(10000);
    run_tests();     /* repeat so a late serial attach still catches the report */
}
