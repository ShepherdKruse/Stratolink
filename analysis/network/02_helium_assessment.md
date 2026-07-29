# Helium for Stratolink: switch entirely, or run alongside TTN?

Decision memo. Built on the TTN baseline (`01_ttn_performance.md`), live Helium
hotspot data (`30/31_*.py`), the reconstructed path (Shepherd/Caleb, `main`), our
firmware, and dated web research. Numbers are script output; claims about Helium's
network state carry sources + dates (some changed post-2023, so verify before acting).

## Bottom line

- **Switch entirely to Helium: NO.** We got ~95 % of our telemetry from Spain's
  dense TTN agriculture mesh (140 named gateways, ~20 per uplink, *proven, live*
  coverage). Helium's effective coverage there is unproven and, per research,
  EU Helium IoT is metro-focused and declining. Switching trades a proven asset
  for an unproven one, and Helium can't do the ocean either.
- **Run Helium alongside TTN: YES, but as geofenced pick-one-per-region, not
  simultaneous.** A LoRaWAN device holds one network session at a time, so "both"
  = the firmware's existing per-region credential swap, extended to choose Helium
  over the **US** (where it is ~84× denser than TTN) and TTN over **Europe**.
  Low firmware effort; ~$235 one-time + a self-hosted LNS; data cost ~$0.73/yr.
- **Neither closes the gap that actually defined this flight.** The 8-day silence
  was **mostly the Atlantic**, where *no terrestrial network has gateways*. Helium
  could plausibly have **shortened** it by ~1-2 days (the eastern-US land transit)
 , not closed it. The ocean is the Meshtastic / balloon-to-balloon / satellite
  problem, not the Helium problem.

## What Helium is now (verified, 2025-2026)

