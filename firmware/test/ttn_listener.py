#!/usr/bin/env python3
"""
TTN Telemetry Listener — Stratolink

Connects to TTN via MQTT and prints decoded telemetry from Stratolink devices
in real time. Decodes the 35-byte big-endian payload into human-readable fields.

Usage:
    python ttn_listener.py --app-id stratolink --api-key "NNSXS.xxx"

Environment variable fallbacks: TTN_APP_ID, TTN_API_KEY, TTN_TENANT (default: ttn)

Requires: pip install paho-mqtt
"""

import argparse
import base64
import json
import os
import ssl
import struct
import sys
import time
from datetime import datetime

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("Error: paho-mqtt not installed. Run: pip install paho-mqtt")
    sys.exit(1)

# 35-byte big-endian telemetry payload format
STRUCT_FMT = '>iiihhHHHHBhhhBHB'
FIELDS = [
    'lat_e7', 'lon_e7', 'altitude_m',
    'temperature_cd', 'pressure_ch',
    'solar_mv', 'battery_mv',
    'speed_cm_s', 'heading_cd', 'satellites',
    'accel_x', 'accel_y', 'accel_z',
    'uv_index', 'ambient_lux', 'acoustic_event'
]

DEFAULT_HOST = 'nam1.cloud.thethings.network'
DEFAULT_PORT = 8883


def decode_telemetry(b64_payload):
    """Decode base64 frm_payload into a dict with human-readable values."""
    raw = base64.b64decode(b64_payload)
    if len(raw) != 35:
        return None

    vals = struct.unpack(STRUCT_FMT, raw)
    d = dict(zip(FIELDS, vals))

    # Unit conversions
    d['lat'] = d['lat_e7'] / 1e7
    d['lon'] = d['lon_e7'] / 1e7
    d['temperature'] = d['temperature_cd'] / 10.0
    d['pressure'] = d['pressure_ch'] / 10.0
    d['speed'] = d['speed_cm_s'] / 100.0
    d['heading'] = d['heading_cd'] / 100.0
    d['accel_x'] = d['accel_x'] / 100.0
    d['accel_y'] = d['accel_y'] / 100.0
    d['accel_z'] = d['accel_z'] / 100.0
    return d


def print_uplink(device_id, t, rssi, snr, freq, sf, bw, fcnt):
    """Print header for an uplink."""
    ts = datetime.fromisoformat(t.replace('Z', '+00:00')).strftime('%H:%M:%S') if t else '??:??:??'
    print(f"\n{'=' * 60}")
    print(f"  {device_id}  {ts}  fcnt={fcnt}")
    freq_mhz = freq / 1e6 if freq else 0
    bw_khz = bw // 1000 if bw else 0
    print(f"  RSSI={rssi} dBm  SNR={snr} dB  {freq_mhz:.1f} MHz  SF{sf} BW{bw_khz}kHz")
    print(f"{'=' * 60}")


def print_telemetry(d):
    """Print decoded telemetry fields."""
    print(f"  GPS:         {d['lat']:.7f}, {d['lon']:.7f}  alt={d['altitude_m']}m")
    print(f"  Satellites:  {d['satellites']}  speed={d['speed']:.2f}m/s  hdg={d['heading']:.1f}")
    print(f"  Temperature: {d['temperature']:.1f} C")
    print(f"  Pressure:    {d['pressure']:.1f} hPa")
    print(f"  Accel:       ({d['accel_x']:.2f}, {d['accel_y']:.2f}, {d['accel_z']:.2f}) m/s2")
    print(f"  UV index:    {d['uv_index']}")
    print(f"  Lux:         {d['ambient_lux']}")
    print(f"  Acoustic:    {'EVENT' if d['acoustic_event'] else 'quiet'}")
    print(f"  Solar:       {d['solar_mv']} mV   VSTOR: {d['battery_mv']} mV")


def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        topic = userdata['topic']
        client.subscribe(topic)
        print(f"Connected to TTN. Listening on: {topic}")
        print("Waiting for uplinks... (Ctrl+C to quit)\n")
    else:
        print(f"Connection failed: rc={rc}")


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        up = payload.get('uplink_message', {})
        dev = payload.get('end_device_ids', {}).get('device_id', '?')
        t = up.get('received_at', '')
        fcnt = up.get('f_cnt', '?')

        # RF metadata
        rx = up.get('rx_metadata', [{}])[0]
        rssi = rx.get('rssi', '?')
        snr = rx.get('snr', '?')

        # Radio settings
        settings = up.get('settings', {})
        freq = int(settings.get('frequency', 0) or 0)
        lora = settings.get('data_rate', {}).get('lora', {})
        sf = lora.get('spreading_factor', '?')
        bw = int(lora.get('bandwidth', 0) or 0)

        print_uplink(dev, t, rssi, snr, freq, sf, bw, fcnt)

        frm = up.get('frm_payload')
        if frm:
            d = decode_telemetry(frm)
            if d:
                print_telemetry(d)
            else:
                raw = base64.b64decode(frm)
                print(f"  Payload ({len(raw)}B): {raw.hex()}")
        else:
            print("  (no payload)")

    except Exception as e:
        print(f"  Error decoding: {e}")


def on_disconnect(client, userdata, rc, properties=None):
    if rc != 0:
        print(f"Disconnected (rc={rc}), reconnecting...")


def main():
    parser = argparse.ArgumentParser(description='TTN Telemetry Listener for Stratolink')
    parser.add_argument('--app-id', default=os.environ.get('TTN_APP_ID'),
                        help='TTN application ID (or TTN_APP_ID env var)')
    parser.add_argument('--api-key', default=os.environ.get('TTN_API_KEY'),
                        help='TTN API key (or TTN_API_KEY env var)')
    parser.add_argument('--tenant', default=os.environ.get('TTN_TENANT', 'ttn'),
                        help='TTN tenant (default: ttn)')
    parser.add_argument('--host', default=DEFAULT_HOST, help='MQTT host')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT, help='MQTT port')
    parser.add_argument('--device', default=None, help='Filter to specific device ID')
    args = parser.parse_args()

    if not args.app_id or not args.api_key:
        print("Error: --app-id and --api-key required (or set TTN_APP_ID / TTN_API_KEY)")
        sys.exit(1)

    username = f"{args.app_id}@{args.tenant}"
    device_filter = args.device or '+'
    topic = f"v3/{username}/devices/{device_filter}/up"

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(username, args.api_key)
    client.tls_set_context(ssl.create_default_context())
    client.reconnect_delay_set(min_delay=1, max_delay=60)

    client.user_data_set({'topic': topic})
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect

    print(f"Connecting to {args.host}:{args.port} as {username}...")

    try:
        client.connect(args.host, args.port)
        client.loop_forever()
    except KeyboardInterrupt:
        print("\nDisconnecting...")
        client.disconnect()


if __name__ == '__main__':
    main()
