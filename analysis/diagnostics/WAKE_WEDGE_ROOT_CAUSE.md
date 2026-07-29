# GPS Wake-Wedge — Root Cause Analysis

*Stratolink-3, investigation 2026-06-02. Substantiated three independent ways:
flight data, published literature, and our own firmware/library source.*

## Symptom

On the flight, the MAX-M10S intermittently **wedged**: it stopped answering on
UART after its software-backup nap, so the firmware (pre-fix) re-shipped the
last cached NAV-PVT as a "valid" fix — a frozen position re-transmitted for
0.9–6.9 h at a time, then spontaneous recovery. Across the flight the data
classified **STALE 216 / FRESH 39 / NOGPS 26** (77 % stale; only 39 distinct
fresh fixes in 12 days).

We had already refuted temperature, power, altitude, and runtime as triggers.
This analysis answers the remaining question: **why does the wake intermittently
fail in the first place?**

---

## Line 1 — The flight data has a specific fingerprint

`wedge_statistics.py` → `wedge_statistics.png`. 11 distinct wedge events:

| onset (UTC)      | dur (min) | cycles | onset gap | recovery | rec gap |
|------------------|----------:|-------:|----------:|----------|--------:|
| 2026-05-17 18:25 |       262 |     53 |      1.0× | FRESH    |    2.0× |
| 2026-05-17 23:22 |        46 |      3 |      5.0× | FRESH    |    4.0× |
| 2026-05-18 00:34 |        62 |     11 |      1.0× | NOGPS    |    1.1× |
| 2026-05-18 02:08 |        15 |      4 |      1.0× | NOGPS    |    1.0× |
| 2026-05-19 14:08 |         0 |      1 |      2.0× | NOGPS    |   24.7× |
| 2026-05-28 07:43 |        26 |      6 |      1.0× | FRESH    |    1.0× |
| 2026-05-28 08:22 |        56 |     12 |      1.0× | FRESH    |    0.7× |
| 2026-05-28 09:27 |       416 |     82 |      1.0× | FRESH    |    1.0× |
| 2026-05-28 16:33 |        31 |      7 |      1.0× | FRESH    |    1.0× |
| 2026-05-28 17:19 |       133 |     26 |      1.0× | NOGPS    |    2.0× |
| 2026-05-29 17:58 |        56 |     11 |      1.5× | NOGPS    |    1.0× |

Reading the columns:

- **Onset gap ≈ 1.0× cadence** (9 of 11): wedges begin *cleanly from a fresh
  fix*, one cycle to the next — there is no erratic precursor, no slow
  degradation. The module is fine, then on the very next sleep/wake it's wedged.
- **Recovery gap ≈ 1.0–2.0×, no gap**: the module un-wedges on a *normal cycle
  boundary with no reboot*. The IWDG never fired (a watchdog reset would show as
  a multi-cycle gap + a `boot_reset_cause` IWDG flag). It simply starts
  answering again. (The single 24.7× is the mid-Atlantic gateway-coverage hole,
  not a real recovery.)
- **Sticky run-length is wildly variable**: 1, 3, 4, 6, 7, 11, 11, 12, 26, 53,
  **82** cycles. Once wedged it stays wedged for a memoryless-looking, highly
  variable number of cycles, then clears.

**Interpretation:** onset and recovery both snapped to the sleep/wake cadence,
recovery without a reboot, geometric-looking variable run-lengths → a **per-cycle
stochastic wake failure**. Each wake is an independent ~Bernoulli "did it come
back?" trial. This is *not* a one-shot event and *not* anything that tracks an
environmental variable.

---

## Line 2 — The literature (two research sweeps)

