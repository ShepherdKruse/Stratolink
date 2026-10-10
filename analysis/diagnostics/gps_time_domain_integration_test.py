#!/usr/bin/env python3
"""Execute real GNSS acquisition against scripted NAV-PVT epochs.

Configuration hardware is idealized with packet-shaped VALGET/ACK responses;
production's strict response checks still execute. This does not exercise the
pinned parser or UART timing (gps_startup_supervision_test.py owns that proof).
"""

from pathlib import Path
import os
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]

ARDUINO = r"""
#pragma once
#include <cstddef>
#include <cstdint>
inline uint32_t fake_millis = 0;
inline uint32_t millis() { return fake_millis; }
inline void delay(uint32_t ms) { fake_millis += ms; }
inline void digitalWrite(int, int) {}
inline void pinMode(int, int) {}
constexpr int LOW = 0, INPUT = 0, OUTPUT = 1, PA_0 = 0;
class Stream {
public:
    virtual ~Stream() = default;
    virtual int available() { return 0; }
    virtual int availableForWrite() { return 63; }
    virtual int read() { return -1; }
    virtual int peek() { return -1; }
    virtual void flush() {}
    virtual size_t write(uint8_t) { return 1u; }
    virtual size_t write(const uint8_t* data, size_t size) {
        size_t accepted = 0u;
        while (accepted < size && write(data[accepted]) == 1u) ++accepted;
        return accepted;
    }
    size_t readBytes(uint8_t* data, size_t size) {
        size_t accepted = 0u;
        while (accepted < size) {
            int value = read();
            if (value < 0) break;
            data[accepted++] = (uint8_t)value;
        }
        return accepted;
    }
};
struct FakeSerial : Stream {
    void begin(uint32_t) {}
};
inline FakeSerial Serial1;
"""

