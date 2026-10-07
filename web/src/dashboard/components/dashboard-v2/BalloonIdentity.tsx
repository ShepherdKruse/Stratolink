import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faGithub } from '@fortawesome/free-brands-svg-icons';
import type { DeviceSummary } from './useTelemetry';
export function OfficialBadge({ official }: { official?: boolean }) {
    return official === true ? <span className="official-badge" title="Operated by Stratolink">Official</span> : null;
}
export function BalloonOwner({ device, link = true }: { link?: boolean; device: Pick<DeviceSummary,'ownerGithub'> }) {
    if (!device.ownerGithub) return null;
    const content = <><FontAwesomeIcon icon={faGithub} aria-hidden /> @{device.ownerGithub}</>;
    return !link ? <span className="balloon-owner">{content}</span> : <a className="balloon-owner" href={`https://github.com/${encodeURIComponent(device.ownerGithub)}`} target="_blank" rel="noreferrer">{content}</a>;
}
