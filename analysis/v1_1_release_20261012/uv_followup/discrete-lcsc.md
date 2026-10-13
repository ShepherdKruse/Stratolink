# Discrete UVB/reference detectors: catalog and analog-front-end check

2026-10-13. **LCSC does catalog genuine UVB photodiodes. The useful exact Genicom detectors checked here currently show no stock; that is a sourcing result, not evidence that such detectors do not exist.** A small two-detector prototype can be sourced from DigiKey now. It needs an analog front end and optical calibration, and the inexpensive small detectors are rated only to −30 °C. No canonical hardware, supplier selection or order was changed by this review.

This subagent's in-app Browser discovery returned no connected backend. The parent explicitly authorized public web fallback; the active JLC quote was untouched. Inventory below is an opened-page observation on October 13, not a reservation or confirmation that JLC will accept consigned parts. Manufacturer-authored documents provide technical specifications; distributor pages provide their own catalog/stock observations.

## LCSC catalog investigation

The [Genicom photodiode catalog](https://www.lcsc.com/brand/1263-13647.html) contains 39 results. The parent inspected and captured both live in-app Browser pages: all 25 first-page entries and all 14 second-page entries show zero availability. Individual product pages were independently checked here for the most relevant devices. This establishes all 39 entries in this catalog snapshot, not every possible detector from every LCSC manufacturer. Local evidence: [page 1](../sourcing_followup/lcsc-genicom-page1.txt), [page 2](../sourcing_followup/lcsc-genicom-page2.txt).

An independent parse verifies both current-page markers, 39 distinct MPNs and zero stock in every product row; [the verification record](discrete-catalog-verification.json) includes all names and capture hashes.

| Exact part and LCSC listing | Observed availability | Spectral/package reason to consider it |
|---|---|---|
| [GUVB-C21SD, C6565190](https://www.lcsc.com/product-detail/C6565190.html) | Out of Stock | Actual UVB-sensitive photodiode, 2.4 × 1.8 mm package; 240–320 nm at 10% response in the 2018 sheet |
| [GUVB-S11SD, C6954997](https://www.lcsc.com/product-detail/C6954997.html) | Out of Stock | Larger 3.5 × 2.8 mm UVB detector, similar 240–320 nm band |
| [GUVA-C22SD, C6050602](https://www.lcsc.com/product-detail/C6050602.html) | Out of Stock | Small 2.4 × 1.8 mm broad UV reference; 240–370 nm, including UVB |
| [GUVA-S12SD, C7200747](https://www.lcsc.com/product-detail/C7200747.html) | Zero in retrieved product/catalog evidence | Larger broad UV reference, 240–370 nm |
| [GUVV-S10SD, C6266322](https://www.lcsc.com/product-detail/C6266322.html) | Zero in retrieved product/catalog evidence | Broad 240–395 nm response; not a separate narrow UVA band |
| GUVB-S31GD, C7200750 | Zero on catalog; exact product page not accessible | Another UVB catalog entry, not verified purchasable |
| [GUVB-C31SM, C6050605](https://www.lcsc.com/product-detail/C6050605.html) | Not available now | Digital UVB device despite photodiode categorization; [DigiKey marks it obsolete](https://www.digikey.com/en/products/detail/genicom-co-ltd/GUVB-C31SM/10474886) |
| GVBL-S12SD, C7200755 | Zero on catalog | Longer-wavelength 345–450 nm response could be a different reference; includes visible light |

Targeted LCSC searches for sGlux and Hamamatsu filtered UVB alternatives did not establish an exact stocked replacement. Generic stocked silicon photodiodes with visible/IR response are not equivalent to a solar UVB channel. No stocked dual discrete UVA/UVB package with a verified useful response was established. Integrated IC alternatives are covered separately in [the main UV review](README.md).

## Small pair that can actually be prototyped

Opened US DigiKey pages showed **GUVB-C21SD: 5,863 pieces, $4.64 each**, and **GUVA-C22SD: 2,717 pieces, $4.13 each**, at quantity one. That is **$8.77 for the two detectors**, before analog circuitry, optics, assembly and shipping. These are the smaller COB packages, not the larger GUVA-S12SD/GUVB-S11SD pair. [GUVB source](https://www.digikey.com/en/products/detail/genicom-co-ltd/GUVB-C21SD/10474936), [GUVA source](https://www.digikey.com/en/products/detail/genicom-co-ltd/GUVA-C22SD/9960950).

The manufacturer-authored [2018 GUVB-C21SD sheet](https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/5786/GUVB-C21SD_Rev1.0_2018.pdf) gives 0.076 mm² active area, 0.11 A/W at 300 nm, a 240–320 nm 10%-response interval, and photovoltaic operation. The [2020 GUVA-C22SD sheet](https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/5786/GUVA-C22SD_Rev1.0_2020.pdf) gives the same area, 0.14 A/W at 350 nm and a 240–370 nm interval. Both rate operating temperature **−30…85 °C**, with −40 °C only a storage limit. Typical response temperature coefficients are 0.1%/°C and 0.08%/°C respectively. Neither source supplies a numerical guaranteed visible-rejection ratio. Broad-response curves and the qualitative visible-blindness claim cannot establish a precision stray-light floor.

There is a material document discrepancy: a [2020 Genicom GUVB-C21SD sheet hosted by Diltronic](https://diltronic.com/downloads/product-sheets/guvb-c21sd-cob2418.pdf) instead gives 0.20 A/W and 260–320 nm. Its lamp conversion is also different. Obtain the controlled datasheet for the purchased lot and measure its response before using absolute gains in an ozone model. A source revision mismatch is not resolved by averaging the two values.

The pair produces **two differently weighted UV measurements**, not ideal rectangular UVA and UVB bins. The GUVA channel overlaps the GUVB channel. Manufacturer sunlight-to-UVI examples are empirical calibrations, not proof that one current uniquely represents UVB irradiance or ozone. In particular the GUVA sheet's sunlight fit includes an intercept. Do not turn its slope into a universal zero-intercept conversion.

## 3.3 V analog implementation and current parts

Use each photodiode in photovoltaic mode with its own transimpedance amplifier (TIA), local feedback resistor/capacitor, decoupling and ADC channel. A small positive reference can keep the dark output above ground. For a positive-going output, connect the diode cathode to the inverting summing node and anode to the same reference as the non-inverting input. Both diode terminals then sit near the same potential; this avoids deliberately reverse-biasing the 3 V-rated UVB part from the 3.3 V rail. Reference noise, startup and power-off photocurrent paths still need circuit review. [ST's AN4451](https://www.st.com/resource/en/application_note/an4451-signal-conditioning-for-a-uv-sensor-stmicroelectronics.pdf) demonstrates this class of GUVA/low-power-amplifier measurement.

| AFE option | Manufacturer specification relevant here | Opened sourcing observation |
|---|---|---|
| LPV812DGKT dual | 1.6–5.5 V; 425 nA/channel typical at 3.3 V; −40…125 °C; 3 × 3 mm VSSOP body; 8 kHz GBP | [LCSC C181487](https://www.lcsc.com/product-detail/C181487.html): **1**, $2.4658 at one; insufficient for three boards without additional sourcing |
| Two TSU111ICT singles | 1.5–5.5 V; 900 nA/channel typical; 1.48 µA/channel maximum over −40…85 °C at 3.3 V; 50 pA maximum input bias over that temperature interval; SC70-5 | [LCSC C157442](https://www.lcsc.com/product-detail/C157442.html): **64**, $1.831 each; **$3.662 per pair** |
| TSU102IQ2T dual | 1.5–5.5 V; 2 × 2 mm DFN; −40…85 °C; used here as a lower-cost external-sourcing candidate, not selected circuitry | [DigiKey](https://www.digikey.com/en/products/detail/stmicroelectronics/TSU102IQ2T/4499536): **3,591**, $1.53 at one; LCSC C125822 search evidence shows only one and exact short page was inaccessible |
| OPA2379AIDR dual | 1.8–5.5 V; 2.9 µA/channel typical; −40…125 °C; SOIC-8 | [LCSC C94068](https://www.lcsc.com/product-detail/C94068.html): **151**, $10.2328; feasible but poor size/price choice for this payload |

Primary references: [TI LPV812](https://www.ti.com/lit/ds/symlink/lpv812.pdf), [ST TSU111](https://www.st.com/resource/en/datasheet/tsu111.pdf), [ST TSU102](https://www.st.com/resource/en/datasheet/tsu102.pdf), [TI OPA379 family](https://www.ti.com/lit/ds/symlink/opa379.pdf). The LPV812's 100 fA bias is a typical value at a stated test condition, not a guaranteed full-temperature leakage bound. The TSU111's bounded bias and offset are useful even though its idle current is higher.

Calculated amplifier-only power is **2.805 µW** for LPV812 or **5.94 µW typical / 9.77 µW full-temperature maximum** for two TSU111s at 3.3 V. Detectors plus two stocked TSU111s total **$12.432** at observed single-unit pricing before passives/ADC/optics. A dedicated ADC or buffered reference can exceed this amplifier power; neither has been selected. Existing accessible ADC pins and firmware acquisition would need a new design review. This is not an I²C drop-in for U6.

Reproducible first-order arithmetic is in [discrete_signal_model.py](discrete_signal_model.py) and [its JSON output](discrete_signal_model.json). It assumes monochromatic light at the specified peak/test wavelengths, **not a predicted flight spectrum**. At 300 nm, an illustrative 1 W/m² gives 8.36 nA and 83.6 mV with 10 MΩ. At 350 nm, 20 W/m² gives 212.8 nA and 212.8 mV with 1 MΩ. The UVB example is about 104 counts on an ideal 12-bit/3.3 V ADC; its irradiance increment is 9.64 mW/m² per ideal count. Actual accuracy also depends on ADC reference/noise, gain tolerance, source spectrum, angular response, temperature and dark calibration.

At 10 MΩ, a 50 pA amplifier-bias bound contributes 0.5 mV. A 1 nA parasitic leakage would contribute 10 mV. Genicom's 1 nA dark-current maximum is specified at 0.1 V reverse bias, not a measured zero-bias dark offset for our circuit. Keep inputs short, clean and guarded; measure dark drift on the actual bare-board finish. Hypothetical 10 MΩ/100 pF and 1 MΩ/1 nF feedback networks have 159 Hz poles, but these values are **not selected or stability-verified**. Real diode/input capacitance and the nanopower amplifier's limited bandwidth require a loop simulation and settling test. No numerical ozone accuracy follows from the ADC counts.

## Filtered and colder alternatives

**sGlux SG01D-B5 / SG01D-A5** are a real filtered pair. The B5 device-specific table gives a 310 nm peak, 290–334 nm 10% interval, 0.020 A/W, >10¹⁰ rejection relative to wavelengths above 405 nm, and −55…170 °C operation. The visible-rejection figure does not describe its remaining UVA tail. The B5 is a Ø9.2 mm TO5 package about 6.7 mm high; that is a substantial mechanical penalty relative to the small Genicom pair. Its sheet has inconsistent generic first-page nomenclature; use the device-specific table and obtain manufacturer clarification before optical design. [B5 primary datasheet](https://sglux.de/download/photodiodes/SG01D-B5.pdf).

The A5 catalog gives a 331 nm peak and 309–367 nm interval. Single-unit catalog prices were €50.50 B5 and €81.40 A5, **€131.90 for detectors alone**. These are quoted catalog prices, not a verified available quantity or delivered quote; exact mass was not obtained. No LCSC stock was verified. They are useful reference-instrument candidates, not an economical tiny-board substitution. [B5 catalog](https://sglux.de/en/product-category/sic-uv-photodiodes/uvb-photodiodes/), [A5 catalog](https://sglux.de/en/product-category/sic-uv-photodiodes/uva-photodiodes/).

**Hamamatsu S16495** is a more attractive narrowband concept: a ceramic surface-mount detector with a 310 nm filter, 1.1 × 1.1 mm photosensitive area and listed 304–316 nm response interval. The product page and broader UV catalog disagree by a factor of ten in responsivity (0.13 versus 0.013 A/W), so this review does not use either in a signal budget. No LCSC stock, current delivered price, controlled temperature limit or exact package-outline dimensions were established. It deserves a controlled datasheet/quote check before a future narrowband design; it is not a sourced pilot substitute. [Product page](https://www.hamamatsu.com/us/en/product/optical-sensors/photodiodes/si-photodiodes/S16495.html), [UV catalog](https://www.hamamatsu.com/content/dam/hamamatsu-photonics/sites/documents/99_SALES_LIBRARY/ssd/uv_koth0022e.pdf).

## Decision supported by this search

The small Genicom pair plus two stocked TSU111s is a concrete **ground prototype** path available through two distributors. Power is small enough that it should not dominate this payload. The detector cold rating, analog acquisition, spectral calibration and optical collection remain work to complete; none requires claiming that the desired two-band measurement is impossible. A room-temperature prototype could characterize the instrument before committing board space.

For an ozone experiment, retain raw channels and detector temperature and characterize the actual spectral/angular response. Each current is an integral of the solar spectrum times a different detector response. A two-channel ratio alone cannot separate ozone from every cloud, aerosol, orientation and gain effect. The deliverable initially is two calibrated UV measurements and a tested forward model for **ozone column above the payload**, not guaranteed local ozone concentration. See [the main UV review](README.md) for the retrieval and integrated-sensor comparison.
