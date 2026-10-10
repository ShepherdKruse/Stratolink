#!/usr/bin/env python3
"""Run the real GPS driver against ACK-delay and shared-deadline fixtures.

Extend the preserved physical-trace experiment without changing its RED source
binding. External transport/time/rails are simulated; SparkFun parsing, real
standby cadence and energy remain outside this host test.
"""

import gps_shutdown_ack_timing_experiment as harness


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError("review changed base fixture before extending it")
    return source.replace(old, new, 1)


harness.ARDUINO = replace_once(
    harness.ARDUINO,
    "NO_EOE, CONTINUED_TRAFFIC, LOW_RAIL_NO_ACK };",
    "NO_EOE, CONTINUED_TRAFFIC, LOW_RAIL_NO_ACK, SHARED_EXHAUSTED, "
    "FINAL_ACK_LATE, FINAL_ACK_EXACT, INTERMEDIATE_ACK_EXACT, "
    "INTERMEDIATE_ACK_LATE, WRAP_DELAYED };",
)
harness.ARDUINO = replace_once(
    harness.ARDUINO,
    "inline unsigned receiver_resets = 0;",
    "inline unsigned receiver_resets = 0;\n"
    "inline unsigned zero_wait_requests = 0;\n"
    "inline unsigned cfg_requests = 0;\n"
    "inline unsigned rate_meas_requests = 0;\n"
    "inline unsigned intermediate_successful_acks = 0;",
)
harness.ARDUINO = replace_once(
    harness.ARDUINO,
    "fake_millis < next_marker_ms",
    "static_cast<int32_t>(fake_millis - next_marker_ms) < 0",
)
harness.GNSS = replace_once(
    harness.GNSS,
    "if (layer != VAL_LAYER_RAM) return false;",
    "++cfg_requests;\n"
    "        if (key == UBLOX_CFG_RATE_MEAS) ++rate_meas_requests;\n"
    "        if (max_wait == 0) ++zero_wait_requests;\n"
    "        if (layer != VAL_LAYER_RAM) return false;",
)
harness.GNSS = replace_once(
    harness.GNSS,
    "uint32_t ack_latency = 20u;",
    "uint32_t ack_latency = shutdown_fixture == SHARED_EXHAUSTED ? 400u : 20u;\n"
    "        if (key == UBLOX_CFG_MSGOUT_UBX_NAV_EOE_UART1) {\n"
    "            // Serial writing occurs before the library starts its ACK timer.\n"
    "            if (shutdown_fixture == FINAL_ACK_EXACT) delay(1400u);\n"
    "            if (shutdown_fixture == FINAL_ACK_LATE) delay(1440u);\n"
    "        }\n"
    "        if (key == UBLOX_CFG_UART1OUTPROT_NMEA) {\n"
    "            // First ACK 20 ms + this ACK 20 ms + transport delay.\n"
    "            if (shutdown_fixture == INTERMEDIATE_ACK_EXACT) delay(1460u);\n"
    "            if (shutdown_fixture == INTERMEDIATE_ACK_LATE) delay(1500u);\n"
    "        }",
)
harness.GNSS = replace_once(
    harness.GNSS,
    "configured |= bit;",
    "configured |= bit;\n"
    "        if (key == UBLOX_CFG_UART1OUTPROT_NMEA &&\n"
    "            (shutdown_fixture == INTERMEDIATE_ACK_EXACT ||\n"
    "             shutdown_fixture == INTERMEDIATE_ACK_LATE))\n"
    "            ++intermediate_successful_acks;",
)
harness.GNSS = replace_once(
    harness.GNSS,
    "shutdown_fixture == DELAYED_ACK && receiver_resets == 0u",
    "(shutdown_fixture == DELAYED_ACK || shutdown_fixture == WRAP_DELAYED) && "
    "receiver_resets == 0u",
)
harness.TEST = replace_once(
    harness.TEST,
    "receiver_resets = configured = marker_offset = 0;",
    "receiver_resets = configured = marker_offset = zero_wait_requests = 0;\n"
    "    cfg_requests = rate_meas_requests = intermediate_successful_acks = 0;",
)
harness.TEST = replace_once(
    harness.TEST,
    "const auto result = gps_ublox_quiesce();",
    "if (selected == WRAP_DELAYED) fake_millis = UINT32_MAX - 200u;\n"
    "    const uint32_t shutdown_started = fake_millis;\n"
    "    const auto result = gps_ublox_quiesce();\n"
    "    const uint32_t shutdown_elapsed = fake_millis - shutdown_started;",
)
harness.TEST = replace_once(
    harness.TEST,
    "bool passed = result == expected &&",
    "// Mutant caught: remove the guard before RATE_MEAS and reuse the old wait.\n"
    "    // Three attempts may send UBX/NMEA only; all three NMEA ACKs succeed.\n"
    "    const bool intermediate_boundary = selected == INTERMEDIATE_ACK_EXACT ||\n"
    "                                       selected == INTERMEDIATE_ACK_LATE;\n"
    "    const bool stopped_after_intermediate = !intermediate_boundary ||\n"
    "        (cfg_requests == 6u && rate_meas_requests == 0u &&\n"
    "         intermediate_successful_acks == 3u);\n"
    "    bool passed = stopped_after_intermediate && result == expected &&",
)
harness.TEST = replace_once(
    harness.TEST,
    "bool passed = stopped_after_intermediate && result == expected &&",
    "bool passed = zero_wait_requests == 0 &&\n"
    "        (selected != NO_ACK || shutdown_elapsed <= 6600u) &&\n"
    "        stopped_after_intermediate && result == expected &&",
)
harness.TEST = replace_once(
    harness.TEST,
    "    if (!passed) ++failures;",
    "    if (intermediate_boundary) {\n"
    '        std::printf("  CFG requests=%u RATE_MEAS requests=%u "\n'
    '                    "successful intermediate ACKs=%u zero-wait requests=%u\\n",\n'
    "                    cfg_requests, rate_meas_requests,\n"
    "                    intermediate_successful_acks, zero_wait_requests);\n"
    "    }\n"
    "    if (!passed) ++failures;",
)
harness.TEST = replace_once(
    harness.TEST,
    '    std::printf("Shutdown ACK timing experiment: %d failing case(s)\\n", failures);',
    '    run_case("cumulative ACK delays exhaust one shared budget", SHARED_EXHAUSTED,\n'
    "             GPS_QUIESCENCE_RESET_HELD, 2, 3);\n"
    '    run_case("final ACK exactly at deadline cannot authorize standby", FINAL_ACK_EXACT,\n'
    "             GPS_QUIESCENCE_RESET_HELD, 2, 3);\n"
    '    run_case("final ACK after deadline cannot authorize standby", FINAL_ACK_LATE,\n'
    "             GPS_QUIESCENCE_RESET_HELD, 2, 3);\n"
    '    run_case("intermediate ACK exactly at deadline blocks the next CFG",\n'
    "             INTERMEDIATE_ACK_EXACT, GPS_QUIESCENCE_RESET_HELD, 2, 3);\n"
    '    run_case("intermediate ACK after deadline blocks the next CFG",\n'
    "             INTERMEDIATE_ACK_LATE, GPS_QUIESCENCE_RESET_HELD, 2, 3);\n"
    '    run_case("delayed ACK across millis rollover preserves state", WRAP_DELAYED,\n'
    "             GPS_QUIESCENCE_CONFIRMED_SOFTWARE_STANDBY, 0, 0);\n"
    '    std::printf("Shutdown ACK timing suite: %d failing case(s)\\n", failures);',
)


if __name__ == "__main__":
    raise SystemExit(harness.main())
