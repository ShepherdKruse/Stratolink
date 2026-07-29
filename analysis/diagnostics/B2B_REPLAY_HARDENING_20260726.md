# B2B replay hardening design boundary — 2026-07-26

## Decision

Do not call wire v3 replay-robust and do not deploy it as a multi-balloon
control mesh. Keep the present StratoLink-2 single-balloon primary TTN mission
scoped separately: with no peer fleet transmitter, its own-source guard drops
echoes and B2B is not required for telemetry or TTN downlink control.

The recommended fleet successor is a reviewed wire v4 with:

1. a durably reserved 32-bit per-origin message counter;
2. a durable per-authorized-source high-water counter plus replay bitmap;
3. TTL included in the AES-CMAC input and re-signed by each trusted relay;
4. fail-closed delivery and forwarding whenever replay state cannot be
   committed exactly;
5. the existing authenticated crumb age advancement retained independently.

This design does not require synchronized clocks. Authenticated absolute GNSS
time may be added as a staleness signal, but cannot be the sole replay root
because a receiver can boot without a fix.

## Executable finding in wire v3

The current receiver keeps 32 dedup keys in RAM for 240 minutes. Strict host
regressions now prove:

- the same authenticated frame is rejected through insertion minute +240;
- it is accepted at minute +241;
- it is accepted immediately after `b2b_reset()`;
- TTL can be restored up to `B2B_TTL_DEFAULT` without invalidating the CMAC,
  because TTL is the one excluded header field.

AES-CMAC still rejects the wrong key and every tested immutable source, ID,
type, length, body, or tag mutation. The defect is freshness, not message
authentication.

## LSI time is now bounded independently

The initial wire-v3 implementation used STM32RTC minutes derived from a
nominal 32 kHz LSI for queue age, 240-minute dedup expiry, and hourly origin
cadence. ST guarantees the STM32WLE5 LSI only from 29.5 to 34 kHz over its full
voltage/temperature range. Those semantics need opposite conservative bounds:

- freshness age must use an **upper** wall-time bound. At 29.5 kHz, 60 nominal
  RTC minutes can occupy 65.1 real minutes, so an uncorrected `age_min` can
  understate residence by about 8.5%;
- replay retention and minimum origin spacing must use a **lower** wall-time
  bound. At 34 kHz, 240 nominal minutes can expire after only 225.9 real
  minutes, and a nominal hourly crumb can become due after 56.5 real minutes.

The implementation now stores raw 32-bit RTC-second epochs and converts only
wrap-safe deltas. `b2b_age_upper_minutes()` uses the 29.5 kHz minimum and a
ceiling division before increasing authenticated crumb age;
`b2b_elapsed_lower_minutes()` uses the 34 kHz maximum and floor division before
allowing dedup expiry or an hourly origin. Host boundary vectors pin 3,318 raw
seconds to an age of 60 minutes, 3,319 to 61, 3,824 raw seconds to less than 60
minutes of minimum elapsed time, and 3,825 to exactly 60. The same lower bound
keeps a frame duplicate through 15,300 raw seconds at the fast corner (240 real
minutes) and permits expiry only later. The flight and B2B-diagnostic embedded
images compile with the change.

This fixes oscillator-direction errors but does not make wire v3 replay-robust:
the receive cache is still volatile and intentionally expires. Wire v4 should
retain the separate raw-delta conversions; do not apply one globally corrected
clock, because making freshness conservative in one direction would weaken
retention and spacing in the other.

## Why the alternatives are insufficient

| Candidate | Failure |
|---|---|
| Larger RAM dedup cache | Reset still erases the freshness root; a finite expiry still permits later replay. |
| Random boot nonce only | A captured frame remains valid after the receiver loses its nonce cache. |
| Authenticated GNSS/UTC timestamp only | No-fix cold boots lack a trustworthy time bound; clock rollback becomes the replay boundary. |
| Durable high-water counter only | Legitimate store-and-forward reordering would discard every older-but-unseen frame. |
| Command sequence alone | Protects command reapplication while retained, but not crumb replay, relay airtime, reset loss, or full transport semantics. |

## Proposed wire and storage model

Replace the 8-bit `msg_id` with a 32-bit monotonically increasing origin
counter. Reserve and verify the successor in nonvolatile storage before a new
logical frame reaches a queue or radio, matching the existing FCntUp safety
ordering.

For each authorized source, persist:

- source ID;
- greatest authenticated counter accepted;
- a 64-bit bitmap for the preceding counter window;
- version and CRC/commit metadata.

A counter above the high-water mark advances the bitmap. A counter within the
64-frame window is accepted only when its bit is clear. An older counter or a
set bit is a replay. Exact authenticated command duplicates may take a separate
re-ACK-without-reapply path after the replay decision, preserving the current
lost-ACK behavior.

At the current hourly crumb cadence, a 64-frame window tolerates about 64 hours
of out-of-order store-and-forward delivery per source. The fleet authorization
list should be bounded explicitly—eight peers is a practical first target—so
the journal size, receive work, and denial-of-service surface remain finite.

## Airtime and storage effects

Growing the header counter from one byte to four adds three bytes. The current
53-byte US915 DR1 application ceiling therefore requires reducing
`B2B_PAYLOAD_MAX` from 44 to 41 bytes unless another field is compressed. With
an 8-byte tag, a maximum crumb body becomes 30 bytes: five crumbs rather than
six. The limit must remain source-bound to the AS923 400 ms dwell screen.

An illustrative 24-byte journal record written once per newly accepted peer
frame fits about 170 records in one 4 KiB flash page. Eight hourly peers fill a
page in roughly 21 hours; ping-pong wear leveling across two pages gives about
42 hours per erase cycle, or roughly 48 years at 10,000 erase cycles before
temperature/endurance derating. This is an order-of-magnitude architecture
screen, not a part-qualified endurance claim. Exact STM32WL erase granularity,
write energy, brownout behavior, linker reservation, and cold endurance must be
bound before implementation.

## Required proof before a fleet launch

- independent CMAC vector covering TTL and the 32-bit counter;
- every one-bit header/body/tag mutation and wrong-key rejection;
- counter rollover and half-range ambiguity fail closed;
- in-order, out-of-order, duplicate, older-than-window, and delayed frames;
- reset and complete backup-domain loss with replay rejection preserved;
- torn write, CRC corruption, journal rollover, and exhausted-storage behavior;
- TTL decrement plus relay re-signing, and restored-TTL rejection;
- dropped ACK followed by exact retry: re-ACK once, apply zero additional times;
- queue-full, CAD-busy, TX-failure/refund, and low-rail persistence failure;
- two-node exact-image RF with delayed store-and-forward and receiver resets;
- updated firmware/web fPort-12 parity and unchanged 53-byte/dwell limits.
- repeat the already-passing minimum/maximum LSI boundary vectors on the exact
  image, proving queue age never understates wall residence, dedup never
  expires before 240 real minutes, and the hourly origin schedule never fires
  before 60 real minutes.

Until those gates pass, wire v3 remains authenticated store-and-forward logic
with a documented volatile replay horizon—not a durable fleet control plane.
