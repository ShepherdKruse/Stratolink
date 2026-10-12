# Firmware

STM32WLE5 firmware for the Stratolink payload. Assembly, TTN registration, and programming instructions are in the [hardware docs](https://stratolink.org/docs/hardware).

## Build and upload

Install PlatformIO and SEGGER's J-Link tools. From this directory:

```sh
cp include/secrets.h.example include/secrets.h
```

Fill in the regional DevEUIs and AppKeys from your TTN registrations. Keep the file private. Empty regional credentials disable joins in that region; an empty fleet key disables authenticated balloon-to-balloon messages.

```sh
pio run -e stratolink
pio run -e stratolink --target upload
```

Upload requires J-Link over SWD. Preserve the device's DevNonce journal when re-flashing a previously joined payload. Do not mass-erase it to force a new join.

Use `stratolink` for the flight candidate. Other PlatformIO environments are bench diagnostics and change the normal radio or power behavior. Build success does not qualify the assembled board for flight; use the [acceptance checks](../docs/flight/acceptance.md).

## Development

- [platformio.ini](platformio.ini): pinned toolchain, dependencies, and build environments.
- [include/config.h](include/config.h): sampling, power, and radio configuration.
- [include/stratolink_pins.h](include/stratolink_pins.h): board pin assignments.
- [DOCUMENTATION.md](DOCUMENTATION.md): module behavior and telemetry format.
- [test/README.md](test/README.md): host checks and offline uplink decoding.

Run the host checks from the repository root:

```sh
bash analysis/diagnostics/run_host_suites.sh
node --experimental-strip-types --test firmware/test/ttn_uplink_formatter.host-test.mjs
```
