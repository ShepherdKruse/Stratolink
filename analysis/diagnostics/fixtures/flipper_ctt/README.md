# Synthetic CTT fixtures

These four files encode a synthetic identifier, not a wildlife detection. Each
contains 80 logical bits at 25 kbit/s, lasting 3.2 ms. The stock Flipper CLI can
leave a longer carrier tail; logical packet duration is not RF-off evidence.

| Fixture | On-air bytes | SHA-256 |
| --- | --- | --- |
| `base/ctt_synthetic_valid.sub` | `AAAAAAD39178554C3358` | `da933c974330d28f53a80f2e32f4227adc32a8404b817f54f68b43c3a1b0a09f` |
| `base/ctt_synthetic_bad_crc.sub` | `AAAAAAD39178554C335A` | `4808d061a3965d65e5ad3c734eb3176e45d766c504287a24ee7d725486f94c11` |
| `minus20/ctt_synthetic_valid_minus20.sub` | `AAAAAAD39178554C3358` | `5034d151ff0c788767e6276775b892bd2fd325c79061e4a1716d3b1894fc9495` |
| `minus20_bad/ctt_synthetic_bad_crc_minus20.sub` | `AAAAAAD39178554C335A` | `4cd4f758dec20544e536868ec2909dac63395590edc64d76bb1a214d9a88a55a` |

The minus20 variants change only preset byte 38 from `0x12` to `0x0E`. The
nominal -30/-20 dBm settings are not calibrated radiated-power measurements.
The fixtures retain their original bytes and hashes. The published helper has
different bytes because it uses these committed paths and requires an explicit
serial target. Both adapters pin that helper; update those pins only after
reviewing a helper change.

From the repository root, the default command checks local fixture hashes only:

```sh
python3 analysis/diagnostics/flipper_ctt_bench_20261009.py
```

The valid and bad-CRC minus20 adapters also default to local checks. Hardware
actions require `--execute-hardware`, an explicit mode, `--serial-port` and a new
output directory. Transmission additionally requires the successful stage
manifest, exact fixture hash and allowed remote path. Existing remote files are
not replaced, uncertain writes/transmissions are not retried, and repeat is
fixed to one. The tools require the reviewed official Flipper 1.3.4 firmware and
its existing region restrictions; the adapter does not change those restrictions.
