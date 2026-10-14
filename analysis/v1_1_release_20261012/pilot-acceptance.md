# v1.1 pilot acceptance record

This is a test procedure, not a completed test report. Fabricate five PCBs and assemble
three pilots before considering the approximately fifteen-payload run.
Record board serial, exact BOM revision, firmware commit, instruments, calibration,
wire diameter/cuts, panel preparation and assembled mass with each result.

## Incoming inspection and first power

1. Compare fabrication files and received construction: 0.4 mm, two copper
   layers, ENIG, green solder mask on both faces, no silkscreen, tented ordinary vias, correct notches,
   exposed solar soldering lands, plated suspension holes and enlarged rear header lands. Inspect mask registration and routing tabs
   after removal; do not accept damage to solar banks or suspension ligaments.
2. Before fitting the supercapacitor or panels, inspect sensor orientation,
   bridges and misplaced parts. The AS7331 pilot variant omits U6 only; verify
   its sixteen pads have no printed paste and C14/C23/R27 are fitted. Use a current-limited bench source for first
   power; start within the harvester's rated input envelope. Record 3.3 V, supply
   current and abnormal heating before enabling GNSS or RF.
3. Check the full three-terminal capacitor footprint against the actual part.
   Fit it only after reflow and board cleaning using the permitted secondary
   soldering process. Verify positive, negative and midpoint independently before
   energizing. Probe each cell differentially without shorting adjacent tabs.

## Power and storage

- Measure the charge plateau and ripple at VSTOR and at C5 itself. The divider's
  nominal target is about 5.041 V for the 7.50 MΩ R1 pilot; model corners are
  screening calculations, not measured acceptance limits.
- Measure both cell voltages throughout charging, storage and discharge. Each
  cell must remain within its 2.75 V rating and the complete module within its
  5.5 V rating. Check balance after controlled initial imbalance and over a long
  hold; a correct total voltage does not prove a safe cell split.
- Scope U8's output and C5 midpoint during startup, charging, load steps and
  imbalance recovery. Validate the 22 Ω isolation circuit against oscillation
  with this exact capacitor, wiring and temperature. Do not infer stability from
  the CAP-XX test of another module at room temperature.
- Characterize actual panel Voc, Isc and I–V curves in cold and strong illumination.
  Measure BQ VIN during open-circuit sampling and charging. BQ25570 recommended
  ceilings are 5.1 V and 400 mW; 5.5 V / 510 mW absolute limits are not operating
  targets. Resolve any excess before outdoor qualification. Historical ADC values
  are a reason to measure directly, not a calibrated overstress determination.
- Observe PB5 VBAT_OK edges against VSTOR. The actual R3/R4/R5 network predicts
  about 3.510 V rising and 2.510 V falling. Boot near 2 V does not establish this
  threshold because VOUT_EN is tied directly to VSTOR.
- Measure debugger-free sleep current, all-cell dark discharge, brownout/recovery,
  dawn startup and simultaneous GNSS-start/RF supply sag. Compare with the same
  known-good v1 configuration. Record actual duration and temperature; do not
  extrapolate a short steady-state sample into a certified night endurance.
- Measure the filtered supply at U3 pins 6/7/8, using a short ground connection,
  during acquisition, charging and LoRa transmissions. Record minimum voltage,
  ripple, recovery and upstream 3.3 V at the same time. Check against the exact
  module's supply limits. C10 is distant from these pins, and FB1's maximum DCR
  exceeds the receiver integration guide's series-resistance recommendation;
  nominal rail voltage alone does not close those findings. Retain C8/C21 while
  establishing this baseline.

## Sensors and radio

- Measure SDA and SCL 30% to 70% rise times at the far devices with a
  low-capacitance probe; record probe loading, bus speed, rail voltage and VOL.
  Use the 300 ns limit required by MAX-M10S and AS7331 even at 100 kHz. Repeat
  after U6 is populated. Keep the existing 4.7 kΩ pull-ups until measurement
  justifies a change; two 10 kΩ resistors in parallel do not improve this margin.
- Use J20 for SWD with its verified cable mapping. A passive receive-only UART
  monitor is suitable for observing J4, but another transmitter on J4.5 can
  contend with GPS TX through R15. Isolate that transmitter path before active
  injection. R9 straps BOOT0 to ground; do not drive J4.6 high while R9 is fitted.
