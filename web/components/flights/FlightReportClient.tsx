'use client';

import Link from 'next/link';
import { useEffect, useRef } from 'react';
import type { Chart } from 'chart.js';
import type { FlightReport } from '@/lib/flights/types';
import type { FlightTelemetryBundle } from '@/lib/flights/getFlightData';
import {
    createAltitudeChart,
    createPressureChart,
    createTemperatureChart,
} from '@/lib/flights/flightReportCharts';
import FlightReportMap from './FlightReportMap';

type FlightReportClientProps = {
    report: FlightReport;
    telemetry: FlightTelemetryBundle;
};

export default function FlightReportClient({ report, telemetry }: FlightReportClientProps) {
    const altRef = useRef<HTMLCanvasElement>(null);
    const tempRef = useRef<HTMLCanvasElement>(null);
    const pressRef = useRef<HTMLCanvasElement>(null);
    const chartsRef = useRef<Chart[]>([]);

    const { samples, freezeMin, floatMin, resumeMin } = telemetry;
    const { kpis } = report;

    useEffect(() => {
        const charts: Chart[] = [];
        if (altRef.current) {
            charts.push(
                createAltitudeChart(altRef.current, samples, freezeMin, floatMin, resumeMin),
            );
        }
        if (tempRef.current) {
            charts.push(createTemperatureChart(tempRef.current, samples));
        }
        if (pressRef.current) {
            charts.push(createPressureChart(pressRef.current, samples));
        }
        chartsRef.current = charts;
        return () => {
            charts.forEach((c) => c.destroy());
            chartsRef.current = [];
        };
    }, [samples, freezeMin, floatMin, resumeMin]);

    return (
        <div className="flight-report">
            <div className="fr-page">
                <nav className="fr-breadcrumb" aria-label="Breadcrumb">
                    <Link href="/flights">Flights</Link>
                    <span> / </span>
                    <span>{report.callsign ?? report.title}</span>
                </nav>

                <header className="fr-header">
                    <div className="fr-kicker">Stratolink · Pico Balloon Flight Report</div>
                    <h1 className="fr-page-title">
                        {report.callsign ?? report.title} — <em>{report.subtitle}</em>
                    </h1>
                    <div className="fr-meta">
                        <span>Device: {report.deviceId}</span>
                        <span>Launched {report.launchedAtUtc}</span>
                        <span className="fr-mono">{report.launchCoords}</span>
                        <span>{report.comms}</span>
                        <span>{report.gpsFixes} GPS fixes</span>
                    </div>
                </header>

                <div className="fr-kpi-strip">
                    <div className="fr-kpi">
                        <div className="fr-kpi-label">Peak Altitude</div>
                        <div className="fr-kpi-number">
                            {kpis.peakAltitudeM.toLocaleString()}
                            <span className="fr-kpi-unit"> m</span>
                        </div>
                        <div className="fr-kpi-sub">
                            {kpis.peakAltitudeFt.toLocaleString()} ft — GPS confirmed
                        </div>
                    </div>
                    <div className="fr-kpi">
                        <div className="fr-kpi-label">Min Temperature</div>
                        <div className="fr-kpi-number">
                            {kpis.minTempC}
                            <span className="fr-kpi-unit"> °C</span>
                        </div>
                        <div className="fr-kpi-sub">{kpis.minTempNote}</div>
                    </div>
                    <div className="fr-kpi">
                        <div className="fr-kpi-label">Float Duration</div>
                        <div className="fr-kpi-number">
                            {kpis.floatDuration}
                            <span className="fr-kpi-unit"> hrs</span>
                        </div>
                        <div className="fr-kpi-sub">{kpis.floatNote}</div>
                    </div>
                    <div className="fr-kpi">
                        <div className="fr-kpi-label">Ground Coverage</div>
                        <div className="fr-kpi-number">
                            ~{kpis.groundCoverageKm.toLocaleString()}
                            <span className="fr-kpi-unit"> km</span>
                        </div>
                        <div className="fr-kpi-sub">{kpis.groundCoverageNote}</div>
                    </div>
                </div>

                <div className="fr-sec-row">
                    <span className="fr-sec-label">Altitude Profile</span>
                    <div className="fr-sec-rule" />
                </div>
                <div className="fr-card">
                    <div className="fr-card-pad">
                        <div className="fr-card-title">Atmospheric Cross-Section</div>
                        <div className="fr-card-sub">
                            Full altitude profile — GPS-validated ascent, barometric derivation through GPS
                            freeze, confirmed float at ~9,500 m
                        </div>
                        <div className="fr-atm-wrap">
                            <canvas ref={altRef} id="altChart" />
                        </div>
                        <div className="fr-legend">
                            <div className="fr-legend-item">
                                <div className="fr-l-solid" style={{ background: 'var(--fr-accent)' }} />
                                GPS altitude (confirmed)
                            </div>
                            <div className="fr-legend-item">
                                <div
                                    className="fr-l-dash"
                                    style={{ borderColor: 'var(--fr-accent)', opacity: 0.5 }}
                                />
                                Pressure-derived altitude
                            </div>
                            <div className="fr-legend-item">
                                <div
                                    className="fr-l-box"
                                    style={{
                                        background: 'rgba(201,82,31,.08)',
                                        borderColor: 'rgba(201,82,31,.4)',
                                    }}
                                />
                                GPS-frozen phase
                            </div>
                            <div className="fr-legend-item">
                                <div
                                    className="fr-l-box"
                                    style={{
                                        background: 'rgba(80,101,184,.08)',
                                        borderColor: 'rgba(80,101,184,.35)',
                                    }}
                                />
                                Confirmed float
                            </div>
                        </div>
                    </div>
                </div>

                <div className="fr-sec-row" style={{ marginTop: 28 }}>
                    <span className="fr-sec-label">Flight Path &amp; Telemetry</span>
                    <div className="fr-sec-rule" />
                </div>
                <div className="fr-lower-grid">
                    <div className="fr-card">
                        <div className="fr-card-pad" style={{ paddingBottom: 0 }}>
                            <div className="fr-card-title">Flight Path</div>
                            <div className="fr-card-sub" style={{ marginBottom: 10 }}>
                                Confirmed GPS fixes, implied drift during GPS freeze, and post-resume
                                position updates. See the map legend for line styles.
                            </div>
                        </div>
                        <FlightReportMap
                            flight={samples}
                            freezeMin={freezeMin}
                            resumeMin={resumeMin}
                        />
                    </div>
                    <div className="fr-small-col">
                        <div className="fr-card fr-card-pad" style={{ paddingBottom: 16 }}>
                            <div className="fr-card-title" style={{ fontSize: 15 }}>
                                Temperature
                            </div>
                            <div className="fr-card-sub" style={{ marginBottom: 10 }}>
                                Degrees C vs time from launch
                            </div>
                            <div className="fr-sm-wrap">
                                <canvas ref={tempRef} id="tempChart" />
                            </div>
                        </div>
                        <div className="fr-card fr-card-pad" style={{ paddingBottom: 16 }}>
                            <div className="fr-card-title" style={{ fontSize: 15 }}>
                                Pressure Trace
                            </div>
                            <div className="fr-card-sub" style={{ marginBottom: 10 }}>
                                hPa vs time — float plateau at ~285 hPa
                            </div>
                            <div className="fr-sm-wrap">
                                <canvas ref={pressRef} id="pressChart" />
                            </div>
                        </div>
                    </div>
                </div>

                <div className="fr-sec-row" style={{ marginTop: 28 }}>
                    <span className="fr-sec-label">Mission Timeline</span>
                    <div className="fr-sec-rule" />
                </div>
                <div className="fr-card">
                    <div className="fr-card-pad" style={{ paddingBottom: 0 }}>
                        <div className="fr-timeline-bar">
                            {report.phases.map((ph) => (
                                <div key={ph.id} className={`fr-ph fr-ph-${ph.id}`}>
                                    <div className="fr-ph-name">{ph.name}</div>
                                    <div className="fr-ph-time">{ph.timeRange}</div>
                                    <div className="fr-ph-detail">{ph.detail}</div>
                                </div>
                            ))}
                        </div>
                        <div className="fr-chips">
                            {report.chips.map((chip) => (
                                <div key={chip.text} className={`fr-chip fr-chip-${chip.variant}`}>
                                    {chip.text}
                                </div>
                            ))}
                        </div>
                    </div>
                </div>

                <footer className="fr-footer">
                    <div className="fr-footer-text">{report.footerLine1}</div>
                    <div className="fr-footer-text">{report.footerLine2}</div>
                </footer>
            </div>
        </div>
    );
}
