# UV follow-up evidence ledger

Access date: 2026-10-13, America/Los_Angeles. Prices and availability are observations, not reservations or purchase quotes. Public web extraction can differ from a live authenticated storefront; the saved root Browser captures take precedence for the LCSC/JLC checks. A failed page retrieval never means zero stock. No manufacturer or distributor was contacted, and no supplier cart was changed by this review.

## Primary engineering evidence

| Source | Exact evidence used | Limits |
|---|---|---|
| [ams AS7331 DS001047 v4-00, 2023-03-24](https://look.ams-osram.com/m/1856fd2c69c35605/original/AS7331-Spectral-UVA-B-C-Sensor.pdf) | Pin map, dimensions, supply/current, reference resistor, common gain/time settings, −40…85°C limits | Current direct manufacturer PDF rechecked; device current bounds retain table conditions, not measured flight power |
| [ams AS7331 design guide PD001048 v2-00, 2022-11-17](https://look.ams-osram.com/m/45d5dfb4a22ecb04/original/AS7331_Design_Guidelines_PD001048_2-00.pdf) | ±10° incidence constraint, diffuser placement above limiting optics, calibration corrections | Establishes optical design need; does not validate ozone retrieval |
| [ams AS7331 product page](https://ams-osram.com/products/sensor-solutions/ambient-light-color-spectral-proximity-sensors/ams-as7331-spectral-uv-sensor) | Three independent UV channels, displayed orderable status | Lifecycle status conflicts with distributors; no guaranteed sustainable supply |
| [ams AS7331 EVK guide UG001037 v3-00](https://docs.rs-online.com/a3b1/A700000010106066.pdf) | Board/interface and adapter scope, §§3,6 | Included adapter is not fully UV-opaque; exact kit contents may vary |
| [Vishay VEML6075 datasheet, document 84304 Rev 1.2](https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/1256/VEML6075.pdf) | Four-pin dimensions, UVA/UVB output channels and nominal 330nm B-channel peak | B label is not an ideal isolated UVB passband |
| [Vishay PTN-OSI-01059-2019-Rev-0](https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/320/PTN-OSI-01059-2019-Rev-0.pdf) | Product termination dated 2019-02-21 | Traceable remaining stock could still exist |
| [Renesas ZOPT2202 product](https://www.renesas.com/en/products/zopt2202), [datasheet dated 2016-09-21](https://www.renesas.com/en/document/dst/zopt2202-datasheet) | True separate UV bands, obsolete status, §3.3 incompatible LGA6 pin map, §3.4 raw mode | No verified available bare-device source; no full footprint proposed |
| [Silicon Labs Si1133 Rev 0.91](https://www.mouser.com/datasheet/2/368/Si1133-1397754.pdf) | Actual UV sensor, UV/UV-Deep mux, dark-reference subtraction, NRND marking | No independent characterized UVA/B pair established by the reviewed data |
| [Genicom GUVA-S12SD](https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/6128/GUVA-S12SD%20%282%29.pdf), [GUVB-S11SD Rev1.0 2018](https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/5786/GUVB-S11SD_Rev1.0_2018.pdf) | Two differing broad response functions, current scale, −30°C operating floor | Current/UV-index example is typical; ADC arithmetic is illustrative only |
| [ROHM ML8511A](https://www.rohm.com/documents/11303/4214223/FEDL8511A-02-e.pdf) | One analog output for combined UVA/B sensitivity | Does not supply an independent UV ratio |
| [ams AS7343](https://ams-osram.com/de/products/sensor-solutions/ambient-light-color-spectral-proximity-sensors/ams-as7343-spectral-sensor) | Visible/NIR multispectral range | Does not cover needed short UVB |
| [sGlux photodiodes](https://sglux.de/en/product-category/sic-uv-photodiodes/) | Filtered analog UV detector alternatives exist | No confirmed LCSC stock or selected front-end design |
| [Egli et al., AMT 16, 2889–2903 (2023)](https://amt.copernicus.org/articles/16/2889/2023/) | Spectral ratio/double-ratio ozone retrieval precedent | Instrument-specific research, not accuracy transferable to a broad-band chip |

The old LTR390 manufacturer PDF link repeatedly failed in the preceding audit. No new claim of a successful fresh Lite-On datasheet read is made. Existing reviewed documentation, board identity and `sensor_ltr390.cpp` establish separate selectable visible ALS and one UV measurement path. The native audit does not establish that historical flight UV values were calibrated spectral irradiance.

## Catalog and stock evidence

| Catalog / source | Result used | Evidence quality |
|---|---|---|
| [JLC AS7331 capture](../sourcing_followup/as7331-jlc-search.txt) | Seven SKU entries, zero assembly/idle/my stock | Root live Browser |
| [LCSC AS7331 capture](../sourcing_followup/lcsc-as7331-search.txt), [C17474749 detail](../sourcing_followup/lcsc-as7331-C17474749.txt) | Three direct-search chip entries zero; additional alias Out of Stock | Root live Browser |
| [JLC VEML6075 capture](../sourcing_followup/veml6075-jlc-search.txt), [canonical LCSC C75329](https://www.lcsc.com/product-detail/C75329.html) | JLC C75329/C19278419 zero; canonical page Not available now | Live Browser + opened public page |
| [LCSC Si1133 GMR](../sourcing_followup/lcsc-si1133-C965911.txt), [GM](../sourcing_followup/lcsc-si1133-C3678545.txt) | Both C965911 and C3678545 Not available now | Root live Browser, both captured |
| [LCSC Genicom page one](../sourcing_followup/lcsc-genicom-page1.txt), [page two](../sourcing_followup/lcsc-genicom-page2.txt), [category](https://www.lcsc.com/brand/1263-13647.html) | All 39 displayed results zero, 25 + 14 | Root live Browser; capture cell counts independently checked |
| [LCSC ZOPT2202 query](../sourcing_followup/lcsc-zopt2202-search.txt) | Exact-name search returns zero results | Root live Browser; does not exclude every possible alias |
| LCSC [C7200747](https://www.lcsc.com/product-detail/C7200747.html), [C6954997](https://www.lcsc.com/product-detail/C6954997.html), [C6565190](https://www.lcsc.com/product-detail/C6565190.html), [C5756514](https://www.lcsc.com/product-detail/C5756514.html) | Selected GUVA/GUVB exact product pages unavailable | Opened public pages |
| [DigiKey AQFM](https://www.digikey.com/en/products/detail/ams-osram-ag/AS7331-AQFM-OLGA16-LF-T-R/16983757), [AQFT](https://www.digikey.com/en/products/detail/ams-osram-ag/AS7331-T-OLGA16-LF-T-RDP/16983752) | Zero; estimated incoming November 9; AQFM quantity-one $9.16 | Opened public pages; arrival estimate not guaranteed |
| [Mouser AS7331 family](https://www.mouser.com/en/c/semiconductors/sensor-ics/ambient-light-sensors/?m=ams+OSRAM&series=AS7331) | AQFM zero; 9,090 expected November 23; $11.38 quantity one | Opened family page; some individual-product opens failed |
| [Future AQFM](https://www.futureelectronics.com/p/semiconductors--analog--sensors--light/as7331-aqfm-ams-osram-3169993) | Zero global/factory/on order; 1,000 minimum; 16 weeks | Opened current public page |
| [Avnet optical sensors](https://www.avnet.com/americas/manufacturers/m/c/ams-osram/sensors-and-transducers-optical-sensors/), [Arrow AQFT](https://www.arrow.com/en/products/as7331-aqft/ams-osram.html) | Avnet indexed zero; Arrow indexed NRND, no verified quantity | Search-index evidence only; fresh pages failed |
| [Rutronik sensor catalog](https://www.rutronik24.com/pg/other-sensors/icinot/) | On request, 50 weeks for Q65114A3064/A3065 | Indexed catalog; not an available quote |
| [DigiKey official AS7331 EVK](https://www.digikey.com/en/products/detail/ams-osram-ag/AS7331-EVALKIT-0V2/16983753) | Three kits, $321.07 quantity one | Opened US page; no reservation |
| [DigiKey GUVA](https://www.digikey.com/en/products/detail/genicom-co-ltd/GUVA-S12SD/9960951), [GUVB](https://www.digikey.com/en/products/detail/genicom-co-ltd/GUVB-S11SD/9960952) | 2,970/$6.59 and 1,654/$4.64 quantity one | Opened pages; $11.23 pair excludes analog front end and shipping |
| [SparkFun SEN-23517 capture](../sourcing_followup/sparkfun-as7331-actual-ui.txt), [Adafruit 6476 capture](../sourcing_followup/adafruit-as7331-actual-ui.txt) | Standard SparkFun board $27.50, Backorder; Adafruit $22.50, Out of stock | Root actual product UI resolves earlier conflicting SparkFun extraction |
| [SparkFun mini](https://www.sparkfun.com/catalog/product/view/id/8126), [DigiKey mini](https://www.digikey.com/en/products/detail/sparkfun-electronics/23518/22321098), [MikroE UV5](https://www.mikroe.com/uv-5-click) | Contradictory SparkFun header/backorder; DigiKey zero; MikroE no longer in stock | No immediate small-breakout supply established |

Additional searches used exact part/family names and LCSC domain restrictions for ZOPT2202, sGlux, Hamamatsu S1226, Genicom GUVB/GUVA, Si1133/Si1145, ML8511, AS7265x and AS734x. Search results for LED emitters, visible-only parts and independent brokers were not treated as valid UVB detector supply. No commercial-market completeness claim is made.

## Reproduction and local audit

Run from the repository root:

```sh
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9 analysis/v1_1_release_20261012/uv_followup/audit.py
```

`audit.json` records reviewed hashes, native U6/U7/C6 geometry, all six U6 connections matched to the release-export schematic netlist, and explicitly assumed energy/ADC calculations. It never saves CAD. It verifies the reviewed release's already corrected U6 footprint identity; it does not verify a replacement layout, low-pressure operation, sensor noise, optical calibration or ozone accuracy.
