# StratoLink two-node CTT wildlife HIL

This test proves the 434 MHz receive/decode/aggregate/queue path using
StratoLink-1 as a finite test-tag emulator and StratoLink-2 as the receiver.
Both payloads use the high-band RAK3172-9 assembly. Passing is functional HIL;
it is **not** calibrated weak-tag sensitivity or airborne-range evidence.

## Preconditions

- Do not touch StratoLink-2 with J-Link until its clean power soak, standby
  handoff, and precursor-preservation gates have passed.
- Keep the ordinary flight image and transmitter diagnostic hashes distinct.
- Use a controlled/shielded RF arrangement with an appropriate antenna or
  load. Never run an RF PA into an open or unknown load.
- Power the boards independently. One J-Link can be moved between them.
- Preserve the exact diagnostic ELFs used to generate the evidence bundle.

## Build and generate exact-image readers

```sh
cd firmware
/Users/twarn/.platformio/penv/bin/pio run -e ctt_diag -e ctt_tx_diag
cd ..
analysis/.venv/bin/python analysis/diagnostics/ctt_two_node_hil.py generate \
  --receiver-elf firmware/.pio/build/ctt_diag/firmware.elf \
  --transmitter-elf firmware/.pio/build/ctt_tx_diag/firmware.elf \
  --output-dir analysis/diagnostics/generated/ctt_two_node
```

## Physical sequence

1. Power off StratoLink-1. Flash its exact `ctt_tx_diag` image through the
   guarded diagnostic flashing procedure, verify bytes, then disconnect it.
2. Flash StratoLink-2 with exact `ctt_diag`, verify bytes, and leave J-Link on
   StratoLink-2. Start the receiver first.
3. Place the payloads in the controlled RF arrangement and power StratoLink-1.
   It waits ten seconds, sends exactly 24 packets at -9 dBm with at least ten
   seconds of silence after each, then permanently enters standby.
4. Wait until the four-minute transmitter sequence is complete. Without
   resetting either board, run the generated receiver J-Link script. It dumps
   `ctt_receiver_s_ctt.bin` and `ctt_receiver_s_ctt_queue.bin`.
5. Keep StratoLink-1 powered, move J-Link to it, and run the generated
   transmitter script to dump `ctt_transmitter_ctt_tx_diag_state.bin`.
6. Evaluate all three raw dumps:

```sh
analysis/.venv/bin/python analysis/diagnostics/ctt_two_node_hil.py evaluate \
  --receiver-stats ctt_receiver_s_ctt.bin \
  --receiver-queue ctt_receiver_s_ctt_queue.bin \
  --transmitter-state ctt_transmitter_ctt_tx_diag_state.bin \
  --output analysis/diagnostics/logs/stratolink_ctt_two_node_result.json
```

The evaluator requires all 24 transmissions and receptions, exactly one CRC
failure, three-beep aggregation of the reference tag, explicit handling of a
CRC-valid non-dictionary ID, 21 distinct detections, the exact 16-entry queue,
five bounded drops, zero receive-arm failures, and clean transmitter state.

## Integrated flight-image gate

The standalone receiver test is not enough to enable wildlife collection.
After it passes, enable `CTT_LISTEN_ENABLE`, rebuild and fully verify a new
flight candidate, and repeat a valid stimulus against that exact image. Require
an fPort-11 event and a later ordinary TTN uplink with no radio restore failure.
Then repeat at increasing separation/attenuation while recording StratoLink RSSI
and RTL-SDR level. Report that sweep only as relative margin because neither
high-band assembly is a calibrated 434 MHz reference receiver or transmitter.
