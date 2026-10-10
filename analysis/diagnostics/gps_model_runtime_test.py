#!/usr/bin/env python3
"""Exercise strict read-first acquisition model proof with ideal packet replies.

This tests application control flow, not SparkFun's parser, actual UART timing,
the radio, or the physical energy envelope. The transport double uses the pinned
library's enum spelling. The legacy public setter/getter doubles remain for
gps_model_deadline_test.py, which tests that separate compatibility API.
"""

import argparse

import gps_time_domain_integration_test as harness


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError("review changed acquisition fixture before extending it")
    return source.replace(old, new, 1)


harness.ARDUINO = replace_once(
    harness.ARDUINO,
    "inline void digitalWrite(int, int) {}",
    "inline unsigned receiver_resets = 0;\n"
    "inline bool receiver_reset_low = false;\n"
    "inline void digitalWrite(int, int level) {\n"
    "    if (level == 0 && !receiver_reset_low) ++receiver_resets;\n"
    "    receiver_reset_low = level == 0;\n"
    "}",
)
harness.ARDUINO = replace_once(harness.ARDUINO,
    "inline void pinMode(int, int) {}",
    "inline void pinMode(int, int mode) { if (mode == 0) receiver_reset_low = false; }")
harness.GNSS = replace_once(
    harness.GNSS,
    "CACHED_FIX, VALIDITY_LOSS, DATE_INVALID, TIME_INVALID",
    "CACHED_FIX, VALIDITY_LOSS, DATE_INVALID, TIME_INVALID, RESET_EPOCH",
)
harness.GNSS = replace_once(
    harness.GNSS,
    "if (scenario == COLD_LATE_WEEK) {",
    "if (scenario == RESET_EPOCH)\n"
    "            return 400000000u + (fake_millis / 1000u) * 1000u;\n"
    "        if (scenario == COLD_LATE_WEEK) {",
)
harness.GNSS = replace_once(
    harness.GNSS,
    "enum dynModel { DYN_MODEL_AIRBORNE_4G = 8 };",
    "enum dynModel { DYN_MODEL_AIRBORNE4g = 8 };",
)
harness.GNSS = replace_once(
    harness.GNSS,
    "inline uint32_t position_reads = 0;",
    "inline uint32_t position_reads = 0;\n"
    "enum ModelScenario { GOOD, RETRY_SUCCEEDS, SET_NEVER_ACKS, WRONG_READBACK,\n"
    "                     RESET_RECOVERS, RAIL_SAGS, INLINE_RESET_MODEL_FAIL,\n"
    "                     REINIT_FAIL, POST_RESET_RAIL_SAG };\n"
    "inline ModelScenario model_scenario = GOOD;\n"
    "inline unsigned model_sets = 0, model_reads = 0, begin_calls = 0;\n"
    "inline unsigned pvt_polls = 0, pvt_after_reset = 0;\n"
    "inline bool wrong_model_or_layer = false;",
)
harness.GNSS = replace_once(
    harness.GNSS,
    "bool begin(Stream& selected, uint16_t) { stream = &selected; return true; }\n"
    "    bool sendCommand(ubxPacket* packet, uint16_t wait) { return sendConfig(stream, packet, wait); }\n"
    "    bool setDynamicModel(dynModel, uint8_t, uint16_t) { return true; }\n"
    "    uint8_t getDynamicModel(uint8_t, uint16_t) { return 8; }",
    "bool begin(Stream& selected, uint16_t) {\n"
    "        stream = &selected; ++begin_calls; return model_scenario != REINIT_FAIL;\n"
    "    }\n"
    "    bool sendCommand(ubxPacket* packet, uint16_t wait) { return sendConfig(stream, packet, wait); }\n"
    "    bool setDynamicModel(dynModel model, uint8_t layer, uint16_t wait) {\n"
    "        ++model_sets;\n"
    "        if (model != DYN_MODEL_AIRBORNE4g || layer != VAL_LAYER_RAM_BBR)\n"
    "            wrong_model_or_layer = true;\n"
    "        const bool ok = model_scenario != SET_NEVER_ACKS &&\n"
    "            model_scenario != REINIT_FAIL &&\n"
    "            model_scenario != RAIL_SAGS &&\n"
    "            (model_scenario != RETRY_SUCCEEDS || model_sets >= 3u) &&\n"
    "            ((model_scenario != RESET_RECOVERS &&\n"
    "              model_scenario != POST_RESET_RAIL_SAG) || receiver_resets != 0u);\n"
    "        delay(ok ? 20u : wait);\n"
    "        return ok;\n"
    "    }\n"
    "    uint8_t getDynamicModel(uint8_t layer, uint16_t) {\n"
    "        ++model_reads;\n"
    "        if (layer != VAL_LAYER_RAM) wrong_model_or_layer = true;\n"
    "        delay(20u);\n"
    "        return model_scenario == WRONG_READBACK ||\n"
    "            (model_scenario == INLINE_RESET_MODEL_FAIL && receiver_resets)\n"
    "            ? 0u : 8u;\n"
    "    }",
)
harness.GNSS = replace_once(harness.GNSS,
    "bool sendCommand(ubxPacket* packet, uint16_t wait) { return sendConfig(stream, packet, wait); }",
    r"""bool config_reply = true;
    bool sendCommand(ubxPacket* packet, uint16_t wait) {
        bool sent = sendConfig(stream, packet, wait);
        config_reply = true;
        if (requested_key == UBLOX_CFG_UART1INPROT_UBX) {
            config_reply = model_scenario != REINIT_FAIL;
        } else if (requested_key == UBLOX_CFG_NAVSPG_DYNMODEL) {
            if (requested_id == UBX_CFG_VALGET) {
                ++model_reads;
                config_reply = model_scenario != RETRY_SUCCEEDS || model_reads >= 3u;
                model = (model_scenario == GOOD || model_scenario == RETRY_SUCCEEDS ||
                    (model_scenario == INLINE_RESET_MODEL_FAIL && !receiver_resets) ||
                    (model_scenario == RESET_RECOVERS && receiver_resets)) ? 8u : 0u;
            } else {
                ++model_sets;
                if (packet->payload[8] != 8u || packet->payload[1] != VAL_LAYER_RAM_BBR)
                    wrong_model_or_layer = true;
                config_reply = model_scenario == WRONG_READBACK ||
                    model_scenario == INLINE_RESET_MODEL_FAIL;
            }
        }
        return sent;
    }""")
