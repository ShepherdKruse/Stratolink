import {
    Chart,
    Filler,
    LineController,
    LineElement,
    LinearScale,
    PointElement,
    Tooltip,
    type ChartConfiguration,
    type Plugin,
} from 'chart.js';
import type { FlightSample } from './types';

/** Chart.js v4 tree-shaking — register scales/elements used by flight reports. */
Chart.register(LineController, LineElement, PointElement, LinearScale, Tooltip, Filler);

function rrect(
    ctx: CanvasRenderingContext2D,
    x: number,
    y: number,
    w: number,
    h: number,
    r: number,
) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r);
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.closePath();
}

Chart.defaults.font.family = "'IBM Plex Sans', system-ui, sans-serif";
Chart.defaults.font.size = 11;
Chart.defaults.color = '#7a8599';

export function createAltitudeChart(
    canvas: HTMLCanvasElement,
    flight: FlightSample[],
    freezeMin: number,
    floatMin: number,
    resumeMin: number,
): Chart {
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('No canvas context');

    const stitched = flight
        .filter((d) => {
            if (d.mins < freezeMin) return d.alt_gps != null;
            if (d.mins < resumeMin) return d.alt_p != null && d.alt_p < 10100;
            return d.alt_gps != null;
        })
        .map((d) => ({
            x: d.mins,
            y:
                d.mins < freezeMin && d.alt_gps != null
                    ? d.alt_gps
                    : d.mins >= resumeMin && d.alt_gps != null
                      ? d.alt_gps
                      : d.alt_p,
        }));

    const pressLine = flight
        .filter((d) => d.alt_p != null && d.alt_p < 10100)
        .map((d) => ({ x: d.mins, y: d.alt_p }));

    const atmoPlugin: Plugin = {
        id: 'atmo',
        beforeDatasetsDraw(chart) {
            const { ctx: c, chartArea: ca, scales } = chart;
            const x = scales.x;
            const y = scales.y;
            if (!ca || !x || !y) return;
            c.save();
            c.beginPath();
            c.rect(ca.left, ca.top, ca.right - ca.left, ca.bottom - ca.top);
            c.clip();

            const bg = c.createLinearGradient(0, ca.bottom, 0, ca.top);
            bg.addColorStop(0, 'rgba(255,246,224,.82)');
            bg.addColorStop(0.1, 'rgba(218,237,255,.72)');
            bg.addColorStop(0.32, 'rgba(182,217,254,.62)');
            bg.addColorStop(0.62, 'rgba(146,183,238,.53)');
            bg.addColorStop(0.88, 'rgba(112,152,224,.44)');
            bg.addColorStop(1, 'rgba(84,120,208,.38)');
            c.fillStyle = bg;
            c.fillRect(ca.left, ca.top, ca.right - ca.left, ca.bottom - ca.top);

            for (const [alt, label] of [
                [3000, '3 km'],
                [6000, '6 km · High Cloud Layer'],
                [9000, '9 km · Upper Troposphere'],
            ] as const) {
                const py = y.getPixelForValue(alt);
                c.save();
                c.setLineDash([4, 5]);
                c.strokeStyle = 'rgba(70,95,155,.2)';
                c.lineWidth = 1;
                c.beginPath();
                c.moveTo(ca.left, py);
                c.lineTo(ca.right, py);
                c.stroke();
                c.restore();
                c.fillStyle = 'rgba(70,95,155,.45)';
                c.font = "10px 'IBM Plex Sans'";
                c.textAlign = 'right';
                c.fillText(label, ca.right - 6, py - 4);
            }

            const xF1 = x.getPixelForValue(freezeMin);
            const xF2 = x.getPixelForValue(floatMin);
            c.fillStyle = 'rgba(201,82,31,.07)';
            c.fillRect(xF1, ca.top, xF2 - xF1, ca.bottom - ca.top);
            c.save();
            c.setLineDash([3, 4]);
            c.strokeStyle = 'rgba(201,82,31,.38)';
            c.lineWidth = 1;
            c.beginPath();
            c.moveTo(xF1, ca.top);
            c.lineTo(xF1, ca.bottom);
            c.stroke();
            c.restore();

            const xFl = x.getPixelForValue(floatMin);
            const xRe = x.getPixelForValue(resumeMin);
            c.fillStyle = 'rgba(80,101,184,.05)';
            c.fillRect(xFl, ca.top, xRe - xFl, ca.bottom - ca.top);
            c.save();
            c.setLineDash([3, 4]);
            c.strokeStyle = 'rgba(80,101,184,.3)';
            c.lineWidth = 1;
            c.beginPath();
            c.moveTo(xFl, ca.top);
            c.lineTo(xFl, ca.bottom);
            c.stroke();
            c.beginPath();
            c.moveTo(xRe, ca.top);
            c.lineTo(xRe, ca.bottom);
            c.stroke();
            c.restore();
            c.restore();
        },
        afterDatasetsDraw(chart) {
            const { ctx: c, chartArea: ca, scales } = chart;
            const x = scales.x;
            const y = scales.y;
            if (!ca || !x || !y) return;
            c.save();

            const fpy = y.getPixelForValue(9491);
            c.save();
            c.setLineDash([7, 5]);
            c.strokeStyle = 'rgba(80,101,184,.55)';
            c.lineWidth = 1.5;
            c.beginPath();
            c.moveTo(ca.left, fpy);
            c.lineTo(ca.right, fpy);
            c.stroke();
            c.restore();
            const flabel = 'Float altitude ~9,491 m';
            c.font = "500 9.5px 'IBM Plex Sans'";
            const ftw = c.measureText(flabel).width;
            c.fillStyle = 'rgba(255,255,255,.94)';
            c.strokeStyle = 'rgba(80,101,184,.25)';
            c.lineWidth = 1;
            rrect(c, ca.left + 7, fpy - 18, ftw + 10, 14, 2);
            c.fill();
            c.stroke();
            c.fillStyle = 'rgba(80,101,184,.8)';
            c.textAlign = 'left';
            c.fillText(flabel, ca.left + 12, fpy - 7);

            const events = [
                { mins: 0, alt: 734, label: 'LAUNCH', color: '#2d8c55', labelPos: 'above' as const, note: null },
                { mins: freezeMin, alt: 6924, label: 'GPS FREEZE', color: '#c9521f', labelPos: 'above' as const, note: null },
                { mins: floatMin, alt: 9491, label: 'FLOAT', color: '#5065b8', labelPos: 'below' as const, note: null },
                {
                    mins: resumeMin,
                    alt: 9744,
                    label: 'GPS RESUME',
                    color: '#5a8c6e',
                    labelPos: 'below' as const,
                    note: 'position stale after this point',
                },
            ];

            for (const { mins, alt, label, color, labelPos, note } of events) {
                const px = x.getPixelForValue(mins);
                const py = y.getPixelForValue(alt);
                if (px < ca.left || px > ca.right) continue;
                c.save();
                c.strokeStyle = color + '28';
                c.lineWidth = 1;
                c.setLineDash([3, 3]);
                c.beginPath();
                c.moveTo(px, ca.bottom);
                c.lineTo(px, py + 7);
                c.stroke();
                c.restore();
                c.beginPath();
                c.arc(px, py, 5, 0, Math.PI * 2);
                c.fillStyle = '#ffffff';
                c.fill();
                c.strokeStyle = color;
                c.lineWidth = 2;
                c.stroke();
                c.font = "600 9px 'IBM Plex Sans'";
                const tw = c.measureText(label).width;
                const pw = tw + 10;
                const ph = 14;
                const pillY = labelPos === 'above' ? py - ph - 9 : py + 9;
                c.fillStyle = 'rgba(255,255,255,.95)';
                c.strokeStyle = color + '35';
                c.lineWidth = 1;
                rrect(c, px - pw / 2, pillY, pw, ph, 3);
                c.fill();
                c.stroke();
                c.fillStyle = color;
                c.font = "600 9px 'IBM Plex Sans'";
                c.textAlign = 'center';
                c.fillText(label, px, pillY + ph - 4);
                if (note) {
                    const noteY = labelPos === 'above' ? pillY - 4 : pillY + ph + 11;
                    c.font = "italic 8.5px 'IBM Plex Sans'";
                    c.fillStyle = 'rgba(122,133,153,.75)';
                    c.fillText(note, px, noteY);
                }
            }

            const gpsFixTicks = [
                { mins: 513.7, alt: 9621, utc: '00:29', above: false },
                { mins: 591.5, alt: 9648, utc: '01:46', above: true },
                { mins: 607.6, alt: 9682, utc: '02:03', above: false },
            ];
            for (const { mins, alt, utc, above } of gpsFixTicks) {
                const px = x.getPixelForValue(mins);
                const py = y.getPixelForValue(alt);
                if (px < ca.left || px > ca.right) continue;
                const dir = above ? -1 : 1;
                const tickLen = 16;
                c.beginPath();
                c.arc(px, py, 3.5, 0, Math.PI * 2);
                c.fillStyle = 'white';
                c.fill();
                c.strokeStyle = '#5065b8';
                c.lineWidth = 1.5;
                c.stroke();
                c.strokeStyle = 'rgba(80,101,184,.35)';
                c.lineWidth = 1;
                c.beginPath();
                c.moveTo(px, py + dir * 5);
                c.lineTo(px, py + dir * (5 + tickLen));
                c.stroke();
                c.font = "9px 'IBM Plex Mono'";
                c.fillStyle = 'rgba(80,101,184,.62)';
                c.textAlign = 'center';
                c.fillText(utc + ' UTC', px, py + dir * (5 + tickLen) + (above ? -4 : 10));
            }

            const zPx = x.getPixelForValue(111.1);
            const zPy = y.getPixelForValue(5809);
            c.beginPath();
            c.arc(zPx, zPy, 4, 0, Math.PI * 2);
            c.fillStyle = 'white';
            c.fill();
            c.strokeStyle = '#4a7ed4';
            c.lineWidth = 1.5;
            c.stroke();
            c.fillStyle = '#4a7ed4';
            c.font = "10px 'IBM Plex Sans'";
            c.textAlign = 'left';
            c.fillText('0°C', zPx + 7, zPy + 4);
            c.restore();
        },
    };

    const config: ChartConfiguration<'line'> = {
        type: 'line',
        plugins: [atmoPlugin],
        data: {
            datasets: [
                {
                    label: 'Best-estimate altitude',
                    data: stitched,
                    borderColor: '#c9521f',
                    backgroundColor(context) {
                        const chart = context.chart;
                        const c = chart.ctx;
                        const chartArea = chart.chartArea;
                        if (!chartArea) return 'transparent';
                        const g = c.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
                        g.addColorStop(0, 'rgba(201,82,31,.2)');
                        g.addColorStop(0.6, 'rgba(201,82,31,.06)');
                        g.addColorStop(1, 'rgba(201,82,31,.00)');
                        return g;
                    },
                    borderWidth: 2.5,
                    fill: true,
                    tension: 0.35,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                    pointHoverBackgroundColor: '#c9521f',
                },
                {
                    label: 'Pressure-derived altitude',
                    data: pressLine,
                    borderColor: 'rgba(201,82,31,.35)',
                    borderWidth: 1.3,
                    borderDash: [5, 4],
                    fill: false,
                    tension: 0.3,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 700, easing: 'easeInOutQuart' },
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(255,255,255,.97)',
                    borderColor: 'rgba(0,0,0,.1)',
                    borderWidth: 1,
                    titleColor: '#1b2438',
                    bodyColor: '#3d4d6a',
                    titleFont: { size: 11, weight: '600' },
                    bodyFont: { size: 11 },
                    padding: 10,
                    callbacks: {
                        title: (items) => 'T + ' + Math.round(items[0].parsed.x) + ' min',
                        label: (item) =>
                            item.dataset.label + ': ' + Math.round(item.parsed.y).toLocaleString() + ' m',
                    },
                },
            },
            scales: {
                x: {
                    type: 'linear',
                    grid: { color: 'rgba(0,0,0,.05)' },
                    border: { color: 'rgba(0,0,0,.1)' },
                    title: {
                        display: true,
                        text: 'Minutes from launch (T+)',
                        color: '#7a8599',
                        font: { size: 11 },
                    },
                    ticks: {
                        color: '#7a8599',
                        maxTicksLimit: 10,
                        callback: (v) => 'T+' + v,
                    },
                },
                y: {
                    grid: { color: 'rgba(0,0,0,.05)' },
                    border: { color: 'rgba(0,0,0,.1)' },
                    title: {
                        display: true,
                        text: 'Altitude (m)',
                        color: '#7a8599',
                        font: { size: 11 },
                    },
                    ticks: {
                        color: '#7a8599',
                        callback: (v) =>
                            Number(v) >= 1000 ? (Number(v) / 1000).toFixed(0) + ' km' : v + ' m',
                    },
                    min: 0,
                    max: 10500,
                },
            },
        },
    };

    return new Chart(ctx, config);
}

