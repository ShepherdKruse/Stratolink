# Meshtastic + LoRaWAN coexistence: architecture assessment

> **Status: superseded design exploration.** This memo predates the implemented
> header-compatible Meshtastic relay, Class-A fPort-10 command path, and
> authenticated B2B wire v3. It is retained as decision history, not as the
> launch architecture. Current truth is in `06_firmware_radio_sharing.md`,
> `08_command_control.md`, `09_observability_payload.md`, and the flight source.
> In particular, the flight image has no worldwide common auxiliary frequency:
> it uses qualified US915/EU868/AU915 channels and disables auxiliary TX in
> AS923/SILENT.

Can a Stratolink balloon run Meshtastic (or a mesh relay) alongside TTN telemetry,
and is Meshtastic the right tool for balloon-to-balloon and for uplink-to-balloon?
Grounded in our KiCad hardware, our firmware, flight data, my own airtime/range
modeling (`80_meshtastic_coexist.py`, fig N7), and dated protocol research.

## Bottom line

- **Hardware is a non-issue.** One **RAK3172** (STM32WLE5 = MCU + SX1262 + RF switch
  in one module, KiCad U2) + one LoRa antenna (AE1). Any second protocol is **firmware
  time-multiplexing on the one radio, zero hardware change.**
- **Stock Meshtastic cannot coexist** with our LoRaWAN on one MCU: it's monolithic
  firmware that owns the radio + main loop, has no library, caps NodeDB at **10 nodes**
  on STM32WL, and assumes **always-on RX**. To "run Meshtastic" you'd flash *only*
  Meshtastic (losing our LoRaWAN telemetry + control) on a dedicated balloon.
- **For coexistence, the embeddable mesh is MeshCore** (MIT, RadioLib-based, official
  RAK3172 target, fits 256 KB, path-routing = controllable airtime), but it's the
  **MeshCore network, not Meshtastic** (no interop).
- **For OUR balloon-to-balloon, a proprietary scheduled P2P beats Meshtastic** -
  decisively, on power (Meshtastic's always-on RX is the 76× load we can't afford;
  a scheduled/TDMA wake-window duty-cycles RX back into budget), on payload
  efficiency, and on cross-region control. We already own a RadioLib radio + a
  hand-rolled MAC, so a lean P2P layer is in-character.
