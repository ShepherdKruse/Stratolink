# Balloon as a Meshtastic relay for the ground community

Can a Stratolink balloon, in its power-gated idle windows, help ground Meshtastic
users, bridge two "buddies" hundreds of km apart who can't reach each other
directly? Grounded in my geometry/saturation modeling (`90_meshtastic_relay.py`,
fig N8), flight-3 power data, and dated research (incl. the one real instrumented
balloon-Meshtastic flight).

## Bottom line

- **The value is real and large.** At float the balloon has a **~410 km LOS
  footprint** (practical air-to-ground ~**200 km** per the community record), so one
  balloon hop bridges buddies **~400 km apart**, vs ~30 km ground-to-ground. Genuine,
  immediate value to anyone under it.
- **The hazard is real too: a naive flood-repeater is a documented "mesh killer."**
  A wide-footprint node that rebroadcasts everything saturates the channel over any
  populated area (suburban density → **249%** channel utilization; metro → **2488%**)
  and preempts local direct paths (the Swiss alpine "ROUTER destroyed our mesh" case).
- **An OPEN, public, default-channel relay for the whole region IS achievable** -
  the airtime self-cap (AirUtilTX ≤ 7.5%) + ROUTER_LATE that keeps it safe also makes
  it auto-target the underserved: full service where the mesh is sparse/absent, defers
  where it's dense/covered (`91_open_relay.py`, fig N9). So it's safe at *every* density
  while maximizing public benefit. What it must NOT be is a naive flood-`ROUTER`.
- **It's genuinely under-tested**, no balloon has measurably saturated a ground mesh
  *or* cleanly bridged buddies at scale. Stratolink would generate novel data. Strong
  community story while our telemetry network grows.

## The value (geometry + real-world range)

My model (`90_*.py`): ground↔balloon is **LOS-limited**, not link-limited (the link
budget reaches ~1,960 km, but the radio horizon caps it):

| Float alt | LOS footprint radius | Buddy-bridge reach | Footprint area |
| --- | --- | --- | --- |
| 8 km | 375 km | ~750 km | 0.44 M km² |
| 10 km | 418 km | ~840 km | 0.55 M km² |
| 12 km | 458 km | ~915 km | 0.66 M km² |

**Reality check:** the documented Meshtastic air-to-ground record is **206 km**
(two T-Beams, stock antennas, LongFast), well below the LOS ceiling, because the
limiting direction is the **balloon hearing a small 22 dBm ground node** (RX
asymmetry), not path loss. HAB Flight 6 (van Staveren, Apr 2025, 30 km) found its
RX was too weak to hear most ground traffic at all. So plan for a **practical ~200 km
bridge radius** (buddies ~400 km apart), still ~13× ground range. Better RX / a real
ground antenna pushes it toward the LOS ceiling.

## The hazard (saturation + path preemption)

The same footprint that gives reach means the balloon hears *every* packet in the
radius. If it blindly rebroadcasts (flood / ROUTER), my model (412 km footprint,
3 pkt/node/hr, LongFast 559 ms ToA):

| Ground density | Nodes heard | Flood-repeat channel use | Relay TX power |
| --- | --- | --- | --- |
| Remote (1 / 10,000 km²) | 53 | 2 % | 4 mW |
| Rural (1 / 1,000 km²) | 534 | **25 %** | 43 mW |
| Suburban (1 / 100 km²) | 5,340 | **249 %** (saturated) | 425 mW |
| Dense metro (1 / 10 km²) | 53,405 | **2488 %** | 4.3 W |

Two documented mechanisms make a wide ROUTER harmful (research):
1. **Airtime saturation**, above (≥ suburban density is physically impossible; even
   rural hits the 25 % "cease using ROUTER" threshold).
2. **Path preemption**, ROUTER uses the early contention window and *always*
   rebroadcasts, suppressing nearby nodes' direct rebroadcasts. The Swiss alpine mesh:
   *"Router literally destroyed our Mesh"* until switched to ROUTER_LATE.

