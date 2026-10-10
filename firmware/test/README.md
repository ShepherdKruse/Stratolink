# Host checks

Run from the repository root. No command below connects to hardware.

```sh
bash analysis/diagnostics/run_host_suites.sh
node --experimental-strip-types --test firmware/test/ttn_uplink_formatter.host-test.mjs
```

The C++ runner uses ASan and UBSan. The decoder test generates packets with
the firmware encoders and compares the public TTN formatter with the web parser.
It covers primary v1/v2/v3, CTT v1/v2, and B2B v3. It does not verify B2B CMACs.

The parser and radio runtime regressions under `analysis/diagnostics` use the
pinned libraries installed by PlatformIO:

```sh
cd firmware
pio pkg install -e stratolink
pio run -e stratolink
```

An empty credential configuration is sufficient for this build. These checks
do not qualify RF sensitivity, receiver timing, current draw, or flight energy.

# Offline decoding

```sh
node firmware/test/decode_ttn_uplink.mjs uplinks.json
node firmware/test/decode_ttn_uplink.mjs < uplinks.ndjson
```

Input can be a direct `{bytes, fPort, recvTime}` object, a raw TTN uplink, an
array, or NDJSON. Output retains each input alongside its decoded result and
returns a nonzero status if any packet fails. The CLI uses the existing
[public TTN formatter](../../web/public/assets/docs/ttn-uplink-formatter.js).
Raw archive envelopes must be validated before their records are extracted.