export function createTemperatureChart(
    canvas: HTMLCanvasElement,
    flight: FlightSample[],
): Chart {
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('No canvas context');

    const data = flight.filter((d) => d.temp != null).map((d) => ({ x: d.mins, y: d.temp }));

    const zeroPlugin: Plugin = {
        id: 'zeroLine',
        afterDatasetsDraw(chart) {
            const { ctx: c, scales, chartArea: ca } = chart;
            const y = scales.y;
            const x = scales.x;
            if (!ca || !y || !x) return;
            const py = y.getPixelForValue(0);
            if (py < ca.top || py > ca.bottom) return;
            c.save();
            c.setLineDash([4, 4]);
            c.strokeStyle = 'rgba(74,126,212,.45)';
            c.lineWidth = 1;
            c.beginPath();
            c.moveTo(ca.left, py);
            c.lineTo(ca.right, py);
            c.stroke();
            c.restore();
            c.fillStyle = '#4a7ed4';
            c.font = "9.5px 'IBM Plex Sans'";
            c.textAlign = 'left';
            c.fillText('0°C', ca.left + 4, py - 3);
        },
    };

    return new Chart(ctx, {
        type: 'line',
        plugins: [zeroPlugin],
        data: {
            datasets: [
                {
                    label: 'Temperature (°C)',
                    data,
                    borderColor: '#c9521f',
                    borderWidth: 1.8,
                    fill: false,
                    tension: 0.3,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                    pointHoverBackgroundColor: '#c9521f',
                    segment: {
                        borderColor: (ctx) => (ctx.p1.parsed.y < 0 ? '#4a7ed4' : '#c9521f'),
                    },
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 500 },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(255,255,255,.97)',
                    borderColor: 'rgba(0,0,0,.1)',
                    borderWidth: 1,
                    titleColor: '#1b2438',
                    bodyColor: '#3d4d6a',
                    padding: 8,
                    callbacks: {
                        title: (items) => 'T+' + Math.round(items[0].parsed.x) + ' min',
                        label: (item) => 'Temp: ' + item.parsed.y.toFixed(1) + '°C',
                    },
                },
            },
            scales: {
                x: {
                    type: 'linear',
                    grid: { color: 'rgba(0,0,0,.05)' },
                    border: { color: 'rgba(0,0,0,.08)' },
                    ticks: { maxTicksLimit: 5, callback: (v) => 'T+' + v },
                },
                y: {
                    grid: { color: 'rgba(0,0,0,.05)' },
                    border: { color: 'rgba(0,0,0,.08)' },
                    ticks: { callback: (v) => v + '°' },
                },
            },
        },
    });
}