- Still a **standard LoRaWAN network** an off-the-shelf device OTAA-joins; the
  device side is unchanged. ([docs.helium.com/iot/lorawan-on-helium](https://docs.helium.com/iot/lorawan-on-helium/))
- **Post-Solana (Apr 2023) it is bring-your-own-LNS.** The hosted Helium Console
  is deprecated ("should not be used for new projects"); production = run your own
  **ChirpStack** + buy an **OUI**. There is no free Nova-Labs catch-all server.
  The free **Educational LNS** (HIP-102) expires devices after ~1 day, testing
  only. ([docs.helium.com/iot/run-an-lns/configure-chirpstack](https://docs.helium.com/iot/run-an-lns/configure-chirpstack/), [HIP-102](https://github.com/helium/HIP/blob/main/0102-helium-educational-lns.md))
- **NOT peered with TTN.** Helium roaming is a *separate, unidirectional* path
  (Helium Packet Router → an external LNS via passive roaming / Semtech UDP), **not
  Packet Broker**. So the `packetbroker` receptions in our TTN data are inter-TTN-
  cluster, **not Helium**, we get **zero** Helium coverage today. (ChirpStack
  "Roaming with Helium"; [disk91 2022-05-20](https://www.disk91.com/2022/technology/lora/roaming-lorawan-with-helium-network/); TTI Packet Broker docs.) This is why Helium is *additive*.

## Coverage on our ACTUAL path (the substance)

Live Helium IoT hotspots pulled from the Entity API (`entities.nft.helium.io`,
free, H3-res8 coords). **Caveat:** the bulk API's `is_active` is unusable (false
for all), so these are *registered* hotspots = an **upper bound** on live coverage
(per Messari/ByteTree ~236k of ~385k+ are active, US-heavy; lots of dead post-boom
hotspots). Registered-vs-registered is the fair comparison; geography is the robust
signal.

**Registered density, same boxes (`30_helium_coverage.py`):**

| Region | TTN registered | Helium registered | Helium ÷ TTN |
| --- | --- | --- | --- |
| California | 510 | 52,921 | **104×** |
| CONUS overall | 3,980 | 334,663 | **84×** |
| Iberia overall | 2,238 | 16,071 | 7× |
| **Extremadura (our EU leg)** | 141 | 245 | **1.7×** |
| Atlantic (open water) | ~0 | ~0 |, |

**Helium within 300 km of each confirmed path anchor (`31_helium_along_path.py`):**
SF 19,896 · Monterey 21,372 · San Diego 36,302 · Sonora 6,131 · **Albuquerque
(last contact) 1,640**. Every land leg sat under thousands of Helium hotspots.

**The 8-day silence, dissected (Albuquerque → Spain great-circle, illustrative -
true route is an under-determined *region* per the main-branch engine):**
Albuquerque→Oklahoma→Carolinas = Helium-dense (5k-11k in range); **at the coast it
drops to 0 and stays 0 for the whole ocean (~64 % of the distance)**; Spain
lights up again (11k). See fig **N6**.

**Reading it:** Over the entire US/Mexico land track, Helium had thousands of
hotspots in range where TTN had a handful, and TTN heard us on a median of *one*
gateway over CONUS. So on **land**, Helium would very likely have added ears.
**But the silence that hurt us was the Atlantic**, and there Helium is as empty as
TTN. Best case (eastern-US route + actively transmitting), Helium shortens the
silence by the ~1.5-2 land days; it cannot touch the ~5-6 ocean days. Two
unknowns blunt even that: the route may have gone over **Canada** (sparse Helium),
and Flight-3 had no application-visible attempt/reset/fix-age diagnostics to
separate "not heard" from "not sent." The current telemetry-v2 design closes
most of that observability gap: it reports reset/boot/fresh-fix age, and its
pre-RF FCntUp reservation makes later counter gaps evidence of attempted frames.

## Why "switch entirely" loses

Spain was our telemetry jackpot: 140 live, purpose-built TTN ag-IoT gateways
(EU-funded: CICYTEX, IFAPA, smart-almond, PERTE) heard ~20 copies of every uplink.
Helium's Iberia advantage is only 1.7× in *registered* count in Extremadura, and
its EU IoT is metro-centric and declining (research). Going Helium-only means
self-hosting an LNS *and* betting our best-covered region on unproven coverage.
No.

## Why "add alongside" works, and how

- **Feasibility is high.** `firmware/src/lorawan.cpp` already carries a per-region
  `(DevEUI, AppKey)` table (`REGION_CREDS[]`) that hot-swaps on geofence
  transitions (`region_manager.cpp`). Helium is just another network's
  credentials + JoinEUI in that same structure. The multi-region OTAA switch
  already flew successfully (US915→EU868).
- **The constraint:** one LoRaWAN session at a time → you cannot be on TTN and
  Helium simultaneously. So "both" = **geofenced pick-one**: Helium over the US
  (84× denser), TTN over Europe (proven mesh). *Not* join-thrashing (re-joining
  both every cycle burns our scarce airtime/power budget, avoid).
- **Cost:** one-time ~$235 (OUI $100 + DevAddr block $100 + $35 DC escrow) +
  run/rent a ChirpStack LNS. Traffic is trivial: our 35 B payload = 2 DC =
  $0.00002/uplink → at SF9/15-min cadence (96/day) ≈ **$0.70/yr**. A DC "discount"
  is therefore meaningless, data was never the cost. ([docs.helium.com/tokens/data-credit](https://docs.helium.com/tokens/data-credit/), [buy-an-oui](https://docs.helium.com/iot/run-an-lns/buy-an-oui/))
- **Positive precedent:** Univ. of Wyoming HAB flights reported >95 % packet
  delivery over public Helium in sparse Wyoming (single study, treat as
  promising). ([AGU 2023 INV23B-0.4K](https://ui.adsabs.harvard.edu/abs/2023AGUFMINV23B0.4K/abstract))

## The partnership (Helium folks on Twitter)

Data cost is ~$0, so a DC discount is worthless to us. What would actually be
valuable, and worth asking for:
1. **Free/managed/sponsored LNS + OUI** so we skip the $235 + ChirpStack ops
   (removes the only real friction).
2. **Co-marketing**, "pico-balloon circumnavigates on Helium" is a strong story
   for both sides; this is the real value of the relationship.
3. Ask directly whether they have **any maritime/long-range coverage** roadmap
   (they don't today, but if a partner is deploying coastal/marine hotspots, that
   changes the ocean calculus). Don't expect yes.
Frame it as: we'll integrate Helium as the **US-leg network** for future
land-heavy flights; in return, sponsorship + a joint writeup.

## Recommendation / sequencing

1. **Keep TTN as primary.** It is free, proven, and owns our best region (Europe).
2. **Add Helium as a geofenced US-leg option** when convenient, small firmware
   add (extend `REGION_CREDS`), needs an LNS. High value for *future US/land-heavy*
   flights; modest value for transoceanic ones.
3. **Deploy and prove telemetry v2 first.** Its reset/boot/fresh-fix-age fields
   and pre-RF FCntUp reservation provide the gap diagnostics this memo originally
   requested; exact-image TTN/Supabase HIL is still required.
4. **The ocean gap is a different project**, Meshtastic relay / balloon-to-balloon
   / satellite. That's the next thread, and it's where the real coverage win is.

## Figures
- `N5_helium_vs_ttn.png`, Helium registered density vs the 75 TTN gateways that heard us.
- `N6_helium_along_path.png`, Helium density vs the reconstructed path; land-dense, ocean-zero.
