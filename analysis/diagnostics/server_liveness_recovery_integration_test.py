#!/usr/bin/env python3
"""Source-level launch regression for bounded LoRaWAN server recovery."""

from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
MAIN_PATH = ROOT / "firmware/src/main.cpp"
LORAWAN_PATH = ROOT / "firmware/src/lorawan.cpp"
FRAME_PATH = ROOT / "firmware/src/lorawan_frame.cpp"
POWER_PATH = ROOT / "firmware/src/power_manager.cpp"
META_PATH = ROOT / "firmware/include/lorawan_session_meta.h"
LIVENESS_PATH = ROOT / "firmware/src/lorawan_liveness.cpp"
DECODER_PATH = ROOT / "analysis/diagnostics/decode_flight_state.py"
SOAK_PATH = ROOT / "analysis/diagnostics/ttn_soak_monitor.py"


def compact(source: str) -> str:
    return re.sub(r"\s+", " ", source)


def function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[opening + 1:index]
    raise AssertionError(f"unterminated function: {signature}")


def main() -> None:
    main_source = MAIN_PATH.read_text(encoding="utf-8")
    lorawan = LORAWAN_PATH.read_text(encoding="utf-8")
    frame = compact(FRAME_PATH.read_text(encoding="utf-8"))
    power = compact(POWER_PATH.read_text(encoding="utf-8"))
    meta = compact(META_PATH.read_text(encoding="utf-8"))
    liveness = compact(LIVENESS_PATH.read_text(encoding="utf-8"))
    decoder = compact(DECODER_PATH.read_text(encoding="utf-8"))
    soak = compact(SOAK_PATH.read_text(encoding="utf-8"))
    main_compact = compact(main_source)
    lorawan_compact = compact(lorawan)

    # ConfirmedDataUp must be a real MType change, never an application flag
    # inside an otherwise-unconfirmed frame. Downlink ACK is exposed only from
    # the already DevAddr/counter/MIC-authenticated decoder success path.
    assert "return confirmed ? 0x80u : 0x40u;" in frame
    assert "pkt[idx++] = lorawan_frame_uplink_mhdr(confirmed);" in lorawan_compact
    decode_body = compact(function_body(
        FRAME_PATH.read_text(encoding="utf-8"),
        "bool lorawan_frame_decode_downlink",
    ))
    mic_gate = decode_body.index("lorawan_crypto_mic")
    ack_publish = decode_body.index("out->ack =")
    success = decode_body.rindex("return true;")
    assert mic_gate < ack_publish < success
    assert "memset(out, 0, sizeof(*out));" in decode_body[ack_publish:success]

    # Pending intent is packed into the same CRC-protected session before
    # FCnt reservation and RF. Every reserved high bit and impossible state is
    # rejected; reset-interrupted pending intent is normalized as ambiguity.
    assert "LORAWAN_SESSION_LIVENESS_MARKER" in meta
    assert "LORAWAN_SESSION_SERVER_PROVEN 0x00002000u" in meta
    assert "LORAWAN_SESSION_INITIAL_PROBE_TRIED 0x00004000u" in meta
    assert "LORAWAN_SESSION_META_ALLOWED_MASK 0x00007FFFu" in meta
    assert "(encoded & ~LORAWAN_SESSION_META_ALLOWED_MASK) != 0u" in meta
    assert "liveness->server_proven ? LORAWAN_SESSION_SERVER_PROVEN" in meta
    assert "liveness->initial_probe_attempted ? LORAWAN_SESSION_INITIAL_PROBE_TRIED" in meta
    assert "SESSION_SERVER_PROVEN = 0x00002000" in decoder
    assert "SESSION_INITIAL_PROBE_TRIED = 0x00004000" in decoder
    assert "SESSION_META_ALLOWED_MASK = 0x00007FFF" in decoder
    confirmed_body = compact(function_body(
        lorawan,
        "bool lorawan_send_confirmed_uplink",
    ))
    assert confirmed_body.index("lorawan_liveness_arm_probe") < confirmed_body.index(
        "send_uplink_port_mode"
    )
    send_body = compact(function_body(lorawan, "static bool send_uplink_port_mode"))
    assert send_body.index("fCntUp++;") < send_body.index(
        "lorawan_export_session"
    ) < send_body.index("power_manager_save_session") < send_body.index(
        "radio->transmit"
    )
    assert send_body.index("power_manager_save_session") < send_body.index(
        "*counter_reserved = true"
    ) < send_body.index("radio->transmit")
    assert "fail_session_persistence();" in send_body
    assert "fCntUp--" not in send_body
    reservation_failure = send_body[
        send_body.index("if (!power_manager_save_session"):
        send_body.index("*counter_reserved = true")
    ]
    assert "fail_session_persistence();" in reservation_failure
    assert "return false;" in reservation_failure
    assert "if (!counter_reserved)" in confirmed_body
    assert confirmed_body.index("if (!counter_reserved)") < confirmed_body.index(
        "lorawan_server_abandon_probe"
    )
    assert "if (_joined) s_liveness_state = state_before_arm;" in confirmed_body
    persistence_failure = compact(function_body(
        lorawan, "static void fail_session_persistence"
    ))
    assert "lorawan_invalidate_session();" in persistence_failure
    invalid_retirement = compact(function_body(
        lorawan, "static void retire_invalid_liveness_session"
    ))
    assert "power_manager_clear_session();" in invalid_retirement
    assert "fail_session_persistence();" in invalid_retirement
    assert "lorawan_liveness_state_valid(&s_liveness_state)" in send_body
    assert "retire_invalid_liveness_session();" in send_body
    assert confirmed_body.index("if (_joined) s_liveness_state = state_before_arm;") < \
        confirmed_body.index("lorawan_server_abandon_probe")
    assert "power_manager_save_session" not in main_compact
    assert "lorawan_persist_session();" in main_compact
    arm_probe = compact(function_body(
        LIVENESS_PATH.read_text(encoding="utf-8"),
        "bool lorawan_liveness_arm_probe",
    ))
    assert arm_probe.index("state->probe_pending = true;") < arm_probe.index(
        "state->initial_probe_attempted = true;"
    )
    import_body = compact(function_body(lorawan, "bool lorawan_import_session"))
    assert import_body.index("lorawan_liveness_begin_session") < import_body.index(
        "lorawan_session_meta_decode"
    ) < import_body.index(
        "lorawan_liveness_normalize_after_import"
    ) < import_body.index("s_liveness_state = meta.liveness") < import_body.index(
        "_joined = true"
    )

    # JoinAccept begins an unproven data session. Both a new session and a
    # pre-patch imported record are due immediately, but attempted/pending
    # metadata prevents repeated resets from amplifying ConfirmedDataUp.
    otaa = compact(function_body(lorawan, "static bool otaa_join"))
    assert "lorawan_liveness_begin_session(&s_liveness_state);" in otaa
    assert "lorawan_liveness_mark_server_proven" not in otaa
    normalize = compact(function_body(
        LIVENESS_PATH.read_text(encoding="utf-8"),
        "bool lorawan_liveness_normalize_after_import",
    ))
    assert "!state->server_proven && !state->initial_probe_attempted" in normalize
    assert "state->countdown =" in normalize and ": 0u;" in normalize
    assert "if (state->probe_pending)" in normalize
    session_proven = compact(function_body(
        lorawan, "bool lorawan_server_session_proven"
    ))
    assert "_joined" in session_proven
    assert "lorawan_liveness_state_valid" in session_proven
    assert "s_liveness_state.server_proven" in session_proven

    # Only an authenticated data-down/ACK reaches the proof transition. The
    # state and advanced FCntDown are staged into one save before application
    # publication; a failed save invalidates the complete RAM session and
    # returns an explicit persistence fault.
    receive = compact(function_body(
        lorawan, "lorawan_class_a_result_t lorawan_receive_downlink_result"
    ))
    proof_decode = receive.index("authenticated = lorawan_frame_decode_downlink")
    proof_stage = receive.index("lorawan_liveness_state_t proven_state")
    counter_advance = receive.index("fCntDown = decoded.frame_counter + 1u;")
    publish_state = receive.index("s_liveness_state = proven_state;")
    persist = receive.index("power_manager_save_session(&reserved)")
    app_publish = receive.index("out->fport = decoded.fport;")
    assert proof_decode < proof_stage < counter_advance < publish_state < persist < app_publish
    save_failure = receive[receive.index("if (!power_manager_save_session"):app_publish]
    assert "fail_session_persistence();" in save_failure
    assert "LORAWAN_CLASS_A_PERSISTENCE_FAULT" in save_failure
    invalid_proof = receive[
        receive.index("if (lorawan_liveness_complete_probe"):
        counter_advance
    ]
    assert "retire_invalid_liveness_session();" in invalid_proof
    assert "LORAWAN_CLASS_A_PERSISTENCE_FAULT" in invalid_proof
    complete_probe = compact(function_body(
        lorawan, "lorawan_liveness_event_t lorawan_server_complete_probe"
    ))
    assert complete_probe.index("lorawan_liveness_state_valid") < \
        complete_probe.index("result->authenticated_downlink")
    invalid_complete = complete_probe[
        complete_probe.index("if (!lorawan_liveness_state_valid"):
        complete_probe.index("result->authenticated_downlink")
    ]
    assert "retire_invalid_liveness_session();" in invalid_complete
    assert "durable" not in invalid_complete[
        invalid_complete.index("retire_invalid_liveness_session();"):]
    assert complete_probe.index("result->authenticated_downlink") < complete_probe.index(
        "lorawan_liveness_complete_probe"
    )
    assert "LORAWAN_LIVENESS_NO_CHANGE" in complete_probe[
        complete_probe.index("result->authenticated_downlink"):
        complete_probe.index("lorawan_liveness_complete_probe")
    ]

    # A miss requires this cycle's fresh PVT/GNSS authority, normal primary,
    # no freefall, legal region, real Class-A rail, local TX success, and the
    # aggregate result that only exists after both healthy windows complete.
    assert "liveness_qualification.fresh_advancing_pvt = fresh_fix_this_cycle;" in main_compact
    assert "liveness_qualification.gnss_region_authority = region_authority_is_gnss();" in main_compact
    assert "liveness_qualification.normal_primary = !burst_mode;" in main_compact
    assert "liveness_qualification.freefall_clear = !power_manager_freefall_pending();" in main_compact
    assert "liveness_qualification.rx_power_qualified = power_adc_get_tier() <= POWER_TIER_REDUCED;" in main_compact
    assert "liveness_qualification.region_tx_legal = region_tx_allowed_now(cycle_started_ms);" in main_compact
    probe_callback = compact(function_body(
        main_source, "static bool complete_server_probe_before_rx_return"
    ))
    assert "qualification->gnss_region_authority = region_authority_is_gnss();" in probe_callback
    assert "qualification->freefall_clear = !power_manager_freefall_pending();" in probe_callback
    assert "qualification->rx_power_qualified = power_adc_get_tier() <= POWER_TIER_REDUCED;" in probe_callback
    assert "qualification->region_tx_legal = region_tx_allowed_now(context->cycle_started_ms);" in probe_callback
    assert "lorawan_server_complete_probe( qualification, result, &durable)" in probe_callback
    empty_result = receive.index("lorawan_liveness_probe_result_t empty")
    empty_callback = receive.index("probe_completion(&empty, probe_context)")
    empty_publish = receive.index("return LORAWAN_CLASS_A_COMPLETE_NO_EVIDENCE")
    assert empty_result < empty_callback < empty_publish
    empty_slice = receive[empty_result:empty_callback]
    for field in (
        "local_tx_succeeded", "rx1_completed", "rx2_completed",
        "rx_path_healthy",
    ):
        assert f"empty.{field} = true;" in empty_slice
    assert "LORAWAN_CLASS_A_PERSISTENCE_FAULT" in receive[empty_callback:empty_publish]
    persist_body = compact(function_body(
        lorawan, "static bool persist_current_session"
    ))
    assert persist_body.index("lorawan_liveness_state_valid") < \
        persist_body.index("lorawan_export_session")
    assert "retire_invalid_liveness_session();" in persist_body
    assert "fail_session_persistence();" in persist_body
    assert probe_callback.index("lorawan_server_complete_probe") < \
        probe_callback.index("return durable")
    assert "complete_server_probe_before_rx_return" in main_compact
    fallback = main_compact[main_compact.index(
        "if (probe_event == LORAWAN_LIVENESS_NO_CHANGE"
    ):main_compact.index(
        "if (probe_event == LORAWAN_LIVENESS_RECOVERY_DUE"
    )]
    assert "rx_result == LORAWAN_CLASS_A_AMBIGUOUS" in fallback
    assert "LORAWAN_CLASS_A_PERSISTENCE_FAULT" not in fallback
    assert "GPS_ACQ_FLOOR_MV" not in compact(
        function_body(main_source, "void loop()")
    )[compact(function_body(main_source, "void loop()")).index(
        "lorawan_liveness_qualification_t liveness_qualification"
    ):compact(function_body(main_source, "void loop()")).index(
        "lorawan_server_complete_probe"
    )], "3.6 V GNSS acquisition floor must not replace the REDUCED Class-A gate"

    # Recovery is a durable state, not only the edge returned by the third
    # miss. Thus a reset after miss3 persistence, clear failure, or any point
    # before helper entry retries before join/send. Without a fresh cycle fix,
    # the normal cycle remains RF-quiet instead of using suspect keys.
    precheck = main_compact.index(
        "if (!burst_mode && lorawan_server_recovery_due())"
    )
    join_gate = main_compact.index(
        "if (!suppress_optional_after_recovery && !burst_mode && !lorawan_joined()"
    )
    primary_gate = main_compact.index(
        "if (!suppress_optional_after_recovery && power_adc_can_tx()"
    )
    assert precheck < join_gate < primary_gate
    precheck_slice = main_compact[precheck:join_gate]
    assert "suppress_optional_after_recovery = true;" in precheck_slice
    assert "fresh_fix_this_cycle && region_authority_is_gnss()" in precheck_slice
    assert "GPS_QUIESCENCE_CONFIRMED_SOFTWARE_STANDBY" in precheck_slice
    assert "GPS_QUIESCENCE_RESET_HELD" in precheck_slice
    assert "GPS_QUIESCENCE_UNCONTAINED" not in precheck_slice

    # The transition makes RAM unusable before touching TAMP, clears only the
    # session marker (not BKP18 authority), and republishes the exact same GNSS
    # region with age including all current-cycle work. Any failed durability
    # step revokes both RAM authority roots and stays quiet.
    recovery = compact(function_body(main_source, "static bool recover_stale_server_session"))
    assert recovery.index("fresh_fix_this_cycle") < recovery.index(
        "region_authority_is_gnss()"
    ) < recovery.index("region_authority_region == lorawan_current_region()")
    assert "(millis() - cycle_started_ms + 999u) / 1000u" in recovery
    assert "region_fix_age_advance( region_fix_age_sec, active_sec)" in recovery
    assert recovery.index("lorawan_invalidate_session();") < recovery.index(
        "power_manager_clear_lorawan_session();"
    ) < recovery.index("power_manager_save_region_authority(")
    assert "live_age, region_authority_region, TAMP_REGION_AUTHORITY_GNSS" in recovery
    failure = recovery[recovery.index("if (!authority_republished)"):]
    assert "region_known = false;" in failure
    assert "region_lease_trusted = false;" in failure
    assert "region_authority_region = LORA_REGION_SILENT;" in failure
    assert "power_manager_clear_session();" in failure
    assert "lorawan_server_liveness_note_recovery(false);" in failure
    session_clear = compact(function_body(
        POWER_PATH.read_text(encoding="utf-8"),
        "bool power_manager_clear_lorawan_session",
    ))
    assert "invalidate_session_marker()" in session_clear
    assert "invalidate_session_and_lease_markers" not in session_clear

    # The edge path suppresses first, invalidates inside the helper, and only
    # then reaches the optional-uplink block. Every later RF-capable service
    # path is independently fenced for reset/maintenance robustness.
    third_miss = main_compact.index(
        "if (probe_event == LORAWAN_LIVENESS_RECOVERY_DUE"
    )
    optional_uplink = main_compact.index(
        "if (suppress_optional_after_recovery)", third_miss
    )
    assert third_miss < optional_uplink
    edge_slice = main_compact[third_miss:optional_uplink]
    assert edge_slice.index("suppress_optional_after_recovery = true;") < edge_slice.index(
        "recover_stale_server_session("
    )
    assert main_compact.count("!suppress_optional_after_recovery") >= 4
    optional_slice = main_compact[optional_uplink:]
    assert optional_slice.index("!lorawan_server_session_proven()") < optional_slice.index(
        "!region_authority_is_gnss()"
    )
    ctt_gate = main_compact.index(
        "if (primary_transaction_ok && !suppress_optional_after_recovery && lorawan_server_session_proven() && region_authority_is_gnss()",
        optional_uplink,
    )
    relay_gate = main_compact.index(
        "if (primary_transaction_ok && !suppress_optional_after_recovery && lorawan_server_session_proven() && relay_window_budget > 0u",
        ctt_gate,
    )
    assert optional_uplink < ctt_gate < relay_gate
    assert main_compact.count("lorawan_server_session_proven()") >= 3
    primary_ok_declaration = main_compact.index(
        "bool primary_transaction_ok = false;"
    )
    primary_ok_publish = main_compact.index("primary_transaction_ok = true;")
    assert primary_ok_declaration < primary_gate < primary_ok_publish
    assert primary_ok_publish < optional_uplink

    # The next primary exposes bounded proof/miss/recovery evidence. Packing
    # happens before the present exchange, so the ACK/miss appears exactly on
    # the next packet and can be proven by the TTN-only soak.
    state_read = main_compact.index("lorawan_server_liveness_get_state")
    diag_read = main_compact.index("lorawan_server_liveness_get_diag")
    telemetry_pack = main_compact.index("telemetry_pack(&ti, tx_payload)")
    primary_send = main_compact.index("lorawan_send_confirmed_uplink")
    assert state_read < diag_read < telemetry_pack < primary_send
    assert "ti.server_proof_count_mod8" in main_compact[state_read:telemetry_pack]
    assert "ti.server_qualified_miss_streak" in main_compact[state_read:telemetry_pack]
    assert "ti.server_recovery_parity" in main_compact[state_read:telemetry_pack]
    assert '"confirmed": uplink.get("confirmed")' in soak
    assert '"session_key_id": uplink.get("session_key_id")' in soak
    assert soak.count('"correlation_ids": body.get("correlation_ids") or []') == 2

    print(
        "PASS: server liveness requires authenticated/fully-qualified proof, "
        "recovers across every reset boundary, and fences same-cycle RF"
    )


if __name__ == "__main__":
    main()
