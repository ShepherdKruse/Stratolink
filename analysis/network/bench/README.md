# Meshtastic-relay bench data

Raw + processed data from the bench tests in
[`../07_meshtastic_bench_plan.md`](../07_meshtastic_bench_plan.md). One subdir per
test; each holds the raw capture (J-Link/RTT log, power-rig export) + a tidy CSV with
the schema below. The analysis scripts read these CSVs so the models become
**bench-substantiated** instead of datasheet-assumed.

## Per-test CSV schemas (log these consistently at the bench)

| Test | file | columns |
| --- | --- | --- |
| T1 rx | `T1_rx/rx.csv` | ts, rssi_dbm, snr_db, len, to, from, id, hop_limit, hop_start, chan_hash, crc_ok |
| T2 tx | `T2_tx/tx.csv` | ts, payload_len, stock_rx (0/1), stock_rssi, notes |
| T3 relay | `T3_relay/relay.csv` | ts, from, id, hop_in, hop_out, forwarded(0/1), c_received(0/1), latency_ms, psk_loaded(0/1) |
| T4 dedup | `T4_dedup/dedup.csv` | ts, from, id, action(forward/dedup/cancel/hop0), late_delay_ms |
| T5 power | `T5_power/power.csv` | mode(rx_stop/rx_run/sleep/tx), i_mean_ma, i_peak_ma, v_rail, woke_on_rxdone(0/1) |
| T6 modeswitch | `T6_modeswitch/swap.csv` | ts, dir(lw2mesh/mesh2lw), swap_ms, ttn_uplink_ok(0/1) |
| T7 solar | `T7_solar/solar.csv` | ts, lamp(bright/dim/dark), vstor_mv, solar_mv, relay_on(0/1), i_ma, floor_abort(0/1) |
| T8 priority | `T8_priority/cycles.csv` | cycle, ttn_due_ts, ttn_actual_ts, late_ms, missed(0/1), relay_pkts_in_gap |
| T9 airtime | `T9_airtime/airtime.csv` | offered_pph, airutiltx_pct, chutil_pct, forwarded_pph, capped(0/1) |
| T10 sensitivity | `T10_sensitivity/sens.csv` | atten_db, rssi_dbm, snr_db, decoded(0/1) |
| T11 bw | `T11_bw/bw.csv` | preset(longfast250/longturbo500), toa_ms, tx_energy_mj, interop_default(0/1) |

## Which model each test updates
- **T5, T7** → `../../power/relay_power_budget.py`, `../../power/relay_availability.py`
  (replace the 5.5 mA / f≈0.58 / surplus assumptions with measured values).
- **T9** → `../../network/91_open_relay.py` (the AirUtilTX cap + ChUtil backoff curve).
- **T10** → `../../network/90_meshtastic_relay.py` (sensitivity → footprint).
- **T3, T4, T6, T8** → validate the firmware design in `../04_meshtastic_architecture.md`
  (pass/fail, no model re-fit).
- **T11** → resolves the BW250-vs-BW500 decision in `../06_compliance_and_setup.md`.

After each test, re-run the linked script with the measured CSV and note in the relevant
doc whether the bench **confirmed** or **refuted** the model number.
