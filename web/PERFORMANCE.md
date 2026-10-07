# Performance review

Baseline: production `7d6c1a7`, October 7, 2026. Google PageSpeed Insights, Lighthouse 13.5.0. These are single lab runs, not field measurements; PageSpeed had no CrUX data for this site.

| Page | Device | Performance | LCP | Total blocking time | CLS |
| --- | --- | ---: | ---: | ---: | ---: |
| Home | Mobile | 54 | 13.4 s | 330 ms | 0 |
| Home | Desktop | 40 | 4.3 s | 3,340 ms | 0.006 |
| Dashboard | Mobile | 48 | 2.9 s | 3,470 ms | 0.202 |
| Dashboard | Desktop | 60 | 0.6 s | 16,980 ms | 0 |
| Balloon preparation | Mobile | 100 | 1.2 s | 0 ms | 0 |

Reports: [home](https://pagespeed.web.dev/analysis/https-stratolink-org/yu4ww6hnnb), [dashboard](https://pagespeed.web.dev/analysis/https-stratolink-org-dashboard/kcqprsa2ri), [docs](https://pagespeed.web.dev/analysis/https-stratolink-org-docs-balloon-prep/05tonm2oji).

## First pass

- Encode the sky as quality-94 WebP and the inline payload at its display resolution. Preserve the source photographs.
- Remove unused RGB channels from alpha masks. All 1,573,352 alpha samples in each mask match the originals exactly. The four delivered launch assets drop from about 2.5 MB to 190 KB. The sky's PSNR against the original is 46.90 dB.
- Load the footer dashboard within 700 pixels of the footer instead of 2,400. It no longer starts during the initial desktop intro at the tested viewport. The globe still uses the same Mapbox instance through navigation.
- Move the unchanged day/night shaders and synchronous pixel readbacks to an OffscreenCanvas worker. Transfer pixel buffers and release the worker with its map source. Retain the renderer for browsers without worker WebGL.
- Cache GPS and altitude indices and use binary lookup while scrubbing. Reuse fleet paths until the underlying history changes.
- Read scroll geometry before writing styles, stop the footer rotation loop when out of view, and initialize the mobile layout from the actual viewport.
- Render the hardware antenna formula through the same installed KaTeX version as the calculator. Equations are built into HTML, with matching local CSS/fonts and accessible MathML. There is no runtime math script or math service key.

The indexed lookup benchmark used 100 synthetic balloons with 10,000 packets each and 120 cursor updates. Median lookup time for the whole fleet was 0.050 ms; p95 was 0.120 ms. This measures only position, packet and card-altitude lookups, not React, networking or Mapbox rendering.

Worker tests cover out-of-order tile replies, cancellation, disposal and fallback when worker WebGL is unavailable. Replay tests cover long histories, exact timestamps, duplicate timestamps, gaps, missing GPS, antimeridian crossings and cache replacement after refresh.

## Remaining measurements

Rerun PageSpeed on the deployed build. Check mobile initial layout shifts, real scroll/globe navigation, large-fleet fetching and rendering, and the Mapbox tile failures reported by the remote audit. Direct read-only checks of the deployed public token returned 200 for the light style, terrain, bathymetry and a night-lights tile; the remote audit's rejected requests still require investigation.
