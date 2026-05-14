#!/usr/bin/env python3
"""RTL-SDR fake gateway for Stratolink dashboard testing.

Monitors US915 sub-band 2 for LoRa TX events. When a transmission is
detected, injects a synthetic telemetry point into the local Next.js
webhook API. The dashboard shows a new data point each time a board
transmits, validating the full pipeline before TTN gateway arrives.

Usage:
    python test/sdr_gateway.py [--url http://localhost:3000/api/ttn-webhook]
"""
import sys, time, json, struct, base64, random, math, argparse
import numpy as np
import urllib.request

DEVICE_IDS = [
    "stratolink-board-1",
    "stratolink-board-2",
    "stratolink-board-3",
]

# Simulated flight path starting near Charlotte, NC
BASE_LAT = 35.2271
BASE_LON = -80.8431
BASE_ALT = 100

CENTER_FREQ = 904.6e6
SAMPLE_RATE = 2.4e6
GAIN = 40
SPECTRAL_THRESHOLD = 15  # dB above mean to flag TX


def build_payload(lat, lon, alt, temp_cd, press_ch, solar_mv, batt_mv,
                  speed_cms, heading_cd, sats, ax, ay, az, uv, lux, acoustic):
    """Build 35-byte big-endian telemetry payload matching firmware."""
    buf = struct.pack('>iiihhHHHHBhhhBHB',
        int(lat * 1e7),
        int(lon * 1e7),
        int(alt),
        int(temp_cd),
        int(press_ch),
        int(solar_mv),
        int(batt_mv),
        int(speed_cms),
        int(heading_cd),
        int(sats),
        int(ax),
        int(ay),
        int(az),
        int(uv),
        int(lux),
        int(acoustic),
    )
    return buf


def make_ttn_payload(device_id, raw_bytes):
    """Wrap raw payload in TTN webhook format."""
    return {
        "end_device_ids": {"device_id": device_id},
        "received_at": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        "uplink_message": {
            "frm_payload": base64.b64encode(raw_bytes).decode(),
            "rx_metadata": [{"rssi": -85, "snr": 8.5}],
        },
    }


def post_webhook(url, payload):
    """POST JSON to local webhook."""
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data,
                                headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=5)
        return resp.status == 200
    except Exception as e:
        print(f"  POST failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="RTL-SDR fake gateway")
    parser.add_argument("--url", default="http://localhost:3000/api/ttn-webhook",
                        help="Webhook URL (default: localhost:3000)")
    parser.add_argument("--duration", type=int, default=300,
                        help="Listen duration in seconds (default: 300)")
    parser.add_argument("--no-sdr", action="store_true",
                        help="Skip RTL-SDR, inject test data every 10s")
    args = parser.parse_args()

    # Flight simulation state
    flight_time = 0
    device_idx = 0

    if args.no_sdr:
        print(f"No-SDR mode: injecting test data every 10s to {args.url}")
        start = time.time()
        while time.time() - start < args.duration:
            flight_time += 10
            alt = BASE_ALT + flight_time * 5  # 5 m/s ascent
            lat = BASE_LAT + flight_time * 0.0001 * math.sin(flight_time / 60)
            lon = BASE_LON + flight_time * 0.0002

            device_id = DEVICE_IDS[device_idx % len(DEVICE_IDS)]
            device_idx += 1

            raw = build_payload(
                lat, lon, alt,
                temp_cd=-450 + random.randint(-20, 20),
                press_ch=10130 - int(alt * 1.2),
                solar_mv=random.randint(3000, 5000),
                batt_mv=random.randint(3200, 4200),
                speed_cms=random.randint(100, 500),
                heading_cd=random.randint(0, 36000),
                sats=random.randint(6, 14),
                ax=random.randint(-50, 50),
                ay=random.randint(-50, 50),
                az=random.randint(950, 1050),
                uv=random.randint(0, 12),
                lux=random.randint(0, 50000),
                acoustic=1 if random.random() < 0.1 else 0,
            )

            ttn = make_ttn_payload(device_id, raw)
            ok = post_webhook(args.url, ttn)
            status = "OK" if ok else "FAIL"
            print(f"[{int(time.time()-start):3d}s] {device_id} alt={alt:.0f}m -> {status}")
            time.sleep(10)
        return

    # RTL-SDR mode
    from rtlsdr import RtlSdr
    sdr = RtlSdr()
    sdr.sample_rate = SAMPLE_RATE
    sdr.center_freq = CENTER_FREQ
    sdr.gain = GAIN

    print(f"RTL-SDR gateway listening on {CENTER_FREQ/1e6:.1f} MHz")
    print(f"Injecting to {args.url}")
    print(f"Duration: {args.duration}s\n")

    # Baseline
    bl = sdr.read_samples(1024 * 64)

    start = time.time()
    last_inject = 0
    inject_count = 0
    MIN_INTERVAL = 5  # Don't inject more than once per 5s

    try:
        while time.time() - start < args.duration:
            s = sdr.read_samples(1024 * 16)
            fft = np.fft.fftshift(np.fft.fft(s[:1024]))
            peak = 10 * np.log10(np.max(np.abs(fft)**2) + 1e-12)
            mean = 10 * np.log10(np.mean(np.abs(fft)**2) + 1e-12)

            if peak - mean > SPECTRAL_THRESHOLD and time.time() - last_inject > MIN_INTERVAL:
                flight_time += MIN_INTERVAL
                alt = BASE_ALT + flight_time * 5
                lat = BASE_LAT + flight_time * 0.0001 * math.sin(flight_time / 60)
                lon = BASE_LON + flight_time * 0.0002

                device_id = DEVICE_IDS[device_idx % len(DEVICE_IDS)]
                device_idx += 1

                raw = build_payload(
                    lat, lon, alt,
                    temp_cd=-450 + random.randint(-20, 20),
                    press_ch=max(100, 10130 - int(alt * 1.2)),
                    solar_mv=random.randint(3000, 5000),
                    batt_mv=random.randint(3200, 4200),
                    speed_cms=random.randint(100, 500),
                    heading_cd=random.randint(0, 36000),
                    sats=random.randint(6, 14),
                    ax=random.randint(-50, 50),
                    ay=random.randint(-50, 50),
                    az=random.randint(950, 1050),
                    uv=random.randint(0, 12),
                    lux=random.randint(0, 50000),
                    acoustic=1 if random.random() < 0.1 else 0,
                )

                ttn = make_ttn_payload(device_id, raw)
                ok = post_webhook(args.url, ttn)
                inject_count += 1
                last_inject = time.time()

                elapsed = int(time.time() - start)
                status = "OK" if ok else "FAIL"
                print(f"[{elapsed:3d}s] TX detected -> {device_id} alt={alt:.0f}m -> {status}")

            time.sleep(0.15)

    except KeyboardInterrupt:
        pass

    sdr.close()
    print(f"\nDone. Injected {inject_count} telemetry points in {int(time.time()-start)}s.")


if __name__ == "__main__":
    main()
