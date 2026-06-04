# Closing the ocean gap (the 8-day silence)

The defining failure of flight-3 was the ~8-day Atlantic silence. No terrestrial
network, TTN, Helium, or any other, has gateways over open ocean, so this is a
fundamentally different problem from the Helium question. This memo answers: the
balloon-to-balloon relay physics, the cross-region frequency problem, how other
global balloons actually do it, and which non-terrestrial networks fit. Physics is
script output (`40_ocean_relay_physics.py`); network state is dated web research
(sources inline).

## Bottom line (ranked)

1. **Lacuna Space, satellite uplink that REUSES our SX1262.** Lacuna's
   satellite mode is **LR-FHSS**, a modulation our SX1262 already supports via
   firmware (not new silicon). This is the ocean analog of the radio-reuse we
   hoped Helium would be, except it actually covers open ocean. **~0 g added
   hardware**; the work is firmware + their node stack + partner onboarding.
   **Pursue first.** (verify: Lacuna doesn't publish device TX/antenna/link budget.)
2. **HF WSPR beacon, the proven amateur ocean solution, as a parallel payload.**
   How sub-$100 balloons circle the globe 30× ([JR29: 32 laps, 528 days](https://www.theastroimager.com/picoballoning/pico-ballooning/)):
   a ~2 g, ~27 mW beacon on 20 m (14 MHz), heard worldwide by the WSPRnet
   volunteer network via the ionosphere, *no satellites, no own ground station*.
   Different radio + a ~5 m wire antenna, beacon-only (~bytes/cycle), but ~$14-class
   and battle-tested. Flies happily alongside the LoRa payload.
3. **Iridium SBD, the heavyweight, bulletproof fallback.** True pole-to-pole incl.
   ocean (66-sat mesh). But ~45 g (RockBLOCK) + ~45-50 mA TX bursts + ~$17/mo -
   the mass and TX current fight our supercap budget. Use only if Lacuna access
   stalls and we can spare the mass/power.
4. **Balloon-to-balloon relay, real physics, but not the near-term answer.** A
   single hop is feasible; a free-drifting *chain* is not (below). Revisit only at
   fleet scale with store-and-forward.

## The balloon-to-balloon relay physics (`O1_b2b_relay_physics.png`)

- **Line-of-sight:** a balloon at 10 km sees the sea horizon at **412 km**; two
  balloons at 10 km see *each other* at **825 km** (4/3-earth).
- **Raw-LoRa P2P link budget** (TX 14 dBm, 2×2.15 dBi, 2 dB pol/fade, 915 MHz):
  SF9 = 510 km, SF10 = 680 km, SF11/12 become **LOS-limited at 825 km**. So a hop
  of ~500-825 km is physically sound, *better* than our ground links because both
  ends are high and the path is clear.
- **Chain to span the Atlantic:** best case **~8-12 balloons** (perfectly spaced,
  SF9-12) for a 3,500-5,500 km crossing.
- **Why it still doesn't work for us now:** that's the *perfectly-spaced* count.
  Free-drifting balloons scatter in 2-D on the winds, you cannot hold a 1-D chain
  across an ocean. Realistic operation is **store-and-forward / delay-tolerant**: a
  balloon buffers fixes and dumps them on any opportunistic B2B or ground contact.
  Coverage is then *statistical in fleet size*, not guaranteed for one balloon
  crossing now. **No amateur balloon-to-balloon relay has ever worked**; the only
  stratospheric mesh that ran in production was **Google Loon** (balloon→balloon→
  ground, even a 155 Mbit/s optical crosslink demo, 2016), and it **shut down in
  2021 on economics**, not physics. Verdict: a constellation play for *later*, not
  the fix for the next flight.

## Different frequencies across regions (the question)

This is the subtle, important part, and the answer is reassuring:

- **The region split is a firmware/regulatory construct, not a hardware limit.**
  Our SX1262 tunes 150-960 MHz, and the antenna is already a ~900 MHz compromise
  that serves both 868 and 915. One radio covers every region we fly.
- **Ground LoRaWAN stays geofenced per region** (US915/EU868/AS923…), the
  firmware *already* does this (`region_manager.cpp` + `REGION_CREDS[]`). Nothing
  changes there.
- **For inter-balloon links, the two radios must be on the same frequency.**
  Meshtastic makes this concrete: a US915 node and an EU868 node **cannot** talk -
  different bands. Meshing requires matching region/frequency-slot + modem preset +
  channel/PSK. ([Meshtastic LoRa config](https://meshtastic.org/docs/configuration/radio/lora/)) But you can **force a common
  inter-balloon frequency** with `override_frequency` + a custom modem on both
  nodes (the SX1262 hardware doesn't care).
- **The elegant resolution, store-and-forward decouples regions entirely.** Data
  doesn't need RF to cross the 868/915 boundary; the *balloon physically carries
  it* across the ocean and uplinks via whatever region's LoRaWAN (or satellite) it
  reaches. So "different frequencies across regions" stops being a problem: each
  link is local and single-band; the data crosses regions by being carried, not by
  any radio bridging bands.
- **Over open ocean there is effectively no regional constraint.** Outside the
  12-nmi territorial sea the link is governed by flag/registry state + ITU Region,
  with no on-scene enforcement, so a single common inter-balloon channel is fine
  in practice. Caveats that bite over *land*: **EU868 has a real, enforced 1%/10%
  duty cycle**; the **US 902-928 band is license-exempt only in ITU Region 2** (not
  Europe); raw P2P is exempt from TTN's fair-use policy (that's TTN policy, not
  law). The clean, globally-harmonized legitimate path for inter-balloon links is a
  **ham allocation** (33/70 cm), but ham rules forbid encryption and require ID.
  ([ETSI EN 300 220](https://www.etsi.org/deliver/etsi_en/300200_300299/30022002/03.03.01_60/en_30022002v030301p.pdf), [eCFR §15.247](https://www.ecfr.gov/current/title-47/chapter-I/subchapter-A/part-15/subpart-C/subject-group-ECFR2f2e5828339709e/section-15.247), [rf.guru](https://shop.rf.guru/pages/meshtastic-meshcore-868-mhz-and-the-ham-radio-trap))
- **HF WSPR sidesteps the whole thing:** HF bands are globally harmonized, so there
  is *no* regional-frequency problem, one of its quiet virtues.

## How other global balloons actually do it

- **Amateur circumnavigators → HF WSPR on 20 m.** They never try to close a link to
  their own station; they beacon weak HF (10-100 mW, 50-bit messages, decodes at
  -28 dB SNR) and let the worldwide **WSPRnet** receiver net hear them via
  ionospheric skip. Telemetry (alt/voltage/temp/speed) is packed via the U4B
  600-channel two-packet scheme. Trackers: QRP Labs U4B (27 mW, 1.8 g), traquito
  JetPack ($14), ZachTek. **This is the dominant, proven method for round-the-world
  flights.** ([IEEE Spectrum, Jan 2026](https://spectrum.ieee.org/explore-stratosphere-diy-pico-balloon), [QRP Labs U4B](https://qrp-labs.com/u4b))
- **APRS (2 m)** works over land via ground digipeaters and dies over ocean, the
  same line-of-sight-to-ground failure our LoRa link has.
- **Professional / NASA / commercial → satellite backhaul.** NASA super-pressure
  balloons (circumnavigate every ~1-3 weeks) use **TDRSS (GEO) + Iridium**;
  Aerostar Thunderhead and World View Stratollite use **Iridium BLOS**. None fly a
  balloon mesh as the load-bearing link. ([NASA CSBF](https://csbf.nasa.gov/documents/ldb/LDB%20Support%20for%20Science%20EL-100-10-H%20rev%20B.pdf), [StratoCat](https://stratocat.com.ar/fichas-e/2024/SVS-20240227a.htm))

## Other networks beyond TTN / Helium (satellite IoT)

| Network | Reuses our SX1262? | Open ocean? | Mass/power | Status | Fit |
| --- | --- | --- | --- | --- | --- |
| **Lacuna Space** | **YES (LR-FHSS firmware)** | Yes (LEO, 15 sats) | ~0 g | Live, partner D2D Mar 2026 | **#1** |
| Iridium SBD (RockBLOCK) | No (L-band modem) | **Yes, best** | ~45 g, ~45 mA bursts | Live, proven | #2 fallback |
| Kineis (KIM1, Argos) | No (UHF modem) | Yes | low-power, 31 B msgs | Live (constellation done Mar 2025) | elegant if dedicated modem ok |
| Globalstar simplex | No | **No (bent-pipe, Atlantic gaps)** | small | Live | unfit |
| EchoStar Mobile | No (S-band 2 GHz) | **No (Europe GEO only)** |, | Live (EU) | unfit |
| Sateliot/Skylo/OQ/Myriota (NB-IoT NTN) | No (cellular modem) | Partial/ramping | cellular-class | Early/2026 | watch |
| **Swarm (SpaceX)** |, |, |, | **DEFUNCT (EOL Sep 2024)** | exclude |

The decisive split: **Lacuna is the only option that reuses our radio** (firmware/
network change, no mass). Everything else needs a dedicated modem (mass + power +
cost). ([Lacuna LoneWhisper](https://lacuna-space.com/technology/lonewhisper/), [Semtech SX1262 LR-FHSS](https://www.semtech.com/products/wireless-rf/lora-connect/sx1262), [eeNews](https://www.eenewseurope.com/en/firmware-boost-for-lora-direct-satellite-connections/))

## Recommendation / sequencing

1. **Engage Lacuna Space**, confirm SX1262 device requirements, link budget, TX/
   antenna, and partner terms. If it checks out, this closes the ocean gap with a
   firmware change and ~0 g. Highest-leverage move on the whole network problem.
2. **Prototype an HF WSPR beacon as a parallel global-position payload** (U4B-class,
   ~2 g). Proven, cheap, independent of LoRa/satellite; the ~5 m HF wire is the
   only real cost. Gives global position even if everything else fails.
3. **Add `tx_count` + `fix_age` to the payload** (ROADMAP item 1), still the
   prerequisite to interpret any gap.
4. **Balloon-to-balloon relay is a real fleet-scale play, not a dead end.** ~40-55
   balloons simultaneously in the corridor (SF10-12) ≈ 90% ocean coverage by
   store-and-forward (fig O2). The barrier is launch cadence (~hundreds/season),
   not physics, and that's the explicit "large constellation" vision. Architecture:
   one common 915-band relay channel + geofenced-TX compliance + store-and-forward
   (see above). Build on **MeshCore on RAK3172** (lighter than Meshtastic,
   configurable duty cycle, STM32WL-supported), or a custom raw-LoRa P2P layer on
   our hand-rolled stack. Complementary to Lacuna: Lacuna gives one-balloon ocean
   coverage now; the relay mesh makes the *fleet* self-sufficient (no per-message
   external cost) as it grows.

## Constellation B2B at fleet scale (the cheap-balloon argument)

The "can't hold a chain" objection dissolves with a fleet: you don't hold a 1-D
chain, you flood the corridor densely enough that an opportunistic store-and-
forward mesh PERCOLATES to a coast. Monte-Carlo over the N-Atlantic jet corridor
(`50_constellation_coverage.py`, fig O2), fleet size for X% of ocean balloons to
reach a coast by multi-hop relay:

| B2B hop | 50% ocean coverage | 90% |
| --- | --- | --- |
| SF9 (510 km) | 60 | 90 |
| SF10 (680 km) | 35 | 55 |
| SF12 (825 km, LOS) | **25** | **40** |

**~40-55 balloons simultaneously in the corridor (SF10-12) ≈ 90% ocean coverage**,
with a sharp percolation onset. Implications:
- **Higher SF wins for B2B**: SF12's 825 km hops need ~40 balloons vs SF9's ~90.
  B2B is raw P2P (no TTN fair-use); over ocean airtime is unregulated, so SF12's
  16× airtime is "free" there (power permitting). Use high SF for the relay.
- **The barrier is launch logistics, not radio.** Holding ~50 in the corridor
  (residence ~7 days) needs ~7 launches/day sustained, hundreds of balloons over
  a season (~$50k at $80 each, before attrition). A real program commitment, but
  it *is* the "large constellation" vision, and economically conceivable in a way a
  chain of 8 hand-placed balloons never was.
- **Latency = store-and-forward** (hours-days to reach a coast), vastly better
  than an 8-day blackout, fine for a position beacon.
- **Caveat:** N* scales with corridor area; tighter jet confinement lowers it,
  global dispersion raises it. The jet tends to band them, which helps.

## Single-antenna frequency architecture for B2B (the definitive answer)

One antenna (~900 MHz, already serves 868+915), one half-duplex radio, two jobs
time-shared: (1) **ground LoRaWAN uplink**, region-geofenced as today; (2)
**inter-balloon relay** on ONE common constellation channel, identical for every
balloon everywhere (they can't relay otherwise).

- **Will a US-band balloon and an ocean balloon talk?** Yes, *if both are on the
  common relay channel at that instant*. The radio time-shares: default = listen/
  relay on `F_relay`; pop to region-LoRaWAN only to offload to a ground gateway,
  then back. A near-coast balloon is the bridge: RX the ocean mesh on `F_relay`,
  dump the buffer to the local network on the region band.
- **One frequency for all, legal?** There is **no single sub-GHz channel
  license-exempt in BOTH the Americas (902-928) and Europe (863-870)**, so a
  "globally-compliant single ISM frequency" doesn't exist. Resolution (which our
  geofence already enables): put **`F_relay` in the 915 band** (antenna-friendly)
  and **geofence the B2B *transmit*: ON over ocean (international waters,
  unregulated) + the Americas; OFF over EU/863-870 land.** RX is not a regulated
  emission, so a balloon may still *listen* on `F_relay` anywhere. This works
  because **relay is only needed over ocean**, over dense-gateway regions a balloon
  offloads straight to ground, so the one compliance-sensitive zone (EU land) is
  exactly where we don't transmit B2B anyway.
- **Store-and-forward decouples the bands**: data crosses the 868/915 line by being
  *carried* in a buffer, not by any radio bridging bands.
- **Fully-legal-global variant**: run the relay under a **ham license** (callsign,
  no encryption) on a harmonized amateur band, but 70 cm needs a second antenna
  (mass), so for a single-antenna 10 g payload the 915-band + geofenced-TX approach
  is best.

**Best answer:** one common relay channel in the 915 band; the firmware's existing
region geofence gates *when/where* B2B transmits (ocean + Americas yes, EU land no);
RX always on; offload via local LoRaWAN. One antenna, one radio, no new hardware,
compliant where it emits, relay where it's needed.

## Figures
- `O1_b2b_relay_physics.png`, B2B hop vs SF (link budget vs LOS) and chain size to span the Atlantic.
- `O2_constellation_coverage.png`, fleet size vs ocean relay coverage (percolation), + a sample realization.
