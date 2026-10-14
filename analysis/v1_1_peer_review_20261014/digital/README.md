# Digital peer-feedback review - 2026-10-14

**Keep the present 4.7 kΩ I²C pull-ups pending a measured rise-time check. The programming pin mapping is correct for the actual standard RAK3172. The real connector concerns are GNSS UART contention when an external transmitter is attached, and the existing zero-ohm BOOT0 ground strap.** No CAD, firmware, Git state, manufacturing package, or cart changes were made in this review.

Reviewed PCB SHA-256: `9d63500a087ef8d345c2337942106e6704d32ded953846883454bfad718adf6c`. `current-netlist.xml` is a fresh native schematic export. `layout.json` records native pads, routes and lengths, plus the flown-v1 repository design at `9bdd19ec707455271f48f5a5d8be352fc696cf9c`. This comparison establishes repository design continuity, not an inspection of the three assembled boards.

## I²C wiring and pull-ups

R11 pulls **SDA** to +3.3 V through **4.7 kΩ**; R12 does the same for **SCL**. These are one pull-up per line, not two resistors on one line. R14/R13 are **zero-ohm series links** into the GNSS SDA/SCL branch; they are not additional pull-ups.

| Connected device | Actual bus connection | Address / state |
|---|---|---|
| U2 RAK3172-8-SM-NI | Module 10 = PA11/SDA; 9 = PA12/SCL | Host |
| U3 MAX-M10S-00B | 16 SDA / 17 SCL, through R14/R13 | Default 7-bit 0x42; physically connected even though normal flight communication uses UART |
| U4 MS561101BA03-50 | 7 SDA / 8 SCL; PS and CSB high | Firmware 0x76 |
| U5 TMP117AIYBGR | A1 SDA / A2 SCL; ADD0 low | 0x48 |
| U7 LIS2DH12TR | 4 SDA / 1 SCL; CS high, SA0 low | Firmware 0x18 |
| U6 AS7331-AQFM | 12 SDA / 13 SCL; A1/A0 low | 0x74 when fitted; **absent on saved three-board pilot** |

The GPS already contributes internal pull-ups: its data sheet Table 14 specifies **8–40 kΩ, 18 kΩ typical** with VIO_SEL open, which is this board's configuration. Thus the nominal 4.7 kΩ external pull-up becomes approximately **2.961–4.206 kΩ**, typically **3.727 kΩ**, while those internal pulls are active. They pull toward GPS V_IO, supplied from the same 3.3 V system through FB1. Do not depend on an unspecified internal-pull state for a disconnected or differently powered receiver.

If “two sets of 10 kΩ” means two 10 kΩ pull-ups **on each line**, then 10 kΩ || 10 kΩ = **5 kΩ**. This is 6.4% more resistance than 4.7 kΩ, so it slightly **slows** an RC rising edge; physical distribution does not halve the bus capacitance. With the typical GPS pull-up included, 5 kΩ || 18 kΩ = 3.913 kΩ, versus the current 3.727 kΩ. One 10 kΩ per line is slower again. Keeping the existing 4.7 kΩ while adding two more 10 kΩ per line is a different proposal: it increases sink current and should not be adopted without a measured need.

## Actual speed, route lengths and bounded RC screen

`firmware/src/sensors.cpp:20` calls `Wire.begin()` without a speed override. The installed STM32duino `Wire.cpp:97` initializes it at **100,000 Hz**; the release source has no later `Wire.setClock()` call. The separate GPS I²C diagnostic explicitly selects 100 kHz too. This is code-derived intended timing, not a scope measurement.

**Do not automatically use the 1 µs Standard-mode rise-time allowance just because the clock is 100 kHz.** TMP117 explicitly permits 1 µs at ≤100 kHz, but the MAX-M10S integration manual §3.2.2 says its I²C is Fast-mode and Standard-mode backward compatibility is not supported; its data-sheet table permits 0–400 kHz with **300 ns** rise/fall limits. AS7331 Figure 39 also specifies **300 ns**. A 100 kHz clock does not itself violate a 0–400 kHz range; it simply does not excuse slower edges or other Standard-mode timings on this mixed bus. Do not switch SCL to push-pull: the GPS supports clock stretching.

| Line | Main-net copper | GNSS copper after 0 Ω link | Total routed copper | Vias |
|---|---:|---:|---:|---:|
| SDA | 87.277 mm | 7.826 mm | **95.103 mm** | 4 |
| SCL | 99.071 mm | 7.843 mm | **106.914 mm** | 9 |

These are sums of all native routed centerlines on each electrical bus, including branches, not straight-line distances or one end-to-end delay. The width set is 0.10/0.15/0.25 mm. No external I²C cable is included.

