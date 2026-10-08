# Assets

## Launch scene

The source is Teddy Warner's launch photograph, supplied as `/Users/twarn/Downloads/IMG_3466.jpeg` (2560 × 1440). The unchanged source photo is served locally as `public/assets/launch/source.jpg`.

| Runtime file | Dimensions | Use |
| --- | --- | --- |
| `public/assets/launch/source.jpg` | 2560 × 1440 | Original photograph, used for the visible foreground and balloon pixels |
| `public/assets/launch/sky.png` | 1672 × 941, RGB | Clear sky plate inpainted with the built-in image generator; fills behind the moving city, clouds and balloon |
| `public/assets/launch/city-clouds.png` | 1672 × 941, RGBA | Generated alpha mask for the original skyline, clouds and foreground palm |
| `public/assets/launch/balloon.png` | 1672 × 941, RGBA | Generated alpha mask for the original balloon, tether and payload |
| `public/assets/stratolink-wordmark.svg` | 7581 × 1510 viewBox | Lowercase Stratolink wordmark, Helvetica Regular converted to outlines; header and footer |

The two transparent extraction files are used only as alpha masks inside inline SVG. Their generated RGB pixels are not displayed. Each SVG displays the original source photograph through its mask, preserving the photograph's original balloon, payload, skyline and cloud pixels. The cloud mask is softly feathered. Below 768px, an SVG alpha transfer removes faint sky residue before a narrower feather is applied; the desktop mask stays unchanged. The balloon mask is restricted to the assembly's bounds to discard stray alpha. All layers share the source photo's full-canvas framing. The sky plate is an inpainted approximation of the original clear-sky gradient, including the areas originally hidden by foreground objects.

Exact built-in image generation prompts, output provenance and known extraction limits are recorded in [reference/launch-layer-prompts.md](reference/launch-layer-prompts.md). Page text uses Helvetica with Arial as a fallback.

An unused white-cloud experiment is archived at `reference/experiments/footer-cloud.png`, outside the production build. Its exact prompts and native output provenance are recorded in [reference/footer-cloud-prompt.md](reference/footer-cloud-prompt.md).

## Inline payload

`public/assets/launch/payload-cutout.png` is a 384 × 256 transparent extraction generated from Teddy's `DSCF0471.JPG`. It appears inline in the homepage's fourth paragraph. The original photograph is unchanged. [Prompt and provenance](reference/payload-cutout-prompt.md) record the built-in imagegen edit and its limits.

## Dashboard

The dashboard's logo and TTN gateway files are unchanged copies from [`ShepherdKruse/Stratolink` at `b95c4f4`](https://github.com/ShepherdKruse/Stratolink/tree/b95c4f4dee684e73fbfdb2d5af2df13a3dd87949/web/public), imported October 5, 2026. Their original public paths are preserved.

| Runtime file | Bytes | Use |
| --- | ---: | --- |
| `public/stratolink-header-logo.png` | 109,433 | Dashboard header wordmark |
| `public/ttnmapper-gateways.json` | 577,506 | Gateway coordinates |
| `public/ttnmapper-coverage.json` | 788,268 | Inner coverage polygons |
| `public/ttnmapper-coverage-outer.json` | 490,552 | Outer coverage polygons |
| `public/assets/dashboard/fonts/*.woff2` | 285,052 total | 13 unchanged Inter and JetBrains Mono files served by the live site's Next font stylesheet |

Font faces, Unicode ranges and fallback metrics are preserved in `src/dashboard/fonts.css`. The telemetry theme retains its upstream Google Fonts import for Space Grotesk, Inter and JetBrains Mono. Mapbox supplies map styles, tiles and night-light imagery at runtime; these are not copied into the repository. Public telemetry and forecasts remain live data rather than bundled snapshots.

The imported dashboard assets total 2,250,811 bytes. [Dashboard import provenance](reference/dashboard-import.md) records their SHA-256 hashes, font source URLs and runtime dependencies.

## Archived Opal reference assets

