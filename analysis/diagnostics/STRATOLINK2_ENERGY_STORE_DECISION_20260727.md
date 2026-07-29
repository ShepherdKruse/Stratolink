# StratoLink-2 energy-store decision

Prepared 2026-07-27 for the Friday 2026-07-31 launch decision. This is a
fail-closed engineering screen, not approval to substitute parts or charge the
payload.

## Decision

The current assembly is **NO-GO** for an energy-store installation:

- C5 is absent and its midpoint/balance terminal has no connected circuit.
- The fitted 8.25 MΩ / 4.22 MΩ BQ25570 divider screens to 5.591979 V over the
  modeled tolerance/temperature corner, above the 5.5 V absolute maximum.
- The planned 1 F dual-cell part has a 0.8-1.2 F specified range. Even its
  specified maximum is below the modeled lower-bound capacitance needed for
  launch night.
- The cycle-energy model still omits loads and environmental penalties, so its
  required capacitances are floors rather than selectable flight ratings.

Do not fit C5, uncover the panels, or charge this assembly until the divider,
balancer, capacitance, cleaning, inspection, and controlled-light procedure are
reviewed together.

## Screened frontier

| R1 top divider | Full-temperature VBAT_OV upper | Worst initial high-cell margin | Lower-screen start | 0.8 F modeled survival | Launch-night lower-bound C | 90-day lower-bound C |
|---:|---:|---:|---:|---:|---:|---:|
| 8.25 MΩ fitted | 5.591979 V — fails | not accepted | not accepted | not accepted | not accepted | not accepted |
| 7.50 MΩ reference | 5.251917 V | 0.019003 V | 4.837277 V | 3.798 h | 1.779 F | 2.662 F |
| 7.32 MΩ safer-margin screen | 5.170302 V | 0.061443 V | 4.763871 V | 3.509 h | 1.822 F | 2.764 F |

The 7.50 MΩ and 7.32 MΩ rows are numerical architectures only. Neither is an
approved BOM substitution, fitted threshold, qualified balance circuit, or
flight-energy result. The 7.32 MΩ row buys 42.44 mV more initial-cell margin
than 7.50 MΩ but stores less energy; that trade cannot rescue the 1 F part.

## Vendor-balanced module comparison

CAP-XX's current HY-series architecture offers dual-cell modules with an
integrated active-balance suffix (`A`). The manufacturer's Revision 3.1 table
specifies 5.5 V, -40..85 °C modules and gives a maximum total leakage for the
active configuration. `vendor_balanced_module_screen.py` replaces the board-C5
leakage plus speculative daughterboard-balancer current with that vendor total
and reuses the same lower mission model.

| Active-balanced reference | Guaranteed-minimum C | Active-config max leakage | 7.32 MΩ survival | 7.50 MΩ survival | Lower-screen boundary |
|---|---:|---:|---:|---:|---|
| `HY25R51122V255RA` | 2.25 F | 21 µA | 9.132 h | 9.594 h | launch night only |
| `HY25R51122V355RA` | 3.15 F | 26 µA | 12.167 h | 12.598 h | launch and first 30 days |
| `HY25R51127V505RA` | 4.50 F | 31 µA | 16.410 h | 17.174 h | through the modeled 90-day night |

This identifies a credible architecture family, not a Friday drop-in. These
cylindrical modules do not fit C5; the exact active-balance suffix and stock
are unverified; wiring, mounting, mass, aerodynamics, RF interaction, divider
rework, and every charge/dark/cold/BOR/recovery test remain open. Even the 5 F
row only clears the deliberately incomplete numerical lower screen. Official
source: [CAP-XX HY Series Datasheet Revision 3.1](https://www.cap-xx.com/wp-content/uploads/2021/05/CAP-XX-HY-Series-Datasheet.pdf).

The active-load lower bound includes the documented 35 µA J-Link-attached
sleep upper observation, 6 µA room-temperature capacitor leakage limit, a
modeled 0.952036 µA unqualified TLV8801 balance overhead, and only typical hot
GNSS, primary TX, and empty Class-A RX energy. It excludes sensor/microphone
energy, shallow-WFI MCU current, GNSS cold starts and failures, OTAA/retries,
auxiliary RF, cold capacitance/ESR/leakage, aging, conversion variation, cloud,
attitude, frost, sag, actual BOR, and explicit recovery reserve.

## Required closure order

1. Measure the exact final image with `env:stratolink_profile` and PPK2. Capture
   complete-cycle phase energy, true STOP1 current, tier crossings, Class-A
   waits, GNSS acquisition/recovery, and load-step sag.
2. Re-run the source-bound mission model with those measured distributions and
   an explicit reserve policy. Size from the guaranteed minimum capacitance at
   the cold/aged corner, never nominal capacitance.
3. Select and independently review a divider whose delivered resistor values,
   tolerance, TCR, voltage coefficient, contamination/leakage, and measured
   threshold remain below both stack and per-cell limits.
4. Design and review a real midpoint balance path. Prove quiescent overhead,
   correction authority, mismatch recovery, and both cell voltages across the
   operating temperature range. An open midpoint is not balanced by the
   BQ25570 total-stack threshold.
5. Fit the exact store only after polarity, pad cleanliness, solder quality,
   capacitance, ESR, and midpoint continuity are inspected. First charge must
   use controlled illumination/current and independent stack-plus-cell DMM
   monitoring with a documented abort threshold.
6. Run the complete exact-image dark discharge from the verified ceiling
   through real mission cycles, tier changes, the conservative 3.32 V
   accounting floor, actual BOR, and sunrise recovery. Repeat at the cold and
   aged limits that bound the mission.

## Friday gate

A Friday launch cannot be approved from a newly soldered capacitor plus a
short room charge. The gate closes only when the fitted divider and balance
circuit pass voltage limits, the guaranteed store exceeds the re-measured
mission requirement with reserve, and the exact assembly completes the dark,
cold, load-step, BOR, and recovery tests. If any of those artifacts is absent,
the energy subsystem remains NO-GO regardless of the ongoing 4.660 V powered
soak.

## Bound evidence

- `stratolink2_supercap_charge_ceiling_20260726.json`
- `stratolink2_supercap_balance_20260726.json`
- `stratolink2_supercap_night_reserve_20260726.json`
- `stratolink2_mission_energy_store_sizing_20260727.json`
- `stratolink2_vendor_balanced_module_screen_20260727.json`
- `stratolink2_friday_darkness_envelope_20260727.json`
- `mission_energy_store_sizing_audit.py`
- `vendor_balanced_module_screen.py`
- `supercap_charge_ceiling_audit.py`
- `supercap_balance_audit.py`

These create-once inputs remain the authority. Any resistor, capacitor,
firmware-energy, trajectory, or environmental change requires regeneration of
the decision evidence.
