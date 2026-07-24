# Observability payload design (telemetry v2)

Adds flight-diagnostic fields (reset/boot detection, GPS staleness, relay and
bird-tag activity, power tier) to the TTN uplink so we can see WHY the balloon
behaves as it does, not just where it is. Designed against the SF9 Fair-Use
wall, which is the binding constraint.

Status: design only, not implemented. The byte layout and the webhook parser
change are the two things to land together. Prepared 2026-07-24; amended same
day after adversarial review (reset_cause priority decode, fix_age in minutes,
length-gating over fPort, decoder characterization corrected).

## Current payload (v1, 35 bytes, big-endian)

From firmware/include/telemetry.h + telemetry.cpp. fPort 1.

| off | bytes | field | units |
|----:|------:|-------|-------|
| 0  | 4 | lat_e7 | deg * 1e7 |
| 4  | 4 | lon_e7 | deg * 1e7 |
| 8  | 4 | altitude_m | m |
| 12 | 2 | temperature_cd | 0.1 C |
| 14 | 2 | pressure_ch | 0.1 hPa |
| 16 | 2 | solar_mv | mV |
| 18 | 2 | battery_mv (VSTOR) | mV |
| 20 | 2 | gps_speed_cm_s | 0.01 m/s |
| 22 | 2 | gps_heading_cd | 0.01 deg |
| 24 | 1 | gps_satellites | count |
| 25 | 6 | accel x/y/z | 0.01 m/s^2 |
| 31 | 1 | uv_index | index |
| 32 | 2 | ambient_lux | lux |
| 34 | 1 | acoustic_event | 0/1 flag |

## The binding constraint: SF9 Fair-Use, and its quantization

TTN's guideline is ~30 s of airtime per device per day. At SF9/BW125, cadence
1200 s (72 uplinks/day), the 35-byte payload is 308 ms ToA -> 22.2 s/day ->
**74% of the FUP budget already spent.** That is the wall every added byte
pushes against.

The non-obvious lever: LoRa ToA is quantized in symbol groups, so payload size
does NOT map linearly to airtime. Measured (toa_sf9, RP002 formula):

| app bytes | ToA | daily | FUP |
|----------:|----:|------:|----:|
| 35 | 308.2 ms | 22.2 s | 74.0% |
| 36 | 328.7 ms | 23.7 s | 78.9% |
| 40 | 328.7 ms | 23.7 s | 78.9% |
| 41+ | 349.2 ms | 25.1 s | 83.8% |

**Bytes 36 through 40 are free.** Crossing from 35 to 36 costs the whole
+4.9% jump; bytes 2 through 5 of that group cost nothing. So the airtime-optimal
observability payload is exactly **40 bytes**: 5 new bytes at the price of one,
holding FUP at 78.9% with headroom before the next 41-byte cliff.

Spend all five. Do not spend six.

## Recommended v2 layout (40 bytes)

Two moves: repurpose spare bits in byte 34 at zero cost, then append exactly
5 bytes to fill the free symbol group.

Byte 34, today a 1-bit acoustic flag in a whole byte, becomes a status byte:

| bit(s) | field | values |
|-------:|-------|--------|
| 0 | acoustic_event | 0/1 (unchanged) |
| 1-3 | power_tier | 0 FULL .. 4 CRITICAL (power_adc_get_tier) |
| 4-6 | reset_cause | 3-bit priority-decoded code, see below |
| 7 | reserved | 0 (v1 firmware always sends 0 here, so it doubles as a free future version bit) |

### reset_cause decode (required, or the field is undefined on real boots)

boot_reset_cause captures raw RCC->CSR, in which MULTIPLE reset flags are set
simultaneously on real boots. There is no standalone POR flag on the STM32WL:
a plain healthy power-on sets BOR and PIN together (observed on the bench,
0x0C01C600 = BORRSTF|PINRSTF). A naive "is BORRSTF set" check would therefore
report brownout on every normal power-up and poison the exact diagnostic this
field exists for. Encode with a strict priority decode, first match wins:

