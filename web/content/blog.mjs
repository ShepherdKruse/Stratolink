export const readingTime = post => Math.max(1, Math.ceil(post.body.replace(/<[^>]*>/g, ' ').trim().split(/\s+/).length / 220));

// Source and editing decisions are recorded in reference/blog-content-audit.md.
export const posts = [{
  slug: 'baja-run',
  title: 'The Baja Run',
  category: 'Flight logs',
  excerpt: 'Stratolink 3 followed the California coast, went quiet near Baja, and returned over Sonora before reaching New Mexico.',
  published: '2026-05',
  publishedLabel: 'May 2026',
  author: { name: 'Shepherd Kruse', github: 'https://github.com/ShepherdKruse' },
  image: {
    src: '/assets/blog/baja-floating.jpg',
    alt: 'Stratolink 3 floating against a clear blue sky with its payload hanging beneath it.',
    width: 1500,
    height: 1000,
    position: '68% center',
    caption: 'Stratolink 3 after release on May 17, 2026.',
  },
  body: `
<p class="post-intro">Stratolink 3 launched from San Francisco on May 17, 2026. It followed the California coast toward Baja, went silent for about 35 hours, then reappeared over Sonora and continued northeast to New Mexico.</p>
<p>Later packets placed the balloon over Spain on May 28 and near Málaga on May 29, extending the observed flight to roughly 12 days.</p>

<figure class="post-figure">
  <img src="/assets/blog/baja-payload.jpg" alt="The Stratolink 3 payload held above the grass at Dolores Park, with its two solar panels and wire antennas." width="1050" height="1400" loading="lazy">
  <figcaption>The payload on May 17, 2026.</figcaption>
</figure>

<h2>Down the coast</h2>
<p>The balloon climbed toward a float altitude of around 9,500 m. Its early track ran south along the California coast, past Los Angeles and toward Baja. The pressure sensor continued to report changing altitude even when the GPS position stopped updating.</p>
<ol class="flight-timeline">
  <li><time datetime="2026-05-17T15:55:00Z">May 17, 15:55 UTC</time><span>South of San Francisco at a reported altitude of 734 m.</span></li>
  <li><time datetime="2026-05-17T18:20:00Z">May 17, 18:20 UTC</time><span>Reported GPS altitude stops changing at 6,924 m.</span></li>
  <li><time datetime="2026-05-18T02:23:00Z">May 18, 02:23 UTC</time><span>Last position before the long gap, offshore near northern Baja.</span></li>
  <li><time datetime="2026-05-19T13:58:00Z">May 19, 13:58 UTC</time><span>Contact resumes over Sonora, Mexico.</span></li>
  <li><time datetime="2026-05-19T22:28:00Z">May 19, 22:28 UTC</time><span>A position southeast of Albuquerque reports 9,814 m.</span></li>
</ol>
<figure class="post-figure">
  <img src="/assets/blog/baja-ascent.svg" alt="GPS and pressure-derived altitude during the first ten and a half hours. GPS readings stop near 6.9 km while pressure-derived altitude continues toward 9.5 km." width="700" height="440" loading="lazy">
  <figcaption>The first 10.5 hours of received altitude data. The GPS gap is left blank. Pressure-derived altitude is an estimate, not a replacement GPS fix.</figcaption>
</figure>

<h2>The frozen position</h2>
<p>Around 18:20 UTC, the reported GPS altitude locked at 6,924 m and repeated across consecutive packets. Meanwhile, pressure kept falling as the balloon climbed. A repeated coordinate could no longer be treated as a new position.</p>
<p>The reported satellite count was 32. That value alone does not identify the failure. The useful evidence is the unchanged position while other sensor readings continued to move.</p>
<p>Fix age and validity need to travel with the coordinates. If a receiver loses its fix, the dashboard should show the last known position as old rather than silently extending the flight track with duplicate points.</p>

<h2>The gap near Baja</h2>
<p>The last reported position before the gap was near northern Baja at 02:23 UTC on May 18. Sensor packets continued briefly afterward. The tracker then went quiet until 13:58 UTC on May 19, when a gateway received it over Sonora.</p>
<p>Light and reported voltage fell before contact stopped. The temperature trace reached -38.2 °C before the gap. Those observations make the power system worth investigating, but they do not establish what happened during the missing hours.</p>
<p>A LoRaWAN packet reaches the dashboard only if a gateway hears it. Missing reception can mean the payload had no power, could not transmit, or was outside usable gateway coverage. Without onboard records from the silent period, the received packets cannot separate those explanations.</p>
<details class="post-aside">
  <summary>What the voltage field can tell us</summary>
  <p>The flown firmware converted its storage-voltage ADC reading using a fixed 3.3 V reference. A later audit found that the reported value can approach a false plateau as the supply drops. The 3.32 V readings therefore do not establish the actual capacitor voltage or the reset threshold. This is why the old trace cannot prove exactly when or why the tracker stopped.</p>
</details>
<p>Once contact resumed, the recorded positions moved northeast through Sonora and into New Mexico. There is no measured track through the 35-hour gap. A line joining the two ends would show a connection between observations, not the route the balloon actually took.</p>

<h2>What the flight exposed</h2>
<p>The flight pointed to several changes for the next tracker revision:</p>
<ul>
  <li>Report fix validity and age so stale coordinates cannot look current.</li>
  <li>Record the firmware version, power state, and GPS diagnostics with telemetry.</li>
  <li>Measure the stored energy available through sunset and the conditions needed to restart.</li>
  <li>Reduce work when power is low, then check that the tracker resumes normally.</li>
  <li>Investigate storing positions while out of coverage and sending them after contact returns.</li>
</ul>
<p>For the current build, see the <a href="/docs/hardware">hardware guide</a> and <a href="/docs/architecture">system overview</a>.</p>

<h2>The flight continued</h2>
<p>Packets arrived from Spain on May 28. The final fresh GPS fix was near Málaga at 17:46 UTC on May 29, at a reported altitude of 10,034 m. Telemetry continued until 19:45 UTC without a fresh GPS position.</p>
<p>That extended the observed flight to roughly 12 days. The Atlantic crossing sits inside a long reception gap, so its exact path remains unknown. The later European packets also confirmed that the tracker could join the EU868 network after leaving US915 coverage.</p>
<p>You can inspect the received positions and telemetry in the <a href="/dashboard?device=stratolink-3">dashboard</a>.</p>
`,
}, {
  slug: 'after-the-last-packet',
  title: 'Looking for Stratolink 3',
  category: 'Flight notes',
  excerpt: 'We heard from Stratolink 3 after almost four weeks of silence. I tried to work out where it was from a timestamp, a network name, and the position of the sun.',
  published: '2026-06',
  publishedLabel: 'June 2026',
  author: { name: 'Teddy Warner', github: 'https://github.com/twarner491' },
  image: {
    src: '/assets/blog/reconstructed-flight.jpg',
    alt: 'A world map showing a dashed reconstruction of a possible Stratolink 3 route, with its last GPS fix near Spain and a separate forecast.',
    width: 1200,
    height: 675,
    caption: 'A June reconstruction of the path of Stratolink 3.',
  },
  body: `
<p class="post-intro">On June 26, I sent Caleb and Shepherd a screenshot of a new ping from Stratolink 3. We hadn't had a fresh position since May 29, when it was near Málaga. The first thing I wanted to know was whether the webhook had caught any telemetry.</p>
<p>It hadn't. We had a join request from two days earlier, at 02:18:34 UTC on June 24. The device was trying to authenticate with the network. No latitude, longitude, altitude, or sensor readings. But something we had let go in San Francisco 38 days earlier was still transmitting.</p>
<p>The join request is super tiny, so there wasn't much to work with. Packet Broker had anonymized the receiving gateway. I couldn't look up its identity or coordinates. The useful bits were the exact time, a weak radio signal, and the name <code>cometsystem-cloud</code>.</p>
<p>That name was the only hint I was working off to identify the network. It pointed to COMET, an IoT sensor company based in Czechia. I started there, using Czechia as a rough footprint for the receivers and adding the distance our radio might reach around it.</p>
<p>We had already received SF7 packets from about 250 km away during the flight. A simple link budget put an idealized range closer to 340 km. Adding those distances around Czechia gave a possible area covering essentially all of central Europe, lol. Still a fairly large place to look for a balloon.</p>
<figure class="post-figure">
  <img src="/assets/blog/reconstruction-radio-footprint.svg" alt="The June Czechia footprint experiment, with 250 and 340 kilometre range buffers and the ground and elevated sunrise lines." width="864" height="533" loading="lazy">
  <figcaption>The first footprint and daylight calculations, replotted. Czechia was a starting assumption about the network, not a known receiver location.</figcaption>
</figure>
<details class="post-aside">
  <summary>Where the 340 km estimate came from</summary>
  <p>The calculation used SF7 at 125 kHz, an assumed receiver sensitivity of about -124.5 dBm, and a 14 dBm transmitter. Antenna gains and small loss allowances gave a maximum free-space path loss of about 141.9 dB. At 868.1 MHz, that corresponds to 343 km. It assumes favorable antennas, a clear path, and no fade margin. This is a reach estimate, not a distance measured from the June packet.</p>
</details>
<p>The obvious problem was that a Czech company could have customers anywhere. Its office gave us a place to start drawing, but it didn't tell us where the receiver actually was. The time of the packet seemed more promising.</p>

<h2>Sunrise at 10,000 meters</h2>
<p>The payload runs on solar panels and supercapacitors. After a night without enough stored energy, it needs sunlight before it can start up again. Caleb pointed out that the timing could help, so I overlaid day and night at the moment the packet arrived.</p>
<p>Sunrise is a little different up there. At 10,000 meters, the horizon is about 3.2 degrees below horizontal. The payload can see the sun while someone directly beneath it is still in darkness. The two dawn lines on the map account for that difference.</p>
<p>I then used the earlier flight data, from when we were receiving packets more regularly, to calculate the time between sunrise and our first received packet. Two mornings gave roughly 100 and 170 minutes. I used that interval as an estimate of how long the payload needed to get going, then worked backward from the June packet to find where sunrise would have been that much earlier.</p>
<figure class="post-figure">
  <img src="/assets/blog/reconstruction-startup-delay.svg" alt="Three dawn curves showing how an assumed zero, 100 or 170 minute delay shifts the inferred sunrise location eastward." width="864" height="533" loading="lazy">
  <figcaption>The June delay experiment, replotted. A longer assumed startup delay moves the estimate east.</figcaption>
</figure>
<p>At the time I described this as the payload's cold-start time at altitude. There is a catch: it was the time until the first <em>received</em> packet. The payload might have started earlier and transmitted somewhere no gateway could hear it. The calculation mixed the behavior of the power system with the availability of receivers.</p>
<p>The next versions allowed a wider range of startup delays. I combined that with a rough receiver footprint, radio range, and an assumed latitude band. By late morning, I had sent this overlap map to the chat.</p>
<figure class="post-figure">
  <img src="/assets/blog/reconstruction-june-overlap.png" alt="The original June 26 overlap experiment combining assumed gateway coverage, available sunlight and latitude, with weighted regions extending into eastern Europe." width="2135" height="900" loading="lazy">
  <figcaption>The map I sent on June 26. Its 50% and 90% contours describe the model's chosen weights, not verified probabilities of the balloon being there.</figcaption>
</figure>
<p>The red dot looks much more definite than the inputs were. The model had a favorite location because I had given it a preferred latitude, a receiver footprint, and a startup-delay distribution. Changing any of those moved the result. The useful part was seeing how those assumptions overlapped, and which ones were doing most of the work.</p>

<h2>The missing month</h2>
<p>Meanwhile, Caleb was working on the much bigger question: how could it have got back to this part of Europe?</p>
<p>His reconstruction at the top of this post followed a possible route east from Spain, across Asia and the Pacific, around a little swirl above Canada, and back across the Atlantic. I thought the swirl was fun. A trip around the world in less than 40 days would be pretty ridiculous for something we had released from a park.</p>
<p>The reconstruction was built to arrive near Czechia on June 24. That endpoint came from the network assumption I was trying to narrow down, so it couldn't also prove the assumption correct. We had a way the flight could fit together, but still needed a position from the balloon.</p>
<p>I was also trying to understand why we would hear so little along the way. The tracker chooses its radio region using GPS position, and this flight had already had trouble with stale GPS data. My best guess in the chat was that it could be holding on to an old position and transmitting on the wrong regional settings. I also wondered whether it had switched back too late to be heard over North America. Both were possibilities to investigate; the join request didn't contain the state needed to tell us.</p>
<p>Later that afternoon, Caleb found public gateway candidates through TTN Mapper. I ran another version using their locations instead of the broad footprint. This pulled the estimate back toward western Ukraine.</p>
<figure class="post-figure">
  <img src="/assets/blog/reconstruction-gateway-candidates.png" alt="The later June experiment with individual public gateway candidates. Its weighted region moves west when the assumed receivers change." width="2021" height="805" loading="lazy">
  <figcaption>The public-gateway experiment from later that afternoon, with its original inputs and clarified labels. None of these candidates was identified as the receiver of the June packet.</figcaption>
</figure>
<p>I sent it with the qualifier that I was assuming the gateways from TTN Mapper. If the packet had come through COMET's private network, it could be farther east. We had changed the possible receiver set and got a substantially different answer without receiving anything new from the balloon.</p>

<h2>Rechecking the radio range</h2>
<p>Another assumption in the later maps deserves a closer look. The June signal was weak: -121 dBm RSSI and -7.25 dB SNR. Some of the calculations treated that as a reason to put the balloon near the edge of the receiver's range.</p>
<p>The earlier flight data gives us a useful check. There are 49 SF7 receptions with a fresh GPS position, a known receiver location, and an SNR reading. Eleven were at least as weak as the June signal. Their distances range from about 22 to 252 km. One packet was heard at -10 dB only 22 km away.</p>
<figure class="post-figure">
  <img src="/assets/blog/reconstruction-signal-range.svg" alt="A present-day comparison of 49 earlier SF7 receptions. Signals at or below the June SNR occur between 22 and 252 kilometres from the receiver." width="864" height="533" loading="lazy">
  <figcaption>A new comparison using the earlier received flight data. Each point is a reception, so one transmission heard by several gateways can appear more than once.</figcaption>
</figure>
<p>So the weak signal couldn't give us a narrow distance ring. Antenna orientation, receiver noise, and the rest of the radio link mattered too. Without the receiver's location, even a perfect distance estimate would leave us with a circle around an unknown point.</p>
<p>The circumnavigation is still a possible reconstruction. The sunrise geometry gave us something to calculate, but the receiving network and startup delay kept moving the answer around. I would very much like another packet with actual coordinates in it.</p>
<p>The positions we did receive are in <a href="/dashboard?device=stratolink-3">Stratolink 3's flight</a>. Shepherd's <a href="/blog/baja-run">Baja Run</a> covers the earlier part of the flight.</p>`,
}];
