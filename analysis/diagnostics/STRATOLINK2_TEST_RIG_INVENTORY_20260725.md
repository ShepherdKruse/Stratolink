# StratoLink-2 launch-rig inventory — 2026-07-25

This is a read-only inventory of the connected bench, first captured at 06:56
PDT and rechecked at 20:00 and 23:47 PDT. The 23:47 recheck still showed the
PPK2, J-Link, and RTL-SDR, while the RAK4631/WisCore serial peer remained
absent. USB enumeration proves host presence, not target-level function.
Target connection, reset, halt, and flash are deliberately deferred until the
16-hour soak and power-handoff gates pass.

| Bench element | Current host evidence | Qualification role | Scope limit |
|---|---|---|---|
| Nordic Power Profiler Kit II | Enumerated directly on a Mac USB controller as `PPK2`, serial `D6269E9D378E`; control/data ports `/dev/cu.usbmodemD6269E9D378E2` and `...E4` | Continuous 4.660 V payload source and later current profiling | Live supervisor acknowledgment plus payload VSTOR/TTN continuity prove the active supply path; the present hold intentionally does not stream current samples |
| StratoLink-2 payload | TTN uplinks received by gateway `onethreenine`; PPK2 log advancing every about 30.44 s | Device under test | No J-Link target access during the active soak |
| SEGGER J-Link EDU Mini | Enumerated through the switched USB 2.x hub as `J-Link`, serial `000802007563` | SWD precursor preservation, exact flash, and state capture | USB presence does not prove VTref/SWD contact; that check is intentionally post-soak |
| Meshtastic peer | Earlier enumerated through the switched hub as `WisCore RAK4631 Board`, serial port `/dev/cu.usbmodem2113201`; the corrected 3,600.756 s passive capture validated 50 current RF packets across 12 opaque source tokens and excluded cached history. The 20:00 PDT recheck does **not** show this serial device, so it must be restored before controlled post-soak HIL. | LongFast receive/forward/duplicate/hop-limit HIL | The earlier capture proves live nearby LongFast stimulus only; active exact-ID StratoLink receive/forward/cancel/CAD evidence remains post-flash and currently lacks its serial peer. |
| RTL-SDR | Enumerated through the switched hub as `RTLSDRBlog Blog V4`, serial `00000001` | Passive spectrum/timing corroboration | Energy detection alone is not protocol demodulation |
| Switched Rosonway path | Visible as nested USB 2.1/3.2 hubs. J-Link and RTL-SDR are currently present; the RAK4631 was present in the earlier inventory but is absent on the 20:00 PDT recheck. | Independently switchable bench peripherals | Hub enumeration is not a payload power source; restore the peer without changing the PPK2 path after the hold. |
| Indoor TTN gateway | Repeated uplinks identify gateway `onethreenine` across all eight tested US915 FSB2 channels | LoRaWAN RF and backend observation | Network evidence does not prove RX2 join acceptance or absolute sensitivity floor |

## Power-path conclusion

The PPK2 is on a separate direct USB-controller branch from the switched hub.
Turning hub ports on or off can affect the J-Link, RAK4631, and RTL-SDR, but
does not remove the PPK2 host connection. The running supervisor explicitly
reasserts source-meter mode, 4.660 V, and DUT power on every heartbeat, has
reported zero reconnects, and never commands DUT power off. J-Link VTref is
therefore a target-reference measurement, not the payload supply.

The originally launched standby was intentionally strict and had already
loaded code that would reject an early/failed terminal record. A second
read-only rescue watcher now observes only the append-only primary log. It
performs no USB/serial access and creates no handoff log for a valid 16-hour
endpoint, leaving the original standby as sole writer. Only an explicitly
short, wrong-voltage, or reconnected terminal record—cases the old standby
would reject—causes it to take over at 4.660 V. Qualification remains failed in
that case; this fallback preserves the no-supercap payload state rather than
confusing power preservation with soak acceptance. Future launches use the
updated `ppk2_power_handoff.py`, which takes over on any well-formed terminal
record while `soak_summary.py` independently enforces the strict evidence.

## Shaded-soak condition

The solar panels were deliberately shaded while the PPK2 remained the sole
controlled source; the required cover is opaque and nonconductive. By fCnt 91
the payload reported 8 mV solar input and 0 lux; fCnt 91-97 then remained at 8 mV solar
with contiguous normal cadence, VSTOR 4.600-4.628 V, and PPK2 heartbeats
bracketing every uplink. Keep the GNSS and RF antennas and sensor apertures
uncovered. This isolates shaded power-path survival; it is not solar-harvester,
charge-ceiling, panel-current, or supercap qualification.

## RAK4631 band boundary

The passive log identifies the connected peer as `WISMESH_TAG`, region `US`,
LongFast. Do not repurpose it as a 434 MHz CTT transmitter merely because its
radio is an SX1262. RAKWireless documents distinct RAK4631(H) matching for
US915/EU868 and RAK4631(L) matching for EU433/CN470. Until the exact module
variant and a correct low-band antenna are physically verified, 434 MHz TX is
outside this rig's accepted configuration and cannot close the CTT RF gate.
The connected peer remains suitable for the post-flash 906.875 MHz LongFast
Meshtastic stimulus. See the [RAK4631 RF characteristics](https://docs.rakwireless.com/product-categories/wisblock/rak4631/datasheet/#rf-characteristics).

The same distinction is decisive on the payload itself. The production BOM's
LCSC part `C18548052` resolves to `RAK3172-9-SM-NI`, the 9xx MHz high-band
module—not the `-43` EU433 variant. RAK assigns EU433 to RAK3172(L) and
documents the high-band P2P floor as 525/600 MHz. A 434 MHz register
configuration on StratoLink-2 is therefore not supported receiver evidence.
The exact ordering suffix also matters inside the high band: RAK assigns the
fitted `-9` SKU to US915/AU915/KR920/AS923 and the separate `-8` SKU to
RU864/IN865/EU868. Flight-3's 142 received EU868 uplinks prove that one flown
assembly worked at 868.1/868.3/868.5 MHz under those conditions, not that this
`-9` SKU has specified conducted power, sensitivity, matching, certification,
cold margin, or repeatability at EU868. The local US915 gateway cannot close
that exact-SKU EU gate.
See the [RAK3172 RF characteristics](https://docs.rakwireless.com/product-categories/wisduo/rak3172-module/datasheet/#rf-characteristics).

## Post-soak connection order

1. Require the primary PPK2 `hold_end` and standby 4.660 V takeover.
2. Freeze the TTN collector and prove final backend parity.
3. Preserve the complete precursor before modifying the MCU.
4. Only then verify J-Link VTref/SWD identity and flash the frozen candidate.
5. Use the RAK4631 and RTL-SDR for focused RF HIL without changing the PPK2
   power source.
