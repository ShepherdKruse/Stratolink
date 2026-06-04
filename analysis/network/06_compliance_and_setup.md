# Meshtastic relay: adversarial compliance review + setup requirements

Due-diligence before bench-testing an airborne open Meshtastic relay on Stratolink.
Primary-source verified (FCC CFR Part 15 text, ETSI EN 300 220, Meshtastic firmware
`master` @ 2026-06-02). Skeptic's stance: assume it's non-compliant until shown otherwise.

## Bottom line

- **Registration: NONE needed to relay.** Meshtastic has *no* TTN-style join server,
  DevEUI/AppKey, account, or authority, it's serverless. A node in **REPEATER role +
  `ALL_SKIP_DECODING`** rebroadcasts the opaque AES ciphertext with **zero identity,
  keys, PSK, or registration**. "Just relay the signals we receive" is exactly a
  supported mode. You only match **region + LongFast preset + frequency** (RF compat,
  not auth).
- **Airborne ISM itself is legal in the US**, there is *no* aircraft ban in §15.247/
  §15.249 (only §15.250 and §15.521 ban airborne, neither our band). 
- **The real US catch:** a **single-channel, non-hopping, <500 kHz LoRa carrier** (which
  is what a Meshtastic relay is, LongFast = BW250) has **no clean Part 15 basis**: it
  fails §15.247 (needs ≥500 kHz *or* frequency hopping) and grossly exceeds §15.249
  (~-1 dBm field-strength limit). This is true of the **entire default US Meshtastic
  network**, not just us. The rigorously-clean option is a **BW≥500 kHz preset**; the
  tradeoff is it leaves the default LongFast mesh. (Our *LoRaWAN telemetry* rides the
  standard certified LoRaWAN basis, separate question.)
- **EU:** power/duty fine if we honor **10%** (our 7.5% cap does), but **airborne SRD
  permission for the 869.4-869.65 / 500 mW band is UNRESOLVED** (Ofcom IR 2030 sources
  conflicted), verify per country before flying.
- **Cross-border overflight** is the largest unmanaged exposure: 915 MHz is **Region-2-
  only** (not legal in EU/Africa), 868 not legal in Region 2; there's no ITU "transit"
  license. The **region geofence we already have is the main control** + minimal power;
  accept that some sovereign states would still call it illegal. The HAB community flies
  low-power and ignores it; zero enforcement on record.
- **Encryption is fine on ISM**, and *forces* us to stay ISM (amateur bands ban
  encryption per §97.113). Routinely flown, no enforcement found, but that's "low risk,"
  **not** an official green light.

## 1. Do we need to register each balloon? (No, the TTN contrast)

| | TTN / LoRaWAN | Meshtastic |
| --- | --- | --- |
| Central authority / join server | **Required** (DevEUI + AppKey provisioned) | **None**, serverless flooding mesh |
| Identity to **relay** | n/a | **None**, no NodeNum, no keys, no PSK |
| Identity to **originate** a beacon | n/a | self-assigned NodeNum (auto, from MAC; not registered) + default channel |
| Account / map | n/a | MQTT + map are **opt-in, off by default**, not needed to serve |
| Callsign/ID | n/a | **none** on ISM; only HAM mode needs a callsign (and disables encryption) |

- **Pure relay = `REPEATER` role + rebroadcast mode `ALL_SKIP_DECODING`** → *"rebroadcasts valid LoRa packets without trying to decrypt them … relays for encrypted channels even if it doesn't have the channel's PSK"* (firmware/docs). Forwards opaque ciphertext, decrements hop. Nothing to register, claim, or key. (There's also a dedicated `Meshtastic-repeater` firmware, but it's WIP/not-functional yet, use the in-tree REPEATER role.)
- **NodeNum** (only relevant if we also *originate*) = bottom 4 bytes of the MAC, self-chosen at first boot, random fallback on collision; **not registered anywhere**, not a durable serial (can change on collision/update).
- **To originate** a "Stratolink overhead" beacon: the auto NodeNum + the default public channel (**name LongFast, PSK `AQ==` = 0x01 → the well-known 16-byte key**), receivable by any stock node, still nothing registered.
- **Minimum interop** = region + modem preset (LongFast) + frequency. PSK only to originate/decode, **not** to relay.

→ **Answer: we can simply relay what we receive, with no registration.** Originating our own beacon adds only a free self-assigned NodeNum + the public channel config.

## 2. Adversarial compliance matrix

