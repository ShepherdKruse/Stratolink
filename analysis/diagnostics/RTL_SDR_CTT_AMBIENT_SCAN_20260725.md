# RTL-SDR ambient 434 MHz check — 2026-07-25

Status: **fixture proven / no CTT claim**

The directly connected RTL-SDR Blog V4 enumerated as serial `00000001` with
its R828D tuner. A 45-row, one-second-cadence `rtl_power` scan covered
433-435 MHz at 7.8125 kHz bins from 19:08:54 through 19:09:38 PDT.

- raw temporary capture: `/tmp/stratolink_ctt_433_435_20260725.csv`
- raw size: 83,565 bytes
- raw SHA-256: `daf893f8abe866b4693f809cb1209512335f22be07af1ac4a793dee99db3b8da`
- largest temporal bin excursion: 5.26 dB at approximately 433.754 MHz
- largest excursion within 433.95-434.05 MHz: 1.01 dB at approximately
  433.973 MHz

This proves only that the USB receiver can acquire an ambient spectrum. It is
not a calibrated noise figure, sensitivity, protocol decode, or evidence that
a CTT tag was present. The strongest transient was away from the firmware's
434.000 MHz center. A real exact-tag stimulus, known attenuation/path loss,
and decoded identifier are still required.

Most importantly, the external RTL-SDR cannot qualify the payload's onboard
receiver. StratoLink-2 fits the high-band `RAK3172-9-SM-NI`; RAK assigns 434
MHz to the low-band module. CTT must remain experimental and be disabled in the
frozen launch image unless an exact 434 MHz tag is decoded by the onboard radio
at a launch-relevant measured margin.
