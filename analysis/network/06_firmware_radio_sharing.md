# Firmware: sharing the one SX1262 between TTN (priority) and a Meshtastic repeater

Can the *current* hardware (single RAK3172 / SX1262, one antenna) run a Meshtastic
ground-relay in the gaps when TTN isn't using the radio, TTN always first? Grounded
in our `main.cpp`/`lorawan.cpp`, the integration research (Meshtastic source, RadioLib,
STM32WL), and my own cycle model (`93_radio_sharing.py`, fig N11).

## Bottom line

**Yes, on the hardware as-is, no second radio.** Two facts make it clean:
1. **A Meshtastic-compatible repeater is tiny**, it forwards the *still-encrypted*
   payload opaque (verified in Meshtastic `Router.cpp`), so no channel key, no AES, no
   protobuf, no NodeDB. Just: match the PHY, parse the 16-byte plaintext header, dedup
   by (from,id), decrement `hop_limit`, re-TX verbatim. A few hundred lines on our
   existing RadioLib radio.
2. **TTN is the scheduled master; the repeater borrows the idle time.** Our loop already
   sleeps ~99.8% of each 1200 s cycle. The relay replaces that sleep *only when tier ==
   FULL and the sun is charging*, and yields the radio back ~2 s before the next TTN
   slot. The integration is **one decision point** in `main.cpp loop()`: the
   end-of-cycle `power_manager_sleep_ms()` becomes "relay-then-sleep."

No one has done LoRaWAN + Meshtastic time-sliced on one SX1262 before, this is novel.

## The minimal repeater (why it's small)

Forwarding is **header-only**. From Meshtastic source (read directly):
- The 16-byte `PacketHeader` (to, from, id, flags, channel-hash, next_hop, relay_node)
  is **sent in the clear**, *"allows nodes to relay packets they can't decrypt."*
