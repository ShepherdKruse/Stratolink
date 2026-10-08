import { memo } from 'react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faChevronRight, faCircle } from '@fortawesome/free-solid-svg-icons';
import type { DeviceSummary } from './useTelemetry';
import type { TelemetryRow } from './atoms';
import { OfficialBadge, BalloonOwner } from './BalloonIdentity';
import { registeredStatus } from '@/lib/telemetry/fleetFilters';
import { altitudeAtTime, balloonName, rowAtTime } from '@/lib/telemetry/fleetPlayback';

export const BALLOON_COLORS = ['#a23a2d', '#476f83', '#7a7650', '#806682'];
export const balloonColor = (id: string) => BALLOON_COLORS[id === 'stratolink-2' ? 0 : id === 'stratolink-3' ? 1 : [...id].reduce((sum,c) => sum+c.charCodeAt(0),0) % BALLOON_COLORS.length];
export const balloonTransitionName = (id: string) => `balloon-${id.replace(/[^a-zA-Z0-9_-]/g, '-')}`;

export default function FleetOverview({ devices, rowsByDevice, loading, error, scrubT, now, onSelect, transitionId }: {
    devices: DeviceSummary[];
    rowsByDevice: Record<string, TelemetryRow[]>;
    loading: boolean;
    error: string | null;
    scrubT: number | null;
    now: number;
    onSelect: (id: string, animate?: boolean) => void;
    transitionId: string | null;
}) {
    return (
        <div className="fleet-cards tlm-scroll" aria-label="Balloons" style={{ viewTransitionName: 'balloon-list' }}>
            {devices.map(device => <FleetCard key={device.id} device={device}
                rows={rowsByDevice[device.id] ?? EMPTY_ROWS}
                waiting={loading && !(device.id in rowsByDevice)}
                scrubT={scrubT} now={now} onSelect={onSelect} transitioning={device.id === transitionId} />)}
            {devices.length === 0 && <p className="fleet-message">{loading ? 'Loading balloons' : 'No balloons match these filters.'}</p>}
            {error && <p className="fleet-message" role="status">Some telemetry could not be loaded. Retrying shortly.</p>}
        </div>
    );
}

const EMPTY_ROWS: TelemetryRow[] = [];

const FleetCard = memo(function FleetCard({ device, rows, waiting, scrubT, now, onSelect, transitioning }: {
    device: DeviceSummary;
    rows: TelemetryRow[];
    waiting: boolean;
    scrubT: number | null;
    now: number;
    onSelect: (id: string, animate?: boolean) => void;
    transitioning: boolean;
}) {
    const row = rowAtTime(rows, scrubT);
    const latest = rows.at(-1);
    const beforeFlight = scrubT !== null && rows.length > 0 && scrubT < rows[0].t;
    const awaitingFlightData = latest && device.launchedAt != null && latest.t < device.launchedAt;
    const status = registeredStatus(device.status) ?? (waiting ? 'Loading telemetry' : beforeFlight ? 'No data yet' : !row ? 'No telemetry' : awaitingFlightData ? 'Missing' : scrubT !== null ? 'Recorded telemetry' : device.status === 'landed' || device.status === 'recovered'
        ? 'Landed' : latest && now - latest.t < 15 * 60_000 ? 'Transmitting' : 'No recent signal');
    const altitude = row ? altitudeAtTime(rows, row.t) : null;
    const metrics = [
        { label: 'Altitude', value: altitude != null ? Math.round(altitude).toLocaleString('en-US') : '-', unit: altitude != null ? 'm' : '' },
        { label: 'Storage', value: row?.batt != null ? row.batt.toFixed(2) : '-', unit: row?.batt != null ? 'V' : '' },
        { label: 'Temperature', value: row?.temp != null ? row.temp.toFixed(1) : '-', unit: row?.temp != null ? '°C' : '' },
        { label: 'RSSI', value: row?.rssi != null ? Math.round(row.rssi) : '-', unit: row?.rssi != null ? 'dBm' : '' },
    ];
    return (
        <button type="button" className="balloon-card"
            style={{ viewTransitionName: transitioning ? balloonTransitionName(device.id) : undefined }}
            onClick={event => onSelect(device.id, event.detail !== 0)} aria-label={`Monitor ${balloonName(device)}`}>
            <CardHeading device={device} />
            <CardStatus id={device.id} status={status} />
            <span className="balloon-card-metrics">
                {metrics.map(metric => <CardMetric key={metric.label} {...metric} />)}
            </span>
        </button>
    );
});

const CardHeading = memo(function CardHeading({ device }: { device: DeviceSummary }) {
    return <>
        <span className="balloon-card-heading">
            <span className="balloon-card-name"><span className="balloon-card-title">{balloonName(device)}</span><OfficialBadge official={device.official} /></span>
            <FontAwesomeIcon icon={faChevronRight} className="balloon-card-chevron" />
        </span>
        {device.ownerGithub && <BalloonOwner device={device} link={false} />}
    </>;
});

const CardStatus = memo(function CardStatus({ id, status }: { id: string; status: string }) {
    return (
        <span className="balloon-card-status">
            <FontAwesomeIcon icon={faCircle} style={{ color: balloonColor(id) }} />
            {status}
        </span>
    );
});

const CardMetric = memo(function CardMetric({ label, value, unit }: { label: string; value: string | number; unit: string }) {
    return <span><span className="balloon-card-label">{label}</span><strong>{value}<small>{unit}</small></strong></span>;
});
