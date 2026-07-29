# Stratolink LoRaWAN Link Characterization — Implementation Plan

> Research output from sub-agent investigation. Link-budget modeling, coverage geometry at altitude, gateway-diversity analytics, PacketBroker un-collapse, TTN Mapper cross-reference.

## 1. Link budget model

Use the canonical formulation:

```
RSSI(dBm) = P_TX + G_TX - L_cable - PL_FS - L_atm - L_pol + G_RX
```

**FSPL** (Friis, free space):
```
PL_FS(dB) = 20·log10(d_km) + 20·log10(f_MHz) + 32.45
```
At 904.5 MHz and 400 km: 20·log10(400) + 20·log10(904.5) + 32.45 ≈ **143.6 dB**.

**Demodulator floor** at SF7/BW125 (kTB + NF + SNR_lim):
```
S_min = -174 + 10·log10(125e3) + NF + SNR_lim(SF)
      = -174 + 50.97 + 6 + (-7.5)  ≈ -124.5 dBm
```
Bake the SF→SNR_lim and SF→sensitivity table directly into code (Semtech datasheet values, BW=125 kHz): SF7=-7.5/-123, SF8=-10/-126, SF9=-12.5/-129, SF10=-15/-132, SF11=-17.5/-134, SF12=-20/-137 dB / dBm. NF=6 dB is Semtech-cited typical.

**Atmospheric absorption at 904.5 MHz: effectively zero.** ITU-R P.676 specific attenuation at 1 GHz, sea-level, standard atmosphere is ~0.005 dB/km — and it falls with altitude as density drops. Over a 500 km slant from 20 km altitude through a thinning column you accumulate well under 0.1 dB. Model it as a constant 0.1 dB and move on; do not bother integrating the Liebert line spectrum. (If you ever want to be rigorous, use the `itur` package: `itur.models.itu676.gaseous_attenuation_slant_path(f=0.9045, el, rho, P, T, h=h_km)`.)

**L_pol** (polarization mismatch antenna-to-antenna, balloon is tumbling, ground antennas vertical): worst-case 3 dB, expected ~1.5 dB. Fold into uncertainty band rather than constant.

**Link margin** for a CONUS ground station at d≈300 km, P_TX=20 dBm (US915 default), G_TX≈2 dBi (¼-wave wire), G_RX≈3 dBi (typical gateway omni):
```
RSSI ≈ 20 + 2 - 0 - 141 - 0.1 - 1.5 + 3 ≈ -117.6 dBm
margin = -117.6 - (-124.5) ≈ 6.9 dB
```
You are running on **fumes** at the horizon. Every dB matters. This justifies SF7 being marginal at long range — SF9 would buy you ~6 dB more, but TTN FUP at 5 min already locks SF7.

## 2. Coverage geometry

Geometric horizon: `d = sqrt(2·R_e·h + h²)` with R_e=6371 km gives 391/505/288 km at 12/20/6.5 km (matches your numbers).

**Refraction:** for 900 MHz at stratospheric altitudes the 4/3-earth (k=1.333) model is the right pick. It is a single-line code change (R_e *= 4/3) that adds ~15% range, giving 449/580/331 km. **Do not** use ducting models — at >10 km altitude you are *above* the troposphere where ducts form, so they are not in your path. Quote both geometric and 4/3-earth values in your output for transparency.

**Coverage disc area:** A = π·d². At h=15 km with k=4/3: A ≈ π·(525)² ≈ 866,000 km². CONUS is ~8M km², so each uplink "sees" ~10% of CONUS area.

**Gateway-density prior:** TTN Mapper does not publish a national density figure but the geojson dump at `http://ttnmapper.org/geojson` plus the CSV dumps at `http://ttnmapper.org/dumps` give per-gateway points. A reasonable empirical prior for CONUS is **0.02–0.10 gateways/km² urban, 0.001 rural**. Compute the actual density from your TTN Mapper pull rather than guessing — covered in §3.

## 3. TTN / PacketBroker analytics

