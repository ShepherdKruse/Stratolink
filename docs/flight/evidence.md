# StratoLink-1 qualification evidence

Cutoff: 2026-10-10 03:35 UTC. **Qualification remains incomplete.** These are
recorded observations of the October 9 candidate, not a live board-status
report or approval to launch. See [remaining acceptance](acceptance.md) and
[recovery and provisioning](recovery.md).

## Exact image and setup

| Artifact | SHA-256 |
| --- | --- |
| Candidate BIN | `55760beecd491a65cbe1bcbfe15f48700ff97c7f5983613af3f7b98666ee56be` |
| Candidate ELF | `c803161e2d440fd394353789ce88305b531b63a8dd1edda01c0ba1d7f81244a1` |
| Build report | `e0f8706116555bd1fdd1c34f3509f2c2be7492824071e92c6d32b73a9ed3f735` |
| Verified October 9 flash manifest | `5b6f29205e9e274519d914adc4084cdc5ae4a97479d9db612fc22a99e58c256b` |

The recorded flash preserved the reserved nonce journal. The bench supplied
VSTOR from a PSU; no supercapacitor was fitted. A lamp and, later, direct sunlight
illuminated the panels. Normal feature and power gates remained enabled.
Voltage samples from this setup do not measure charging energy or MCU-rail
transients. A build from a later source revision is a different candidate until
its bytes and relevant qualification are bound to a new record.

## GNSS, telemetry and commands

The retained TTN archive spans October 9 05:27:51 through October 10 03:22:39 UTC:

| Observation | Result and limit |
| --- | --- |
| Archive coverage | 64 consecutive uplinks, frame counters 1 through 64: 62 primary packets and two known synthetic CTT events. |
| GNSS freshness | 61 primaries report fresh fixes with age zero; one reports atomic no-fix. Independent byte decoding agrees across all 62. This does not measure each acquisition duration or qualify motion. |
| Reset and gap | Frame 44 changes boot count 3 to 4 with reset code 5, classified as brownout with retained session. It reports no fix. Frame 45 follows 4,000.025 seconds later, about 66 minutes 40 seconds. The physical cause and activity during the gap are unknown. |
| Recovery | Frames 45 through 64 contain 20 consecutive fresh primaries on boot 4. Reception intervals range from about 20 minutes 38 seconds to 23 minutes 12 seconds. |
| Decoder checks | Reset, first-recovery and final packets each passed 15 recorded offline gates. Wire fields agree exactly across Python, Node and stored TTN decoding. One derived velocity component in the final packet differs by one floating-point unit in the last place, within the existing four-unit tolerance. |
| Class-A command | One addressed PING sequence 2 was accepted in RX1 and acknowledged by the ordinary primary at 06:52:14 UTC. This establishes that round trip, not every command or session-loss case. |

The reset and gap prevent an uninterrupted-soak pass. An earlier apparent
six-hour capture gap was different: TTN retained the packets while the laptop
was asleep. Preserve this distinction when evaluating future missing records.

## Radio and sensor scope

| Path | Evidence | Still unqualified |
| --- | --- | --- |
| CTT reception | On this image, a short-range synthetic valid/bad-CRC/valid sequence demonstrated reception, CRC rejection, rearm and repeat handling. The normal 60-second window ended. Two synthetic fPort-11 events reached TTN; the later event contained two aggregated hits. | Installed-antenna sensitivity, range, orientation and margin with a representative tag. This was not a wildlife detection. Source power and receiver RSSI were uncalibrated. |
| Meshtastic | Older integrated image `07547a6f` reported at least eight successful driver forwards. The current archive has relay enabled but a forward-delta sum of zero. | Independent peer receipt on the current image, duplicate suppression, bounded loading and return to ordinary TTN service. Historical driver reports are not independent delivery proof. |
| B2B | A July 30 two-board diagnostic received one authenticated synthetic crumb into the receiver's pending queue. | Current-image private-fleet operation, wrong-key rejection, forwarding, command/ACK paths and fPort-12 receipt. The diagnostic used a public test key, omitted TTN delivery and lacks a recovered exact ELF binding. |
| Temperature | The fitted TMP117 has not produced a verified direct reading in these records. Teddy accepted compensated MS5611 temperature as this assembly's fallback. | The TMP117 fault's physical cause and any claim of ambient-air accuracy. A failed dedicated TMP117 is not an additional launch gate for this accepted assembly. |
| Other sensors | Telemetry contains changing sensor samples. | Controlled light, acoustic, pressure and motion stimuli in final mounting. Zero UV or acoustic flags without a stimulus do not qualify those paths. |

The retained BOM audit identifies U2 as RAK3172-9-SM-NI. Its reviewed high-band
qualification does not establish 434 MHz performance. The observed nearby CTT
reception does not close that hardware limit. A compatible independent LoRa
peer is needed for Mesh and B2B; the available FSK source and receive-only SDR
cannot provide that peer.

## Retained evidence

The raw archive, build bundle and detailed bench records are reviewer-local
artifacts held by the test owner. They are not shipped in this repository:
they can include precise locations, session identifiers and credential-bearing
binary state. Arrange private review by the following artifact labels and
hashes. The summary above is the public evidence scope.

| Artifact label | SHA-256 |
| --- | --- |
| October 9 evening TTN archive, 64 records | `1ad21b5e62f5d87d1fca365b2aae5194702a954f65b0c5d75a83a7d7d0ab0f0f` |
| Archive normalization | `69d05a647bf4c9818b890fdbf64e877e4af9e38bd77bef1a02936f326fc97d67` |
| Frame 44 offline parity | `5c72e7437d960759c89e32ff4de85a96524eca24b94045fb494249098c16cd6b` |
| Frame 45 offline parity | `830e4c774ba0d439e81fb883a773c1f54fdac56d99063194c944ed74466de53a` |
| Frame 64 offline parity | `831703b5ce67aad2e15fefd674a3d86e693c1c165213f4eea18ca333edc866fb` |
| Independent CTT CRC-control review | `38665fd30b4f2448dce726b3ae6d44797dd1a916772932813ea654c85d42e771` |
| Historical Mesh/B2B review | `83c0c7de6e27e3e784bf7340ab11383847352d7c4d57eae7343e03dc85e7377b` |