**Backup-wake reliability.** u-blox's "wake on a UART-RX edge" is a
*documented-unreliable* wake source. The u-blox M10 low-power platform notes
themselves recommend using **EXTINT (a hardware pin)** instead, and there are
field reports (Meshtastic firmware #4061) of the M10 failing to cleanly
enter/exit backup when UART-RX is the wake source. Our `0xFF×2 + 10 ms` nudge is
a community heuristic — u-blox specifies only "an edge on UART RX," with no
sanctioned byte sequence, settle time, or guaranteed wake latency.

**Cosmic-ray SEU — refuted, decisively.** The atmospheric neutron flux at
~10.5 km is genuinely elevated (~200× sea level), but the expected single-event
*functional-interrupt* rate for these COTS parts works out to **~1 event per
~19 years** (most-generous cross-section), versus our observed **~3 wedges/day**
— a **4–5 order-of-magnitude** gap. To close it you would need a device
cross-section larger than the physical die area, which is impossible. The
stickiness *morphology* is SEFI-like, but the *rate* rules radiation out
entirely. **Implication: radiation hardening / shielding would fix nothing.**
The HAB/cubesat field consensus matches: treat COTS u-blox lockups as a *hang to
recover* (watchdog / power-cycle), not a radiation problem.

---

## Line 3 — Our own code kills the two obvious firmware-timing culprits

**"Clock not restored before the wake nudge" (the classic STM32 post-STOP bug) —
REFUTED in our firmware.** In `firmware/src/power_manager.cpp`
(`enter_stop1_for_ms`), `SystemClock_Config()` is called on STOP1 exit *before*
control returns to the caller, and the GPS wake nudge happens a full loop
iteration later. Our nudge goes out at a correct 9600 baud — it is not garbled
by a wrong post-STOP clock.

**"The single 0xFF nudge missed the wake edge" — also REFUTED.** We never enable
auto-PVT, so SparkFun's `getPVT()` takes the **explicit-poll branch**
(`u-blox_GNSS.cpp` ~line 11513): every `getPVT()` call sends a UBX-NAV-PVT poll
request = UART TX = a fresh wake edge. Over a 30 s fix window that is **~25 wake
edges per cycle**, not one. If the wedge were merely a missed edge, the *next*
poll 100 ms later would wake the module — it could not persist for 82 cycles.
The library's polling and retry waits historically called STM32duino
`delay()`, whose weak `yield()` is empty on this core. Flight source now
overrides that hook with explicitly shallow WFI so these waits no longer
busy-spin; SysTick and UART remain live. This reduces MCU energy but does not
change the repeated-UART-edge argument or cure a module that ignores UART.

So the module is not "asleep waiting for an edge." It is in a state where it
**ignores UART entirely, and continuous polling does not clear it.** Only a
hardware reset / power-cycle does.

---

## Conclusion (ranked)

1. **The MAX-M10S intermittently fails to exit software-backup into a
   UART-responsive state.** A sticky, module-side wedge induced by our
   `powerOffWithInterrupt()` + UART-RX-wake usage. It clears only when a later
   backup→wake transition happens to come up clean (self-recovery) or on a
   hardware reset. This single mechanism explains *all* of the data fingerprint:
   sticky-for-hours, cycle-aligned onset/recovery, no reboot, variable
   run-lengths. **Primary cause.**
2. *(lower)* An MCU-side USART1 quirk post-STOP1. Possible but less consistent
   with the data; can't be fully separated from (1) without in-flight per-cycle
   telemetry.
3. **Cosmic-ray SEU — refuted** (rate off by 10⁴–10⁵).

---

## What this means for the final candidate

The current postflight StratoLink-2 source goes substantially further than the
original five-cycle patch. It is not a frozen flight candidate until the
post-soak freeze gates pass. During each energy-bounded acquisition it permits at most one
PA0 hardware reset after either:

- 3 seconds without iTOW progress after an epoch anchor; or
- 5 seconds without any new PVT.

Recovery happens inside the same acquisition rather than waiting another
20-minute flight cadence. The reset clears the freshness anchor, so the module
must then produce two forward-moving, in-range GPS-week epochs before any
position can become valid. If same-window recovery still fails, the older
cycle-count ladder remains as a bounded fallback. Power-floor or freefall
mission aborts do not increment that ladder because neither is evidence of a
GNSS wedge.

This would turn the 82- and 53-cycle Flight-3 freezes into honest NOGPS
telemetry immediately and attempt physical recovery within five seconds. The
36-check sanitized freshness/recovery suite plus 400,000 deterministic property
trials proves repeated, backward,
out-of-range, rollover, reset, frozen, silent, and `millis()`-wrap behavior.
Clear-sky HIL must still prove the PA0 reset and two-epoch reacquisition on the
actual MAX-M10S.

### Remaining v2 hardware/observability upgrades, evidence-ranked

1. **Switch GPS wake to EXTINT** — u-blox's own recommendation; attacks the root
   cause (the unreliable UART-RX-wake path). Needs an MCU GPIO → GPS EXTINT
   trace on the v2 PCB.
2. **Hardware power-gate the GPS rail** (load switch on a GPIO) — a true
   power-cycle as the final recovery rung, beyond the PA0 reset.
3. **Per-cycle GPS-state telemetry** (wake-attempts / responded / bytes-rx) — so
   the next flight *proves* the mechanism instead of us inferring it, and
   disambiguates cause (1) from (2).

The formerly proposed software item—verify progress and retry once inside the
same acquisition—is implemented in the current v1 source and covered by the
36 named checks above. It remains a clear-sky final-image HIL gate, not a v2
design item.

---

*Reproduce from the immutable local export:
`analysis/.venv/bin/python analysis/diagnostics/gps_stale_audit.py --csv
analysis/antenna/data/telemetry_raw.csv --no-plot` (run from repo root).*