`model.py` / `rc-screen.json` calculate **t₃₀–₇₀ = ln(0.7/0.3) RC ≈ 0.8473 RC**. A simple plane-only microstrip approximation using the 0.31 mm core and assumed εr=4.2 gives about 0.055–0.076 pF/mm. The deliberately wider screening range is 0.04–0.20 pF/mm for trace loading, plus TMP117's published **4 pF typical**, assumed 3–10 pF for each other connected IC input, and 5–15 pF for pads/vias/module fringing. The remaining IC maxima and complete stackup field solution are not available: **these are conditional engineering bounds, not guaranteed capacitance specifications or an electrostatic simulation**.

The resulting screen is roughly **28–90 pF** fully populated, **25–80 pF** with U6 absent. With the weakest published GPS pull-up, the full-design upper estimate reaches **314–322 ns**; the pilot upper estimate is **278–286 ns**, before resistor tolerance or probe/cable additions. The typical-GPS-pull full-design upper estimate is 278–285 ns. This is enough to prioritize a bench measurement, not enough to certify a populated AS7331 bus.

For reference, 4.7 kΩ alone permits **75.3 pF at 300 ns**; including a 40 kΩ GPS pull-up gives **84.2 pF**. Two 10 kΩ alone reduce that allowance to 70.8 pF. Current at VOL=0.4 V with 3.3 V and the strongest GPS pull-up is approximately **0.98 mA per low line**, below the GPS data sheet's 2 mA digital-output test load. Internal pull-up variability, temperature, actual pin capacitance, noise and probe loading remain measurement limits.

**Disposition:** no evidence supports changing to two 10 kΩ pairs as a capacitance remedy. Measure 30–70% rise time and VOL at the far devices, with ordinary operational power/temperature and with U6 populated later. A high-capacitance scope probe can change the answer. Choose any future resistor reduction from the measured C/rise time and weakest sink capability; it is not justified by this feedback alone.

## Programming pin mapping and header identity

The current U2 is **RAK3172-8-SM-NI**, standard **32-pad** RAK3172 using STM32WLE5CC; the firmware board declaration specifies **STM32WLE5CCU6** and J-Link target **STM32WLE5CC**. It is not the **40-pad RAK3172-F** (STM32WLE5JCI6). Module pad numbers also are not raw-MCU package pin numbers. The fresh official RAK table explicitly confirms these mappings:

| Function | Standard module pad / MCU signal | Current connector | Flown-v1 mapping |
|---|---|---|---|
| SWDIO | U2.7 / PA13 | J20.2 | Same |
| SWCLK | U2.8 / PA14 | J20.4 | Same |
| MCU reset | U2.22 / NRST | J20.3 (`RST` net) | Same |
| BOOT0 | U2.21 | J4.6, R9 to GND | Same |
| Reference supply | U2.24 / 3.3 V | J20.1, J4.7 | Same |
| Ground | U2 ground pads | J20.5 | Same |
| SWO | Not routed | J20.6 NC | Same |

J20 matches the primary Tag-Connect **TC2030-CTX** six-pin mapping: 1 VCC/reference, 2 SWDIO/TMS, 3 nRESET, 4 SWCLK/TCK, 5 GND, 6 SWO/TDO. Check the actual adapter variant; physical six-pin compatibility alone does not identify every cable. SWD routes are **8.339 mm data / 8.013 mm clock**. Firmware uses SWD/J-Link at 4 MHz; this short difference does not call for trace matching.

All seven J3/J4 pad net assignments match flown v1. J3 pins 1–7 are **PA1, GND, PA9, GND, GND, PB2, GND**. J4 pins 1–7 are **GND, VSTOR, GND, TX, RX, BOOT0, +3.3 V**. They expose GPIO/power/GNSS access, whereas **J20 is the actual SWD programming connector**.

Two practical qualifications matter:

- **R9 is 0 Ω from BOOT0 to GND.** J4.6 cannot be driven high safely with that strap populated. This is inherited, not a new v1.1 pinout error. Normal SWD programming does not require asserting BOOT0; a future UART/boot-mode procedure would need its own strap/isolation plan.
- Official RAK firmware update/AT UART2 is **PA3 pad 1 / PA2 pad 2**, both intentionally NC on this PCB. J4's UART1 GNSS signals are not automatically the official RAK UART2 update port. Any raw-STM32 ROM bootloader procedure must be checked separately for its supported alternate-function pins and option bytes.

No incorrect SWD, BOOT0 or reset module-pad assignment was found. The peer's exact alternate pin numbers were not supplied, so a RAK3172-F/raw-MCU table mix-up is a plausible explanation, not a proven description of their reasoning.

## UART topology, stubs and contention

| Net | On-board direction | Header | Routing |
|---|---|---|---|
| `TX` | U2.4 PB6 UART1_TX → R16 **33 Ω** → U3.3 RXD | J4.4; external **RX** only for passive observation | 47.484 mm before resistor + 2.785 mm GPS-side copper |
| `RX` | U3.2 TXD → R15 **33 Ω** → U2.5 PB7 UART1_RX | J4.5; external **RX** for observation | 43.064 mm before resistor + 2.783 mm GPS-side copper |
| UART2/LPUART1 | U2.2 PA2 TX / U2.1 PA3 RX | Neither reaches J3/J4/J20 | Both NC |