- U5: prove address 0x48 ACK, expected device ID and direct temperature reads;
  distinguish the pressure sensor fallback. Compare with a calibrated reference
  through cold starts and the intended range. Measure solar/conduction bias
  separately from IC die accuracy.
- U4/U7: check IDs, plausible pressure/acceleration and bus recovery across
  power cycles. Check U7's CTRL_REG0 SDO_PU_DISC setting: its grounded address pin
  can otherwise draw internal pull-up current. Record register values.
- Use `stratolink_v1_1_uv_dnp` for the U6-omitted pilots. Verify PB3/PB4 remain
  quiet, acoustic/UV/lux data are explicitly unavailable, and sensor recovery
  causes no requests to the omitted UV device. The older v1.1 environment still
  expects LTR390 and is not the selected pilot population.
- A later populated AS7331 requires separate bring-up: reviewed 100 µm stencil
  or qualified local process, correct pin 1, clean unobstructed aperture, 0x74 ID,
  all three raw channels, saturation/overrun handling, and measured power-down
  current. Validate a dedicated driver and science telemetry before use; the
  DNP firmware deliberately supplies no UV measurements. The AS7331 operating
  range is −40…85°C. Its internal temperature output is not a TMP117 substitute.
- Before deriving ozone, qualify the actual optics, angular acceptance and
  visible/infrared rejection; record dark response, gain, exposure, temperature,
  UTC and position with raw counts. Validate a spectral forward model against
  independent calibrated observations. Separate UVA/UVB/UVC readings alone do
  not establish an accurate ozone column above a moving balloon.
- Compare GNSS acquisition, satellite C/N0 and recovery during actual local RF
  transmissions. Verify firmware airborne configuration independently from PCB
  identity. Retain the selected MAX-M10S until an alternative is justified.
- For the revised feed, compare v1 and v1.1 with the same firmware configuration,
  recorded wire dimensions, panel assembly, orientation and nearby environment.
  Use simultaneous observations or alternate boards and positions to reduce
  changing-sky bias. Log C/N0 by satellite, fix availability, acquisition/recovery
  times and supply voltage with radio quiet and transmitting, across representative
  charging states. Record converter activity with the observations. A calculated
  feed impedance or an antenna match measurement alone does not demonstrate
  improved reception or immunity to local interference.
  Follow the [complete-assembly GNSS comparison](../v1_1_top_gnss_20261014/reception-test.md)
  for matched satellite/elevation bins, satellites actually used, dilution of
  precision and fix continuity. More visible satellites alone is not acceptance.
- Compare orientation-dependent telemetry and supported receive/relay modes with
  the final panel/wire assembly. Record the regional LoRa cut (82 mm at 915 MHz,
  86 mm at 868 MHz or documented 83 mm compromise) and 48 mm GNSS starting cut
  from the feed. Confirm the final assembly experimentally.

## Mechanical and environmental checks

- Dry-fit prepared panel tabs into both notches. Verify wettable bank contact,
  front/back solder fillets, insulated positive returns and capacitor clearance.
  Measure output before and after assembly; inspect foil lifting and terminal
  damage under magnification.
- Thread the actual stretchy string as the triangular bridle. Record material,
  diameter and apex geometry. Compare corner flex and rim wear with v1 under the
  same measured loads, including uneven and out-of-plane loading on sacrificial
  samples. Do not turn a finite-element plot into an asserted breaking load.
  Check the upward GNSS wire against both bridle legs through expected sway and
  stretch. A clear top-view drawing does not prove three-dimensional separation;
  record the string's depth relative to the wire and allow for motion.
- Repeat electrical and joint checks after representative handling and thermal
  cycles. The retained capacitor is rated −40 to +70°C; operation outside that
  range requires separate evidence. Altitude alone does not establish component
  temperature or low-pressure performance.

## Release decisions

For each item record pass/fail, raw evidence, anomalies and resolution. A pilot
can be useful for bench characterization while still failing flight qualification.
Do not approve the larger batch until the storage/solar limits, sensor repair,
installed radio behavior and mechanical changes have measured acceptance results.
