# Remaining V1 acceptance

Status at the [October 10 evidence cutoff](evidence.md): **not qualified for
launch**. The next steps are a PSU-backed driving trial, controlled peer RF
tests and final solar/store qualification. None is recorded here as complete.

## Driving trial

Keep the recorded image and production burst detector enabled unless a later,
explicit test plan changes them. A disabled burst detector would not qualify
normal flight behavior.

1. Verify the image identity, antenna mounting and power arrangement. Record
   power-on/off times and any supply interruption. Obtain an open-sky stationary
   baseline before motion, including a fresh fix and an ordinary TTN primary.
2. Record an independent, timestamped phone-GPS route privately. Run long enough
   for several ordinary wake cycles; the preceding bench intervals were about
   20 to 23 minutes. Do not accelerate the schedule to manufacture continuity.
3. Retain raw TTN records before their configured retention expires. Compare
   received fixes with the independent route, boot/reset state and fix age.
   Keep gateway coverage gaps separate from demonstrated acquisition failures.
4. Record false burst entries, their duration, return to normal cadence and any
   reset. A successful drive requires fresh moving fixes, ordinary wake recovery
   and accounted-for exceptions. It does not qualify the final energy store.

Stop and investigate an unexpected reset or persistent acquisition failure.
Preserve the preceding records before changing firmware or power. An absent
packet by itself is inconclusive outside known receiver coverage.

## Final power and thermal assembly

The PSU setup had no fitted supercapacitor. Before fitting or charging one,
resolve the actual divider, store rating and balancing circuit together. The
retained tolerance screen reaches about 5.592 V against a 5.5 V store limit;
this is a calculation, not a measured charge voltage. C5's balance pin was
unconnected in the reviewed PCB. Verify the assembled topology and measure
stack and accessible cell voltages before accepting it.

Measure energy and rail margin across GNSS acquisition and extended retries,
transmit/receive windows, normal sleep and GNSS reset-held containment. Historical
STOP-current measurements do not establish this image's complete-cycle budget.
Size reserve for the intended darkness interval, cold conditions and component
aging using those measurements.

Then test the final panels, store, antennas and mounting through controlled
dark discharge, load sag, brownout and autonomous sunrise restart. Record MCU
rail behavior as well as VSTOR. Repeat startup, GNSS, radio, sensor and recovery
checks at the intended cold envelope. Historical cold telemetry from another
flight does not qualify this assembly.

## RF and fault acceptance

| Test | Required observation |
| --- | --- |
| CTT margin | A stated required range/margin, representative transmitter and controlled levels, distances and orientations; packet-success measurements on the installed antenna. Resolve the exact module's 434 MHz qualification before accepting range claims. |
| Mesh forwarding | Controlled compatible LoRa peer traffic, independent receipt of a forward, duplicate suppression, bounded load and the next ordinary primary. |
| Authenticated B2B | Compatible authorized peer, private-fleet authentication, wrong-key/duplicate rejection, correct identity and age, required command/ACK behavior and fPort-12 delivery. Add a further peer if the claimed hop count requires it. Duplicate suppression is expiring state, not durable replay protection. |
| Session and peripheral faults | Planned cases for lost server session, failed counter persistence, retained-state loss, GNSS shutdown failure, radio BUSY/sleep failure and ADC/I2C faults. Each must reach bounded recovery or a measured low-current state with an autonomous exit. |
| Burst and primary service | Bounded burst behavior during representative motion and power sag; optional radios and sensor faults must not indefinitely suppress primary health telemetry. |

A missing peer or uncalibrated source leaves a test open. It does not establish
a firmware defect or a pass. Record any intervention and restore and verify the
candidate before continuing ordinary-operation evidence.

## Final release gate

Freeze one BIN/ELF and its source, dependency and provisioning identities after
the required changes stop. On that exact fitted assembly:

- Obtain two advancing fresh GNSS epochs and the correct region decision.
- Receive at least two ordinary, non-burst TTN primaries separated by a measured
  sleep interval and scheduled wake, without a debugger or bench authority seed.
- Exercise the required radio, command and sensor paths with the accepted
  MS5611 fallback explicitly recorded.
- Complete at least 24 hours across a day/night transition after final-power
  qualification, preserving server evidence before retention expires. Account
  for every reset, interruption and missing interval.
- Close the October 9 brownout/gap investigation and repeat the relevant power
  and recovery cases. A later firmware or assembly change needs a stated scope
  of requalification.

Keep a short sign-off record: candidate hashes, assembly revision, test dates,
measured limits, evidence hashes, exceptions and reviewer. Website deployment
is coordinated with its owners; it is not a substitute for these physical gates.
