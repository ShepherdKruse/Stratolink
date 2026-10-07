import { useEffect, useId, useRef, useState, type FormEvent } from 'react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faCheck, faChevronRight, faCircleInfo, faCopy, faXmark } from '@fortawesome/free-solid-svg-icons';
import { useCommunity } from './community-account';
import { BalloonOwner } from './BalloonIdentity';
import type { ConnectionResponse, RegisteredBalloon, TTNCluster, TTNConnection } from '@/lib/community/types';

function FieldTip({ label, children }: { label: string; children: string }) {
    return <span className="field-tip" tabIndex={0} role="img" aria-label={`${label}: ${children}`}><FontAwesomeIcon icon={faCircleInfo} /><span role="tooltip">{children}</span></span>;
}

function CopyValue({ value, label, secret = false }: { value: string; label: string; secret?: boolean }) {
    const [copied, setCopied] = useState(false);
    const [failed, setFailed] = useState(false);
    const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
    useEffect(() => () => clearTimeout(timer.current), []);
    return <label className="community-field">{label}<span className="community-copy-value">
        <input readOnly type={secret ? 'password' : 'text'} value={value} autoComplete="off" spellCheck={false} onFocus={event => event.currentTarget.select()} />
        <button type="button" aria-label={`Copy ${label.toLowerCase()}`} title={copied ? 'Copied' : 'Copy to your clipboard'} onClick={async () => {
            try {
                await navigator.clipboard.writeText(value);
                setCopied(true); setFailed(false);
                clearTimeout(timer.current); timer.current = setTimeout(() => setCopied(false), 1800);
            } catch { setFailed(true); }
        }}><FontAwesomeIcon icon={copied ? faCheck : faCopy} /></button>
    </span>{failed && <span role="status">Select the field to copy it.</span>}</label>;
}

function ManagedBalloon({ balloon }: { balloon: RegisteredBalloon }) {
    const community = useCommunity();
    const [error, setError] = useState('');
    const [webhook, setWebhook] = useState<ConnectionResponse['webhook']>();
    const [reconnecting, setReconnecting] = useState<TTNConnection | null>(null);
    const details = useRef<HTMLDetailsElement>(null);
    const apiKey = useRef<HTMLInputElement>(null);
    const errorId = useId();

    async function connect(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const form = event.currentTarget;
        const data = new FormData(form);
        setError(''); setWebhook(undefined);
        const input = {
            cluster: String(data.get('cluster')) as TTNCluster,
            applicationId: String(data.get('applicationId')).trim(),
            deviceEui: String(data.get('deviceEui')).trim(),
            apiKey: String(data.get('apiKey')).trim(),
        };
        // The key is sent once for verification and is never saved in browser storage.
        if (apiKey.current) apiKey.current.value = '';
        try {
            const result = await community.connect(balloon.id, input);
            setWebhook(result.webhook);
            if (!result.webhook && details.current) details.current.open = false;
        } catch (error) { setError(error instanceof Error ? error.message : 'Unable to connect TTN. Please try again.'); }
    }

    return <div className="managed-balloon">
        <div className="managed-balloon-row">
            <div><strong>{balloon.callsign}</strong><BalloonOwner device={balloon} /><small>{balloon.devEui}</small></div>
            <select aria-label={`Status of ${balloon.callsign}`} value={balloon.status} disabled={community.busy} onChange={async event => {
                setError('');
                try { await community.update(balloon.id, event.target.value); }
                catch (error) { setError(error instanceof Error ? error.message : 'Unable to update status.'); }
            }}>
                <option value="planned">Planned</option><option value="flying">Flying</option><option value="landed">Landed</option><option value="missing">Missing</option><option value="retired">Retired</option>
            </select>
        </div>
        {balloon.connections.length > 0 && <ul className="community-connections">{balloon.connections.map(connection => <li key={connection.id}><span>{connection.region || connection.cluster}<small>{connection.applicationId}</small><small className="community-connection-status">{connection.lastReceivedAt ? `Last received ${new Date(connection.lastReceivedAt).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}` : 'Awaiting telemetry'}</small></span><button className="community-text-button" disabled={community.busy} onClick={() => {
            setReconnecting(connection); setError(''); setWebhook(undefined);
            if (details.current) details.current.open = true;
        }}>Reconnect</button></li>)}</ul>}
        <details className="community-connect" ref={details} open={!balloon.connections.length || undefined}>
            <summary><span>{reconnecting ? 'Reconnect TTN' : balloon.connections.length ? 'Add a network' : 'Connect TTN'}</span><FontAwesomeIcon icon={faChevronRight} /></summary>
            <form key={reconnecting?.id ?? 'new'} onSubmit={connect} autoComplete="off">
                <div className="community-connection-row">
                    <label className="community-field"><span>Cluster <FieldTip label="TTN cluster">Use the cluster shown in your TTN Console URL. The radio region is read from your device settings.</FieldTip></span><select name="cluster" defaultValue={reconnecting?.cluster ?? 'nam1'}><option value="nam1">North America</option><option value="eu1">Europe</option><option value="au1">Australia</option></select></label>
                    <label className="community-field">Application ID<input name="applicationId" defaultValue={reconnecting?.applicationId} required maxLength={36} pattern="[a-z0-9](?:[a-z0-9-]*[a-z0-9])?" placeholder="my-balloons" spellCheck={false} autoCapitalize="none" /></label>
                </div>
                <label className="community-field"><span>Device EUI <FieldTip label="Regional device EUI">Use this network’s DevEUI. It can differ from the DevEUI on your other networks.</FieldTip></span><input name="deviceEui" defaultValue={reconnecting?.devEui ?? balloon.devEui} required maxLength={32} spellCheck={false} autoCapitalize="characters" /></label>
                <label className="community-field"><span>Application API key <FieldTip label="TTN API key">In TTN, open your application, then API keys. Allow reading end devices. The key verifies your device, then is discarded. You will add the webhook in TTN afterward.</FieldTip></span><input ref={apiKey} name="apiKey" type="password" placeholder="NNSXS…" required maxLength={512} autoComplete="off" spellCheck={false} aria-describedby={error ? errorId : undefined} /></label>
                {reconnecting && <p>Replacing the key disconnects the old webhook until you update it in TTN.</p>}
                <button className="community-primary" type="submit" disabled={community.busy}>{community.busy ? 'Connecting…' : reconnecting ? 'Replace webhook key' : 'Connect'}</button>
                {reconnecting && <button className="community-text-button community-cancel-connection" type="button" disabled={community.busy} onClick={() => setReconnecting(null)}>Cancel</button>}
            </form>
        </details>
        {webhook && <div className="community-webhook">
            <p>Add a custom JSON webhook in <a href={`https://${balloon.connections.at(-1)?.cluster ?? 'nam1'}.cloud.thethings.network/console`} target="_blank" rel="noopener noreferrer">TTN</a>. Use this URL, add the Authorization header, and enable uplink messages. Copy the secret now.</p>
            <CopyValue label="Webhook URL" value={webhook.url} />
            <CopyValue label="Authorization header" value={`Bearer ${webhook.secret}`} secret />
            <button className="community-text-button" onClick={() => setWebhook(undefined)}>Done</button>
        </div>}
        {error && <p className="community-error" id={errorId} role="alert">{error}</p>}
    </div>;
}

