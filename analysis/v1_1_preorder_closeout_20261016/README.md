# v1.1 pre-order closeout

The desktop engineering and manufacturing-package review is complete for the three development assemblies. **The only current external wait is JLC's reply to the AS7331 sourcing and lead-time inquiry.** The saved Y26 cart remains UV-omitted until that answer establishes the exact part, total added cost and timing. Nothing has been ordered.

This closes the ambiguous wording in the previous final response. There is no outstanding native reroute, symbol correction, unexplained DRC/ERC finding, BOM mismatch or library repair identified by the reviews. Factory production-file approval and physical tests of the assembled pilots are later workflow stages, not unfinished pre-order CAD review. Those stages remain real and cannot be marked passed before their evidence exists.

## Completed now

- Corrected the stale [hardware checklist](../../hardware/pcb/TODO.md), which still described Y24 and left the already-completed JLC import and placement review unchecked.
- Independently audited every remaining item: [residual review](residual-review.md). No additional demonstrated CAD or population defect requires a layout change before ordering development samples.
- Completed the [U6 pre-order review](uv-review.md), with fresh checks of all sixteen pins/lands, support components, native/exported placement and stencil. The [placement guide](uv-placement-guide.svg) specifies the physical pin-1 target independent of JLC's rotation convention.
- Prepared complete manufacturing exports for both choices. The populated option adds U6 and exactly sixteen paste apertures; all other BOM/CPL rows and fabrication geometry remain unchanged.
- Reopened the saved JLC form and verified **Confirm Production file = Yes**, **Confirm Parts Placement = Yes**, and **Do not confirm automatically = checked**. [Captured controls](jlc-confirmations.json). No order settings, CAD, BOM or placements were changed during this closeout.
- Reran the existing package verifier independently. [Passing result](residual-package-check.json): 166 manufacturing inputs, both complete output inventories and 57 matching selected JLC references.

## Where the reply will arrive

The inquiry was sent **by email**, from Teddy's personal Gmail account to **support@jlcpcb.com**. The subject is **AS7331 sourcing cost and lead time for three-board PCBA draft**. The thread contains the original request and the Y26 identifier update. It is not a sourcing request submitted through the JLC website. The personal inbox was checked during this closeout; no supplier reply was present at that check.

The expected answer should settle availability, exact orderable, required spares, all incremental charges and earliest dispatch. A [supplement was sent in the same email thread](inquiry-supplement.md) with the completed UV review, exact orientation, populated files and process constraints, so those can be addressed in the same sourcing response. If JLC selects AQFT instead of AQFM, record its exact identity in the BOM; the manufacturer documents the same electrical device/package with a different reel quantity.

## What happens after that answer

Choose the UV population and ordering cost/timing. If U6 is included, use the full-population BOM, CPL and stencil together and obtain JLC's mapping of its placement library to the supplied physical pin-1 target. That mapping is supplier information, not an unreviewed native pin assignment. The current 180-degree export must not be treated as a verified JLC machine-library angle by itself.

JLC's order workflow will generate production panel, rail/tab, stencil and final placement outputs. They must be compared to the supplied files before manufacturing approval. Current customer files and instructions are already reviewed, and automatic production approval is disabled.

Once the pilots arrive, perform the [physical acceptance procedure](../v1_1_release_20261012/pilot-acceptance.md). Cold solar input bounds, balancer startup, real solder joints, RF/GNSS performance and mounted mechanical strength require actual hardware. In particular, missing cold panel Voc/I–V data cannot be supplied by a desktop simulation. This is development-sample ordering readiness, not a claim that the assembled revision is already flight-qualified.

## Recheck

```sh
python3 analysis/v1_1_final_sweep_20261016/verify.py
python3 hardware/downloads/build.py --check
```

For the fresh native U6 checks, run `verify_uv.py` with KiCad's bundled Python. It reads CAD and writes only this directory's UV evidence/diagram. Previous frozen evidence and current CAD remain unchanged.
