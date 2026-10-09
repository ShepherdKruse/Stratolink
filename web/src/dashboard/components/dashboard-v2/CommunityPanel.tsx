import { useEffect, useId, useRef, useState, type FormEvent } from 'react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faCheck, faChevronRight, faCopy, faXmark } from '@fortawesome/free-solid-svg-icons';
import { useCommunity } from './community-account';
import { BalloonOwner } from './BalloonIdentity';
import type { ConnectionResponse, RegisteredBalloon, TTNCluster, TTNConnection } from '@/lib/community/types';
import BalloonRegistrationForm, { FieldTip, radioRegions, savedRegionalEuis } from './BalloonRegistrationForm';
import { validClaimToken } from '@/lib/community/onboarding';

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
    const [selectedRegion, setSelectedRegion] = useState('');
    const regionalEuis = savedRegionalEuis(balloon);
    const selectedRadio = radioRegions.find(region => region.value === selectedRegion);
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
            <div><strong>{balloon.callsign}</strong>{balloon.sharedWith?.length ? <div className="community-coowners" aria-label="Shared owners">{balloon.sharedWith.map(login => <BalloonOwner key={login} device={{ownerGithub:login}} />)}</div> : <BalloonOwner device={{ownerGithub:balloon.ownerGithub ?? undefined}} />}{balloon.devEui && <small>{balloon.devEui}</small>}</div>
            <select aria-label={`Status of ${balloon.callsign}`} value={balloon.status} disabled={community.busy} onChange={async event => {
                setError('');
                try { await community.update(balloon.id, event.target.value); }
                catch (error) { setError(error instanceof Error ? error.message : 'Unable to update status.'); }
            }}>
                <option value="planned">Planned</option><option value="flying">Flying</option><option value="landed">Landed</option><option value="missing">Missing</option><option value="retired">Retired</option>
            </select>
        </div>
        <details className="community-connect community-settings">
            <summary><span>Launch and settings</span><FontAwesomeIcon icon={faChevronRight} /></summary>
            <BalloonRegistrationForm balloon={balloon} busy={community.busy} onSubmit={input => community.update(balloon.id, input)} />
        </details>
        {balloon.connections.length > 0 && <ul className="community-connections">{balloon.connections.map(connection => <li key={connection.id}><span>{connection.region || connection.cluster}<small>{connection.applicationId}</small><small className="community-connection-status">{connection.lastReceivedAt ? `Last received ${new Date(connection.lastReceivedAt).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}` : 'Awaiting telemetry'}</small></span>{connection.managedBy === 'stratolink' ? <span className="community-managed-network">Managed by Stratolink</span> : <button className="community-text-button" disabled={community.busy} onClick={() => {
            setReconnecting(connection); setError(''); setWebhook(undefined);
            if (details.current) details.current.open = true;
        }}>Reconnect</button>}</li>)}</ul>}
        <details className="community-connect" ref={details} open={!balloon.connections.length || undefined}>
            <summary><span>{reconnecting ? 'Reconnect TTN' : balloon.connections.length ? 'Add a network' : 'Connect TTN'}</span><FontAwesomeIcon icon={faChevronRight} /></summary>
            {!reconnecting && Object.keys(regionalEuis).length > 0 && <label className="community-field community-saved-region">Saved region<select value={selectedRegion} onChange={event => setSelectedRegion(event.target.value)}><option value="">Choose a region</option>{radioRegions.filter(region => regionalEuis[region.value]).map(region => <option key={region.value} value={region.value}>{region.label}</option>)}</select></label>}
            <form key={reconnecting?.id ?? selectedRegion} onSubmit={connect} autoComplete="off">
                <div className="community-connection-row">
                    <label className="community-field"><span>Cluster <FieldTip label="TTN cluster">Use the cluster shown in your TTN Console URL. The radio region is read from your device settings.</FieldTip></span><select name="cluster" defaultValue={reconnecting?.cluster ?? selectedRadio?.cluster ?? 'nam1'}><option value="nam1">nam1</option><option value="eu1">eu1</option><option value="au1">au1</option></select></label>
                    <label className="community-field">Application ID<input name="applicationId" defaultValue={reconnecting?.applicationId} required maxLength={36} pattern="[a-z0-9](?:[a-z0-9-]*[a-z0-9])?" placeholder="my-balloons" spellCheck={false} autoCapitalize="none" /></label>
                </div>
                <label className="community-field"><span>Device EUI <FieldTip label="Regional device EUI">Use this network’s DevEUI. It can differ from the DevEUI on your other networks.</FieldTip></span><input name="deviceEui" defaultValue={reconnecting?.devEui ?? (selectedRadio ? regionalEuis[selectedRadio.value] : balloon.devEui) ?? ''} required maxLength={32} spellCheck={false} autoCapitalize="characters" /></label>
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
    const claimCode = useRef<HTMLInputElement>(null);
    const [freshProof, setFreshProof] = useState(false);
    const ownsPayload = Boolean(community.user && community.intent && community.balloons.some(balloon => balloon.id === community.intent?.deviceId));
    useEffect(() => { setFreshProof(false); setError(''); }, [community.intent?.deviceId]);
    useEffect(() => { setError(''); }, [community.panel]);
    async function claim(event: FormEvent<HTMLFormElement>) {
        event.preventDefault(); setError('');
        const token = claimCode.current?.value.trim();
        if ((community.intent?.requiresProof || freshProof) && (!token || !validClaimToken(token))) { setError('Enter the claim code supplied with your payload.'); return; }
        if (claimCode.current) claimCode.current.value = '';
        try { await community.claimPayload(token); }
        catch (error) { setFreshProof(true); setError(error instanceof Error ? error.message : 'Unable to claim this payload. Please try again.'); }
    }
    async function reserve(event: FormEvent<HTMLFormElement>) {
        event.preventDefault(); setError('');
        const data = new FormData(event.currentTarget);
        try { await community.reserve(String(data.get('callsign'))); }
        catch (error) { setError(error instanceof Error ? error.message : 'Unable to reserve this callsign.'); }
    }
    return <div className="community-expand" data-open={Boolean(community.panel)} data-panel={community.panel ?? undefined} inert={!community.panel}>
        <div className="community-expand-inner"><section className="community-panel" aria-label={community.panel === 'manage' ? 'Manage balloons' : community.panel === 'activate' ? 'Claim payload' : community.panel === 'reserve' ? 'Reserve a callsign' : 'Register a balloon'}>
            {(community.panel === 'activate' || community.panel === 'reserve') && <div className="community-panel-title"><h2>{community.panel === 'activate' ? 'Claim payload' : 'Reserve a callsign'}</h2><button type="button" className="community-close" aria-label="Cancel onboarding" disabled={community.busy} onClick={() => community.setPanel(null)}><FontAwesomeIcon icon={faXmark} /></button></div>}
            {community.panel === 'activate' && <>
                {community.activationLoading ? <p role="status">Opening payload…</p> : community.intent ? <>
                    <div className="community-payload-id">{community.intent.deviceId}</div>
                    {ownsPayload ? <button className="community-primary" type="button" disabled={community.busy} onClick={() => community.managePayload(community.intent!.deviceId)}>Manage payload</button> : community.account ? <form onSubmit={claim} autoComplete="off">
                        {(community.intent.requiresProof || freshProof) && <label className="community-field"><span>Claim code <FieldTip label="Claim code">Use the current claim code supplied with your payload. An old activation PIN will not work. Contact contact@stratolink.org if you need a new code.</FieldTip></span><input ref={claimCode} type="password" name="claimToken" required minLength={43} maxLength={43} spellCheck={false} autoComplete="off" autoCapitalize="none" /></label>}
                        <button className="community-primary" type="submit" disabled={community.busy}>{community.busy ? 'Claiming…' : 'Claim payload'}</button>
                        <button type="button" className="community-text-button community-cancel-connection" disabled={community.busy} onClick={() => { setError(''); void community.openPayload(''); }}>Change device</button>
                    </form> : <p>Sign in to claim this payload.</p>}
                </> : <form onSubmit={event => { event.preventDefault(); setError(''); void community.openPayload(String(new FormData(event.currentTarget).get('deviceId'))); }}>
                    <div className="community-device-row"><label className="community-field">Device ID<input name="deviceId" required maxLength={80} pattern="[a-zA-Z0-9_-]+" autoCapitalize="none" spellCheck={false} autoComplete="off" placeholder="stratolink-orion" /></label><button className="community-primary" type="submit" disabled={community.busy}>Continue</button></div>
                </form>}
                {(error || community.activationError) && <p className="community-error" role="alert">{error || community.activationError}</p>}
            </>}
            {community.panel === 'reserve' && (community.account ? <form onSubmit={reserve}>
                <div className="community-device-row"><label className="community-field">Callsign<input name="callsign" required minLength={3} maxLength={36} pattern="[a-z0-9](?:-?[a-z0-9]){2,35}" autoComplete="off" autoCapitalize="none" spellCheck={false} placeholder="stratolink-orion" /></label><button type="submit" className="community-primary" disabled={community.busy}>{community.busy ? 'Reserving…' : 'Reserve'}</button></div>
                {error && <p className="community-error" role="alert">{error}</p>}
            </form> : <p>Sign in to reserve a callsign.</p>)}
            {community.panel === 'register' && <BalloonRegistrationForm busy={community.busy} onSubmit={community.register} />}
            {community.panel === 'manage' && <div className="community-managed">
                <div className="community-panel-title"><h2>Your balloons</h2><button className="community-close" aria-label="Close account panel" onClick={() => community.setPanel(null)}><FontAwesomeIcon icon={faXmark} /></button></div>
                {community.balloons.map(balloon => <ManagedBalloon key={balloon.id} balloon={balloon} />)}
                {!community.balloons.length && <p>No balloons registered yet.</p>}
                <button className="community-text-button" disabled={community.busy} onClick={() => community.setPanel('register')}>Register a balloon</button>
            </div>}
        </section></div>
    </div>;
}