`gps_ublox.cpp:503` starts Serial1 at **9600 baud**, matching the MAX-M10S default. One bit is 104.167 µs. Optional debug Serial uses LPUART1 on PA2/PA3 at 115200 baud, but `DEBUG_ENABLE=0` in the release, and those pads are not routed to these headers. J3 GPIOs are not configured as additional UART ports in the reviewed flight build.

The J4 TX/RX copper lands are junctions along the two GNSS nets: the MCU-side and GPS-side tracks both terminate in the same plated header pad. There is **no separate long, open-ended PCB trace branch** from the GNSS link to a remote programming connector. The TX copper paths already overlap near `(74.564, 72.168)` before the header, leaving a local landing tail bounded by **1.7 mm including the rear 1.2 mm pad width**; RX joins through the plated contact itself. There is no centimetre-scale open PCB stub. The longest point-to-point route is conservatively **under 55 mm including the resistor gap**. With an explicitly assumed conservative propagation velocity of 1.4×10⁸ m/s, that is **<0.40 ns one way / <0.80 ns round trip**. It does not bound an attached wire or cable. Detailed ringing still depends on actual edge rate, return geometry, loading and source impedance, not baud alone; no IBIS transient simulation or measured edge is claimed.

UART here is two asynchronous single-ended signals. **TX and RX do not need length matching to each other.** One transmitter can feed multiple high-impedance receivers if loading is acceptable. Multiple ordinary push-pull transmitters cannot simply share the same wire as an I²C-style bus; proper isolation, a suitable transceiver/topology and a protocol are needed for a true multidrop arrangement.

**Real contention case:** attaching a USB-UART adapter's TX to J4.5 while the GPS remains active puts two push-pull outputs on the RX net (the GPS has only 33 Ω in series). Lowering baud or matching lengths does not fix that. For observation, connect adapter RX only to the desired signal with common ground and compatible voltage. For injection into the MCU, isolate the GPS TX path (for example remove R15 in a deliberately prepared bench configuration) or use a verified tri-state/isolation scheme. Do not assume a powered-down GPS is a safe isolation method because input protection/back-power paths still need review. A normal SWD probe on J20 does not drive either UART net.

## Primary evidence and limits

- [Official RAK3172 data sheet](https://docs.rakwireless.com/product-categories/wisduo/rak3172-module/datasheet/), fresh Browser capture in `../sources/rak3172-datasheet.txt`: standard-module table lines 168–200, separate RAK3172-F table 206–246, vendor update UART note at 340.
- [Tag-Connect TC2030-CTX manufacturer drawing](https://www.tag-connect.com/wp-content/uploads/bsk-pdf-manager/TC2030-CTX_1.pdf), pin table lines 27–32 verified by root through official PDF fallback after the browser PDF rendered blank. See `sources/tag-connect-provenance.json`.
- u-blox **MAX-M10S data sheet UBX-20035208 R08**, pp. 12, 14–15; **MAX-M10S integration manual**, §3.2.1–3.2.2. Local primary PDFs are in `analysis/redesign_20261010/metrology/sources/`; extracted searchable text is in this review's `sources/`.
- TI **TMP117 data sheet**, digital IO table and §6.6 timing requirements: 4 pF typical input, 300 ns Fast-mode / 1000 ns at ≤100 kHz. Local primary PDF: `analysis/v1_1_layout_20261012/pcb_audit/sources/tmp117.pdf`.
- ams OSRAM **AS7331 DS001047 v4-00**, §7.8 and Figure 39: address bits, 300 ns edges, up to 400 kbit/s, no clock stretching. Local primary PDF: `analysis/v1_1_release_20261012/as7331/review/as7331-datasheet-v4-00.pdf`.
- Native extraction and calculations are reproducible with `extract_layout.py` under KiCad's Python and `model.py` under Python 3. Input hashes are in `input-hashes.json`.

The independent browser runtime was unavailable for this agent; the fresh RAK capture and Tag-Connect verification were obtained by the root agent's working browser/source session. No live board waveform, actual cable, raw-MCU ROM boot configuration, or guaranteed total bus capacitance was measured here. The populated-AS7331 driver is still unimplemented; the selected pilot environment deliberately omits UV transactions rather than probing the new device with the legacy LTR390 driver.

## Final routing check, 14 October

The accepted RF/C5 revision preserves every physical pad net and all 250 logical pad connections. The combined SCL length changes from 106.9141 to 106.8819 mm; SDA remains 95.1026 mm. This negligible length change does not replace the required 300 ns rise-time measurement. See [scope](final-rf-scope.json), [route lengths](final-route-lengths.json) and [actual ground reference](final-rf-reference.json), all bound to PCB `8df85b3e4bdd546ec174bb9d7b9ee9d795d55d486a68e1e853aaf1b871f863d3`.