export default function CommunityPanel() {
    const community = useCommunity();
    const [error, setError] = useState('');
    const callsign = useRef<HTMLInputElement>(null);
    useEffect(() => { setError(''); if (community.panel === 'register') callsign.current?.focus({ preventScroll: true }); }, [community.panel]);
    async function register(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const form = event.currentTarget;
        const data = new FormData(form);
        setError('');
        try { await community.register(String(data.get('callsign')), String(data.get('devEui'))); form.reset(); }
        catch (error) { setError(error instanceof Error ? error.message : 'Check your device details.'); }
    }
    return <div className="community-expand" data-open={Boolean(community.panel)} inert={!community.panel}>
        <div className="community-expand-inner"><section className="community-panel" aria-label={community.panel === 'manage' ? 'Manage balloons' : 'Register a balloon'}>
            {community.panel === 'register' && <form onSubmit={register}>
                <label className="community-field">Callsign<input ref={callsign} name="callsign" placeholder="Your balloon’s name" required minLength={2} maxLength={40} autoComplete="off" /></label>
                <div className="community-device-row">
                    <label className="community-field"><span>Device EUI <FieldTip label="Device EUI">The 16-character device identifier in TTN, under End devices, General settings. You will connect its TTN application after registration.</FieldTip></span><input name="devEui" aria-label="Device EUI" placeholder="70B3D57ED0000000" required maxLength={32} autoComplete="off" spellCheck={false} aria-describedby={error ? 'registration-error' : undefined} /></label>
                    <button className="community-primary" type="submit" disabled={community.busy}>{community.busy ? 'Registering…' : 'Register balloon'}</button>
                </div>
                {error && <p className="community-error" id="registration-error" role="alert">{error}</p>}
            </form>}
            {community.panel === 'manage' && <div className="community-managed">
                <div className="community-panel-title"><h2>Your balloons</h2><button className="community-close" aria-label="Close account panel" onClick={() => community.setPanel(null)}><FontAwesomeIcon icon={faXmark} /></button></div>
                {community.balloons.map(balloon => <ManagedBalloon key={balloon.id} balloon={balloon} />)}
                {!community.balloons.length && <p>No balloons registered yet.</p>}
                <button className="community-text-button" disabled={community.busy} onClick={() => community.setPanel('register')}>Register a balloon</button>
            </div>}
        </section></div>
    </div>;
}
