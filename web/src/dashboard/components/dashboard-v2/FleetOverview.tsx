import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faChevronRight, faCircle } from '@fortawesome/free-solid-svg-icons';
import type { DeviceSummary } from './useTelemetry';
import type { TelemetryRow } from './atoms';
import { OfficialBadge, BalloonOwner } from './BalloonIdentity';
import { registeredStatus } from '@/lib/telemetry/fleetFilters';
import { balloonName, rowAtTime } from '@/lib/telemetry/fleetPlayback';

export const BALLOON_COLORS = ['#a23a2d', '#476f83', '#7a7650', '#806682'];
export const balloonColor = (id: string) => BALLOON_COLORS[id === 'stratolink-2' ? 0 : id === 'stratolink-3' ? 1 : [...id].reduce((sum,c) => sum+c.charCodeAt(0),0) % BALLOON_COLORS.length];
export const balloonTransitionName = (id: string) => `balloon-${id.replace(/[^a-zA-Z0-9_-]/g, '-')}`;

export default function FleetOverview({ devices, rowsByDevice, loading, error, scrubT, onSelect }: {
    devices: DeviceSummary[];
    rowsByDevice: Record<string, TelemetryRow[]>;
    loading: boolean;
    error: string | null;
    scrubT: number | null;
    onSelect: (id: string, animate?: boolean) => void;
}) {
    return (
        <div className="fleet-cards tlm-scroll" aria-label="Balloons">
            {devices.map((device) => {
                const rows = rowsByDevice[device.id] ?? [];
                const row = rowAtTime(rows, scrubT);
                const latest = rows.at(-1);
                const waiting = loading && !(device.id in rowsByDevice);
                const beforeFlight = scrubT !== null && rows.length > 0 && scrubT < rows[0].t;
                const awaitingFlightData = latest && device.launchedAt != null && latest.t < device.launchedAt;
                const status = registeredStatus(device.status) ?? (waiting ? 'Loading telemetry' : beforeFlight ? 'No data yet' : !row ? 'No telemetry' : awaitingFlightData ? 'Missing' : scrubT !== null ? 'Recorded telemetry' : device.status === 'landed' || device.status === 'recovered'
                    ? 'Landed' : latest && Date.now() - latest.t < 15 * 60_000 ? 'Transmitting' : 'No recent signal');
                const altitudeRow = row ? rows.filter(sample => sample.t <= row.t && (sample.presAlt != null || sample.alt != null)).at(-1) : null;
                const altitude = altitudeRow?.presAlt ?? altitudeRow?.alt;
                const metrics = [
                    { label: 'Altitude', value: altitude != null ? Math.round(altitude).toLocaleString('en-US') : '-', unit: altitude != null ? 'm' : '' },
                    { label: 'Storage', value: row?.batt != null ? row.batt.toFixed(2) : '-', unit: row?.batt != null ? 'V' : '' },
                    { label: 'Temperature', value: row?.temp != null ? row.temp.toFixed(1) : '-', unit: row?.temp != null ? '°C' : '' },
                    { label: 'RSSI', value: row?.rssi != null ? Math.round(row.rssi) : '-', unit: row?.rssi != null ? 'dBm' : '' },
                ];
                return (
                    <button type="button" className="balloon-card" key={device.id}
                        style={{ viewTransitionName: balloonTransitionName(device.id) }}
                        onClick={event => onSelect(device.id, event.detail !== 0)} aria-label={`Monitor ${balloonName(device)}`}>
                        <span className="balloon-card-heading">
                            <span className="balloon-card-name"><span className="balloon-card-title">{balloonName(device)}</span><OfficialBadge official={device.official} /></span>
                            <FontAwesomeIcon icon={faChevronRight} className="balloon-card-chevron" />
                        </span>
                        {device.ownerGithub && <BalloonOwner device={device} link={false} />}
                        <span className="balloon-card-status">
                            <FontAwesomeIcon icon={faCircle} style={{ color: balloonColor(device.id) }} />
                            {status}
                        </span>
                        <span className="balloon-card-metrics">
                            {metrics.map(metric => <span key={metric.label}><span className="balloon-card-label">{metric.label}</span><strong>{metric.value}<small>{metric.unit}</small></strong></span>)}
                        </span>
                    </button>
                );
            })}
            {devices.length === 0 && <p className="fleet-message">{loading ? 'Loading balloons' : 'No balloons match these filters.'}</p>}
            {error && <p className="fleet-message" role="status">Some telemetry could not be loaded. Retrying shortly.</p>}
        </div>
    );
}
