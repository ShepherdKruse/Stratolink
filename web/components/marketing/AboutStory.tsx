'use client';

import Link from 'next/link';
import { StickerSection } from '@/components/marketing/StickerSection';

/**
 * Fun narrative for /about — balloon/hardware as floating stickers,
 * people scenes as full-frame photos (cleaner than rembg cutouts).
 */
export function AboutStory() {
    return (
        <>
            <StickerSection
                id="meet"
                eyebrow="The payload"
                title="Meet Stratolink."
                body="A 10-gram satellite that circumnavigates the globe — solar wings, a radio, and a pocketful of sensors riding under a balloon not much bigger than the ones at a party store."
                stickers={[
                    {
                        src: '/stickers/payload.png',
                        alt: 'Stratolink payload with solar panels',
                        width: 560,
                        variant: 'sticker',
                    },
                ]}
            />

            <StickerSection
                id="how"
                eyebrow="The ride"
                title="How does it work?"
                reverse
                body={
                    <>
                        <p>
                            Stratolink is carried by a balloon not so different from those you&apos;d find at a party
                            store. The balloon rises above 30,000 feet, where it drifts in the jet stream for weeks at a
                            time.
                        </p>
                        <p>
                            Fill it, name the mission, let go — and the payload starts talking to gateways on the ground
                            while you watch from Mission Control.
                        </p>
                    </>
                }
                stickers={[
                    {
                        src: '/photos/launch-held.jpg',
                        alt: 'Team holding a clear pico balloon before launch',
                        width: 900,
                        variant: 'photo',
                    },
                ]}
            />

            <StickerSection
                id="what"
                eyebrow="Two jobs"
                title="What can it do?"
                body={
                    <p>
                        Stratolink fills two important roles: it collects data from hard-to-reach regions of the upper
                        atmosphere, and it hears and relays signals from off-grid IoT devices on the ground.
                    </p>
                }
                stickers={[
                    {
                        src: '/stickers/payload-pair.png',
                        alt: 'Solar-powered Stratolink payloads',
                        width: 620,
                        variant: 'sticker',
                        className: 'z-10',
                    },
                    {
                        src: '/stickers/balloon-ascent.png',
                        alt: 'Pico balloon with hanging payload',
                        width: 360,
                        variant: 'sticker',
                        className: '-mt-6 opacity-95',
                    },
                ]}
            />

            <StickerSection
                id="where"
                eyebrow="The path"
                title="Where does it go?"
                reverse
                body={
                    <>
                        <p>
                            Once it finds its altitude, the balloon doesn&apos;t pop — it floats. Wind currents carry it
                            across states, borders, and sometimes oceans, while live telemetry paints the trail on the
                            map.
                        </p>
                        <p>
                            Scroll the globe above, or open Mission Control to follow a real flight as it happens.
                        </p>
                    </>
                }
                stickers={[
                    {
                        src: '/photos/launch-ascent.jpg',
                        alt: 'Balloon rising over the park after launch',
                        width: 900,
                        variant: 'photo',
                    },
                ]}
            >
                <div className="mt-8 flex flex-wrap gap-4">
                    <Link
                        href="/dashboard"
                        className="inline-flex items-center rounded-sm bg-primary px-5 py-2.5 font-mono text-xs font-medium uppercase tracking-[0.12em] text-primary-foreground transition-colors hover:bg-primary/90"
                    >
                        Mission Control
                    </Link>
                    <Link
                        href="/learn"
                        className="inline-flex items-center font-mono text-xs uppercase tracking-[0.12em] text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
                    >
                        How the balloon works →
                    </Link>
                </div>
            </StickerSection>

            <StickerSection
                id="who"
                eyebrow="Built with people"
                title="Made to launch together."
                body="From park benches to classrooms, Stratolink is meant to be built, named, and flown as a team — every student a Mission Commander on the same live map."
                stickers={[
                    {
                        src: '/photos/classroom-group.jpg',
                        alt: 'Group preparing a Stratolink balloon launch',
                        width: 900,
                        variant: 'photo',
                    },
                ]}
            >
                <div className="mt-8 flex flex-wrap gap-4">
                    <Link
                        href="/classrooms"
                        className="inline-flex items-center rounded-sm border border-border bg-card px-5 py-2.5 font-mono text-xs font-medium uppercase tracking-[0.12em] text-foreground transition-colors hover:border-foreground/30"
                    >
                        For teachers
                    </Link>
                    <Link
                        href="/activate"
                        className="inline-flex items-center font-mono text-xs uppercase tracking-[0.12em] text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
                    >
                        Activate a device →
                    </Link>
                </div>
            </StickerSection>
        </>
    );
}