GNSS = r"""
#pragma once
#include "Arduino.h"
enum dynModel { DYN_MODEL_AIRBORNE_4G = 8 };
constexpr uint8_t VAL_LAYER_RAM = 1, VAL_LAYER_RAM_BBR = 3;
constexpr uint32_t VAL_RXM_PMREQ_WAKEUPSOURCE_UARTRX = 8;
constexpr uint32_t UBLOX_CFG_UART1OUTPROT_UBX = 1;
constexpr uint32_t UBLOX_CFG_UART1OUTPROT_NMEA = 2;
constexpr uint32_t UBLOX_CFG_RATE_MEAS = 3, UBLOX_CFG_RATE_NAV = 4;
constexpr uint32_t UBLOX_CFG_MSGOUT_UBX_NAV_EOE_UART1 = 5;
constexpr uint8_t UBX_CLASS_NAV = 1, UBX_NAV_PVT = 7;
constexpr uint8_t UBX_CLASS_CFG = 6, UBX_CFG_VALGET = 0x8b, UBX_CFG_VALSET = 0x8a;
constexpr uint8_t UBX_CLASS_ACK = 5, UBX_ACK_ACK = 1, UBX_ACK_NACK = 0;
constexpr uint8_t SFE_UBLOX_SENTENCE_TYPE_NONE = 0, SFE_UBLOX_PACKET_PACKETBUF = 0;
constexpr size_t MAX_PAYLOAD_SIZE = 300u;
constexpr uint32_t UBX_CFG_SIZE_MASK = 0x0f00f000;
constexpr uint32_t UBLOX_CFG_NAVSPG_DYNMODEL = 0x20110021;
constexpr uint32_t UBLOX_CFG_UART1INPROT_UBX = 0x10730001;
enum sfe_ublox_packet_validity_e {
    SFE_UBLOX_PACKET_VALIDITY_NOT_DEFINED,
    SFE_UBLOX_PACKET_VALIDITY_VALID,
    SFE_UBLOX_PACKET_VALIDITY_NOT_VALID
};
struct ubxPacket {
    uint8_t cls = 0, id = 0;
    uint16_t len = 0, counter = 0, startingSpot = 0;
    uint8_t* payload = nullptr;
    uint8_t checksumA = 0, checksumB = 0;
    sfe_ublox_packet_validity_e valid = SFE_UBLOX_PACKET_VALIDITY_NOT_DEFINED;
    sfe_ublox_packet_validity_e classAndIDmatch = SFE_UBLOX_PACKET_VALIDITY_NOT_DEFINED;
};
// Ideal configuration receiver: preserve the requested key and return a fully
// shaped RAM-layer reply, with ACKs on their separate packet. The production
// caller checks these fields; no production check is replaced or bypassed.
struct IdealConfigPackets {
    // Storage only: parser synchronization is exercised by the separate real-
    // parser suite, not by this ideal packet-returning boundary.
    uint8_t currentSentence = SFE_UBLOX_SENTENCE_TYPE_NONE;
    uint8_t activePacketBuffer = SFE_UBLOX_PACKET_PACKETBUF;
    uint16_t ubxFrameCounter = 0u;
    uint8_t config_payload[MAX_PAYLOAD_SIZE] = {}, ack_payload[2] = {};
    ubxPacket packetCfg{}, packetAck{};
    bool config_pending = false;
    uint8_t requested_id = 0, model = 8;
    uint32_t requested_key = 0;
    IdealConfigPackets() {
        packetCfg.payload = config_payload;
        packetAck.payload = ack_payload;
    }
    bool setPacketCfgPayloadSize(size_t size) {
        if (size == 0u || size > sizeof(config_payload)) return false;
        packetCfg.payload = config_payload;
        return true;
    }
    bool sendConfig(Stream* stream, ubxPacket* packet, uint16_t wait) {
        if (!stream || wait != 0u || packet->cls != UBX_CLASS_CFG ||
            (packet->id != UBX_CFG_VALGET && packet->id != UBX_CFG_VALSET) ||
            packet->len != (packet->id == UBX_CFG_VALGET ? 8u : 9u)) return false;
        requested_id = packet->id;
        requested_key = 0u;
        for (unsigned i = 0; i < 4u; ++i)
            requested_key |= uint32_t(packet->payload[4u + i]) << (8u * i);
        if (requested_id == UBX_CFG_VALSET && requested_key == UBLOX_CFG_NAVSPG_DYNMODEL)
            model = packet->payload[8];
        uint8_t frame[17] = {0xb5, 0x62, UBX_CLASS_CFG, packet->id,
                             uint8_t(packet->len), 0};
        for (unsigned i = 0; i < packet->len; ++i) frame[6u + i] = packet->payload[i];
        uint8_t a = 0, b = 0;
        for (unsigned i = 2; i < 6u + packet->len; ++i) { a += frame[i]; b += a; }
        frame[6u + packet->len] = a;
        frame[7u + packet->len] = b;
        config_pending = stream->write(frame, packet->len + 8u) == packet->len + 8u;
        return config_pending;
    }
    bool configResponse(uint8_t cls, uint8_t id) {
        if (cls != UBX_CLASS_CFG || !config_pending || id != requested_id) return false;
        config_pending = false;
        if (id == UBX_CFG_VALGET) {
            packetCfg.cls = UBX_CLASS_CFG;
            packetCfg.id = UBX_CFG_VALGET;
            packetCfg.len = 9u;
            packetCfg.payload[0] = 1u;
            packetCfg.payload[1] = packetCfg.payload[2] = packetCfg.payload[3] = 0u;
            for (unsigned i = 0; i < 4u; ++i)
                packetCfg.payload[4u + i] = requested_key >> (8u * i);
            packetCfg.payload[8] = requested_key == UBLOX_CFG_NAVSPG_DYNMODEL
                ? model : requested_key == UBLOX_CFG_UART1INPROT_UBX ? 1u : 0u;
            packetCfg.valid = packetCfg.classAndIDmatch = SFE_UBLOX_PACKET_VALIDITY_VALID;
        } else {
            packetAck.cls = UBX_CLASS_ACK;
            packetAck.id = UBX_ACK_ACK;
            packetAck.len = 2u;
            packetAck.payload[0] = UBX_CLASS_CFG;
            packetAck.payload[1] = UBX_CFG_VALSET;
            packetAck.valid = packetAck.classAndIDmatch = SFE_UBLOX_PACKET_VALIDITY_VALID;
        }
        return true;
    }
};
union FakeValid { uint8_t all; struct { uint8_t validDate : 1; uint8_t validTime : 1; } bits; };
union FakeFlags { uint8_t all; struct { uint8_t gnssFixOK : 1; } bits; };
struct UBX_NAV_PVT_data_t {
    uint32_t iTOW;
    FakeValid valid;
    FakeFlags flags;
    uint8_t numSV;
    int32_t lon, lat, height, gSpeed, headMot;
};
union FakeQueried { uint32_t all; struct { uint32_t all : 1; } bits; };
struct FakePvtPacket {
    UBX_NAV_PVT_data_t data{};
    struct { FakeQueried moduleQueried1{}, moduleQueried2{}; } moduleQueried;
};
enum Scenario {
    COLD_LATE_WEEK, PROVISIONAL_ONLY, FROZEN_VALID, SILENT,
    CACHED_FIX, VALIDITY_LOSS, DATE_INVALID, TIME_INVALID
};
inline Scenario scenario = COLD_LATE_WEEK;
inline uint32_t position_reads = 0;
struct SFE_UBLOX_GNSS_SERIAL : IdealConfigPackets {
    Stream* stream = nullptr;
    FakePvtPacket storage{};
    FakePvtPacket* packetUBXNAVPVT = nullptr;
    bool begin(Stream& selected, uint16_t) { stream = &selected; return true; }
    bool sendCommand(ubxPacket* packet, uint16_t wait) { return sendConfig(stream, packet, wait); }
    bool setDynamicModel(dynModel, uint8_t, uint16_t) { return true; }
    uint8_t getDynamicModel(uint8_t, uint16_t) { return 8; }
    bool setVal8(uint32_t, uint8_t, uint8_t, uint16_t) { return true; }
    bool setVal16(uint32_t, uint16_t, uint8_t, uint16_t) { return true; }
    bool powerOffWithInterrupt(uint32_t, uint32_t, bool, uint16_t) {
        return true;
    }
    bool getPVT(uint16_t) {
        packetUBXNAVPVT = &storage;
        const uint8_t prefix[] = {0xb5, 0x62, 0x01, 0x07, 0x00, 0x00};
        const uint8_t suffix[] = {0x08, 0x19};
        (void)stream->write(prefix, sizeof(prefix));
        (void)stream->write(suffix, sizeof(suffix));
        return false;
    }
    uint32_t getTimeOfWeek() {
        if (scenario == COLD_LATE_WEEK) {
            return fake_millis < 3000u ? (fake_millis / 1000u) * 1000u :
                400000000u + ((fake_millis - 3000u) / 1000u) * 1000u;
        }
        if (scenario == VALIDITY_LOSS) {
            if (fake_millis < 1000u) return 400000000u;
            if (fake_millis < 2000u) return 0;
            return 120000u + ((fake_millis - 2000u) / 1000u) * 1000u;
        }
        return scenario == PROVISIONAL_ONLY ? 0u : 400000000u;
    }
    bool timeQualified() {
        if (scenario == COLD_LATE_WEEK) return fake_millis >= 3000u;
        if (scenario == VALIDITY_LOSS) {
            return fake_millis < 1000u || fake_millis >= 2000u;
        }
        return scenario != PROVISIONAL_ONLY;
    }
    bool getDateValid() { return timeQualified() && scenario != DATE_INVALID; }
    bool getTimeValid() { return timeQualified() && scenario != TIME_INVALID; }
    bool getTimeFullyResolved() { return false; }
    bool getGnssFixOk() {
        if (scenario == VALIDITY_LOSS) return fake_millis >= 2000u;
        return scenario != FROZEN_VALID && scenario != PROVISIONAL_ONLY;
    }
    uint8_t getSIV() { return 8; }
    int32_t getLatitude() { ++position_reads; return 370000000; }
    int32_t getLongitude() { ++position_reads; return -1220000000; }
    int32_t getAltitude() { ++position_reads; return 100000; }
    int32_t getGroundSpeed() { ++position_reads; return 1000; }
    int32_t getHeading() { ++position_reads; return 9000000; }
    bool checkUblox(uint8_t cls, uint8_t id) {
        if (cls == UBX_CLASS_CFG) return configResponse(cls, id);
        if (scenario == SILENT) return false;
        storage.data.iTOW = getTimeOfWeek();
        storage.data.valid.all = (getDateValid() ? 1u : 0u) |
                                 (getTimeValid() ? 2u : 0u);
        storage.data.flags.all = getGnssFixOk() ? 1u : 0u;
        storage.data.numSV = getSIV();
        storage.data.lat = 370000000;
        storage.data.lon = -1220000000;
        storage.data.height = 100000;
        storage.data.gSpeed = 1000;
        storage.data.headMot = 9000000;
        storage.moduleQueried.moduleQueried1.all = 1u;
        storage.moduleQueried.moduleQueried2.all = 1u;
        return true;
    }
};
"""

