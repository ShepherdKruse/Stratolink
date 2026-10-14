# v1.1 manual review list

Open `hardware/pcb/stratolink.kicad_pro` in KiCad 10. Current PCB SHA-256: `8df85b3e4bdd546ec174bb9d7b9ee9d795d55d486a68e1e853aaf1b871f863d3`. Reload the board from disk before reviewing; an already-open editor may still show the earlier layout.

- **Temperature:** corrected TMP117AIYBGR pin map and local routing. Address 0x48; A1 SDA, A2 SCL, B1 3.3 V, B2/C1 GND, C2 unused ALERT grounded.
- **Microphone:** removed MK1/R20/C13, dedicated traces and acoustic opening. PB3/PB4 stay quiet in v1.1 firmware.
- **Solar attachment:** two 1.0 × 2.0 mm open unplated notches with GND solder banks on both faces, plus separate 0.70 mm positive wire holes. Curved panel and lead models show assembly; actual terminal thickness and joint strength still need measurement.
- **Suspension and headers:** 2.0 mm plated suspension holes with 3.2 mm GND rings at the original centers. J3/J4 rear lands enlarged to 1.20 × 0.88 mm, offset 0.12 mm inward. Their 0.50 mm holes and 1 mm pitch remain. These are ordinary PTH contacts.
- **Finish and small geometry:** green solder mask, no silkscreen, tented ordinary vias, copper solar polarity marks. Corrected edge clearance, small pad rings, thermal connections and the duplicate VSTOR stub. U7 keeps its copper lands with 81% paste area and explicit ground returns.
- **Etching cleanup:** widened narrow contacts and the U6 ground bridge, closed tiny copper pockets, rounded trace junctions and removed microscopic artwork specks. Copper labels retain their original shapes and grouped editable text on F.Fab.
- **GNSS feed:** AE2 moves to (55.3, 47.85) mm with its 48 mm straight wire exiting left. D3 moves to (58.0, 45.05) mm at 270°. A 6.575 mm rounded feed replaces the 13.439 mm route, removes the boost-switch crossing and has connected grounds beside it and a rear reference beyond the antenna-pad transition. U3.10/U3.12 and D3.1 connect solidly to GND. Copper label groups move up 0.55/0.22 mm to fit the guard.
- **Rear capacitor:** C5 moves 1.8 mm right to (66.675, 64.707) mm, preserving its flat orientation and three terminal nets. Local VBAT, SC_MID, +3.3 V, SCL and GND routes change accordingly. The revised courtyard follows the maximum case/terminal envelope with a stated 0.125 mm manual-assembly allowance. Check the 0.4505 mm maximum-case gap to J1's exposed bank on the real assembly.
- **Power:** R1 becomes 7.50 MΩ for a nominal 5.041 V ceiling. Add U8 TLV8801, R24/R25 4.75 MΩ, R26 22 Ω and C22 100 nF for midpoint balancing. Feedback is before R26. C5 pads are 1 positive, 2 negative, 3 SC_MID; hand-fit after reflow and cleaning. Keep C8/C21 and the existing 4.7 kΩ I²C pull-ups.
- **UV:** U6 is AS7331-AQFM, C20482877, with UVA/UVB/UVC channels and address 0x74. Add C23 100 nF and precision R27 3.3 MΩ; move U6/C14 and shift C21 0.90 mm left. Local SDA/SCL, PB5, VSTOR and GND routing changes. The pilot omits **U6 only**, retaining C14/C23/R27 and removing only U6's 16 stencil apertures.
- **Identities and rules:** correct exact TMP117, diode, resistor, radio and capacitor metadata; freeze project-local libraries. Enable copper/edge/annular/mask checks plus 0.10 mm minimum connection/groove checks. Only the two documented U5 ALERT / U7 SA0 ERC exclusions remain in the strict published project.

The board remains 0.40 mm two-layer FR4 with ENIG, one radio, MAX-M10S GNSS, existing pressure/IMU and the same flat capacitor. The LoRa wire's documented starting cut is 82 mm at 915 MHz; the GNSS reference cut remains 48 mm. Actual wire bends, assembly loading and radio/GNSS performance need testing.

Strict native checks report zero DRC violations, opens, schematic mismatches or unexcluded ERC findings. Independent checks cover 259 physical pads, 250 logical connections, actual filled copper, RF ground and library changes. The full-copper screen finds no candidates under its stated angle/pocket/island thresholds. This does not establish factory CAM acceptance or a qualified 50 Ω antenna system. [Current peer evidence](../v1_1_peer_review_20261014/README.md).

Use `stratolink_v1_1_uv_dnp` firmware while U6 is absent. Populated AS7331 needs a driver, power-down verification and calibrated optics before any ozone-column claim. J20 SWD mapping is retained. J4 UART observation must not add a competing transmitter; do not drive BOOT0 high while R9 grounds it. Check I²C rise time against 300 ns and GNSS supply transients, including the separate C10/FB1 follow-up.

The matching [offline package](../../hardware/gerbers/v1.1-pilot/README.md) contains 58 complete-design / 57 pilot references, 30 pilot part groups and 11 manual/DNP exclusions. Retained supplier CPL conventions are U1/U2/U8 90°, U4 270°, U7 0°, U3 180°, U5 0°; they do not rotate native footprints. Recheck relocated D3 and both faces in the new supplier preview.

The saved JLC **fabrication-review_Y24** cart is an older revision. Its files, previews and price do not apply to this update. Planned quantity remains five PCBs, three assembled. Supplier reimport/CAM review and the [pilot acceptance procedure](pilot-acceptance.md) remain outstanding. No checkout or payment was made.

[Fabrication details](../../hardware/pcb/FABRICATION.md) · [v1.1/v2 checklist](../../hardware/pcb/TODO.md) · [UV circuit](as7331/README.md) · [Power](power/README.md) · [Solar](../v1_1_solar_attachments_20261012/qualification/README.md)
