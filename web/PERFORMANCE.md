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

## Dashboard startup follow-up

Production `cfe7167` (PR 81), [repeat PageSpeed run](https://pagespeed.web.dev/analysis/https-stratolink-org-dashboard/pihu1viccg), October 7, 16:46 PDT:

| Device | Performance | FCP | LCP | TBT | CLS |
| --- | ---: | ---: | ---: | ---: | ---: |
| Mobile | 48 | 2.9 s | 3.3 s | 6,800 ms | 0 |
| Desktop | 60 | 0.6 s | 0.6 s | 11,130 ms | 0 |

An earlier run at 16:43 returned mobile 48 with LCP 2.4 s, TBT 3,100 ms and CLS 0.224; its desktop run timed out. These cold-load results vary considerably. Mapbox startup remains the dominant cost. The request reduction is verified functionally, but these runs do not establish a total-blocking-time improvement for PR 81.

Further targeted changes:

- Serve Space Grotesk locally with its license. Remove the external Google stylesheet that duplicated the local Inter and JetBrains Mono faces. Preload the two Latin fonts used by the initial fleet view.
- Keep the empty map container hidden until the registry resolves. Hiding only its children did not prevent the painted container from shifting when cards arrived. A local 390 x 844 layout observer measured this shift as 0.1957 before the fix. Afterward, only the attribution control shifted, by 0.00028.
- Combine six terrain fill layers into two, retaining the level filters, band ordering, per-band opacity and zoom fades. This reduces repeated tile layout/draw work without changing the terrain palette.

The compiled build and 120 tests pass. Local desktop/mobile map checks report no rendering errors. Production PageSpeed follow-up appears below.

Selected balloons now take the next available history slot ahead of queued background fleet loads. The fleet and detail views still share one request, and the four-request limit remains in force. A regression test verifies promotion, request sharing and resumption of the background queue.

## Production startup result: October 7, 16:54 PDT

Production `8f9c5bb` (PR 82), [PageSpeed report](https://pagespeed.web.dev/analysis/https-stratolink-org-dashboard/360yry4dlc):

| Device | Performance | FCP | LCP | TBT | CLS |
| --- | ---: | ---: | ---: | ---: | ---: |
| Mobile | 59 | 2.0 s | 2.6 s | 3,080 ms | 0 |
| Desktop | 61 | 0.4 s | 0.5 s | 12,020 ms | 0 |

Mobile main-thread work was 6.0 s, compared with 10.1 s in the prior repeat. The font and layout changes improved initial rendering; the remaining long tasks are dominated by Mapbox. Lab runs vary, so this is not a guarantee for every device or network.

Desktop blocking time remains high and variable in the PageSpeed cold-load run. The live WebGL globe, its initial map tiles and day/night appearance are retained. The report does not establish a desktop TBT improvement for the terrain-layer consolidation. The measured homepage improvement and the request/cache/queue tests should not be confused with a claim that the dashboard has a green cold-start score.
