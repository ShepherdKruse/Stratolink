# SF / airtime / range optimization — the biggest lever

The link, not the antenna, was the binding constraint on flight-3 (Parts A–C
largely exonerated the antenna: a well-matched 2.7 dBi horizon radiator, thermally
stable). This quantifies the spreading factor — the single largest dB lever we have.
Canonical Semtech formulas, our real 35 B payload. Code `_link.py` + `90_sf_linkbudget.py`,
figures `D1`–`D3`, data `sf_scorecard.csv`. Numbers verbatim (2026-06-01).

## Scorecard (35 B payload + 13 B MAC, BW125, CR4/5, TX 14 dBm)
| SF | ToA (ms) | sensitivity (dBm) | gain vs SF7 | FUP max/day | range US915 (km) | range EU868 (km) |
|---|---|---|---|---|---|---|
| **7 (flown)** | **97.5** | **−124.5** | — | **308** | **329** | 343 |
| 8 | 174.6 | −127.0 | +2.5 dB | 172 | 439 | 458 |
| 9 | 308.2 | −129.5 | +5.0 dB | 97 | 586 | 610 |
| 10 | 575.5 | −132.0 | +7.5 dB | 52 | 781 | 814 |
| 11 | 1232.9 | −134.5 | +10.0 dB | 24 | 1041 | 1085 |
| 12 | 2302.0 | −137.0 | +12.5 dB | 13 | 1389 | 1447 |

Radio horizon (4/3-earth): **412 km @10 km, 452 km @12 km.** Flight-3 best FRESH
reception: **252 km** (at SF7); median 68 km.

## The three coupled facts

1. **SF7 is link-budget-limited BELOW the horizon (D2).** SF7 reaches 329 km but the
   geometry allows 412 km — and we only achieved 252 km (polarization/fade eats the
   rest). So at SF7 we leave range on the table the horizon would permit. Raising SF
   converts that unused horizon margin into real reach: **SF9 (586 km) and SF10
   (781 km) are horizon-limited, not budget-limited** — at 10 km altitude everything
   past ~SF9–10 is wasted on range (though the lower floor still helps marginal links
   get decoded at any distance).

2. **Each SF step = +2.5 dB floor but ~1.8× airtime (D3).** +2.5 dB ≈ 1.33× range per
   step. The cost is exponential time-on-air: SF7 97 ms → SF12 2.3 s.

3. **The FUP wall couples SF to cadence (D1).** TTN Fair-Use = 30 s airtime/day. At our
   **current 300 s cadence, SF7 already uses 28.1 / 30 s — we are maxed out.** You
   CANNOT raise SF for free: SF8@300s = 50 s/day (illegal). To raise SF you must slow
   the cadence:
   - SF9 needs ≥ ~890 s (15 min) → 97 uplinks/day
   - SF10 needs ≥ ~1660 s (28 min) → 52 uplinks/day
   - SF12 needs ≥ ~6600 s (110 min) → 13 uplinks/day

## Recommendation: spend the FUP budget on range, not packet rate

For a balloon over **sparse** gateways, each packet *getting heard* matters far more
than packet rate (Part A: 86% of the flight had no fresh-position uplink heard at all
in some regions; the Atlantic/Morocco gaps were coverage, not cadence). A fix every
15 min that's *heard* beats a fix every 5 min that isn't. So:

| region | DR cap | recommended | cadence | uplinks/day | why |
|---|---|---|---|---|---|
| **US915 / AU915** | SF10 (DR0) | **SF9 @ 900 s** | 15 min | 97 | +5 dB (≈1.8× range) fills the horizon; FUP-legal; 97 fixes/day ample. SF10 is the regional floor if we want max reach (28-min cadence). |
| **EU868 / AS923** | SF12 (DR0) | **SF9 @ 900 s** (option SF10) | 15 min | 97 | same; EU *can* go SF12 (1389 km) but that's far past the 412 km horizon — pure airtime waste at float. SF9–10 is the sweet spot. |

**Net: pin SF9, slow cadence to ~15 min.** +5 dB is ~2× the dB any antenna change can
give (Part B: ~1–3 dB), at zero hardware cost — just firmware constants
(`TRANSMIT_INTERVAL_SEC`, `tx_sf`). This is the highest-leverage single change for v2.

### Nuances / honest caveats
- **Adaptive SF** is the sophisticated play: SF7 + fast cadence when a gateway is near
  (ascent, populated regions), step to SF9–10 + slow cadence over open ocean / sparse
  coverage. LoRaWAN ADR can't do this airborne (no downlink contact), so it'd be a
  custom geofenced rule like the region manager already does — a v2 firmware feature.
- The flown **252 km < SF7's 329 km budget** says ~2–4 dB is lost to polarization +
  fade (the spinning payload, Part A/B). SF margin directly buys that back.
- **RX1 downlink window** uses join_sf (SF10 in US/AU) — raising uplink SF doesn't
  touch the join/downlink path, so the multi-region OTAA that worked stays intact.
- Numbers assume the published Semtech sensitivity; **bench-verify RSSI/SNR vs SF on
  the spare boards** before committing (the next hardware step).
- FUP is a TTN *policy*, not a regulator limit; the hard legal limit is regional duty
  cycle (EU868 1%, US915 dwell). At SF9/900 s we are far under both.

## Figures
- `D1_airtime_fup.png` — airtime explosion + FUP-feasible (SF, interval) region.
- `D2_range_vs_sf.png` — range vs SF with horizon and flight-3 achieved overlaid.
- `D3_db_vs_airtime.png` — dB gained vs airtime spent, with the 300 s FUP wall.