**You can recover individual PacketBroker gateways**, but only some of them. The webhook payload contains a `packet_broker` sub-object alongside the collapsed `gateway_id: "packetbroker"` entry, with fields:
- `forwarder_net_id` (e.g. `000013` = TTN)
- `forwarder_tenant_id`
- `forwarder_gateway_id` (the originating gateway's device ID)
- `forwarder_gateway_eui`

**Action:** your webhook ingester is probably dropping this. Extend the parser to preserve `packet_broker.*` on every rx_metadata entry — backfill from raw webhook bodies if you have them in storage. After that change, "packetbroker" stops being a single bucket and you get per-real-gateway diversity.

**Caveat:** some TTN→TTI relays strip the `packet_broker` node entirely (known bug per the TTN forum). Treat those as "anonymous remote gateway" — count them for diversity but not for ID.

**Cross-reference data sources:**
- **TTN Mapper public dumps** (PDDL v1.0, no API key): `ttnmapper.org/dumps` CSV + `ttnmapper.org/geojson`. Pull the latest, load into a `GeoDataFrame`, build a spatial index of gateway lat/lon.
- **PacketBroker Mapper API**: `GET https://mapper.packetbroker.net/api/v2/gateways` returns netID/tenantID/id/eui/clusterID/location/online-status. Public, no auth. This is the canonical source for resolving `forwarder_net_id + forwarder_gateway_id` → coordinates.
- **Helium Mapper / Hotspotty**: Helium gateway locations are public on-chain; pull from explorer APIs.
- **LoRa Cloud / Semtech LoRa Edge**: paid, does device-side geolocation via TDOA — not relevant here.

## 4. Metrics to compute

- **PRR**: `received_uplinks / expected = received / (mission_seconds / 300)`. Bucket by 1-hour windows.
- **RSSI/SNR percentiles** (p10/p50/p90) binned by 1 km altitude.
- **Gateway diversity per uplink**: `len(rx_metadata)`, plus distinct `forwarder_gateway_id` count after the parser fix.
- **RSSI spread / SNR spread** within a single uplink (max-min across receivers) — measures geometric vs RF-path variance.
- **Measured–predicted RSSI residual** (per receiver where we know its lat/lon): mean and std. The std becomes your empirical fade margin.
- **Empirical gateway density**: cluster gateways from rx_metadata into a CONUS grid (0.5°×0.5°), divide by area.
- **Link margin time series**: per uplink, `min(rx_rssi) − S_min(SF)`.
- **TX retry counts**: not in telemetry. Flag clearly. Add to the §9 open-questions list — needs firmware MAC-layer counter pushed up as a frame-port-200 status payload.

## 5. Visualization plan

All in Plotly for the dashboard (interactive, ships to Next.js cleanly via `react-plotly.js`) plus Folium for static map exports:

- **RSSI vs altitude scatter**, colored by latitude band, with predicted-FSPL overlay curves at d=100/200/400 km.
- **Folium choropleth**: coverage disc per uplink overlaid on TTN Mapper gateway points; opacity by gateway count received.
- **Histogram**: gateway count vs altitude band (stacked: TTN-native vs PacketBroker-relayed).
- **Time-series ribbon**: link margin median with p10/p90 band, twinned y-axis with altitude.
- **Residual diagnostic**: measured−predicted RSSI vs distance; should be zero-mean if the model is right.

## 6. Validation strategy

1. **TTN Mapper cross-check**: for each uplink with a known forwarder_gateway_id, look up its position, compute predicted RSSI, compare to measured. Residual histogram tells you if your gain/cable-loss numbers are right.
2. **CONUS density sanity**: count rx_metadata gateways inside your coverage disc, divide by disc area, compare to TTN Mapper density in the same disc. Match within 2× is good.
3. **Range record check**: the TTN balloon record (702 km, 2019; SODAQ 354 km at 15 km altitude) sets the upper bound — if you predict reception beyond ~700 km regularly, something is wrong.
4. **FSPL residual**: residual should be 0 ± ~6 dB (multipath + fade). Bias >5 dB means systematic — antenna gain assumed wrong, cable loss missed, or TX power not what firmware reports.

## 7. Code architecture

```
analysis/lora/
├── __init__.py
├── constants.py         # SF→SNR_lim table, sensitivity table, R_e, c, NF
├── link_budget.py       # fspl(d,f), sensitivity(sf,bw,nf), rssi_predicted(...), margin(...)
├── coverage.py          # radio_horizon_km(h, k=4/3), coverage_disc_area(h, k)
├── atmosphere.py        # thin wrapper around itur for slant-path attenuation; default constant 0.1 dB
├── ingest.py            # parse webhook JSON → tidy DataFrame; preserve packet_broker.*
├── gateways.py          # TTN Mapper + PacketBroker Mapper clients with on-disk parquet cache
├── metrics.py           # PRR, diversity, residuals, density estimator
├── validation.py        # cross-check vs TTN Mapper, FSPL residual diagnostics
├── plot.py              # Plotly figures (return Figure objects, no .show()) + Folium maps
└── tests/
```

**Library pins:** `numpy`, `pandas`, `geopandas`, `shapely`, `pyproj`, `haversine`, `itur` (optional, only if exercising the line-by-line absorption model), `plotly`, `folium`, `httpx` (for TTN Mapper / PacketBroker pulls), `pyarrow` (parquet cache). **Skip** `pylorawan`/`pyliblorawan` — they are decoder libraries for MAC frames, not what you need. **Skip** the PyPI `link-budget` package (inactive, satellite-focused, not worth the dependency for ten lines of FSPL).

Wire ingest off your existing Supabase `uplinks` table — point `ingest.from_supabase(client, since=...)` at the same schema your webhook writes to. Keeps the Python pipeline cleanly off the hot path.

## 8. Pitfalls

- **Single-gateway RSSI in flat columns**: your `rssi`/`snr` columns are first-gateway-only and bias high (best receiver). Compute all metrics from `gateways` JSONB. Quote the flat columns only as a "first-heard" proxy.
- **PacketBroker collapse**: fixed by the parser change in §3 — until then, treat any `gateway_id=packetbroker` row as one anonymous reception, do not double-count.
- **Gateway position trust**: TTN Mapper positions are user-submitted, sometimes off by km. Filter out gateways with `accuracy > 1 km` or no recent activity.
- **Multipath at altitude**: minimal direct multipath (no nearby reflectors), but **ground bounce from balloon nadir** can cause 6 dB nulls. Expect higher RSSI variance at low elevation angles to a given gateway.
- **TTN FUP**: 30 s/day/device uplink airtime. SF7/BW125, 25-byte payload ≈ 56 ms ToA → 535 messages/day cap. At 5-min cadence you send 288/day — safe. Document this; if you ever upshift SF you blow through the budget fast.
- **Channel-hopping**: US915 cycles 902.3–914.9 MHz on uplink. Bin RSSI by channel before averaging or you smear narrow-band site-specific fades.
- **Frame counter rollover** on long missions — make sure ingest dedupes by (dev_eui, f_cnt) modulo 2^16.

## 9. Open questions to flag

1. **Per-gateway RSSI/SNR exposed in webhook?** Your flat columns drop everything past the first receiver — verify ingest writes the full `rx_metadata` array to JSONB, not just `[0]`.
2. **TX attempt / MAC retry counter** — surface from firmware as a status frame on a dedicated FPort.
3. **Real TX power as transmitted** (firmware-reported, after region clamping) vs configured — needed to close the link budget rigorously.
4. **Antenna orientation telemetry** (IMU quaternion at time of TX) — lets us model polarization loss instead of treating it as a constant.
5. **Receiver-side timing** — `received_at` per gateway gives you TDOA, which gives you a position fix on each gateway you don't have a location for. Worth the data volume.
6. **Channel-plan diagnostics** — log which of the 8 sub-band-2 channels was used; lets you flag whether one channel performs worse than others.

---

## Sources

- [SX1276/77/78/79 Semtech datasheet](https://cdn-shop.adafruit.com/product-files/3179/sx1276_77_78_79.pdf)
- [LoRa Spreading Factors Explained (SF7–SF12) — Avramut](https://vladavramut.substack.com/p/lora-spreading-factors-explained)
- [LoRa and High-Altitude Platforms: Path Loss, Link Budget and Optimum Altitude (IEEE)](https://ieeexplore.ieee.org/document/9642705/)
- [ITU-R P.676-13 Attenuation by atmospheric gases](https://www.itu.int/dms_pubrec/itu-r/rec/p/R-REC-P.676-13-202208-I!!PDF-E.pdf)
- [ITU-Rpy (`itur`) Python package](https://pypi.org/project/itur/)
- [TTN Fair Use Policy explained](https://www.thethingsnetwork.org/forum/t/fair-use-policy-explained/1300)
- [TTN forum — different structure for rx_metadata from packet broker](https://www.thethingsnetwork.org/forum/t/different-structure-for-rx-metadata-for-gateways-from-the-packet-broker/69365)
- [PacketBroker Mapper API](https://www.thethingsindustries.com/docs/concepts/packet-broker/api/)
- [TTN Mapper FAQ — geojson + CSV dumps, PDDL v1.0](https://docs.ttnmapper.org/FAQ.html)
- [packetbroker/api issue #23 — gateway identifier in metadata](https://github.com/packetbroker/api/issues/23)
- [TTN forum — GatewayID from packetbroker](https://www.thethingsnetwork.org/forum/t/gatewayid-from-packetbroker/46756)
- [TTN world record 702 km LoRaWAN reception](https://www.thethingsnetwork.org/article/ground-breaking-world-record-lorawan-packet-received-at-702-km-436-miles-distance)
- [SODAQ stratospheric balloon test — 354 km at 15 km altitude (TTN Labs)](https://www.thethingsnetwork.org/labs/story/lora-module-test-with-a-stratospheric-balloon)
- [Line-of-sight propagation, 4/3 Earth radius — Wikipedia](https://en.wikipedia.org/wiki/Line-of-sight_propagation)
- [haversine on PyPI](https://pypi.org/project/haversine/)
- [GeoPandas + Folium plotting guide](https://geopandas.org/en/stable/gallery/plotting_with_folium.html)