- **For uplink/command to the balloon, LoRaWAN Class A beats Meshtastic**, a
  duty-cycled supercap node is *deaf* to Meshtastic (no scheduled-RX in the protocol;
  low-power roles can't receive). Class A RX windows (after each uplink, ~free power)
  are the reliable command path. They were a roadmap item when this memo was
  written and are implemented in the current source.
- **Recommended: keep LoRaWAN/TTN as the telemetry+command spine; add a
  power-tier-gated second mode in surplus windows, proprietary P2P for the B2B
  constellation, and/or MeshCore if we want to serve ground users.** One radio,
  modes scheduled on RadioLib.

## The radio reality (hardware)

KiCad (`stratolink.kicad_sch`, 62 footprints): the LoRa side is **U2 RAK3172**
(integrated STM32WLE5 + SX1262 + RF switch) on a **single antenna AE1**. The SX1262
silicon tunes 150-960 MHz and the modeled antenna straddles 868/915, but neither
fact overrides the fitted module's internal matching: exact BOM part
`RAK3172-9-SM-NI` is specified by RAK for US915/AU915/KR920/AS923, not EU868.
Within an exact-SKU-qualified band, switching the radio
between LoRaWAN params and a mesh preset is a **RadioLib reconfigure** (set SF/BW/
freq, ~ms), not new silicon. The radio is **half-duplex**, it does one thing at a
time, so the modes are strictly time-sliced. Per 1200 s cycle the radio is busy only
~**0.2%** (GPS hot 2 s + LoRaWAN TX 247 ms); **99.8% is free** for a relay mode -
so *radio time is never the constraint; power is* (`relay_power_budget.py`).

## The firmware reality

Our stack is the enabler: `lorawan.cpp` drives the radio **directly via RadioLib**
(`radio->begin / setSpreadingFactor / setFrequency / transmit`) and `main.cpp` owns
a simple loop (`tier → GPS → pack → TX → sleep`). Because **we own the radio and the
loop**, a second mode is a scheduler branch + a reconfigure, not a rewrite.

Meshtastic is the opposite shape: monolithic, no library, `MeshService`/
`RadioInterface`/NodeDB entangled with global state, **STM32WL = 10-node afterthought**
([firmware discussion #5739, 2025-01-25](https://github.com/meshtastic/firmware/discussions/5739); `mesh-pb-constants.h`). Embedding it next to our MAC means
fighting a codebase that expects to *be* the firmware. **MeshCore** (`variants/rak3x72`,
`board_upload.maximum_size = 229376`) is MIT C++ on RadioLib that actually targets our
MCU and fits flash, the integrable option, at the cost of zero Meshtastic interop.

## Protocol mismatch + airtime/range (my model, fig N7)

| Mode | SF/BW | ToA @40 B | Sensitivity | Range vs our SF9 |
| --- | --- | --- | --- | --- |
| **Stratolink LoRaWAN** | SF9/125 | 329 ms | -129.5 dBm | 1.00× (ref) |
| Meshtastic **LongFast** (default) | SF11/250 | **682 ms** | -131.5 dBm | **1.26×** |
| Meshtastic MediumFast | SF9/250 | 191 ms | -126.5 dBm | 0.71× |
| Meshtastic ShortFast | SF7/250 | 58 ms | -121.5 dBm | 0.40× |

LongFast buys +26% range for ~2× the airtime/energy of our SF9, *and it's a
different BW (250 vs 125) and frequency slot*, so LoRaWAN and a Meshtastic mode are
two distinct radio configs the firmware swaps between. Meshtastic also adds a 16-byte
plaintext header + protobuf framing per packet, and **floods** (each packet
rebroadcast up to hop_limit×neighbors), airtime amplification we'd pay in TX energy.

## Five architectures, assessed

| # | Architecture | Telemetry coverage | Command path | B2B / ocean | Ground-community value | Power | Firmware effort | Verdict |
|---|---|---|---|---|---|---|---|---|
| 1 | **LoRaWAN-only** (+ add Class A) | yes TTN (proven) | yes Class A | no none | no | yes lean | low | **baseline, do this regardless** |
| 2 | LoRaWAN + **stock Meshtastic** | yes | no | weak | yes Meshtastic net | no always-RX | no can't coexist (monolithic) | no not feasible on one MCU |
| 3 | LoRaWAN + **MeshCore** relay | yes | yes Class A | ok-ish (MeshCore mesh) | ~ MeshCore net (not Meshtastic) | ~ gate to surplus | med-high | ~ good for **ground service** |
| 4 | LoRaWAN + **proprietary P2P** | yes | yes Class A | yes+ scheduled, power-fit | no | yes duty-cycled | med | yes **best for B2B/constellation** |
| 5 | **Meshtastic-primary** (drop LoRaWAN) | no loses TTN's 140-gw mesh | Meshtastic (deaf asleep) | weak | yes | no | high | no throws away our coverage |

## Would Meshtastic work as uplink (ground → balloon)?

Technically yes, a ground node DMs the balloon's NodeNum (with WANT_ACK), **but a
duty-cycled supercap balloon is deaf to it.** Meshtastic has **no scheduled-RX
(Class-B-like) mechanism**; its only low-power roles (TRACKER/SENSOR) explicitly
*don't* keep the radio listening, so they can't be commanded, and any role that *can*
receive needs **always-on RX**, the 76× power load we can't sustain. The 16-symbol
preamble helps a *briefly*-sleeping receiver but isn't a coordinated wake window.
→ **For reliable commanding, implement LoRaWAN Class A** (RX1/RX2 windows right after
each uplink, we're already awake, so it's ~free power; works with TTN; FUP ~10
downlinks/day). Meshtastic-uplink is a fun community demo *during* surplus relay
windows, not the primary command path.

## Is Meshtastic better than a proprietary protocol for B2B?

**No, for our balloons talking to each other, proprietary wins:**
- **Power:** Meshtastic/MeshCore assume always-on RX to relay; our supercap can't
  (drains in ~4 min without sun). A proprietary **scheduled/TDMA wake-window** (both
  ends are ours, so we coordinate) duty-cycles RX to a few % → back in budget. This
  is the decisive factor.
- **Payload:** telemetry is ~tiny; Meshtastic's 16 B header + protobuf + flood is
  pure overhead for point-to-point store-and-forward.
- **Cross-region (superseded concept):** this memo proposed a common relay
  channel. The implemented flight policy instead uses the selected local
  US915/EU868/AU915 channel and carries queued records across the 868/915 line;
  this is software behavior, not proof that the fitted `-9` SKU is EU868-qualified;
  direct RF requires both balloons to share a compatible plan.
- **Meshtastic's advantage is interop with ground devices**, which is irrelevant for
  balloon↔balloon (both ends are ours). So Meshtastic/MeshCore is the right tool only
  when the *other end is a ground Meshtastic user*, i.e. the community-service relay,
  not the constellation backbone.

## Recommendation / sequencing

The clean design is **one radio, modes scheduled on RadioLib, all gated by the power
tier** (relay/P2P only on FULL + sun surplus, floor-abort, `relay_availability.py`):

1. **LoRaWAN telemetry uplink** remains the TTN spine.
2. **LoRaWAN Class A downlink is implemented** for bounded fPort-10 commands and
   reports its durable sequence/relay state in telemetry v2.
3. **Authenticated B2B wire v3 is implemented** inside the shared LongFast
   window with bounded queues, randomized contention, CAD, CMAC, deduplication,
   TTL, delayed-age accounting, and TTN tunneling. It is not TDMA and still needs
   true two-node RF HIL.
4. **The public Meshtastic-compatible relay is implemented as a narrow
   header-level service**, not stock Meshtastic or MeshCore firmware. It remains
   subordinate to solar, rail, region, airtime, and primary-telemetry gates.

Thus TTN remains the telemetry/command spine; the current public relay and private
B2B service share only proven surplus windows, and telemetry always wins.

## Figures
- `N7_meshtastic_coexist.png`, airtime per packet and the range-vs-airtime plane for our LoRaWAN vs Meshtastic presets on the same SX1262.
