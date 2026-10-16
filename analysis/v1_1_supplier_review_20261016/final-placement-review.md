# Independent supplier placement review

PCB `25b201eb09c6746a22d1c3be42f7d4023319dd6fa5e3e587dc8cf42d97bb4d7f`.
Corrected CPL `bf3bb3cf5d633fe95922b7a415dff4278c8bb8fd261d1d737c2401d201be1b00` from `hardware/gerbers/v1.1-pilot-supplier-20261016/CPL-stratolink.csv`.

**U8 at top-side CPL 90° is accepted for this supplier preview.** The fresh screenshot shows a vertical body, three leads right, two left and the pin 1 marker lower-right. All five leads align with the native lands. The only CSV field changed from the original import is U8 Rotation, 180° to 90°; no XY, layer or other part row changed.

| Ref | Supplier side / angle | Independent result |
|---|---|---|
| U1 | bottom / 270° | Consistent: upper-left index. |
| U2 | top / 90° | Consistent: lower-left index, twelve-pad lower edge. |
| U3 | top / 180° | Consistent: lower-right index. |
| U4 | top / 270° | Consistent: upper-left separate index, vertical body. |
| U5 | top / 180° | Consistent: lower-right A1 index. |
| U7 | top / 0° | Consistent: lower-left index. |
| U8 | top / 90° | Consistent: lower-right pin 1, three leads right. |

The bottom population image shows the 16 expected bottom parts, with U1 the only IC. CSV population remains 57 references: 41 top and 16 bottom. Prior BOM selection independently established U6 only DNP, with C14/C23/R27 retained.

D1 and D3 show checkerboard placeholders centered on horizontal and vertical lands respectively. L2 also lacks a true body model. Their actual package-body orientation and clearance cannot be certified from these pictures; retain native placement and exact part identities for factory assembly review. D1/D3 are bidirectional TVS parts. L1 body alignment appears consistent.

All screenshot hashes, observations and exact CPL comparison are in `final-placement-review.json`. The unchanged IC closeups belong to the original import; the corrected CSV alters U8 rotation only. No browser or CAD changes were performed. This review qualifies the visible placement previews, not factory CAM or physical solder joints.
