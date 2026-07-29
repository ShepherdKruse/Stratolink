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
  next_hop = 0                               # anonymous flood/no preference only
  relay_node = 0                             # do not impersonate a native NodeNum
  wait getTxDelayMsec()                       # ~N * 28 ms slots (ROUTER_LATE → late window)
  if channel still quiet (CSMA) and not preempted by TTN: retransmit(frame)  # ciphertext untouched
```
No protobuf parse, no decode, no keys. The dedup ring + header edits + a timed re-TX.
StratoLink deliberately does not invent a native Meshtastic identity: a fabricated
low byte can poison `NextHopRouter` learning for a real node with that byte. It only
relays packets whose `next_hop` is already `NO_NEXT_HOP_PREFERENCE` (zero), and writes
both `next_hop` and `relay_node` as zero on the forwarded copy.

**Wire contract to be Meshtastic-compatible (pin these exactly):** LongFast =
SF11 / BW250 / CR4-5, **16-symbol preamble** (not the LoRaWAN 8), explicit header,
CRC on, **sync word 0x2B** (LoRaWAN uses 0x34), default channel **"LongFast"**. Center
frequency (DJB2-hash slot, verified): **US915 = 906.875 MHz**, **EU868 = 869.525 MHz**,
and **AU915 = 919.875 MHz**. The coarse AS923 geofence intentionally returns no
LongFast carrier: it can use the implemented LoRaWAN common channels, but cannot
prove one auxiliary carrier legal across every AS sub-plan. SILENT also returns none.

## The radio-sharing scheme (fig N11)

One ~1200 s cycle, in order: **GPS fix (≤30 s) → LoRaWAN uplink (0.31 s) → [swap
~1 ms] → Meshtastic relay window (gated) → [swap ~1 ms] → sleep.** TTN owns the radio
on its fixed cadence; the relay window is the smaller of the remaining cadence
and the live GNSS-backed regional-TX lease, and only runs if power allows.

- **Mode swap (~1 ms):** from `standby()`, re-apply *every* differing param -
  `setSpreadingFactor(11) / setBandwidth(250) / setCodingRate(5) / setSyncWord(0x2B) /
  setPreambleLength(16) / setFrequency(906.875|869.525|919.875) / setCRC(true)`, then
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

The implemented CTT/relay window keeps the SX1262 receiving while the MCU runs a
bounded service loop. A final audit found that the old `delay(2)` loop busy-spun
because STM32duino's weak `yield()` is empty. The repaired loop explicitly selects
shallow CPU sleep and executes WFI between SysTick, radio-DIO, and freefall-EXTI
wakes; it does **not** enter STOP1/STOP2 while RX is armed. The earlier radio-only
5.5 mA model therefore understated the former implementation by the estimated
active-MCU term. Conversely, radio-only is only a lower screen for the repaired
path until its exact clock/peripheral state is measured. Mission protection is
explicit: the flight profile
starts service only in FULL tier with active solar, aborts immediately below **4.2 V
VSTOR**, caps relay/B2B transmit airtime at **5%** of the shared window, restores the
complete LoRaWAN PHY, and debits the service time from the sleep budget. The first
60 seconds are reserved for CTT receive before the shared LongFast Meshtastic/B2B
window. That reservation is experimental on StratoLink-2: the fitted part is
`RAK3172-9-SM-NI`, RAK's 9xx-MHz SKU for US915/AU915/KR920/AS923; RAK assigns
EU868 and 434 MHz to different ordering codes. A radio
configuration call succeeding outside the supported module band is not receiver
sensitivity evidence. Exact-tag HIL must either qualify the path or the frozen
image must disable CTT rather than spend this time ahead of B2B/Meshtastic.
Exact energy qualification remains a final-supercap, exact-binary bench gate.

The regional lease is also a deadline, not merely an entry gate. After one
missed fix, a service window can begin before the 1,800 s lease expires and
otherwise run beyond it. Current source rechecks live age before join, primary,
and auxiliary packets, captures live age before future-sleep persistence, and
caps the shared LongFast window to the remaining legal TX duration with a
one-second guard. Join, primary, and auxiliary frames also require that guard,
so none may begin on the represented expiry second. Any preceding CTT receive
time is deducted. Retained sleep age is charged using the STM32WLE5's 29.5 kHz
datasheet-minimum LSI against STM32RTC's 32 kHz prescalers: a nominal 1,200 s
STOP is persisted as 1,302 s, so oscillator tolerance can only expire RF
authority early. The bound comes from ST's current
[STM32WLE5/E4 electrical characteristics](https://www.st.com/resource/en/datasheet/stm32wle5cb.pdf),
which specify 29.5-34 kHz across 1.8-3.6 V and -40 to 125 °C. In the pinned
age-1,200 s plus 40 s active example, the relay gets 559 s rather than the full
1,200 s, then returns to RF-quiet STOP1.

## Gotchas / bench-test and hardware gates

1. **Measure the implemented shallow-WFI + RX window**, including CTT diagnostic,
   LongFast receive, CAD, forwards, one-hertz housekeeping, floor/solar/freefall
   aborts, and the transition back to STOP1. Do not substitute either the radio-only
   screen or a STOP2 estimate for the actual flight path.
2. **Re-apply ALL differing params every swap**, sync word, preamble (16 vs 8), freq,
   SF, BW, CRC. Forgetting any = silent interop failure.
3. **Honor BUSY + disambiguate the shared DIO IRQ** (`getIrqFlags()`), the two most-
   reported RadioLib/STM32WL failure modes (#1679, #588).
4. **Preemption discipline**, never let a relay RX/TX overrun a scheduled TTN slot.
5. **Hysteretic gate**, clean on/off (2-cycle FULL + floor-abort); a browning-out
   reboot loop must not become a flood/advert storm.
6. **ROUTER_LATE timing**, slotTime ≈ 28 ms at LongFast; rebroadcast delay =
   `random(...) × slotTime`, sub-second, easily fits the gap.
7. **Regional-lease deadline**, cap the complete TX-capable service window—not
   just entry—and conservatively convert LSI-timed sleep to real wall time, so
   a missed fix or slow cold oscillator cannot authorize packets at/after age
   1,800 s.

## What we'd actually build (scoped to just this)

- `firmware/src/meshtastic_relay.{h,cpp}`, the wire-compat PHY profile, the dedup ring,
  the header parse + hop-decrement + ROUTER_LATE-timed re-TX, the RX/forward loop with
  floor-abort + IWDG kicks.
- The implemented source mapping yields 906.875 / 869.525 / 919.875 MHz for
  US915 / EU868 / AU915 and zero for AS923/SILENT; the relay window returns
  before radio reconfiguration when the mapping is zero.
- The one-line hook + the radio borrow/return accessor in `lorawan.cpp`.
- Bench: prove EWRFIRQ wake-from-STOP, then air-to-air interop with a real Meshtastic
  node, then measure ChUtil/AirUtilTX.

## Figures
- `N11_radio_sharing.png`, the cooperative SX1262 cycle: TTN priority + relay in the FULL+sun gap.
