# Stratolink-3 first-flight notes

Working notes from the May 17 to May 29 2026 flight. Raw observations and open questions only, no recommendations. Use these to drive v2 dev priorities.

## Flight summary

- Launch: 2026-05-17 from Dolores Park, SF
- Last contact: 2026-05-29 17:46 UTC, 36.889°N 4.532°W (Málaga), 10,034 m altitude
- Duration: 12 days
- Distance: ~9,400 km drift
- Final payload mass: 10.28 g (PCB + battery + PV + supercap)
- Envelope: Yokohama 32-inch sphere, ~47 g
- Total fresh GPS fixes received: 38 (after dedupe of identical-tuple repeats)

## GPS data quality observations

### Impossible-speed fix dropped during analysis

EU fix #2 (2026-05-28 08:17:03 UTC, 40.555°N 6.607°W, alt 10016 m):

- Reported 24.3 km north in 3.2 minutes from the previous fix
- Implied ground speed: 127 m/s (~3x the strongest jet stream ever recorded)
- Either a GPS position error or a LoRa packet decode glitch on uplink

Things to investigate:

- Does the GPS module output corrupt fixes under weak-signal conditions? If yes, what does the firmware do with them? Is there a "low signal quality" gate before transmitting?
- Could this be a frame CRC issue on the LoRa side that still managed to decode? Worth running raw packet captures for v2 if a gateway sees a corrupted-but-decoded packet.
- Log raw NMEA or module-level output alongside the formatted telemetry, so when a packet looks weird downstream you can correlate it with the underlying GPS state.

### Stale / cached data being transmitted

Multiple consecutive rows have identical (lat, lon, altitude_m) tuples in the Supabase data. The analysis script filters them out as "stale repeats."

Things to confirm:

- Does the firmware transmit the last-known GPS fix when a fresh fix isn't available?
- If yes, is there a "fix age" or "seconds since last lock" field in the uplink payload? Without that field, downstream can't tell stale from fresh.
- If no fresh-fix marker exists, add one for v2. Until then, the analysis pipeline is using a heuristic (identical-tuple dedupe) which would miss the case where a stale fix is sent with updated altitude or pressure.

### Early bad data, pre-launch

2026-05-15 16:48:38, lat = -208.35, lon = -122.40, alt = 4 m, pressure = 3358 hPa.

- Latitude out of valid range (range is [-90, 90])
- Pressure 3x atmospheric
- Likely uninitialized memory or pre-GPS-lock placeholder being sent

Things to fix in v2 firmware: confirm uplinks during pre-lock state either don't transmit GPS fields or use a sentinel value the receiver can ignore.

### Borderline-fast fix

EU fix 5 to 6: 7.7 km south in 5.1 minutes (25 m/s southward).

- Within physical limits at jet-stream altitude but unusual direction (due south not zonal)
- Not necessarily an error, but flag it as the upper edge of what's plausible

## Radio silence gaps

### Atlantic crossing

- 201.2 hours (8.4 days) between last CONUS fix and first EU fix
- TTN gateway map shows zero coverage over open ocean, so this gap is expected
- Cached path reconstruction estimates the actual trajectory, but no telemetry exists for this period

### Salamanca to Málaga gap

- 24.5 hours between EU fix 6 (40.547°N 5.306°W, May 28 17:14 UTC) and EU fix 7 (36.889°N 4.532°W, May 29 17:46 UTC)
- Drift: 412 km SSE during this period
- TTN coverage exists across central Morocco / Spain interior, so the device should have had gateway visibility during at least part of this stretch

Things to investigate:

- Was the device transmitting during this period and not being received, or not transmitting?
- Does the firmware track uplink attempts vs. successful uplinks? If yes, can we get that count back somehow on next contact?
- Check Morocco / Algeria TTN gateway density along the actual path the balloon took. If there were live gateways within range, the device side was failing somehow (TX, antenna, power, or all three).

## Multi-region OTAA switching

Worked correctly. Device transitioned from US915 (TTN nam1, app `stratolink`) to EU868 (TTN eu1, app `eu-stratolink`) somewhere over the mid-Atlantic. Joined the EU TTN cluster and started uplinking when it reached EU gateway coverage.

Open questions:

- Exact band-switch time is unknown. Is there a band-switch event logged on the device? Could we tag uplinks with the active region so we can confirm the timing on next flight?
- Is the join sequence robust to the case where the device boots in one region and migrates to another mid-flight? On Stratolink-3 it apparently was, but the success criterion was binary ("did we hear from it again"). Worth deliberately exercising this in v2 testing.

## Antenna (dig deeper, manual research)

This is the area to focus on for v2. Things to figure out before committing to a design:

