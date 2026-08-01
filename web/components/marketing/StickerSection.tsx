'use client';

import Image from 'next/image';
import { motion, useReducedMotion } from 'framer-motion';
import type { ReactNode } from 'react';

type Visual = {
    src: string;
    alt: string;
    /** Relative visual weight */
    width?: number;
    className?: string;
    /**
     * sticker = transparent cutout (balloons / hardware)
     * photo = full-frame image with background (people / scenes)
     */
    variant?: 'sticker' | 'photo';
};

type StickerSectionProps = {
    id?: string;
    eyebrow?: string;
    title: ReactNode;
    body: ReactNode;
    /** One or more visuals in the media column */
    stickers: Visual[];
    /** Image on the left (default) or right */
    reverse?: boolean;
    className?: string;
    children?: ReactNode;
};

export function StickerSection({
    id,
    eyebrow,
    title,
    body,
    stickers,
    reverse = false,
    className = '',
    children,
}: StickerSectionProps) {
    const reduceMotion = useReducedMotion();

    return (
        <section
            id={id}
            className={`border-b border-border/60 bg-background py-24 sm:py-32 ${className}`}
        >
            <div className="mx-auto grid max-w-6xl items-center gap-12 px-6 sm:px-8 lg:grid-cols-2 lg:gap-20">
                <div
                    className={`relative flex min-h-[240px] flex-col items-center justify-center gap-8 ${
                        reverse ? 'lg:order-2' : 'lg:order-1'
                    }`}
                >
                    {stickers.map((s, i) => {
                        const isPhoto = (s.variant ?? 'sticker') === 'photo';
                        const float = !isPhoto && !reduceMotion;
                        return (
                            <motion.div
                                key={`${s.src}-${i}`}
                                className={`w-full ${isPhoto ? 'max-w-[min(100%,520px)]' : ''} ${s.className ?? ''}`}
                                animate={
                                    float
                                        ? {
                                              y: [0, i % 2 === 0 ? -10 : -6, 0],
                                              rotate: [0, i % 2 === 0 ? -1.2 : 1.4, 0],
                                          }
                                        : undefined
                                }
                                transition={
                                    float
                                        ? {
                                              duration: 7 + i,
                                              repeat: Infinity,
                                              ease: 'easeInOut',
                                              delay: i * 0.4,
                                          }
                                        : undefined
                                }
                            >
                                <Image
                                    src={s.src}
                                    alt={s.alt}
                                    width={s.width ?? (isPhoto ? 900 : 520)}
                                    height={s.width ?? (isPhoto ? 700 : 520)}
                                    className={
                                        isPhoto
                                            ? 'h-auto w-full object-cover'
                                            : 'h-auto w-full max-w-[min(100%,420px)] object-contain drop-shadow-xl mx-auto'
                                    }
                                    sizes={
                                        isPhoto
                                            ? '(max-width: 1024px) 90vw, 520px'
                                            : '(max-width: 1024px) 80vw, 420px'
                                    }
                                    priority={i === 0}
                                />
                            </motion.div>
                        );
                    })}
                </div>

                <div className={`max-w-xl ${reverse ? 'lg:order-1' : 'lg:order-2'}`}>
                    {eyebrow ? (
                        <p className="mb-4 font-mono text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
                            {eyebrow}
                        </p>
                    ) : null}
                    <h2 className="text-4xl font-semibold tracking-tight text-foreground sm:text-5xl">
                        {title}
                    </h2>
                    <div className="mt-6 space-y-4 text-lg leading-relaxed text-muted-foreground">
                        {typeof body === 'string' ? <p>{body}</p> : body}
                    </div>
                    {children}
                </div>
            </div>
        </section>
    );
}
