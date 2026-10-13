# R4 equivalent — 2026-10-13

**YAGEO RC0402FR-073M65L / C477700 is an electrically and mechanically suitable replacement for R4.** Keep its 3.65 MΩ value and existing footprint; update manufacturer, MPN, supplier part, description and datasheet consistently in schematic, PCB and BOM.

The manufacturer’s RC_L V14 datasheet, dated 14 November 2025, decodes `F` as ±1%, `07` as standard-power 7-inch reel and `3M65` as 3.65 MΩ. For RC0402 in this range it specifies ±100 ppm/°C, 1/16 W, 50 V and −55…155°C. The nominal body is 1.00×0.50×0.35 mm, each dimension ±0.05 mm. These match the intended ordinary 0402 resistor and the original electrical requirements. [YAGEO datasheet, pp.2,4–5](https://yageogroup.com/content/datasheet/asset/file/PYU-RC_GROUP_51_ROHS_L)

Native extraction confirms R4’s two 0.54×0.64 mm copper lands have 1.020002 mm center spacing. Their nets remain `Net-(U1-VRDIV)` and `Net-(U1-OK_HYST)`. This is the VBAT_OK rising-threshold divider resistor, not the revised overvoltage resistor R1. Retaining its value, tolerance and temperature coefficient preserves the existing 3.5095 V nominal rising-threshold calculation and its screening envelope. Even an intentionally conservative 5.5 V across the entire 3.65 MΩ resistor would dissipate only 8.29 μW, comfortably below its standard rating; actual divider stress is lower. [Native geometry](native-u2.json), [existing threshold model](../power/calculate_limits.py)

The parent’s actual JLC search captured **9,822 public pieces**, Select enabled, at $0.0022 for quantity one. The public JLC listing independently matches the exact value and ratings. Availability is a dated observation, not a reservation. [Captured JLC search](../sourcing_followup/r4-jlc-search.txt), [JLC C477700](https://jlcpcb.com/partdetail/YAGEO-RC0402FR073M65L/C477700)

No canonical edits or supplier actions were performed by this review.
