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

## Day/night shade computation

The shade-only source now evaluates the same solar-altitude and smootherstep formula directly in its worker. It no longer creates a separate WebGL context or reads pixels back from the GPU. City lights retain their existing texture shader.

A local browser comparison checked 24 tiles across equinox/solstice dates, zooms 0/2/5 and both themes against the original shader. Maximum channel difference was 1/255; the mean difference was 0.00000318 on the 0-255 scale. For those tiles, total software calculation took 12.2 ms versus 30.6 ms for shader drawing/readback on this machine, excluding renderer construction. This is a tile benchmark, not a page-load claim. Tests cover day/night reversal, polar winter, theme colors and exact alignment of adjacent tiles.

Production `39a5888` (PR 84), [October 7, 17:04 PDT report](https://pagespeed.web.dev/analysis/https-stratolink-org-dashboard/y3k6kobxvw):

| Device | Performance | FCP | LCP | TBT | CLS |
| --- | ---: | ---: | ---: | ---: | ---: |
| Mobile | 32 | 3.1 s | 8.9 s | 5,150 ms | 0 |
| Desktop | 61 | 0.4 s | 0.4 s | 8,250 ms | 0 |

Desktop blocking time decreased in this run, but mobile first paint regressed. The mobile LCP element was still the wordmark, with a large main-thread render delay. The next change explicitly gives the interface a paint opportunity before starting the lazy map import, instead of depending on network timing to separate those tasks.

## Interface paint result

Production `58c8b01` (PR 85), [October 7, 17:12 PDT report](https://pagespeed.web.dev/analysis/https-stratolink-org-dashboard/c1cj1rr0vj):

| Device | Performance | FCP | LCP | TBT | CLS |
| --- | ---: | ---: | ---: | ---: | ---: |
| Mobile | 53 | 1.8 s | 3.1 s | 7,420 ms | 0.035 |
| Desktop | 60 | 0.4 s | 0.5 s | 10,030 ms | 0 |

Giving the interface a paint opportunity reduced mobile first-paint time in this run. It did not resolve the expensive Mapbox cold start. These results remain variable and are not a green dashboard score.

## Shared map data and larger fleet

Both stock basemaps already include terrain-v2 and bathymetry-v2 in their composite vector source. Custom terrain and depth layers now reuse that source, with a fallback for styles that omit either tileset. Sampled decoded depth and hillshade tile properties and geometry matched at zooms 1, 5, 8 and 12. This removes two redundant metadata requests. The local two-balloon trace did not show a material frame-time improvement.

The local stress fixture uses 1,000 synthetic balloons and 250 packets per balloon. It never writes to production. Before card memoization, 14 keyboard timeline actions produced 17 long tasks of 65-72 ms, including work continuing between inputs. Unchanged headings, icons and metric values now reuse their rendered output; history summaries and selection callbacks preserve identity between unrelated updates. Signal freshness still refreshes on the existing minute clock.

After the change, the same 14 timeline actions produced no tasks over 50 ms. The 30-second startup trace fell from 17 long tasks (50-60 ms) to one (59 ms). Map frame callbacks remained similar: p95 2.5 ms and maximum 11.6 ms. This confirms a local reduction in card-update work; it does not predict PageSpeed's cold-load score or low-end mobile performance.

Validation: 128 unit/API tests, TypeScript and the production build pass. Local checks cover fleet search, keyboard selection, return to the filtered list, 390-pixel card widths without overflow, and both globe themes. No frontend styles or markup structure changed.

## Production result and optional flight tails

Production `997dace` (PR 86), [October 7, 17:38 PDT report](https://pagespeed.web.dev/analysis/https-stratolink-org-dashboard/pbl1f20ohb):

| Device | Performance | FCP | LCP | TBT | CLS |
| --- | ---: | ---: | ---: | ---: | ---: |
| Mobile | 61 | 1.8 s | 2.3 s | 5,440 ms | 0.035 |
| Desktop | 61 | 0.4 s | 0.4 s | 13,740 ms | 0 |

Best Practices remains 100. Desktop's 16.8 seconds of main-thread work contains 14.1 seconds classified as Other and 2.3 seconds of script evaluation. Its long tasks are predominantly Mapbox rendering. These lab cold starts remain expensive despite responsive local interactions.

The optional flight-tail layer exposed a separate scaling problem: one source and one draw layer per balloon. With 1,000 synthetic balloons, enabling it produced a 1.43-second task and a 211 ms map frame callback. Tails now share sources by the existing four-color palette, with separate LineString features and per-feature opacity. The gradient still restarts along each balloon's own line. Geometry, colors, line width and replay boundaries are preserved.

The longer fixture also exposed unnecessary refresh work. Repeated overlap packets replaced history arrays even when their data was unchanged, invalidating every derived track and merged timeline. Identical packets now retain their history identity, and the fleet publishes only changed snapshots. Updates to packet values or gateway reception metadata still replace the changed row.

After both changes, the local 1,000-balloon test covered enabling tails, eight keyboard timeline actions and a complete one-minute refresh. It recorded one 81 ms long task (31 ms above the long-task threshold), with a maximum map-frame callback of 26.3 ms. The earlier per-balloon source run recorded 135 long tasks including the 1.43-second toggle stall; batching alone removed that stall but left repeated refresh work. These synthetic local measurements establish the source-count and unchanged-data improvements, not a production PageSpeed score or a low-end-device guarantee.

All 133 unit/API tests, TypeScript and the production build pass. Tests include 1,000 independent tails in four colors, per-flight fade values, replay clipping, dateline crossings, and packet/gateway changes invalidating the cache. The generated docs contain eight KaTeX equations and no rendering errors.

## Fleet projection follow-up: October 7, 18:15 PDT

The optional fleet projection layer now puts independent balloon tracks in one GeoJSON source and one line layer, preserving its color, dash pattern, opacity and width. Completed paths publish in 100 ms batches. Filtering adds or removes only the affected subscriptions; an unchanged result keeps the existing geometry.

Forecast reads are shared between fleet and detail views, with at most four in flight. Selecting a queued balloon promotes it to the next slot. Hiding the layer or changing selection cancels abandoned reads and timers. Requests time out after 20 seconds so a stalled response cannot occupy a slot indefinitely. The bounded 64-response cache lasts five minutes; computing responses expire after eight seconds. The existing capped fast-poll behavior is retained.

The local comparison used 1,000 simulated balloons, 250 recorded packets and 97 projected coordinates per balloon. It enabled the optional layer, waited for all forecasts, then performed eight keyboard timeline steps. The local API delayed each forecast by 30 ms. Both runs also included a normal telemetry refresh.

| Measurement | Current main | Batched projections |
| --- | ---: | ---: |
| Map frame callback total | 5,221 ms | 392 ms |
| Maximum frame callback | 58.1 ms | 5.8 ms |
| Long tasks | 2 | 0 |
| Blocking time above 50 ms | 25 ms | 0 ms |
| Peak forecast requests reaching local server | 6 | 4 |

The old build submitted all forecast requests at once; the local browser limited HTTP/1.1 connections to six. The new limit is enforced by the application independently of transport. Both runs loaded all 1,000 forecasts. These are local hardware measurements with cached map assets, not PageSpeed or low-end mobile results.

All 140 unit/API tests, firmware decoder/auth contracts, migration contracts, forecast-worker tests, staff tooling tests, type checks and the production build pass. Tests specifically cover concurrency, selection priority, shared cancellation, abandoned queued requests, retry behavior, cache expiration/bounds and polling shutdown. Local real-fleet and selected-flight checks pass in desktop light and mobile dark themes without map errors.

## Mapbox renderer update

The 3.18.1 renderer spent most of its PageSpeed CPU time outside JavaScript evaluation, consistent with synchronous graphics-driver work. That attribution alone does not prove which graphics call stalls. Inspection of the installed source showed synchronous shader setup; the current stable renderer includes parallel shader compilation and idle-time precompilation, introduced in [3.24.0](https://github.com/mapbox/mapbox-gl-js/releases/tag/v3.24.0). Later releases reduce shader size, GeoJSON memory use, redundant initial repaints and style/asset loading work.

Pin Mapbox GL JS to [3.32.0](https://github.com/mapbox/mapbox-gl-js/releases/tag/v3.32.0) and use its supported ESM entry point through an exact Vite alias. The alias leaves CSS imports and the existing map styling unchanged. The modular build loads core, shared code and the lightweight terrain module for this map; unused 3D/HD/debug features remain separate. Mapbox's worker is emitted as a local asset. The dependency update removes 26 transitive packages, and the production dependency audit reports no known vulnerabilities.

Compiled Mapbox main-thread code changes from a 1,644 KB monolithic chunk (447 KB gzip) to 776 KB core + 589 KB shared + 42 KB lightweight terrain (378 KB combined gzip). A separate 779 KB worker asset is also loaded, so this is a main-thread parsing reduction, not a claim of lower total network transfer.

On local hardware, the old warmed renderer completed 229 frame callbacks in 618 ms, with a 14.6 ms maximum and no long tasks. The first run of the upgraded monolithic renderer incurred four shader-related long tasks, including a 234 ms frame. A subsequent modular run completed 228 callbacks in 647 ms, with a 14.8 ms maximum and no long tasks. Shader caching makes these runs unsuitable for proving a cold-start improvement. Production PageSpeed follow-up is required.

All 140 unit/API tests and the full verification suite pass. Real telemetry, replay, light/dark themes, mobile layout and the mobile footer globe transition were checked locally without map errors. No frontend layout, colors, copy or animation settings changed.

A further local 1,000-balloon check enabled projected paths and flight tails together, performed eight replay steps, and included a normal telemetry refresh. All 1,000 forecasts loaded, with four requests in flight, and no map errors. It recorded three long tasks (65, 56 and 99 ms), 70 ms total blocking time and a 64.8 ms maximum map callback. This combined-layer check is not directly comparable to the projection-only run above. The compiled footer transition completed at both 1280 px and a verified 390 px viewport.

## Renderer production follow-up: October 7, 18:39 PDT

Production `b855476` (PR 89), [PageSpeed report](https://pagespeed.web.dev/analysis/https-stratolink-org-dashboard/cfgoh1q5jd), compared with a [fresh pre-upgrade run](https://pagespeed.web.dev/analysis/https-stratolink-org-dashboard/7z2fbomlo7) two minutes earlier:

| Build | Device | Performance | LCP | TBT | CLS |
| --- | --- | ---: | ---: | ---: | ---: |
| Before | Mobile | 59 | 2.7 s | 2,600 ms | 0.035 |
| Before | Desktop | 61 | 0.4 s | 13,400 ms | 0 |
| Modular 3.32 | Mobile | 54 | 3.1 s | 5,130 ms | 0.035 |
| Modular 3.32 | Desktop | 61 | 0.5 s | 11,590 ms | 0 |

Best Practices remains 100. Desktop blocking time decreased in this pair; mobile increased. These results do not establish a consistent cold-start improvement. The upgrade reduces main-thread module size and keeps the renderer current, but the dashboard still has substantial graphics startup cost in PageSpeed. Production mobile telemetry and replay render without map errors.

## Fleet forecast payload

Fleet projections need only the nominal path, but previously downloaded every ensemble member, confidence polygon and reconstructed track. `GET /api/forecast?device=…&view=path` now returns only the generation timestamp and sanitized nominal path. The default response retains every field used by the selected-balloon view. Both forms keep the existing connected-device check, private storage access and location privacy rules.

The request queue shares its four slots across both forms, with separate cache keys so a small fleet response cannot replace a full selected-flight response. Duplicate reads of the same form still share a request. Cancellation, selected-flight priority, timeouts and polling behavior are unchanged.

For the current public Stratolink 3 forecast, the JSON response shrinks from 380,100 bytes to 79 bytes (106,424 versus 97 bytes using local gzip). Its nominal path currently contains only one coordinate, so active forecasts will be larger. A local 1,000-iteration sanitation/serialization check took 1,450 ms for full responses and 1 ms for paths. This measures response preparation, not private Blob transfer, production latency or cold map rendering; the server still reads the same stored forecast.

A 97-coordinate fixture with 62 ensemble members shrank from 244,340 to 2,787 bytes (103,802 to 1,173 with local gzip). The compiled 1,000-balloon fixture fetched 1,000 path responses and no full forecasts, with a peak of four requests. Opening a balloon fetched one full response, retained its 48-hour forecast timeline and returned to the filtered fleet without map errors. Initial loading with both optional layers already enabled still recorded 36 tasks of 50-66 ms; this payload change does not eliminate the cost of streaming a large fleet into the map. All 145 unit/API tests and the full verification suite pass.

Production `42e9c1d` (PR 90) returns matching nominal paths from both response forms. The full response retains all 62 ensemble members; the small response contains only its two documented fields. Both return 200 with `no-store`. Shared CI and isolated database checks passed.

## Fleet timeline indexing

The fleet timeline copied and sorted every packet after each history batch arrived. It now reads each already-sorted history's endpoints for its range and searches within those histories for keyboard replay. No merged packet array is needed. Strict previous/next navigation still skips equal timestamps across balloons, and empty histories, gaps and live/future bounds retain their behavior.

For 1,000 histories of 250 packets each, a local 50-run median range calculation fell from 12.62 ms to 0.012 ms; finding the previous fleet packet took 0.030 ms. The same compiled 1,000-balloon startup fixture, with flight tails and projections already enabled, fell from 36 tasks over 50 ms to three (53, 66 and 52 ms), totaling 21 ms above the threshold. The maximum map callback did not improve in this pair (50.1 versus 64.9 ms); the change removes packet-array work, not graphics startup.

All 149 unit/API tests and the full verification suite pass. Tests compare keyboard navigation against a merged reference across gaps and duplicate timestamps, and verify that a million-packet fixture reads endpoints and logarithmic candidates rather than scanning every packet.

## Renderer rollback

Additional production reload checks found intermittent errors in the modular 3.32.0 build: `refreshFeatureState` accessed an unavailable painter style, and another load failed while defining `_classRegistryKey` on a non-extensible object. A fresh temporary tab succeeded, but the native browser tab reproduced an initialization failure. The exact trigger is not established.

Restore the previously deployed 3.18.1 dependency, lockfile and standard import. The upgrade did not establish a consistent PageSpeed improvement, and its reload failure outweighs the smaller main-thread module. Retain the independent history, card, map-source, forecast payload and timeline improvements. Do not describe the modular renderer experiment as the final shipped configuration.

## City-light raster processing

The remaining city-light source used a second WebGL context to sample Black Marble tiles and synchronously read pixels back from the GPU. It now decodes the same images through a software-backed 2D canvas and samples them in the existing worker. The solar boundary, luminance-weighted alpha, bilinear filtering and ancestor-tile overzoom are preserved. The shade and lights share the same solar calculation. Cached decoded tiles are bounded to 64 entries; disposing the fallback renderer aborts pending fetches and releases its canvas.

A browser comparison against the previous shader checked 16 tiles across both themes, two dates and zooms 0, 2, 5 and 9. Across 4,194,304 channel samples, the maximum difference was 1 out of 255 and the mean absolute difference was 0.0041. The tiles contained visible city lights, so this was not a comparison of empty responses. The final 12 warmed tile operations totaled 48.4 ms for the shader and 33.9 ms for the CPU version. Earlier network timings were cache-dependent and are excluded. This establishes pixel agreement and a local processing improvement, not a cold PageSpeed gain.

All 156 unit/API tests and the full verification suite pass. New tests cover daylight transparency, brightness weighting, north-up filtering, overzoom, missing images, cache bounds and cancellation. No map layers, colors, opacity, layout or animation timing changed.

Production `5ff6802` (PR 93), [October 7, 19:25 PDT report](https://pagespeed.web.dev/analysis/https-stratolink-org-dashboard/nw0wycwwkq): mobile 58, LCP 3.1 s, TBT 1,800 ms, CLS 0.035; desktop 60, LCP 0.5 s, TBT 16,820 ms, CLS 0. Best Practices remains 100. Mobile blocking decreased in this run, while desktop increased. Cold startup remains unresolved.

## On-demand map shaders

Mapbox 3.18.1 enables `precompilePrograms` by default. Its first style update schedules shader programs for every layer, including hidden layers and alternate fog/draping combinations. Disable that supported option so the renderer compiles programs when a visible layer needs them. This preserves the style and the existing rendering/reveal behavior.

In the same compiled two-balloon fixture, startup compiled 28 shaders / 14 linked programs instead of 48 shaders / 24 programs. Both warmed runs had no long tasks. Frame callback totals were 654 ms versus 602 ms, so the local comparison establishes fewer shader variants, not a warmed frame-time improvement. First use of a previously unseen layer may still compile its program; zoom, theme and replay checks are required alongside production cold-load measurements.

A separate interaction trace covered zooming, panning, switching light/dark themes, selecting a flight and replaying it. It compiled two additional programs, recorded no long tasks and had an 8.3 ms maximum frame callback on local hardware. Real Stratolink 3 telemetry and both themes also rendered without errors in the compiled build. All 156 unit/API tests and the full verification suite pass.

## Fleet arrival batches and transition snapshots

Fleet histories now publish their first successful result immediately, combine subsequent arrivals every 200 ms instead of 50 ms, and flush when the batch completes. Fetch concurrency, selected-device priority and the polling interval stay the same. This reduces repeated map updates while a large fleet loads.

Two local 1,000-balloon checks, each with 250 packets per balloon and both tails and projections enabled, reduced total map-frame callback time from 6,640 / 6,903 ms to 3,291 / 3,314 ms. The 95th-percentile callback fell from 22.8 / 24.4 ms to 9.7 / 8.9 ms. Long-task counts varied between runs, so this establishes reduced rendering work rather than the elimination of all startup blocking.

Only the selected card now has an individual view-transition name. The remaining cards share one list snapshot, preserving their fade and the selected card's expansion without separately capturing every offscreen card. A matching 1,000-balloon selection/return check recorded two tasks of 2,555 and 2,504 ms with the original snapshots; the candidate's longest tasks were 203 and 204 ms across two checks. Direct selectors were used in the control and final repeat to avoid attributing accessibility-name lookup work to the transition. These are local fleet measurements, not evidence that the production cold Mapbox startup is resolved.

The compiled dashboard passes real-telemetry selection, replay, fleet return and keyboard checks at 1280 px and 390 px without browser errors. All 156 unit/API tests and the full verification suite pass.

## Production page checks, October 7 at 20:45-20:52 PDT

After PR 95 deployed, dashboard PageSpeed measured 59 mobile / 60 desktop. Mobile LCP was 3.1 s, TBT 1,700 ms and CLS 0.035. Desktop LCP was 0.4 s, TBT 11,600 ms and CLS 0. The desktop main-thread breakdown attributes 12,173 ms to Other and 1,832 ms to script evaluation. Cold rendering remains unresolved. Report: https://pagespeed.web.dev/analysis/https-stratolink-org-dashboard/9t92bre7b0

The blog and balloon-preparation page both scored 100 for performance on mobile and desktop, with zero TBT and CLS. Mobile LCP was 1.1 s for the blog and 1.2 s for preparation. Both scored 100 for Best Practices. Reports: https://pagespeed.web.dev/analysis/https-stratolink-org-blog/930mirse2v and https://pagespeed.web.dev/analysis/https-stratolink-org-docs-balloon-prep/md922dy0bk

The public page generators now provide regular meta descriptions alongside social metadata, using the existing article introductions. The five preparation illustrations declare their intrinsic dimensions so the browser can reserve their space before lazy loading. Their files, styling and captions are unchanged. The preparation report also flagged oversized image delivery; dimensions alone do not reduce those transferred bytes.

## Responsive preparation illustrations

The five preparation illustrations now offer 480 px and 960 px WebP variants, with the originals retained for enlargement. Lazy-loaded images use their rendered width to select a source in browsers supporting automatic sizes; older browsers have explicit responsive fallbacks. This changes image delivery without changing the layout, captions, source illustrations or math.

At a 390 px viewport, the first three illustrations selected files totaling 164,624 bytes instead of 475,824 bytes, a 65% reduction. The before/after illustrations remain 150 px tall with captions at the same vertical position. Desktop at 1280 px retains the same layout without horizontal overflow. Clicking a smaller inline image opens its original 1244 px or 1208 px source in the existing dialog and returns focus to the image link on closing.

## Interpreting the dashboard lab result

Lighthouse maintainers document that PageSpeed Insights runs WebGL without a hardware GPU, using software rendering instead. Their [globe demo comparison](https://github.com/GoogleChrome/lighthouse/issues/14301#issuecomment-1219754117) and [explanation of large Other rendering time](https://github.com/GoogleChrome/lighthouse/issues/15180#issuecomment-1601726668) describe this limitation. The corresponding [WebGL issue](https://github.com/GoogleChrome/lighthouse/issues/8557) remains open. This is relevant evidence for the large gap between dashboard PageSpeed results and local browser traces, not proof of which rendering operation dominates every current lab run.

The production dashboard still scores about 59 mobile / 60 desktop. Keep reporting that result alongside real-browser checks rather than treating software-rendered globe startup as a pure JavaScript bottleneck. A local two-balloon trace on the retained 3.18.1 renderer recorded no long tasks, a 13.3 ms maximum frame callback and a 4 ms 95th percentile. Separate zoom, pan, theme and replay checks and the large-fleet measurements above establish improvements on the tested hardware. They do not establish frame rates on every mobile GPU or eliminate the need for field measurements as traffic grows. No user-agent detection or PageSpeed-specific rendering path is used.

## Mobile launch scene, October 8

Teddy reported very slow initial loading in mobile Firefox despite a responsive desktop site. Desktop browser emulation did not reproduce that device's slowdown. The homepage did, however, apply Gaussian blur, alpha transfer and morphology to two full-photo SVG surfaces at runtime. These are unnecessary rendering costs on mobile, separate from transfer size and the dashboard's WebGL work.

The original SVG masks are now compiled into transparent WebP layers. Mobile retains its stronger cloud alpha cutoff. The balloon uses a 205 × 403 crop instead of a 2560 × 1440 masked source. The intro waits for the actual selected image elements to decode. The text mask is removed after the cloud edge clears the viewport and restored on upward scrolling; changing its variables no longer invalidates the entire scene's inherited style.

The three initial scene images total 188,386 bytes on mobile and 215,058 on desktop, compared with 251,765 bytes for the prior source photo, sky and two masks. The source photograph remains unchanged for social cards. Both mobile and desktop visual checks preserve the composition, feathered cloud edge and tether. At 390 × 844, the original desktop-hosted comparison already had no long tasks, so those results cannot establish a phone speedup. The affected mobile Firefox device still needs a retest. No browser-specific detection, Mapbox change or dashboard redesign is included.

Validation: all 156 unit/API tests, TTN and migration contracts, forecast and staff tests, type checks and production build pass. Browser checks cover 390 × 844 and 1440 × 900, selected mobile/desktop assets, upward mask restoration, no horizontal overflow and no runtime scene filters.

Follow-up: Teddy retested the production homepage in mobile Firefox and confirmed, "much better. mobile is great now."

## Footer globe preparation, October 8

The footer globe previously started loading only 700 px before the footer reached the viewport. It now starts within three screens of the footer once the reader has scrolled more than 120 px, or immediately if the footer is already visible. The iframe still has no source on an initial visit at the top. Offscreen rotation remains paused, and the same map instance handles the dashboard transition.

In a controlled six-second scroll at 390 × 844, the request began at 433 ms instead of 2,366 ms. The new globe was ready before the footer entered the viewport; the previous run became ready just after reaching the bottom. These local timings include different cache states and do not measure a faster map download. They verify the earlier start and added loading time while reading. Checks also cover 1440 × 900, the mobile dashboard transition and console errors. Full verification passes.

## Homepage scroll and footer globe, October 9-10

Measured on an iPhone 17 Pro (Safari, 120 Hz) with the page's own overlay, not in the lab. Open the homepage with `?perf` for a scroll-smoothness overlay (frame cadence while scrolling, dropped frames, scene-script cost, hero and globe ready times); `?perf&static` freezes the scene script for an A/B, and `&noglobe`, `&noimages`, `&nolayers`, `&nomask`, `&nowarmth`, `&nofooter`, `&noshadow` each remove one suspect. The overlay also posts its readings and the portal iframe's resource waterfall to `http://<host>:5174/perf` when a collector listens there, so a phone's numbers can be read on the dev machine.

- The scroll judder was not main-thread cost. With the scene script frozen the phone dropped frames identically, and the parallax looked smooth only because it was off: JavaScript positioned the layers a frame late at 60 Hz against a 120 Hz compositor scroll. The hero motion (city drop, balloon flight, story, warmth, cloud mask, footer reveal, header exit) and the footer globe's placement, reveal and clip now compile into keyframes on `animation-timeline: scroll(root)` from the same formulas, and the JavaScript path remains for browsers without scroll-driven animations (`?jsscene`, `?jsglobe` force it).
- Hero load: no intro overlay, text or layers animate in; the scene waits for its images to decode behind a 164-byte blurred inline placeholder and appears in one 50 ms fade. Resting geometry is mirrored in CSS custom properties so the first paint matches the script, and the hero uses `lvh` so the collapsing browser bar no longer shifts it.
- Footer globe: the dashboard iframe boots with the page and renders only the map while it is the footer preview. It fetches four telemetry columns via one latest-packets request per balloon instead of paging full missions, loads the Supabase auth client on demand (dashboard chunk 131 → 97 KB gzipped), boots on a 16-layer basemap reduced from the stock style (`components/maps/basemapStyle.ts`, generated by `scripts/prepare-basemap-style.mjs`) that the dashboard shares, so entering the dashboard never swaps styles, and opens at the globe camera. On the phone the globe went from ready at about 2.9 s to about 1.0-1.9 s depending on main-thread contention with the hero. The hidden portal keeps a near-zero opacity so iOS does not rebuild the iframe and canvas layers on reveal, which flashed a blank box.
