[![Stratolink - stratolink.org](assets/images/stratolink-banner.png)](https://stratolink.org)

[stratolink.org](https://stratolink.org)

An open source pico balloon network. This repository contains the payload hardware, firmware, website, and flight models. Follow the [docs](https://stratolink.org/docs/getting-started) to build a payload, prepare a balloon, and register it on the [dashboard](https://stratolink.org/dashboard).

## Repository

```text
hardware/    KiCad schematics, PCB layouts, component libraries, and assembly files
firmware/    STM32WLE5 firmware, PlatformIO configuration, and host tests
web/         Website, public docs, dashboard, APIs, and forecast worker
supabase/    Database migrations and permission checks
simulation/  Balloon trajectories, buoyancy, and fleet coverage models
analysis/    Antenna, radio, power, and flight studies; bench diagnostics
docs/        Engineering notes for flight qualification and forecasting
scripts/     Sticker layout tool
assets/      Original project artwork and simulation media
```

## Firmware

Install [PlatformIO](https://platformio.org/install/cli). From the repository root:

```sh
cd firmware
cp include/secrets.h.example include/secrets.h
```

Fill in your regional TTN credentials, then build the flight environment:

```sh
pio run -e stratolink
```

Upload through J-Link over SWD:

```sh
pio run -e stratolink --target upload
```

Use the firmware revision that matches your board. [Hardware setup](https://stratolink.org/docs/hardware) covers assembly and programming; [firmware/README.md](firmware/README.md) covers configuration and host checks.

## Website

Use Node 22. From the repository root:

```sh
cd web
cp .env.example .env.local
ONNXRUNTIME_NODE_INSTALL=skip npm ci
npm run dev
```

Set the values in `.env.local` as described in [web/README.md](web/README.md). Run `npm run verify` before submitting website changes. Deployment and backend setup are documented there.

---

- [Fork this repository](https://github.com/Stratolink-hq/Stratolink/fork)
- [Watch this repo](https://github.com/Stratolink-hq/Stratolink/subscription)
- [Create issue](https://github.com/Stratolink-hq/Stratolink/issues/new)
