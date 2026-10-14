# GNSS antenna placement and orientation

Teddy wants the antenna positioned for reliable satellite reception with the side solar panels installed. A top-mounted, upward 48 mm straight wire is the v1.1 baseline; its hole may move within the top area to improve the feed and assembly fit. The preceding left exit improved the PCB feed but changed this assembly constraint without enough antenna evidence.

Top placement separates the wire from the side panels. It does not prove that an upward straight wire has the strongest overhead reception. A straight thin wire has its weakest idealized direction along its axis; its main reception is broadside. A sky-facing patch or a purpose-designed circularly polarized helix is a different antenna. On this small payload, the ground copper, capacitor, conductive panel structures, feed and wire bend together affect impedance and pattern. The pattern cannot be inferred from the wire alone.

The u-blox antenna application note describes approximately 3 dB polarization loss for a linear whip receiving GNSS signals, plus pattern and gain penalties compared with suitable patch/helix designs. It also warns that a larger visible satellite count can include reflected paths and need not improve navigation. For this balloon, use C/N0 by satellite elevation/azimuth, satellites actually used, dilution of precision, fix continuity, cold acquisition and radio/converter coexistence as acceptance metrics. Compare contemporaneously with a known-good complete v1 assembly, with matched receiver configuration and panels fitted.

No patch, helix, active antenna, GNSS receiver replacement or extra power draw is introduced by this correction. A future antenna change should compare mass, power, polarization, phase-center stability, matching and whole-assembly measurements. The existing LoRa NEC study models a different antenna/frequency and is not evidence of GNSS optimization.

Primary sources:

- [NTIA / National Institute of Justice Antenna System Guide](https://its.ntia.gov/umbraco/surface/download/publication?reportNumber=NIJ-202-00.pdf), section 4.2, printed page 12: the ideal vertical dipole has maximum broadside gain and nulls along its axis. This supports the directional distinction, not a computed Stratolink radiation pattern.

- [u-blox GNSS antennas, UBX-15030289 R03](https://content.u-blox.com/sites/default/files/products/documents/GNSS-Antennas_AppNote_%28UBX-15030289%29.pdf), sections 2.3, 3.3, 4 and 5: placement, linear-whip compromises, antenna selection and complete assembly effects.
- [u-blox: Please, mind the GNSS antenna](https://www.u-blox.com/en/use-case/tech/antennas), 11 August 2023: radiation pattern, polarization, noise, matching and whole-solution assessment.

The application-note PDF was opened in the in-app browser; its viewer exposed no text, so the PDF text was read through the web tool. No search-engine AI summary was used as evidence.
