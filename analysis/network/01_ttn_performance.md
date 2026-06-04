# How TTN actually performed for Stratolink-3

Empirical baseline for the network-choice study (TTN vs Helium vs Meshtastic).
All numbers are script output from `analysis/network/10_gateway_census.py` +
`20_network_plots.py`, run against Supabase `public.telemetry` on 2026-06-01.
Flight devices only (`stratolink-3`, `stratolink-3-eu`); the `stratolink-2`
bench board on the same table is excluded.

**Method note, band, not device_id.** The TTN webhook collapses late EU868
uplinks onto the `stratolink-3` (US app) device id (commit 0e1a39a), so
`device_id` is NOT a reliable RF-band tag. True band is derived from
`frequency_hz`: 868.x MHz → EU868, 90x MHz → US915. Pre-launch rows (before
2026-05-17 14:00 UTC, GPS class PRE_LAUNCH) are excluded from flight stats -
they include strong bench receptions (RSSI to -43 dBm) that would otherwise
flatter the numbers.

## Headline

TTN performance for us was **entirely a function of ground-gateway density under
the flight path**, it had almost nothing to do with our radio. Three regimes:

| Regime | Named gw | Anonymized | gw / uplink | RSSI median |
| --- | --- | --- | --- | --- |
| **CONUS (US915)** | 9 | 77 % | mean 2.0, **median 1, 60 % solo** | -112 dBm |
| **Iberia (EU868)** | 140 | 8 % | mean 20.6, **median 20, 0 % solo** | -115 dBm |
| **Atlantic** | 0 |, | 0 (8.4-day silence) |, |

## Counts (verbatim)

- Uplinks (flight devices): 458 total, 281 post-launch. GPS class post-launch:
  **STALE 216 / FRESH 39 / NOGPS 26** (77 % stale, the keystone bug, unrelated
  to the link but it poisons geometry, so range/angle stats use FRESH only).
- Receptions (uplink × receiving gateway): **3,692** total, **3,516** in-flight.
- Distinct **named** gateways that heard us: **149** (US915 **9**, EU868 **140**).
- The named gateways are overwhelmingly a Spanish smart-agriculture TTN mesh:
  `cicytex-*` (CICYTEX, Extremadura ag research), `ifapa-*` (Andalusian ag
  institute), `sg50-perte-malpica-*`, `*-smartalmond`, `mtcdtip02-*`. EU-funded
  rural IoT, not hobbyists. Top single gateway `cicytex-ic003` heard **119**
  distinct uplinks by itself.

## The Packet Broker / anonymization finding (matters for Helium)

- **616 / 3,692 receptions (16.7 %) came in anonymized**, `gateway_id =
  "packetbroker"` (417, coarsened/no coords) or null (199, top-level RSSI only,
  no `gateways[]` array). These are uplinks that reached us via **cross-network
  roaming through The Things Stack Packet Broker**, with the receiving gateway's
  identity, network, and location stripped.
- **Of 457 heard uplinks, 246 (54 %) were heard ONLY by anonymized gateways** -
  for over half our contacts, the *only* thing that heard us is something TTN
  won't identify. On the US915 leg specifically, **77 %** of receptions were
  anonymized vs **8 %** in Spain.
- **Implication (VERIFIED 2026-06-01, see `02_helium_assessment.md`):** Packet
  Broker peers TTN's own clusters (eu1/nam1/au1) and other PB-connected networks
 , but **NOT Helium**, which uses a separate, *unidirectional* roaming path
  (Helium Packet Router → an external LNS), not Packet Broker. So these
  anonymized receptions are almost certainly **inter-TTN-cluster** roaming (our
  nam1-homed uplinks heard by eu1-registered Spanish gateways; US gateways that
  registered on eu1), **we are NOT currently heard by Helium for free.** Helium
  coverage would therefore be genuinely *additive*, gated only by Helium gateway
  density on our track (quantified in the Helium assessment).

## Signal: we lived on the floor

- RSSI (flight): US915 median -112 (p10 -118, min -126); EU868 median -115
  (p10 -119, **min -129**). SNR medians -2.8 (US) / -4.5 (EU).
- The EU868 distribution piles up between -110 and -120 dBm with a tail to **-129
  dBm, at/below the nominal SF7 sensitivity floor (-124.5 dBm)**, i.e. good
  SX130x concentrators pulling us out 4-5 dB under nominal. We flew **SF7 for the
  entire flight** (281/281 post-launch uplinks SF7; 34 SF10 receptions are
  join-era). See fig N2.
- This is the quantified case for the SF lever: dropping the floor to SF9
  (-129.5 dBm) would convert marginal-miss links into hits. The dense-Spain
  receptions don't need it; the *sparse* legs (CONUS, ocean edges, the
  Salamanca→Málaga stretch) are exactly where extra floor margin buys coverage.

## Gaps

- **Atlantic: 201 h (8.4 d) silence**, zero gateways over open ocean. Expected
  and unavoidable for a ground-gateway network; this is the single biggest
  argument for an off-grid path (satellite, or balloon-to-balloon relay).
- **Salamanca→Málaga: 24.5 h** with TTN coverage present along the path, device
  was either not transmitting or not heard. No `tx_count` in the payload to
  disambiguate (ROADMAP item 1). Distinct from the ocean gap.

## Figures (light theme, `analysis/network/figs/`)

- `N1_gateway_diversity.png`, gw-per-uplink histogram, US915 vs EU868. The pattern.
- `N2_rssi_vs_floor.png`, RSSI distribution vs SF7/9/10 sensitivity floors.
- `N3_timeline.png`, gw/uplink + best-RSSI over time; the two silences shaded.
- `N4_coverage_map.png`, 75 geolocated gateways (self-reported + TTN registry)
  + fresh-fix track; two islands of coverage (California, Iberia) across the void.

## What this tells the network decision

1. **The binding constraint is gateway geography, not the radio.** Any network's
   value to us = its gateway density under high-altitude balloon tracks. Evaluate
   Helium/others on *that*, on our actual and likely-future paths.
2. **We already roam.** 1 in 6 receptions is cross-network. Quantify the marginal
   gain of explicit multi-join before paying complexity for it.
3. **Redundancy collapses to 1 off the dense mesh.** 60 % of CONUS uplinks were
   single-gateway, no diversity, no margin. More networks = more independent
   ears exactly where we're thin.
4. **Nothing terrestrial solves the ocean.** 8.4 days dark. Only a non-terrestrial
   relay (sat backhaul, or a balloon constellation doing store-and-forward) closes
   it, which is precisely the Meshtastic-relay / balloon-to-balloon thread.