Counter-nuance from the real flight: at altitude the balloon may **under-hear** ground
(Flight 6 stayed <10 % chUtil because it couldn't detect ground packets). So with a
*weak* RX the risk is under-performance; with a *good* RX it's saturation. Either way
the design answer is the same: **be selective.**

## Open public relay, the airtime cap makes it safe (`91_open_relay.py`, fig N9)

The goal is an OPEN relay on the **default public LongFast channel** that helps the
whole region, and that's achievable as a good citizen, because the airtime self-cap
that keeps it safe ALSO steers its help to where it's needed. Cap the balloon's own
airtime at AirUtilTX ≤ 7.5% (≤ **483 rebroadcasts/hr**, ≤ **12.8 mW** relay TX, in
surplus budget) + ROUTER_LATE (defer/give-way), and:

| Ground density | Offered traffic | Balloon serves | Behavior |
| --- | --- | --- | --- |
| Remote (1/10,000 km²) | 160 pkt/hr | **100%** | carries it all, max public benefit |
| Rural (1/1,000 km²) | 1,602 pkt/hr | 30% | relays a big chunk, caps the rest |
| Suburban (1/100 km²) | 16,021 pkt/hr | 3% | defers, ground already covers it |
| Metro (1/10 km²) | 160,215 pkt/hr | 0% | defers entirely, not needed |

A capped open relay is **safe at every density** (channel contribution never exceeds
~7.5%, vs a naive flood-ROUTER blowing past 100%) and **auto-targets the underserved**:
full service where the mesh is sparse and nobody else can relay, near-silent where it's
dense and already covered. "Help the whole region" becomes "help the parts with no
other coverage", the highest public benefit anyway. This is the right answer.

## Why managed flooding makes ROUTER_LATE non-negotiable (`92_*.py`, fig N10)

Managed flooding = rebroadcast a received packet, but first wait a **contention
window** and cancel if you hear someone else rebroadcast it first. The window is
**SNR-based**: a node that heard the packet *weakly* (low SNR = far) gets a *shorter*
delay and goes **first** (so the farthest node extends range; nearer nodes hear it and
suppress). Normally elegant, but it is a **trap for a balloon**: the balloon hears
*everyone* weakly (it's ~400 km from all of them), so the SNR rule tells it to
rebroadcast **first for almost every packet**, and its 400 km rebroadcast is then heard
across the whole footprint, making ground nodes cancel their own hops region-wide. That
is the exact "ROUTER killed our mesh" mechanism, from first principles.

**ROUTER_LATE overrides the SNR window and forces the balloon to a LATE slot.** Now the
ground nodes go first; the balloon listens, and:
- **dense area** → it hears a ground node already rebroadcast → it **cancels** (silent,
  no harm);
- **sparse area** → nobody else rebroadcast → its late slot fires → it **fills the gap**.

So managed flooding, *with the late-window override*, is what gives the N9 self-targeting
**for free**, the balloon auto-defers where covered and carries traffic where it's the
only relay. (Caveats: hop-limit 1 so its rebroadcasts don't propagate further; it must be
in continuous RX during the window to hear both the original and others' rebroadcasts for
the cancel decision; the AirUtilTX cap is the backstop. Balloon-hop propagation delay
~1.3 ms ≪ the window, so the timing still works.)

## The good-citizen config (open + public, done right)
1. **Default public LongFast channel**, open to everyone; that's the point. It's safe
   *because of the airtime cap*, not because of a private channel. (A private channel
   is an optional alternative for a guaranteed buddy-only service; the open public relay
   is the bigger win.)
2. **Role = ROUTER_LATE** (forwards, but uses the late window so it *gives way* to
   ground paths) **+ an explicit AirUtilTX/ChUtil self-throttle** (cease relaying when
   ChUtil > 25%). **Never plain ROUTER** on an airborne footprint (the documented
   mesh-killer). CLIENT_MUTE is the ultra-safe "be reachable but forward nothing"
   fallback if we ever see harm.
3. **Hop limit 1**, a sky node covers a huge area in one hop; more hops just re-flood
   the ground.
4. **Hysteretic power-gating**, a browning-out relay that reboots repeatedly can spew
   broadcast storms (esp. MeshCore flood-adverts). Our floor-abort + 2-cycle hysteresis
   (the power design) is exactly the clean on/off this needs.
5. **Part-time by design**, available the ~12-14 h/day the cap is full + sunlit
   (f≈0.58); off at night. A daytime sky-repeater.
6. **Geofence the region/preset**, US915 over the Americas, EU868 over Europe (the
   firmware already geofences) so it serves whatever region it's over, on the matching
   Meshtastic preset.
7. Keep self-traffic minimal (altitude-milestone beacons), watch ChUtil < 25 % /
   AirUtilTX < 7-8 % if any gateway can see it.

## Meshtastic vs MeshCore for this

- **Meshtastic**: works, huge ground install base (the buddies already have it), proven
  config path (CLIENT_MUTE/ROUTER_LATE + private channel + hop 1). But it floods on
  group/broadcast channels, and stock firmware can't coexist with our LoRaWAN (so this
  is a *dedicated relay role/build*, time-shared on the radio only via the
  power-gate, OR a dedicated community balloon).
- **MeshCore**: more airtime-frugal for *directed* messages (companions don't relay,
  path-based unicast) and embeddable on our RAK3172, but **group/broadcast still
  floods**, repeaters send flood-adverts every 12 h, and a boot-looping repeater can
  *storm* the mesh (our power-cycling makes this a real risk to design against).
- **For the buddy-bridge use case specifically** (group messaging on a shared channel),
  *both* flood, so the private-channel + hop-1 + hysteresis discipline matters either
  way. Meshtastic wins on ground install base; MeshCore wins on embeddability + unicast
  frugality. Lead with Meshtastic for reach to existing users.

## Status & recommendation

This is the most community-valuable, lowest-regret edge feature: it helps people under
the balloon *now*, independent of our telemetry mission, and costs only surplus power.
But it's **pioneering**, do it as a *good citizen* (private channel, CLIENT_MUTE/
ROUTER_LATE, hop 1, hysteretic gate, sparse-area focus) and *measure* ChUtil so we
contribute the missing data instead of becoming the cautionary tale. Sequence it after
the telemetry-spine items (it's a surplus-window add, not the mission).

## Figures
- `N8_meshtastic_relay.png`, the 410 km buddy-bridge footprint, and the flood-repeat saturation-vs-density curve.
- `N9_open_relay.png`, open public relay with an airtime cap: self-targets the underserved, safe at every density.
- `N10_managed_flooding.png`, managed-flooding contention window vs a balloon: the SNR trap, and the ROUTER_LATE flip.
