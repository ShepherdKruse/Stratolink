#!/usr/bin/env python3
"""RTL-SDR watcher for the Meshtastic relay bench.

Watches 906.875 MHz (US LongFast default slot) and reports power-vs-time bursts, to
(a) CONFIRM the diag's TX bursts off-air (correlate timing with the TXBEACON / BW500 /
RELAY phases on watch_mrd.sh), and (b) SCAN for ambient LongFast traffic near the bench
(if a local mesh is active, the RX phase can then receive + parse real frames -> T1).

Full LoRa demodulation needs gr-lora_sdr (GNU Radio); this is presence + timing +
relative power, which is exactly what verifies wire-level TX without a stock node.

Usage:  python3 sdr_observe.py [--freq 906.875e6] [--secs 120]
Needs:  pip install pyrtlsdr numpy   ;   brew install librtlsdr
"""
import argparse, sys, time
try:
    import numpy as np
    from rtlsdr import RtlSdr
except Exception as e:
    sys.exit("Need pyrtlsdr + numpy:\n  pip install pyrtlsdr numpy\n  brew install librtlsdr\n(" + str(e) + ")")

ap = argparse.ArgumentParser()
ap.add_argument("--freq", type=float, default=906.875e6, help="center Hz (US LongFast slot)")
ap.add_argument("--secs", type=float, default=120)
ap.add_argument("--rate", type=float, default=1.024e6, help="sample rate (>> 250 kHz BW)")
ap.add_argument("--gain", default="auto")
ap.add_argument("--thresh_db", type=float, default=8.0, help="burst = noise floor + this")
a = ap.parse_args()

sdr = RtlSdr()
sdr.sample_rate = a.rate
sdr.center_freq = a.freq
sdr.gain = a.gain
BLK = 32768
blk_ms = BLK / a.rate * 1000.0

# noise-floor estimate from a few quiet blocks
nf = min(10*np.log10(np.mean(np.abs(sdr.read_samples(BLK))**2)+1e-12) for _ in range(5))
thr = nf + a.thresh_db
print(f"center {a.freq/1e6:.3f} MHz | rate {a.rate/1e6:.3f} Msps | block {blk_ms:.0f} ms | "
      f"noise≈{nf:.1f} dB(rel) | burst > {thr:.1f} dB")
print("watching… (run a TX phase / send a Meshtastic message nearby to see a BURST line)")

t0 = time.time(); n = 0; inb = False; bstart = 0.0
try:
    while time.time() - t0 < a.secs:
        s = sdr.read_samples(BLK)
        p = 10*np.log10(np.mean(np.abs(s)**2)+1e-12)
        now = time.time() - t0
        if p > thr and not inb:
            inb = True; bstart = now; n += 1
            print(f"  +{now:6.1f}s  BURST start  {p:5.1f} dB (+{p-nf:.1f})")
        elif p <= thr and inb:
            inb = False
            print(f"  +{now:6.1f}s  BURST end    ({(now-bstart)*1000:.0f} ms)")
finally:
    sdr.close()
print(f"done: {n} bursts over {a.secs:.0f}s @ {a.freq/1e6:.3f} MHz")