- `hop_limit = flags & 0x07`; `hop_start = (flags & 0xE0) >> 5`.
- `Router.cpp::send()` skips the encrypt step when forwarding (*"it might already be
  encrypted if we are just forwarding it"*), the relay re-TXs the original ciphertext
  unchanged. **A repeater never needs the channel PSK.**

So the whole repeater is this loop, run during the relay window:
```
on RxDone:
  if len < 16: drop
  hop = flags & 0x07
  if hop == 0: drop
  if seen(from,id) recently: drop            # small dedup ring buffer
  flags = (flags & ~0x07) | (hop-1)          # decrement hop_limit
  relay_node = lastByte(myNodeNum)           # optional
  wait getTxDelayMsec()                       # ~N * 28 ms slots (ROUTER_LATE → late window)
  if channel still quiet (CSMA) and not preempted by TTN: retransmit(frame)  # ciphertext untouched
```
No protobuf parse, no decode, no keys. The dedup ring + a flags edit + a timed re-TX.

**Wire contract to be Meshtastic-compatible (pin these exactly):** LongFast =
SF11 / BW250 / CR4-5, **16-symbol preamble** (not the LoRaWAN 8), explicit header,
CRC on, **sync word 0x2B** (LoRaWAN uses 0x34), default channel **"LongFast"**. Center
frequency (DJB2-hash slot, verified): **US915 = 906.875 MHz**, **EU868 = 869.525 MHz**.
Geofence picks the region freq, same as the LoRaWAN region switch already does.

## The radio-sharing scheme (fig N11)

One ~1200 s cycle, in order: **GPS fix (≤30 s) → LoRaWAN uplink (0.31 s) → [swap
~1 ms] → Meshtastic relay window (gated) → [swap ~1 ms] → sleep.** TTN owns the radio
on its fixed cadence; the relay window is whatever's left, and only runs if power
allows.

- **Mode swap (~1 ms):** from `standby()`, re-apply *every* differing param -
  `setSpreadingFactor(11) / setBandwidth(250) / setCodingRate(5) / setSyncWord(0x2B) /
  setPreambleLength(16) / setFrequency(906.875|869.525) / setCRC(true)`, then
  `startReceive(INF)`. Swapping back loads the LoRaWAN profile. Each setter is a short
  SPI command; the swap is negligible vs the cycle. Our firmware already does
  `setFrequency`/`setSpreadingFactor` per-uplink/region, so this is established ground.
- **TTN priority / preemption:** the relay loop is time-boxed to `next_tx_due - 2 s`.
  When the window ends it stops accepting packets, finishes any in-flight TX, swaps to
  the LoRaWAN profile, and the normal TTN cycle runs. A Meshtastic packet in flight when
  the window closes is simply lost, fine, relay is best-effort and TTN's duty is tiny.

## The one-line integration point

`main.cpp loop()` ends with `lorawan_sleep(); gps_ublox_sleep();
power_manager_sleep_ms(sleep_sec*1000);`. That becomes:
```c
lorawan_sleep_session();                 // keep LoRaWAN session in TAMP (already done)
if (tier == POWER_TIER_FULL && ti.solar_mv > SOLAR_RELAY_MV && relay_region_ok(region)) {
    meshtastic_relay_run(sleep_sec*1000 - 2000);   // borrow the gap; yields 2 s early
}
gps_ublox_sleep();
power_manager_sleep_ms(remaining_ms);    // sleep whatever's left
```
`meshtastic_relay_run()` does the swap-in, the RX/forward loop with a VSTOR floor-abort
and IWDG kicks, then swaps back. The `radio` object is file-scope in `lorawan.cpp`, so
the relay either lives there or borrows it via a small accessor
(`lorawan_radio_borrow()/return()`).

## Power (the real limiter, as always)

Relay listening = SX1262 RX **~5.5 mA** while receiving. Crucially, the STM32WL can keep
the radio in RX-continuous while the **MCU sleeps in STOP2 (~2.5 µA)** and wakes on
RxDone, **but only if `EWRFIRQ` (PWR_CR3) is set** (a documented STM32WL foot-gun:
without it the MCU never wakes on RxDone). So relay-window draw ≈ the radio RX itself,
~5.5 mA, with the MCU near-free except during an actual forward. That sits inside the
clipped-surplus budget for the ~12-14 h/day the cap is FULL (f≈0.58 from
`relay_availability.py`), throttled by the **VSTOR floor-abort (<4.7 V)** so it never
touches the telemetry reserve. Forward TX adds ~96 mJ each, capped at ≤7.5% AirUtilTX
(≈483/hr) per the good-citizen rule.

## Gotchas / bench-test list (all documented, none blocking)

1. **`EWRFIRQ` wake-from-STOP2-on-RxDone**, verify on the bench *first*; it's the make-
   or-break for low-power listening (without it the listen falls back to MCU-in-RUN,
   ~+2-4 mA, halving the affordable relay duty).
2. **Re-apply ALL differing params every swap**, sync word, preamble (16 vs 8), freq,
   SF, BW, CRC. Forgetting any = silent interop failure.
3. **Honor BUSY + disambiguate the shared DIO IRQ** (`getIrqFlags()`), the two most-
   reported RadioLib/STM32WL failure modes (#1679, #588).
4. **Preemption discipline**, never let a relay RX/TX overrun a scheduled TTN slot.
5. **Hysteretic gate**, clean on/off (2-cycle FULL + floor-abort); a browning-out
   reboot loop must not become a flood/advert storm.
6. **ROUTER_LATE timing**, slotTime ≈ 28 ms at LongFast; rebroadcast delay =
   `random(...) × slotTime`, sub-second, easily fits the gap.

## What we'd actually build (scoped to just this)

- `firmware/src/meshtastic_relay.{h,cpp}`, the wire-compat PHY profile, the dedup ring,
  the header parse + hop-decrement + ROUTER_LATE-timed re-TX, the RX/forward loop with
  floor-abort + IWDG kicks.
- A `region_manager` extension yielding the Meshtastic freq per region (906.875 / 869.525)
  and a `relay_region_ok()` (disable over ocean, no ground users).
- The one-line hook + the radio borrow/return accessor in `lorawan.cpp`.
- Bench: prove EWRFIRQ wake-from-STOP, then air-to-air interop with a real Meshtastic
  node, then measure ChUtil/AirUtilTX.

## Figures
- `N11_radio_sharing.png`, the cooperative SX1262 cycle: TTN priority + relay in the FULL+sun gap.