| # | Item | Rating | Skeptic's one-liner |
|---|------|--------|---------------------|
| US-1 | Airborne Part 15 in 902-928 (the airborne question) | **Legal** | No aircraft ban in §15.247/§15.249; only §15.250 & §15.521 ban airborne. |
| US-2 | Basis for single-channel BW250 non-hopping relay carrier @ +14-22 dBm | **Gray → weak** | Fails §15.247 (needs ≥500 kHz or FHSS); far over §15.249 (~-1 dBm). Whole US Meshtastic mesh shares this. |
| US-3 | §15.5 harmful-interference from a ~1,000 km footprint | **Gray** | Must cease on FCC notice; big footprint ↑ interference odds; rarely enforced. |
| EU-1 | 869.4-869.65 power/duty (500 mW, 10%) | **Legal if duty honored** | Our 7.5% cap < 10%; never set `override_duty_cycle`. |
| EU-2 | Airborne SRD permission for the 500 mW band | **UNRESOLVED** | IR 2030 default "no airborne unless stated"; sources conflict, verify per country. |
| X-1 | Cross-border overflight / wrong-region windows | **Gray → prohibited in some states** | 915 = Region 2 only; 868 illegal in Region 2; no ITU transit license. |
| C-1 | AES encryption on ISM | **Legal** | Part 15 / EU SRD don't restrict content. |
| C-2 | Open relay forwarding others' (unreadable) traffic | **Gray (non-spectrum)** | No Part 15 carrier duty; minor general liability; worse under Part 97. |
| H-1 | Must stay ISM (not amateur) because we encrypt | **Confirmed** | §97.113 bans encryption; §97.119 needs callsign, encrypted relay ⇒ ISM only. |
| R-1 | Real-world enforcement | **Low risk, not a green light** | Balloons flown routinely (206 km record, +22 dBm); zero enforcement found; no official airborne guidance. |

## 3. Actionable decisions (before flight)

1. **US bandwidth decision (the one real lever).** For a rigorously-clean US Part 15
   basis, use a **BW ≥ 500 kHz** Meshtastic preset (ShortTurbo SF7/BW500 or LongTurbo
   SF11/BW500) → qualifies under §15.247 at up to 1 W. **Cost:** it's a *different
   frequency slot / mesh* than the default LongFast (SF11/BW250), so you'd relay for the
   BW500 community, not the default public mesh. **Alternative:** match the default
   **LongFast (BW250)** to actually help the existing public mesh, and accept the same
   gray Part 15 basis the whole US ecosystem operates under. This is a values call -
   maximal interop (BW250, gray) vs maximal compliance (BW500, fragmented). Worth a bench
   A/B and a deliberate decision.
2. **EU:** honor the 10% duty cycle (the 7.5% cap does), and **verify the current Ofcom
   IR 2030 row + each overflown country's table** for airborne permission on 869.4-869.65
   before relaying over Europe. Treat as open until confirmed.
3. **Cross-border:** the **region geofence is the compliance control**, it must *never*
   emit 915 over Region 1 or 868 over Region 2 (we already geofence the LoRaWAN band by
   lat/lon; the relay must use the *same* gate). Keep power minimal. Accept residual
   sovereign-law exposure that no one can clear.
4. **Stay ISM, keep encryption.** Do not switch to amateur mode to gain power, it would
   force plaintext (§97.113) and a periodic callsign, and the encrypted-relay value
   disappears.
5. **Be a measured good citizen** (ROUTER_LATE, AirUtilTX cap, hop-1 from the relay
   design) and **log ChUtil**, "low risk" rests on staying genuinely low-impact.

## 4. Bench-test checklist (have data before we cut firmware)

- **Wake-on-RxDone from STOP**, verify the radio RX-listens while the MCU sleeps and
  wakes on RxDone (needs `EWRFIRQ` in PWR_CR3); measure relay-listen current (the 5.5 mA
  vs ~10 mA question). *This sizes the whole power-gated duty.*
- **Mode-switch**, time a LoRaWAN→Meshtastic radio reconfigure (standby + setSF/BW/
  freq/syncword(0x2B)/preamble(16)/CRC); confirm < a few ms and that LoRaWAN TX still
  works after switching back (BUSY-line/DIO-IRQ gotchas).
- **Header-only forward**, confirm we can RX a real LongFast packet, parse the 16-byte
  header, decrement hop_limit (flags & 0x07), and re-TX verbatim, received by a stock
  Meshtastic node, **without any PSK**.
- **BW250 vs BW500**, A/B interop (does a stock LongFast node hear us?) vs the §15.247
  basis, to make decision #1 with data.
- **Duty/airtime**, measure actual AirUtilTX/ChUtil under a realistic packet load;
  confirm the 7.5% cap holds and EU 10% is never breached.

## Sources
Adversarial RF review + Meshtastic-registration research (2026-06-02), both primary-source
verified, see the per-item citations in the research (FCC CFR §15.5/15.247/15.249/15.250/
15.521, §97.113/97.119; ETSI EN 300 220-2; Ofcom IR 2030 [unresolved]; Meshtastic firmware
NodeDB.cpp/Channels.cpp/AdminModule.cpp + device-role/lora/channels docs).
