# Bench harness, plug-and-play runbook

Everything to run the Meshtastic-relay bench on **stratolink-2** (PSU at 4.8 V, no
supercap yet; solar attached) with **J-Link** + **RTL-SDR**. Firmware compiles clean
(`env:meshtastic_relay_diag`, RAM 4.6% / Flash 21%); these host tools were authored
against the built `.elf` (mrd @ 0x200003F8, 72 B).

## When you get home (3 terminals)

```
# 1) flash the diag (builds + uploads over J-Link; board then auto-cycles phases)
analysis/network/bench/tools/flash_diag.sh

# 2) live-watch the diagnostic struct (one CSV row every ~3 s)
analysis/network/bench/tools/watch_mrd.sh

# 3) watch the air (confirm TX bursts off-air + scan for ambient LongFast)
python3 analysis/network/bench/tools/sdr_observe.py --secs 300
```

The firmware needs **zero interaction**, it auto-cycles a 7-phase battery and
exposes everything in `mrd`. Watch the `phase` column in terminal 2 and the PSU
current display together.

## What each phase gives us

| Phase (≈20 s each) | Read this | Validates |
| --- | --- | --- |
| `SLEEP` | PSU current (radio off baseline) | T5 baseline |
| `STANDBY` | PSU current (radio standby) | T5 |
| `RX` | PSU current = **relay-listen draw**; `rx`/`last_*` if ambient traffic | **T5** (key #), T1 |
| `TXBEACON` | SDR shows bursts @906.875; `toa_us` | T2 (wire presence), TX current |
| `RELAY` | `fwd`/`dedup`/`hop0` counters (vs ambient or, later, a node/emulator) | T3 logic |
| `MODESW` | `msw_us` = mean LoRaWAN↔Meshtastic reconfig time | T6 |
| `BW500` | SDR burst + `bw500_us` (vs LongFast `toa_us`) | T11 |

**T5 (the gating number) on the PSU board:** relay-listen current ≈ `RX` PSU current
- `STANDBY` PSU current. (The 1 F-cap coulomb-counter method returns once the supercap
is installed; on the stiff PSU rail we just read the current directly.)

## Notes / knobs
- `mrd.phase` numbers: 0 SLEEP · 1 STANDBY · 2 RX · 3 TXBEACON · 4 RELAY · 5 MODESW · 6 BW500.
- Force a phase (optional): GDB `set var mrd.cmd=<n>` (else it auto-sequences; cmd 255 = auto).
- Bench courtesy: the beacon uses a **private channel hash** (header byte 13 = 0x7F) and
  **TX power = 2 dBm**, so we don't inject into the live public LongFast mesh while
  characterising. Bump `MESH_TX_DBM` / set the real default channel only for the brief
  interop check once a stock node is on hand.
- SDR needs: `pip install pyrtlsdr numpy` + `brew install librtlsdr`.
- `watch_mrd.sh` briefly halts the core (~ms) each read; harmless for this diag. If JLink
  `mem`/`si` syntax differs on your JLink version, tweak the heredoc in watch_mrd.sh.

## Deferred (need hardware we don't have yet)
- **T3 full A→relay→B bridge, T4 dedup-load, T9 airtime**, need a stock Meshtastic node
  (ordering 2× Heltec V3) and/or the 2nd board as emulator (stratolink-1 back Sunday).
- **T7 solar / floor-abort / f**, needs the **supercap** installed (PSU rail can't show
  harvester/cap dynamics), but only after the BQ25570 charge-ceiling gate is
  closed. The exact ±1% divider has a conservative 5.544 V room-reference
  screen and 5.592 V full-operating-temperature screen against 5.5 V absolute
  maximums; do not begin with unrestricted sun.
- **T10 sensitivity sweep**, needs a step attenuator; SDR + RSSI-of-received is the proxy.