- What antenna actually flew on Stratolink-3? Confirm the geometry, length, conductor, and feed point.
- Is the antenna detuning at altitude as temperature drops? Aluminum, copper, and PCB trace antennas all behave differently below -50 °C.
- Ground plane: is there enough metal on the payload to make a quarter-wave see a real ground, or is it effectively a dipole-half?
- For a multi-region device transmitting on both 915 MHz and 868 MHz, is a single antenna a reasonable compromise, or should v2 consider a switched / dual-band setup?
- Polarization mismatch at altitude: gateways are mostly vertical-polarized, balloon antenna orientation is random (rotating, swinging). What link budget hit does this cause?
- Read what the BLT / W6MRR / KQ4UYY / WB8ELK pico balloon community has settled on. Most use horizontal dipoles cut for the band. Worth understanding why before deviating.

Useful references to read:

- BLT/pico-balloon community antenna designs on QRP Labs, picoballooning.com
- Theoretical link budget at 10 km altitude (free-space path loss, ground plane absence, vertical pattern)
- TTN forum threads about reception from high-altitude balloons

## Power system

- Final mass: 10.28 g including PV, supercap, board, antenna, harness. Lift from 47 g envelope is enough margin.
- System survived 12 days through multiple day/night cycles
- No telemetry on actual supercap voltage over time

Things we don't know that we should:

- Did the supercap ever drop into brownout? Was there a successful recovery after sunrise?
- What was the actual TX duty cycle achieved vs. designed?
- PV current at float altitude across the day. Did the harvester saturate the supercap during direct sun?
- Did the device experience extended-night conditions during the float (e.g. polar night or thick cloud cover)?
- Temperature of the supercap and how that affected its ESR.

## Pressure / altitude

- Last reported altitude: 10,034 m
- Pressure altitude (last reading): not extracted yet
- Diurnal pressure schedule (day-up / night-down) for the analysis script is modeled with p_day ~ 260-340 hPa, p_night ~ p_day + 30 to 480 hPa. Not validated against actual flight data.

Things to dig into:

- Pull the actual barometric pressure column over the flight and plot it. Does it show the expected diurnal cycle?
- If the balloon did diurnal cycling, the gas mass was off-design (would have stayed at constant float altitude if the fill was perfect). Worth working back to "what gas mass was actually flown" from the observed pressure swing.

## Flight path reconstruction notes (analysis side, not firmware)

- 2000-member Monte Carlo ensemble through GFS winds, anchored to last CONUS fix and first EU fix
- Best endpoint convergence: 8 km on the run with the freshest GFS cycle (May 30 12Z analysis), 660 km on a run using stale frozen wind from May 24
- Reconstruction quality is directly proportional to GFS cycle freshness
- Atlantic ensemble centroid drifts roughly along the jet stream over CONUS, then dips south by ~5 degrees latitude during the crossing as it leaves the jet at the eastern Atlantic edge

Caches now living in `~/.cache/stratolink/`:

- `reconstructed_path.npz`: cached path coords (auto-written when `transatlantic_path.py` runs)
- `gateway_coverage_v2.pkl`: cached TTN coverage union
- `predictor/gfs/`: cached GRIB partial fetches from NOAA AWS S3

## Data infrastructure observations

- Telemetry sits in Supabase `telemetry` table
- Device IDs split: `stratolink-3` (CONUS uplinks via TTN nam1) and `stratolink-3-eu` (EU uplinks via TTN eu1)
- Merging is done client-side at analysis time

Open question:

- Use a single device ID per flight on v2, with a `region` or `band` column distinguishing US915 vs EU868 uplinks? Cleaner downstream but requires firmware to surface the active region.

## Tooling notes

- Open-Meteo was rate-limiting hard on multi-pressure-level, multi-time wind fetches. Falling back to NOAA AWS S3 directly via Shepherd's predictor module (`simulation/predictor/weather/`) eliminates this. Use that path going forward.
- The shared cache directory `~/.cache/stratolink/` is doing real work. Worth checking it into the analysis README so the next person knows what's in there.

## Open questions for v2 design

- Should v2 carry a second redundant downlink path (e.g. APRS in addition to LoRaWAN)?
- Does the GPS module need a more aggressive cold-start strategy after extended power-saving?
- Worth instrumenting the LoRa transceiver state more (RSSI/SNR of any received downlinks if any, last-TX timestamp, last-join timestamp)?
- Should the firmware log to an onboard buffer that gets dumped on next gateway contact? Would explain the Morocco gap if it does happen.
- Is the supercap large enough to survive multi-day shadow conditions, or does v2 need a small lithium primary as backup?