export function createPressureChart(
    canvas: HTMLCanvasElement,
    flight: FlightSample[],
): Chart {
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('No canvas context');

    const data = flight
        .filter((d) => d.pres > 260 && d.pres < 950)
        .map((d) => ({ x: d.mins, y: d.pres }));

    const floatPlugin: Plugin = {
        id: 'floatBand',
        beforeDatasetsDraw(chart) {
            const { ctx: c, scales, chartArea: ca } = chart;
            const y = scales.y;
            const x = scales.x;
            if (!ca || !y || !x) return;
            const y1 = y.getPixelForValue(283);
            const y2 = y.getPixelForValue(290);
            c.save();
            c.fillStyle = 'rgba(80,101,184,.07)';
            c.fillRect(ca.left, y1, ca.right - ca.left, y2 - y1);
            c.setLineDash([4, 4]);
            c.strokeStyle = 'rgba(80,101,184,.32)';
            c.lineWidth = 1;
            const mid = (y1 + y2) / 2;
            c.beginPath();
            c.moveTo(ca.left, mid);
            c.lineTo(ca.right, mid);
            c.stroke();
            c.restore();
            c.fillStyle = 'rgba(80,101,184,.6)';
            c.font = "9.5px 'IBM Plex Sans'";
            c.textAlign = 'right';
            c.fillText('Float plateau ~285 hPa', ca.right - 4, mid - 4);
        },
    };

    return new Chart(ctx, {
        type: 'line',
        plugins: [floatPlugin],
        data: {
            datasets: [
                {
                    label: 'Pressure (hPa)',
                    data,
                    borderColor: '#c9521f',
                    backgroundColor: 'rgba(201,82,31,.06)',
                    borderWidth: 1.8,
                    fill: true,
                    tension: 0.25,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                    pointHoverBackgroundColor: '#c9521f',
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 500 },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(255,255,255,.97)',
                    borderColor: 'rgba(0,0,0,.1)',
                    borderWidth: 1,
                    titleColor: '#1b2438',
                    bodyColor: '#3d4d6a',
                    padding: 8,
                    callbacks: {
                        title: (items) => 'T+' + Math.round(items[0].parsed.x) + ' min',
                        label: (item) => 'Pressure: ' + item.parsed.y + ' hPa',
                    },
                },
            },
            scales: {
                x: {
                    type: 'linear',
                    grid: { color: 'rgba(0,0,0,.05)' },
                    border: { color: 'rgba(0,0,0,.08)' },
                    ticks: { maxTicksLimit: 5, callback: (v) => 'T+' + v },
                },
                y: {
                    grid: { color: 'rgba(0,0,0,.05)' },
                    border: { color: 'rgba(0,0,0,.08)' },
                    reverse: true,
                },
            },
        },
    });
}
