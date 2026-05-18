/** Scroll-reveal + live telemetry ticker for the /mission outreach page. */
export function initMissionOutreach(root: HTMLElement) {
    const reveals = root.querySelectorAll<HTMLElement>('.reveal');
    const io = new IntersectionObserver(
        (entries) => {
            entries.forEach((e) => {
                if (e.isIntersecting) {
                    e.target.classList.add('in');
                    io.unobserve(e.target);
                }
            });
        },
        { threshold: 0.1, rootMargin: '0px 0px -40px 0px' },
    );
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

    try {
        const unit = new URLSearchParams(window.location.search).get('unit');
        if (unit) {
            const safe = unit.trim().slice(0, 24).toUpperCase();
            const unitEl = root.querySelector('#unit-name');
            if (safe && unitEl) unitEl.textContent = `JROTC UNIT ${safe}`;
        }
    } catch {
        /* ignore */
    }

    const els = {
        alt: root.querySelector('#r-alt'),
        temp: root.querySelector('#r-temp'),
        pres: root.querySelector('#r-pres'),
        spd: root.querySelector('#r-spd'),
        rssi: root.querySelector('#r-rssi'),
        met: root.querySelector('#r-met'),
        utc: root.querySelector('#utc-time'),
        ulAge: root.querySelector('#ul-age'),
        np: root.querySelector('#np'),
        coord: root.querySelector('#coord-text'),
        altT: root.querySelector('#r-alt-t'),
    };

    let st = {
        alt: 9487,
        temp: -48.6,
        pres: 282.4,
        spd: 38.2,
        rssi: -94,
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
        st.alt += (Math.random() - 0.5) * 3.5;
        st.temp += (Math.random() - 0.5) * 0.25;
        st.pres += (Math.random() - 0.5) * 0.6;
        st.spd += (Math.random() - 0.5) * 0.6;
        if (Math.random() < 0.3) st.rssi += Math.random() < 0.5 ? -1 : 1;
        st.metSec += 1;
        st.ulAgeSec += 1;
        st.lon += 0.0004;
        if (st.ulAgeSec >= 60) st.ulAgeSec = 0;

        if (els.alt) els.alt.textContent = comma(st.alt);
        if (els.temp) els.temp.textContent = fmt(st.temp, 1);
        if (els.pres) els.pres.textContent = fmt(st.pres, 1);
        if (els.spd) els.spd.textContent = fmt(st.spd, 1);
        if (els.rssi) els.rssi.textContent = fmt(st.rssi, 0);
        if (els.met) els.met.textContent = dur(st.metSec);
        if (els.utc) {
            const d = new Date();
            const p = (n: number) => String(n).padStart(2, '0');
            els.utc.textContent = `${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())} UTC`;
        }
        if (els.ulAge) els.ulAge.textContent = `${st.ulAgeSec}s`;
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
    const interval = window.setInterval(tick, 1000);
    return () => window.clearInterval(interval);
}