The Opal visual assets and fonts were retrieved from [Opal Electronics](https://op.al/) on October 5, 2026 for the initial local reference recreation. They are preserved under `reference/opal-assets/`, outside `public/`, and are not shipped by the current page.

| Local file | Original source | Details |
| --- | --- | --- |
| `reference/opal-assets/DieGrotesk-C-Regular.woff2` | [Regular font](https://op.al/fonts/DieGrotesk-C-Regular.woff2) | Die Grotesk C, weight 400 |
| `reference/opal-assets/DieGrotesk-C-Bold.woff2` | [Bold font](https://op.al/fonts/DieGrotesk-C-Bold.woff2) | Die Grotesk C, weight 700 |
| `reference/opal-assets/desktop-first-frame-long-may6.avif` | [Desktop poster](https://op.al/images/desktop-first-frame-long-may6.avif) | 2160 × 3840, original desktop first frame |
| `reference/opal-assets/mobile-first-frame-may6.avif` | [Mobile poster](https://op.al/images/mobile-first-frame-may6.avif) | 1440 × 7300, original mobile first frame |
| `reference/opal-assets/noise.avif` | [Noise texture](https://op.al/images/noise.avif) | 400 × 400, original grain tile |
| `reference/opal-assets/footer-canvas-logo.svg` | [Footer logo](https://op.al/svg/footer-canvas-logo.svg) | 1561 × 743 viewBox, canvas dot mask |
| `reference/opal-assets/opal-electronics.svg` | [Homepage](https://op.al/) | Header SVG extracted from the public HTML, 130 × 40 viewBox |
| `reference/opal-assets/share-1200x630.jpg` | [Share image](https://op.al/images/share-1200x630.jpg) | Original social preview image |
| `reference/opal-assets/table-desktop.mp4` | [Desktop video stream](https://stream.mux.com/YB6EvIvPQIBZ02XNCo4FyikxpaamDsTp4OSgtSxVJlIM.m3u8) | 2160 × 3840, 118.3 seconds; H.264 CRF 24, original resolution, fast start |
| `reference/opal-assets/table-mobile.mp4` | [Mobile video stream](https://stream.mux.com/i00IsRNG1QFKYPOWSEDqo4eTloV2E2heEd2wzXMMbNgo.m3u8) | 758 × 3840, 49.43 seconds; original H.264 stream remuxed with fast start |

The reference footage, fonts, logos and copy remain their respective owners' work. `reference/opal-essay.html` preserves the original page reference. Original media has been moved, not deleted.

- `public/assets/icons/`: Font Awesome Free 7.3.1 solid chevron, bars, and close icons from the installed package. Icons by Fonticons, Inc., licensed under [CC BY 4.0](https://fontawesome.com/license/free).

## Globe favicon

`public/assets/favicon/` and `public/favicon.ico` are generated by `python3 scripts/favicon.py` (Pillow required). The orthographic globe uses the footer map's pale land and blue-gray ocean palette, with 96 small rotation frames. The geometry is Natural Earth land data from [world-atlas 2.0.2](https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/land-110m.json). Source data and the world-atlas ISC license are preserved in `reference/favicon/`. These icons are locally rendered, not Mapbox tile captures.

## Documentation and flight report

- `public/assets/docs/prep/step-1.webp` through `step-5.webp`: Caleb's supplied balloon preparation illustrations from [Balloon Prep Instructions](https://docs.google.com/document/d/1MAjnRQ_FJlPp3UlCDkJsattvJtSizqM8LzH9ldyVReM/edit). Originally made with the Midjourney edit model, as confirmed in the team discussion. Exterior white backgrounds removed using built-in image editing, preserving the illustration subjects and actual alpha, then encoded to WebP. Original PNGs are archived under `reference/balloon-prep-images/`. See [edit prompts](reference/prep-image-edits.md).
- The `step-*-480.webp` and `step-*-960.webp` variants are smaller delivery copies of those illustrations. Regenerate them with `node scripts/prepare-docs-images.mjs` and libwebp's `cwebp` installed. Color quality is 90 and alpha quality is 100. The browser selects an inline size; enlargement always opens the unchanged full-resolution file. Generated variants are committed, so the deployment build does not need libwebp.
- `public/assets/docs/ttn-credentials.png`: original official TTN Console image, with no browser frame. `ttn-decoder.png` and `ttn-webhook.png` are additional official examples. The Things Industries documentation is Apache 2.0; its license is included beside the screenshot. See [source details](reference/content-audit.md).
- `public/assets/docs/dashboard-fleet.png` and `dashboard-register.png`: screenshots of this local frontend. The registration image uses dummy identifiers and does not imply a working authentication service.
- `public/assets/docs/ttn-uplink-formatter.js`: current Stratolink decoder, MIT license retained in the file. It includes no credentials.
- `public/assets/blog/baja-ascent.svg`: regenerated from the report's 98 published ascent samples, with missing GPS readings left blank. See [blog provenance](reference/blog-content-audit.md).
- The antenna mounting plot is an accessible SVG generated from saved simulation results. It is identified as simulation, not a physical antenna measurement. See [research sources](reference/antenna-research.md).
- KaTeX 0.19.0 supplies equation markup and fonts. Equations render at build time; no remote math service is used.

- `public/assets/docs/payload-in-flight.jpg`: Teddy’s supplied DSCF0471.JPG, with metadata removed. An actual payload photograph.
- `public/assets/docs/schematic/stratolink.svg`: exported directly from the local KiCad schematic with kicad-cli, black-and-white and without the page frame. PICO Mainboard revision 2026-02-08.
- `public/assets/blog/baja-floating.jpg` and `baja-payload.jpg`: actual May 17 launch media from Teddy's Stratolink chat. The hero is a frame from the release video. Original capture times and provenance are in [the media audit](reference/radio-silence-research.md). Web exports contain no EXIF/GPS metadata. The unused pre-release `baja-launch.jpg` web export was removed; its original remains in the ignored reference archive.
- `public/assets/blog/reconstructed-flight.jpg`: user-supplied June map by Caleb. The article explains the assumed endpoint used to reconstruct the route.
- `public/assets/blog/reconstruction-june-overlap.png`: original June 26 11:09 graphic exported from Teddy's Messages attachment. The caption identifies its percentages as model weights, not established location probabilities.
- `public/assets/blog/reconstruction-gateway-candidates.png`: June 26 gateway experiment reproduced with its original calculations and neutral labels. See `reference/blog/reconstruction-gateway-candidates.py`.
- `public/assets/blog/reconstruction-radio-footprint.svg` and `reconstruction-startup-delay.svg`: clean scientific replots of the June range and dawn calculations. `reconstruction-signal-range.svg` is a new comparison of the earlier received flight data. Their reproducible script, sanitized input rows and provenance are in `reference/blog/reconstruction-figures.py`. Map geometry uses locally cached Natural Earth data.
- Copy, help, check, close and storage icons use Font Awesome Free from the installed package.
