'use client';

import Link from 'next/link';
import { useEffect, useRef } from 'react';

type Props = {
    contentHtml: string;
};

function easeOutPow2(t: number): number {
    return 1 - (1 - t) ** 2;
}

function animateCount(
    el: HTMLElement,
    from: number,
    to: number,
    fmt: (n: number) => string,
    duration = 1800,
) {
    const start = performance.now();
    const step = (now: number) => {
        const t = Math.min(1, (now - start) / duration);
        el.textContent = fmt(from + (to - from) * easeOutPow2(t));
        if (t < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
}

export function StratolinkLearnClient({ contentHtml }: Props) {
    const rootRef = useRef<HTMLDivElement>(null);
    const navCurRef = useRef<HTMLSpanElement>(null);

    useEffect(() => {
        const root = rootRef.current;
        if (!root) return;

        const starsEl = root.querySelector<HTMLElement>('#hero-stars');
        if (starsEl) {
            let html = '';
            for (let i = 0; i < 100; i++) {
                const size = Math.random() < 0.75 ? 's1' : 's2';
                const tw = Math.random() < 0.3 ? ' tw' : '';
                const x = Math.random() * 100;
                const y = Math.random() * 100;
                const delay = (Math.random() * 4).toFixed(2);
                html += `<div class="star ${size}${tw}" style="left:${x}%;top:${y}%;animation-delay:${delay}s;opacity:${(0.3 + Math.random() * 0.5).toFixed(2)}"></div>`;
            }
            starsEl.innerHTML = html;
        }

        const io = new IntersectionObserver(
            (entries) => {
                for (const entry of entries) {
                    if (entry.isIntersecting) {
                        entry.target.classList.add('in');
                        io.unobserve(entry.target);
                    }
                }
            },
            { threshold: 0.12, rootMargin: '0px 0px -60px 0px' },
        );
        const reveals = root.querySelectorAll<HTMLElement>('.reveal');
        reveals.forEach((el) => io.observe(el));

        requestAnimationFrame(() =>
            setTimeout(() => {
                const vh = window.innerHeight;
                reveals.forEach((el) => {
                    if (el.classList.contains('in')) return;
                    if (el.getBoundingClientRect().top < vh - 40) {
                        el.classList.add('in');
                        io.unobserve(el);
                    }
                });
            }, 100),
        );

        const atmoRail = root.querySelector<HTMLElement>('#atmo');
        const layers = root.querySelectorAll<HTMLElement>('.atmo-layer');
        const sections = root.querySelectorAll<HTMLElement>('section[data-section]');
        const bandTops: Record<string, string> = {
            sea: '92%',
            clouds: '74%',
            cruise: '56%',
            float: '32%',
            space: '10%',
        };
        const ind = root.querySelector<HTMLElement>('#here-ind');

        const activate = (band: string, sectionNum: string) => {
            layers.forEach((l) => l.classList.toggle('here', l.dataset.band === band));
            if (ind && bandTops[band]) ind.style.top = bandTops[band];
            if (navCurRef.current) navCurRef.current.textContent = sectionNum.padStart(2, '0');
            atmoRail?.classList.add('in');
        };

        const sectIO = new IntersectionObserver(
            (entries) => {
                for (const entry of entries) {
                    if (entry.isIntersecting && entry.intersectionRatio > 0.32) {
                        const target = entry.target as HTMLElement;
                        const band = target.dataset.band || 'sea';
                        const num = target.dataset.section || '01';
                        activate(band, num);
                    }
                }
            },
            { threshold: [0.32, 0.6] },
        );
        sections.forEach((s) => sectIO.observe(s));

        const faqItems = root.querySelectorAll<HTMLElement>('.faq-item');
        const faqCleanups: Array<() => void> = [];
        faqItems.forEach((item) => {
            const btn = item.querySelector<HTMLButtonElement>('.faq-q');
            if (!btn) return;
            const onClick = () => {
                const wasOpen = item.classList.contains('open');
                root.querySelectorAll('.faq-item.open').forEach((o) => o.classList.remove('open'));
                if (!wasOpen) item.classList.add('open');
            };
            btn.addEventListener('click', onClick);
            faqCleanups.push(() => btn.removeEventListener('click', onClick));
        });
        faqItems[0]?.classList.add('open');

        try {
            const name = new URLSearchParams(window.location.search).get('name');
            if (name) {
                const trimmed = name.trim().slice(0, 32);
                const cmdr = root.querySelector('#cmdr-name');
                if (trimmed && cmdr) cmdr.textContent = trimmed;
            }
        } catch {
            /* ignore */
        }

        const els = {
            alt: root.querySelector<HTMLElement>('#r-alt'),
            temp: root.querySelector<HTMLElement>('#r-temp'),
            pres: root.querySelector<HTMLElement>('#r-pres'),
            spd: root.querySelector<HTMLElement>('#r-spd'),
            met: root.querySelector<HTMLElement>('#r-met'),
            dist: root.querySelector<HTMLElement>('#r-dist'),
            utc: root.querySelector<HTMLElement>('#utc-time'),
            ulAge: root.querySelector<HTMLElement>('#ul-age'),
            np: root.querySelector<HTMLElement>('#np'),
            coord: root.querySelector<HTMLElement>('#coord-text'),
            altT: root.querySelector<HTMLElement>('#r-alt-t'),
        };

        let st = {
            alt: 9487,
            temp: -54.0,
            pres: 285.7,
            spd: 112,
            distKm: 684,
            metSec: 4 * 3600 + 42 * 60 + 13,
            ulAgeSec: 23,
            lat: 37.78,
            lon: -122.4,
        };

        const fmt = (n: number, dp = 0) => n.toFixed(dp);
        const comma = (n: number) => Math.round(n).toLocaleString();
        const dur = (s: number) => {
            const h = Math.floor(s / 3600);
            const m = Math.floor((s % 3600) / 60);
            const ss = Math.floor(s % 60);
            return [h, m, ss].map((v) => String(v).padStart(2, '0')).join(':');
        };

        const tick = () => {
            st.alt += (Math.random() - 0.5) * 4;
            st.temp += (Math.random() - 0.5) * 0.3;
            st.pres += (Math.random() - 0.5) * 0.5;
            st.spd += (Math.random() - 0.5) * 1.2;
            st.metSec += 1;
            st.ulAgeSec += 1;
            st.distKm += st.spd / 3600;
            st.lon += 0.0004;
            if (st.ulAgeSec >= 60) st.ulAgeSec = 0;

            if (els.alt) els.alt.textContent = comma(st.alt);
            if (els.temp) els.temp.textContent = fmt(st.temp, 1);
            if (els.pres) els.pres.textContent = fmt(st.pres, 1);
            if (els.spd) els.spd.textContent = fmt(st.spd, 0);
            if (els.met) els.met.textContent = dur(st.metSec);
            if (els.dist) els.dist.textContent = comma(st.distKm);
            if (els.utc) {
                const d = new Date();
                const p = (n: number) => String(n).padStart(2, '0');
                els.utc.textContent = `${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())} UTC`;
            }
            if (els.ulAge) els.ulAge.textContent = st.ulAgeSec < 60 ? `${st.ulAgeSec}s ago` : 'just now';
            if (els.np) els.np.textContent = `${Math.max(0, 60 - st.ulAgeSec)}s`;
            if (els.coord) els.coord.textContent = `${st.lat.toFixed(2)}° N · ${st.lon.toFixed(2)}° W`;
            if (els.altT) {
                const d = st.alt - 9487;
                els.altT.textContent =
                    Math.abs(d) < 4
                        ? '↑ stable · float band'
                        : d > 0
                          ? `↑ ${Math.abs(d).toFixed(0)} m above trim`
                          : `↓ ${Math.abs(d).toFixed(0)} m below trim`;
            }
        };

        tick();
        const ticker = window.setInterval(tick, 1000);

        const dashEl = root.querySelector<HTMLElement>('#dash');
        let dashCounted = false;
        const dashIO = dashEl
            ? new IntersectionObserver(
                  (entries) => {
                      for (const entry of entries) {
                          if (!entry.isIntersecting || dashCounted) continue;
                          dashCounted = true;
                          const targets = [
                              { el: els.alt, from: 0, to: st.alt, fmt: comma },
                              { el: els.temp, from: 20, to: st.temp, fmt: (n: number) => n.toFixed(1) },
                              { el: els.pres, from: 1013, to: st.pres, fmt: (n: number) => n.toFixed(1) },
                              { el: els.spd, from: 0, to: st.spd, fmt: (n: number) => Math.round(n).toString() },
                              { el: els.dist, from: 0, to: st.distKm, fmt: comma },
                          ];
                          for (const t of targets) {
                              if (t.el) animateCount(t.el, t.from, t.to, t.fmt);
                          }
                          dashIO?.disconnect();
                      }
                  },
                  { threshold: 0.2, rootMargin: '0px 0px -20% 0px' },
              )
            : null;
        if (dashEl) dashIO?.observe(dashEl);

        return () => {
            io.disconnect();
            sectIO.disconnect();
            dashIO?.disconnect();
            window.clearInterval(ticker);
            faqCleanups.forEach((fn) => fn());
        };
    }, [contentHtml]);

    return (
        <>
            <nav className="learn-subnav" aria-label="Learn page sections">
                <div className="learn-subnav-in">
                    <Link href="/" className="brand">
                        <span className="mark" aria-hidden />
                        Stratolink
                    </Link>
                    <span className="learn-subnav-progress">
                        <span id="nav-cur" ref={navCurRef}>
                            01
                        </span>{' '}
                        / 08
                    </span>
                    <div className="learn-subnav-right">
                        <a href="#faq" className="btn btn-ghost">
                            FAQ
                        </a>
                        <Link href="/activate" className="btn btn-pri">
                            Launch →
                        </Link>
                    </div>
                </div>
            </nav>
            <div
                ref={rootRef}
                className="learn-page"
                dangerouslySetInnerHTML={{ __html: contentHtml }}
            />
        </>
    );
}
