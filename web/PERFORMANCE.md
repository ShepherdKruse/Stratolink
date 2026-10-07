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
- Send only the site origin on Mapbox requests. The dashboard keeps its page-wide no-referrer policy for QR/auth privacy, but the URL-restricted production Mapbox token needs an origin to validate map requests. The same night-lights tile returned 403 without a referrer and 200 with the site origin. No path, query or claim token is sent.

The indexed lookup benchmark used 100 synthetic balloons with 10,000 packets each and 120 cursor updates. Median lookup time for the whole fleet was 0.050 ms; p95 was 0.120 ms. This measures only position, packet and card-altitude lookups, not React, networking or Mapbox rendering.

Worker tests cover out-of-order tile replies, cancellation, disposal and fallback when worker WebGL is unavailable. Replay tests cover long histories, exact timestamps, duplicate timestamps, gaps, missing GPS, antimeridian crossings and cache replacement after refresh.

## Remaining measurements

Rerun PageSpeed on the deployed build. Check mobile initial layout shifts, real scroll/globe navigation, large-fleet fetching and rendering, and verify that the Mapbox tile failures are resolved in the deployed browser.

## Production follow-up: October 7, 16:33 PDT

Deployed commit: `f49c476` (PR 80). New PageSpeed reports:

- [Homepage](https://pagespeed.web.dev/analysis/https-stratolink-org/trgvchra3k)
- [Dashboard](https://pagespeed.web.dev/analysis/https-stratolink-org-dashboard/d1gkjga21z)

| Page | Device | Performance | FCP | LCP | TBT | CLS |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Home | Mobile | 97 | 0.9 s | 1.2 s | 0 ms | 0 |
| Home | Desktop | 100 | 0.3 s | 0.3 s | 0 ms | 0.006 |
| Dashboard | Mobile | 23 | 5.1 s | 9.1 s | 1,860 ms | 0.202 |
| Dashboard | Desktop | 61 | 0.6 s | 0.6 s | 8,370 ms | 0 |

Mapbox requests now pass its origin restriction. Best Practices is 100 on both pages. Dashboard blocking time decreased, but its mobile load worsened in this run. The largest paint is the wordmark loaded after JavaScript. The 0.202 shift comes from map controls moving as fleet cards arrive. Most remaining desktop blocking time is within Mapbox initialization/rendering. The dashboard remains under investigation.

## Fleet loading follow-up

- Render the interface before loading the Mapbox module; preload the wordmark and declare its dimensions.
- Wait for the initial registry before mounting map controls, so they do not move when cards arrive.
- Derive contact times and positions from the same sanitized histories already used by cards and replay. Remove redundant per-device summary queries and unused fleet aggregates.
- Preserve the registry when selecting a card. Refresh registry metadata once a minute while visible.
- Limit simultaneous history requests to four across fleet and detail views. Share pending requests and publish completed histories in batches.
- Stop polling completed flights. Continue checking missing balloons for new packets.
- Release the temporary WebGL capability-check context.

A local synthetic fixture loaded 100 balloons with 1,000 packets each through the compiled dashboard. All 100 cards rendered; search and timeline navigation worked; the request peak was four. This fixture never contacted the production telemetry API. It is a functional scaling check on the development machine, not a claim about slow-device frame rates or production network latency.
