#!/usr/bin/env python3
"""Decode the `mrd` struct from a JLinkExe `mem` hex dump (stdin) -> one CSV row.

Layout (from `arm-none-eabi-gdb -ex 'ptype /o mrd'`, 72 bytes, naturally aligned):
  I magic, I uptime_s, B phase, B cmd, H vstor_mv, H solar_mv, h begin_state,
  I rx, I crc_err, I fwd, I dedup, I hop0, I to, I from, I id,
  B flags, B hop, B chan, B len, h rssi, h snr_cdb, I txc, I toa, I msw, I bw500
"""
import re, struct, sys, time

PHASES = ["SLEEP", "STANDBY", "RX", "TXBEACON", "RELAY", "MODESW", "BW500"]
FMT = "<IIBBHHhIIIIIIIIBBBBhhIIII"  # == 72 bytes

raw = sys.stdin.read()
# grab hex byte tokens from JLink mem lines:  "200003F8 = 31 44 52 4D ..."
bytes_ = []
for line in raw.splitlines():
    m = re.match(r"^\s*[0-9A-Fa-f]{6,8}\s*[=:]\s*(.*)$", line)
    if not m:
        continue
    for tok in m.group(1).split():
        if re.fullmatch(r"[0-9A-Fa-f]{2}", tok):
            bytes_.append(int(tok, 16))
data = bytes(bytes_[:72])
if len(data) < 72:
    sys.stderr.write(f"[mrd_decode] only {len(data)}/72 bytes parsed; raw:\n{raw}\n")
    sys.exit(1)

(magic, uptime, phase, cmd, vstor, solar, begin, rx, crc, fwd, dedup, hop0,
 to, frm, pid, flags, hop, chan, length, rssi, snr_cdb, txc, toa, msw, bw500) = struct.unpack(FMT, data)

if magic != 0x4D524431:
    sys.stderr.write(f"[mrd_decode] bad magic 0x{magic:08x} (expected 4D524431 'MRD1'), wrong addr or not flashed?\n")
ph = PHASES[phase] if phase < len(PHASES) else f"?{phase}"
ts = time.strftime("%H:%M:%S")
print(f"{ts},{uptime},{ph},{vstor},{solar},{begin},{rx},{crc},{fwd},{dedup},{hop0},"
      f"0x{frm:08x},{hop},{rssi},{snr_cdb/100:.2f},{txc},{toa},{msw},{bw500}")