harness.GNSS = replace_once(harness.GNSS,
    "if (cls == UBX_CLASS_CFG) return configResponse(cls, id);",
    "if (cls == UBX_CLASS_CFG) return config_reply && configResponse(cls, id);")
harness.GNSS = replace_once(
    harness.GNSS,
    "bool getPVT(uint16_t) {\n"
    "        packetUBXNAVPVT = &storage;",
    "bool getPVT(uint16_t) {\n"
    "        ++pvt_polls;\n"
    "        if (receiver_resets) ++pvt_after_reset;\n"
    "        packetUBXNAVPVT = &storage;",
)
harness.TEST = r"""
#include <cstdio>
#include "gps_ublox.cpp"

uint16_t power_adc_read_vSTOR_mv() {
    return (model_scenario == RAIL_SAGS && model_sets >= 1u) ||
           (model_scenario == POST_RESET_RAIL_SAG && receiver_resets != 0u)
        ? 3500u : 5000u;
}
void power_manager_kick_watchdog() {}
bool power_manager_freefall_pending() { return false; }

static int failures = 0;
static void check(const char* name, bool passed) {
    passed = passed && !wrong_model_or_layer;
    std::printf("[%s] %s: sets=%u reads=%u resets=%u pvt=%u after_reset=%u "
                "tick=%u begin_fail=%u terminal=%u\n",
        passed ? "PASS" : "FAIL", name, model_sets, model_reads,
        receiver_resets, pvt_polls, pvt_after_reset, fake_millis,
        s_gps_diag.begin_failures, s_gps_diag.dyn_model_terminal_failures);
    if (!passed) ++failures;
}
static void reset_case(ModelScenario selected, Scenario navigation = COLD_LATE_WEEK) {
    model_scenario = selected;
    scenario = navigation;
    fake_millis = position_reads = receiver_resets = 0;
    receiver_reset_low = false;
    model_sets = model_reads = begin_calls = pvt_polls = pvt_after_reset = 0;
    wrong_model_or_layer = false;
    gps_freshness_reset(&pvt_freshness);
    consecutive_no_fresh = 0;
    gps_quiescence_state = GPS_QUIESCENCE_UNCONTAINED;
    s_gps_diag.hardware_resets = 0;
    s_gps_diag.dyn_model_failures = 0;
    s_gps_diag.dyn_model_terminal_failures = 0;
    s_gps_diag.accepted_fixes = 0;
    s_gps_diag.no_fresh_cycles = 0;
    s_gps_diag.power_aborts = 0;
    s_gps_diag.begin_failures = 0;
    last_fix = {};
    gnss.stream = &gps_gnss_stream;
}
int main() {
    gps_fix_t fix{};
    reset_case(GOOD);
    check("verified model permits fresh acquisition without resetting GPS",
        gps_ublox_get_fix(&fix, 6000u) && fix.valid &&
        model_sets == 0u && model_reads == 1u && receiver_resets == 0u &&
        s_gps_diag.accepted_fixes == 1u);

    reset_case(RETRY_SUCCEEDS);
    check("two missing model replies then verified read preserve receiver state",
        gps_ublox_get_fix(&fix, 6000u) && fix.valid &&
        model_sets == 0u && model_reads == 3u && receiver_resets == 0u &&
        s_gps_diag.dyn_model_failures == 2u);

    // Removing the initial model gate must fail these no-PVT assertions.
    reset_case(SET_NEVER_ACKS);
    fix.valid = true;
    fix.satellites = 8;
    check("exhausted SET verification resets once then fails before PVT",
        !gps_ublox_get_fix(&fix, 6000u) && !fix.valid && fix.satellites == 0u &&
        model_sets == 2u && model_reads == 2u && begin_calls == 2u &&
        receiver_resets == 1u && pvt_polls == 0u && position_reads == 0u &&
        s_gps_diag.dyn_model_terminal_failures == 1u);

    reset_case(WRONG_READBACK);
    check("SET ACK without correct model readback never permits PVT",
        !gps_ublox_get_fix(&fix, 6000u) && !fix.valid &&
        model_sets == 6u && model_reads == 12u && receiver_resets == 1u &&
        pvt_polls == 0u && position_reads == 0u &&
        s_gps_diag.dyn_model_terminal_failures == 1u);

    reset_case(RESET_RECOVERS, RESET_EPOCH);
    pvt_freshness.anchored = true;
    pvt_freshness.itow_ms = 400010000u;
    check("reset recovery clears old anchor and proves new advancing epochs",
        gps_ublox_get_fix(&fix, 6000u) && fix.valid &&
        model_sets == 1u && model_reads == 2u && begin_calls == 2u &&
        receiver_resets == 1u && s_gps_diag.hardware_resets == 1u &&
        s_gps_diag.accepted_fixes == 1u && position_reads == 0u);

    reset_case(REINIT_FAIL);
    check("connection recovery shares the six-second acquisition deadline",
        !gps_ublox_get_fix(&fix, 6000u) && !fix.valid &&
        fake_millis == 6000u && receiver_resets == 1u && pvt_polls == 0u &&
        s_gps_diag.begin_failures == 0u &&
        s_gps_diag.dyn_model_terminal_failures == 0u);

    reset_case(REINIT_FAIL);
    // Ten seconds permits all three 1100 ms connection proofs after the
    // failed model gate and reset, so this isolates connection failure from
    // exhaustion of the acquisition-entry deadline.
    check("failed connection proof stops before post-reset model or PVT",
        !gps_ublox_get_fix(&fix, 10000u) && !fix.valid &&
        model_sets == 1u && model_reads == 1u && begin_calls == 2u &&
        receiver_resets == 1u && pvt_polls == 0u &&
        s_gps_diag.begin_failures == 1u &&
        s_gps_diag.dyn_model_terminal_failures == 1u);

    reset_case(POST_RESET_RAIL_SAG);
    check("low rail during reset suppresses connection and acquisition",
        !gps_ublox_get_fix(&fix, 6000u) && !fix.valid &&
        model_sets == 1u && model_reads == 1u && receiver_resets == 1u &&
        pvt_polls == 0u && s_gps_diag.power_aborts == 1u &&
        s_gps_diag.dyn_model_terminal_failures == 0u);

    // Deleting the post-attempt rail gate must cause an observable reset here.
    reset_case(RAIL_SAGS);
    check("low rail after failed model attempts suppresses reset and PVT",
        !gps_ublox_get_fix(&fix, 6000u) && !fix.valid &&
        model_sets == 1u && receiver_resets == 0u && begin_calls == 1u &&
        pvt_polls == 0u && s_gps_diag.power_aborts == 1u &&
        s_gps_diag.dyn_model_terminal_failures == 0u);

    reset_case(INLINE_RESET_MODEL_FAIL, SILENT);
    check("failed model proof after inline recovery stops further PVT polling",
        !gps_ublox_get_fix(&fix, 7500u) && !fix.valid &&
        model_sets == 3u && model_reads == 7u && receiver_resets == 1u &&
        pvt_polls != 0u && pvt_after_reset == 0u && position_reads == 0u &&
        s_gps_diag.dyn_model_terminal_failures == 1u);

    reset_case(RESET_RECOVERS, SILENT);
    check("model recovery and silent-PVT recovery cannot double-reset one cycle",
        !gps_ublox_get_fix(&fix, 7500u) && !fix.valid &&
        model_sets == 1u && receiver_resets == 1u && begin_calls == 2u &&
        s_gps_diag.hardware_resets == 1u && s_gps_diag.no_fresh_cycles == 1u);
    return failures ? 1 : 0;
}
"""


MUTATIONS = {
    "skip-initial-proof": (
        "if (!gps_startup_model(startup)) {",
        "if (false && !gps_startup_model(startup)) {"),
    "accept-wrong-model": (
        "if (model == GPS_DYNMODEL_AIRBORNE_4G) return true;",
        "if (model <= GPS_DYNMODEL_AIRBORNE_4G) return true;"),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mutation", choices=MUTATIONS)
    args = parser.parse_args()
    if args.mutation:
        source = (harness.ROOT / "firmware/src/gps_ublox.cpp").read_text()
        source = replace_once(source, *MUTATIONS[args.mutation])
        harness.TEST = replace_once(harness.TEST, '#include "gps_ublox.cpp"', source)
    harness.main()


if __name__ == "__main__":
    main()