| code | meaning | condition (on RCC_CSR flags) |
|-----:|---------|------------------------------|
| 1 | watchdog | IWDGRSTF or WWDGRSTF |
| 2 | software | SFTRSTF |
| 3 | low-power/option | LPWRRSTF or OBLRSTF |
| 4 | power-on | BORRSTF and PINRSTF both set |
| 5 | brownout | BORRSTF alone (in-operation supply dip) |
| 6 | nrst pin | PINRSTF alone (external reset / debugger) |
| 0 | unknown | none of the above |

Code 7 stays reserved. Mask CSR to the reset-flag field before decoding.

Appended (bytes 35-39, the free group):

| off | bytes | field | units | why |
|----:|------:|-------|-------|-----|
| 35 | 1 | boot_count | count, wraps | brownout/reset detector; a jump means the board rebooted (the LoRaWAN fcnt alone cannot tell a reset from a rejoin) |
| 36 | 2 | fix_age_min | minutes, saturating 65535 (45.5 days) | the keystone diagnostic for the known GPS stale-fix bug; how long since a real 3D fix. Minutes, not seconds: flight #3 logged a 24.5 h EU fix gap and a 201 h ocean crossing, both past a seconds-u16's 18.2 h saturation, and the 20 min uplink cadence makes sub-minute resolution worthless |
| 38 | 1 | relay_fwd_delta | count since last uplink, cap 255 | Meshtastic relay forwarded traffic (the mission-visible relay metric) |
| 39 | 1 | ctt_tags_delta | distinct bird tags since last uplink, cap 255 | bird-detection activity; the tag IDs themselves go via the fPort-10 data-dump command, not every uplink |

That is exactly 40 bytes. power_tier + reset_cause + boot_count + fix_age give
the reset-and-staleness picture that today is invisible; relay_fwd_delta and
ctt_tags_delta surface the two new radio features per uplink.

### What did not make the cut, and why
- relay_rx_delta: rx is less informative than fwd (fwd is traffic we actually
  carried) and there is no free byte for it. Infer it loosely from fwd.
- last tag id (4 B) / acoustic detail: too big for the free group; belongs in
  the fPort-10 data-dump response, not the every-cycle uplink.
- A wider fix_age or 16-bit counters: not worth crossing the 41-byte cliff.

## Downlink-side change (must land together)
The webhook decoder (web/lib/ttn/payload-parser.ts, parseBinaryPayload) parses
PROGRESSIVELY with a 12-byte minimum, filling each field only if the buffer
reaches its offset. Consequences that make the lockstep update mandatory:
- An unversioned 40-byte v2 sent to the old decoder is NOT rejected. It is
  silently persisted with the whole v2 status byte (0-255) written into
  acoustic_event and bytes 35-39 dropped. Quiet data corruption, not an error.
- The parser has ZERO fPort visibility today: TTNWebhookPayload never extracts
  uplink_message.f_port and nothing in the ingest path branches on it. An
  fPort-2 rollout would need new plumbing before it isolates anything.

So: gate the v1/v2 layouts on PAYLOAD LENGTH (35 vs 40) in parseBinaryPayload.
The parser's existing length-progressive structure supports that today with a
near-zero diff, and v1/v2 coexist cleanly during rollout. In-band tagging in
byte-34 bit 7 (v1 always sends 0 there) would also work but is unnecessary
given the lengths differ.

## Recommendation
Ship the 40-byte v2 on the existing fPort, length-gated in the decoder, both
sides in the same change. FUP moves 74% -> 78.9%, and every added field is
either free (byte 34 bits) or inside the free symbol group. Open decision for
Teddy: bless the reset_cause priority table above, and confirm relay_fwd_delta
over relay_rx_delta as the single relay byte.

## Fine print
- The ToA figures assume empty FOpts. An uplink carrying a MAC answer (e.g.
  LinkADRAns, 2 bytes) jumps one symbol group; that is equally true of the
  35-byte v1 today, so it does not change the comparison.
- 40 bytes sits exactly on the symbol-group edge: there is zero BYTE headroom
  before the 41-byte cliff. The headroom that remains is FUP margin (78.9% vs
  the 100% wall), not spare bytes.

## Sources
- RP002-1.0.3 Regional Parameters (SF9 ToA, symbol count formula).
- TTN Fair Use (30 s/day airtime guideline).
- firmware/include/telemetry.h, firmware/src/telemetry.cpp (v1 layout).
- doc 08 (command channel; fPort-10 data-dump for bulk tag IDs).
