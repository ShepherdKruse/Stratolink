# Observability payload (telemetry v2)

The final-source candidate carries the reset, GNSS-staleness, command, relay,
wildlife-radio, and power evidence needed to diagnose Flight-3-style failures
from TTN rather than inferring them from missing positions.

**Implementation status (2026-07-25):** implemented locally in firmware,
the webhook parser, database migration, TTN monitor/listener, Storage replay,
and strict host/HIL decoders. It has passed sanitized host vectors and all 13
PlatformIO builds. It is not yet a frozen or flashed flight image. Production
must apply `20260725222000_telemetry_observability_v2.sql` and deploy the
matching webhook before the 40-byte image is flashed.

## Wire contracts

fPort 1 uses exact length as its version discriminator:

- 35 bytes: historical telemetry v1, still accepted.
- 40 bytes: telemetry v2 below.
- any other length: rejected.

The webhook decodes `frm_payload` before considering TTN
`decoded_payload`. That makes the authenticated LoRaWAN application bytes
authoritative if a TTN formatter lags the firmware rollout.

## Why 40 bytes

At SF9/BW125 and the nominal 1,200-second cadence, LoRa airtime is quantized:

| Application bytes | Airtime | 72 primaries/day |
|------------------:|--------:|-----------------:|
| 35 | 308.224 ms | 22.192 s |
| 36-40 | 328.704 ms | 23.667 s |
| 41 | 349.184 ms | 25.141 s |

Bytes 36 through 40 occupy one symbol group, so 40 bytes costs the same
airtime as 36. The firmware uses the complete group and does not cross the
41-byte boundary.

The shared CTT/B2B budget permits one worst-case 53-byte auxiliary every eight
successful primaries. Nine such packets/day add 3.511 s, making the modeled
worst case 27.178 s/day and leaving 2.822 s below TTN's 30 s/day community
guideline for joins/model error/clock error.

## v2 layout (40 bytes, big-endian)

Bytes 0-33 are unchanged from v1:

| Offset | Bytes | Field | Units |
|------:|------:|-------|-------|
| 0 | 4 | latitude | degrees × 1e7 |
| 4 | 4 | longitude | degrees × 1e7 |
| 8 | 4 | altitude | m |
| 12 | 2 | temperature | 0.1 °C |
| 14 | 2 | pressure | 0.1 hPa |
| 16 | 2 | solar voltage | mV |
| 18 | 2 | VSTOR | mV |
| 20 | 2 | GPS speed | 0.01 m/s |
| 22 | 2 | GPS heading | 0.01° |
| 24 | 1 | GPS satellites | count |
| 25 | 6 | acceleration x/y/z | 0.01 m/s² each |
| 31 | 1 | UV index | integer |
| 32 | 2 | ambient light | lux |

Byte 34 is a packed status byte:

| Bits | Field | Values |
|-----:|-------|--------|
| 0 | acoustic event | 0/1 |
| 1-3 | power tier | 0 FULL through 4 CRITICAL |
| 4-6 | reset cause | 0-6 below; 7 rejected |
| 7 | command ACK valid | byte 38 is meaningful |

Bytes 35-39 are:

| Offset/bits | Field | Encoding |
|------------:|-------|----------|
| 35 | boot count | retained counter low byte, modulo 256 |
| 36-37 | fresh-fix age | minutes since an accepted fix this boot; `0xFFFF` means none this boot |
| 38 | command ACK sequence | last durably applied fPort-10 sequence when valid; otherwise zero |
| 39 bit 7 | relay enabled | actual retained public-Meshtastic policy |
| 39 bits 4-6 | relay forwards | delta since last successful primary, saturated at 7 |
| 39 bits 0-3 | CTT tags | delta since last successful primary, saturated at 15 |

The activity baselines advance only after a successful primary uplink. A
failed primary therefore retries the same accumulated activity rather than
silently acknowledging it. Saturation means these are evidence of activity,
not lossless traffic accounting; exact counters and queued event records are
available through HIL and the typed auxiliary paths.

## Reset cause

Multiple STM32WL RCC flags can be set on one boot, so firmware applies one
strict priority decoder:

| Code | Meaning | Condition, first match wins |
|----:|---------|-----------------------------|
| 1 | watchdog | IWDG or WWDG flag |
| 2 | software | software reset flag |
| 3 | low-power/option | low-power or option-byte flag |
| 4 | cold power-on | BOR flag without a valid retained LoRaWAN session |
| 5 | warm brownout | BOR flag with a valid retained LoRaWAN session |
| 6 | NRST pin | pin-reset flag |
| 0 | unknown | none above |

The retained-session discriminator avoids labeling every normal power-up as a
brownout. If the backup domain survives but its session record is corrupt, a
BOR can conservatively appear as cold power-on; the raw RCC value remains
available in exact-image HIL.

## Command/reset coherence

TAMP word 25 stores a v2 command-state record: tag, sequence, relay-enabled
bit, and CRC-8/ATM. The command validates the complete frame, persists the
next sequence and resulting relay state, then applies the effect. After a warm
reset the ACK and actual relay behavior therefore restore together. Every
one-bit record corruption is rejected. A true backup-domain loss clears this
state and remains a documented fleet replay-hardening limit.

## Rollout and qualification gate

Before this is a launch claim:

1. Apply the observability migration and deploy the matching webhook.
2. Freeze a reproducible exact image and regenerate its 46-symbol HIL bundle,
   including `region_lease_trusted` provenance.
3. Flash only after the precursor soak and PPK2 handoff pass.
4. Prove one 40-byte primary through TTN and Supabase.
5. Queue PING and relay-off/on commands, verify next-primary ACK/state, then
   prove the sequence and relay state survive a guarded warm reset.
6. Prove clear-sky GNSS makes fix age advance from zero, and a no-fix cycle
   never emits cached coordinates.

## Sources

- `firmware/include/telemetry.h`, `firmware/src/telemetry.cpp`
- `firmware/src/reset_cause.cpp`
- `firmware/src/command_sequence_store.cpp`, `firmware/src/command.cpp`
- `web/lib/ttn/payload-parser.ts`
- `web/lib/supabase/migrations/20260725222000_telemetry_observability_v2.sql`
- LoRaWAN RP002 airtime calculation and TTN Fair Use guideline
