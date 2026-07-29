#!/usr/bin/env python3
"""Export EVERYTHING we have on a single Stratolink-3 join, as a shareable packet.

Pulls the live Network-Server record from TTN EU1 and writes two files:
  board3_join_<date>_raw.json  -- the raw join uplink + session context (machine readable)
  board3_join_<date>.md        -- annotated, plain-English breakdown of every field

Provenance: this is the ONLY place the data lives. Storage API has 0 data uplinks
(joins only), the app webhook never fired (no telemetry), so the connection metadata
is read straight from the Network Server:
  GET https://eu1.cloud.thethings.network/api/v3/ns/applications/eu-stratolink/devices/
      stratolink-3-eu?field_mask=mac_state,pending_mac_state,session,pending_session

Run: set -a; source ~/.config/stratolink/env; set +a
     analysis/.venv/bin/python analysis/network/export_join_packet.py
"""
import os, sys, json, base64, datetime as dt, urllib.request, urllib.parse
from pathlib import Path

KEY = os.environ.get("TTN_EU_API_KEY")
if not KEY:
    sys.exit("set TTN_EU_API_KEY (source ~/.config/stratolink/env)")
APP, DEV = "eu-stratolink", "stratolink-3-eu"
BASE = "https://eu1.cloud.thethings.network/api/v3"
URL = (f"{BASE}/ns/applications/{APP}/devices/{DEV}"
       "?field_mask=mac_state,pending_mac_state,session,pending_session")
req = urllib.request.Request(URL, headers={"Authorization": f"Bearer {KEY}"})
rec = json.load(urllib.request.urlopen(req, timeout=40))

# newest uplink across both mac states (a NEW join from a different gateway = triangulation!)
def uplinks(ms): return (rec.get(ms) or {}).get("recent_uplinks") or []
allu = uplinks("mac_state") + uplinks("pending_mac_state")
joins = [u for u in uplinks("pending_mac_state")] or allu
join = joins[-1]
# the join we care about is the most recent pending (the 2026-06-24 one)
ts_guess = "2026-06-24"

def decode_token(tok):
    if not tok: return {}
    raw = base64.b64decode(tok)
    ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in raw)
    # readable network identifiers embedded by Packet Broker
    nets = [s for s in ascii_str.replace(".", " ").split() if "." in s or "-" in s and len(s) > 6]
    return {"len_bytes": len(raw), "ascii": ascii_str,
            "forwarder_hints": [s for s in ("cometsystem-cloud", "eu1.cloud.thethings.industries") if s in ascii_str]}

rx0 = (join.get("rx_metadata") or [{}])[0]
tok = decode_token(rx0.get("uplink_token", ""))

packet = {
    "_provenance": {
        "source": "TTN The Things Stack v3 Network Server (eu1.cloud.thethings.network)",
        "endpoint": URL,
        "pulled_field": "pending_mac_state.recent_uplinks[-1]",
        "note": "gateway is Packet-Broker anonymized: gateway_id='packetbroker', no EUI/location/RSSI-from-named-gw",
    },
    "device": {"application_id": APP, "device_id": DEV,
               "dev_eui": join.get("payload", {}).get("join_request_payload", {}).get("dev_eui")},
    "join_request_payload": join.get("payload", {}),
    "phy_settings": join.get("settings", {}),
    "rx_metadata": join.get("rx_metadata", []),
    "decoded_uplink_token": tok,
    "session": {"current_dev_addr": (rec.get("session") or {}).get("dev_addr"),
                "pending_dev_addr": (rec.get("pending_session") or {}).get("dev_addr")},
    "newest_uplink_seen": max((u.get("received_at") or "" for u in allu), default="(none in record)"),
}

OUT = Path(__file__).resolve().parent
(OUT / f"board3_join_{ts_guess}_raw.json").write_text(json.dumps(packet, indent=2))

jr = join.get("payload", {}).get("join_request_payload", {})
dr = join.get("settings", {}).get("data_rate", {}).get("lora", {})
md = f"""# Stratolink-3 — raw data from the 2026-06-24 join ("connection request")

**One ping. This is everything the network captured.** Pulled from the TTN EU1 Network
Server (see `_provenance` in the JSON). The app webhook never fired and Storage has zero
data uplinks, so this NS record is the only copy.

## What a LoRaWAN join-request actually contains
An OTAA **join-request is tiny** — it is just the device knocking on the door. It carries
**no GPS, no sensor data, no location** — only enough to authenticate:

| field | our value | meaning |
|---|---|---|
| MHDR | join-request | message type |
| JoinEUI (AppEUI) | `{jr.get('join_eui')}` | which application it wants to join |
| DevEUI | `{jr.get('dev_eui')}` | the device's globally-unique id (board #3) |
| DevNonce | `{jr.get('dev_nonce')}`  (= {int(jr.get('dev_nonce','0') or '0',16)} dec) | anti-replay nonce; if a counter, ~that many lifetime joins |
| MIC | `{join.get('payload',{}).get('mic')}` | integrity check (AppKey-signed) |

That's the whole request. **Everything useful about *where* it was comes from the
gateway's reception metadata**, which the network adds on top:

## Reception metadata (what the gateway/network reported)
| field | value | note |
|---|---|---|
| gateway_id | `{rx0.get('gateway_id') if rx0.get('gateway_id') else (rx0.get('gateway_ids') or {}).get('gateway_id')}` | **anonymized by Packet Broker** — real id/EUI/location stripped |
| channel_rssi | **{rx0.get('channel_rssi')} dBm** | signal strength of the channel |
| snr | **{rx0.get('snr')} dB** | SF7 demod floor is ~-7.5 dB → this is right at the cliff |
| rssi | {rx0.get('rssi')} | stripped by Packet Broker |
| location | {rx0.get('location')} | none (anonymized) |
| fine_timestamp | {rx0.get('fine_timestamp')} | none → no TDOA geolocation |
| data_rate | SF{dr.get('spreading_factor')} / BW {int(dr.get('bandwidth',0))//1000} kHz / CR {dr.get('coding_rate')} | the flight config |
| uplink_token | (decoded) | routes back to **{', '.join(tok.get('forwarder_hints') or ['?'])}** = COMET's private network |

## What it tells us (and doesn't)
- **No location, no gateway EUI, no fine timestamp, only one gateway** → we cannot read a
  position straight off it, and cannot triangulate from this single anonymized receiver.
- **The one usable signal is the strength:** channel_rssi **-121 dBm** + SNR **-7.25 dB**
  sit right at the SF7 sensitivity cliff → the link was at ~**max range** (~250-340 km at
  10 km), so the balloon was at the *edge* of that gateway's reach, not overhead.
- Forwarder network = **COMET** (cometsystem-cloud, a private TTI tenant), so the gateway
  is a COMET customer site somewhere in Europe — exact location not exposed.

See `board3_join_{ts_guess}_raw.json` for the byte-level record.
"""
(OUT / f"board3_join_{ts_guess}.md").write_text(md)
print("wrote", OUT / f"board3_join_{ts_guess}_raw.json")
print("wrote", OUT / f"board3_join_{ts_guess}.md")
print("newest uplink in record:", packet["newest_uplink_seen"], "(if newer than 2026-06-24 -> NEW ping!)")
print("join time field / dev_nonce:", jr.get("dev_nonce"), "| pending DevAddr:", packet["session"]["pending_dev_addr"])