TEST = r"""
#include <cstdio>
#include <initializer_list>
#include "gps_ublox.cpp"

uint16_t power_adc_read_vSTOR_mv() { return 5000u; }
void power_manager_kick_watchdog() {}
bool power_manager_freefall_pending() { return false; }

static int failures = 0;
static void check(const char* name, bool passed) {
    std::printf("[%s] %s\n", passed ? "PASS" : "FAIL", name);
    if (!passed) ++failures;
}
static void reset_case(Scenario selected) {
    scenario = selected;
    fake_millis = 0;
    position_reads = 0;
    gps_freshness_reset(&pvt_freshness);
    consecutive_no_fresh = 0;
    gps_quiescence_state = GPS_QUIESCENCE_UNCONTAINED;
    s_gps_diag.hardware_resets = 0;
    last_fix = {};
    (void)gnss.begin(gps_gnss_stream, GPS_BEGIN_MAX_WAIT_MS);
}
int main() {
    gps_fix_t fix{};
    reset_case(COLD_LATE_WEEK);
    check("real driver acquires across provisional-to-late-week jump",
          gps_ublox_get_fix(&fix, 10000u) && fix.valid &&
          fix.lat_e7 == 370000000 && fake_millis >= 4000u &&
          s_gps_diag.hardware_resets == 0u);

    reset_case(PROVISIONAL_ONLY);
    bool bounded_unresolved = true;
    for (unsigned cycle = 0; cycle < GPS_STALE_RECOVERY_CYCLES + 2u; ++cycle) {
        fix.valid = true;
        fix.satellites = 8;
        if (gps_ublox_get_fix(&fix, 6000u) || fix.valid || fix.satellites != 0u)
            bounded_unresolved = false;
    }
    check("real driver leaves invalid-time acquisition out of both reset ladders",
          bounded_unresolved && s_gps_diag.hardware_resets == 0u &&
          consecutive_no_fresh == 0u && position_reads == 0u);

    scenario = FROZEN_VALID;
    check("qualified frozen epoch after invalid-time cycles still resets once",
          !gps_ublox_get_fix(&fix, 6500u) &&
          s_gps_diag.hardware_resets == 1u && !fix.valid);

    reset_case(SILENT);
    check("real driver still resets a silent UART once per acquisition",
          !gps_ublox_get_fix(&fix, 7500u) &&
          s_gps_diag.hardware_resets == 1u && !fix.valid);

    reset_case(CACHED_FIX);
    check("valid flags and fixOK cannot promote repeated cached coordinates",
          !gps_ublox_get_fix(&fix, 6500u) && !fix.valid &&
          position_reads == 0u && s_gps_diag.hardware_resets == 1u);

    reset_case(VALIDITY_LOSS);
    check("real driver reanchors after losing and reacquiring time validity",
          gps_ublox_get_fix(&fix, 6000u) && fix.valid &&
          fake_millis >= 3000u && s_gps_diag.hardware_resets == 0u);

    for (Scenario invalid : {DATE_INVALID, TIME_INVALID}) {
        reset_case(invalid);
        check("either invalid date or invalid time prevents a position read",
              !gps_ublox_get_fix(&fix, 6500u) && !fix.valid &&
              position_reads == 0u && s_gps_diag.hardware_resets == 0u);
    }
    return failures ? 1 : 0;
}
"""


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="stratolink-gps-time-") as dirname:
        directory = Path(dirname)
        (directory / "Arduino.h").write_text(ARDUINO, encoding="utf-8")
        (directory / "SparkFun_u-blox_GNSS_v3.h").write_text(GNSS, encoding="utf-8")
        test = directory / "test.cpp"
        test.write_text(TEST, encoding="utf-8")
        binary = directory / "test"
        subprocess.run(
            [
                os.environ.get("CXX", "c++"), "-std=c++17", "-Wall", "-Wextra",
                "-Werror", "-fsanitize=address,undefined", "-g",
                "-I", str(directory), "-I", str(ROOT / "firmware/include"),
                "-I", str(ROOT / "firmware/src"), str(test),
                str(ROOT / "firmware/src/gps_freshness.cpp"),
                str(ROOT / "firmware/src/gps_pvt_validation.cpp"),
                str(ROOT / "firmware/src/gps_backup_policy.cpp"),
                "-o", str(binary),
            ],
            check=True,
        )
        subprocess.run([str(binary)], check=True)
    print("PASS: real GNSS driver time-domain/reset regression under ASan/UBSan")


if __name__ == "__main__":
    main()
