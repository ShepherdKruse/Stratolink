import { useEffect, useId, useRef, useState, type FormEvent } from 'react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faCircleInfo, faPlus, faXmark } from '@fortawesome/free-solid-svg-icons';
import type { BalloonSettings, RadioRegion, RegisteredBalloon, TTNCluster } from '@/lib/community/types';

export const radioRegions: { value: RadioRegion; label: string; cluster: TTNCluster }[] = [
    { value: 'northAmerica', label: 'North America', cluster: 'nam1' },
    { value: 'europe', label: 'Europe', cluster: 'eu1' },
    { value: 'asia', label: 'Asia', cluster: 'eu1' },
    { value: 'australia', label: 'Australia', cluster: 'au1' },
];

export function FieldTip({ label, children }: { label: string; children: string }) {
    return <span className="field-tip" role="img" tabIndex={0} onClick={event => { event.preventDefault(); event.currentTarget.focus(); }} aria-label={`${label}: ${children}`}><FontAwesomeIcon icon={faCircleInfo} /><span role="tooltip">{children}</span></span>;
}

export function savedRegionalEuis(balloon: RegisteredBalloon): BalloonSettings['regionalEuis'] {
    const saved = { ...balloon.regionalEuis };
    for (const connection of balloon.connections) {
        const plan = connection.region.toUpperCase();
        const region = plan.startsWith('US') ? 'northAmerica' : plan.startsWith('EU') ? 'europe' : plan.startsWith('AS') ? 'asia' : plan.startsWith('AU') ? 'australia' : null;
        if (region && !saved[region]) saved[region] = connection.devEui;
    }
    return saved;
}

export default function BalloonRegistrationForm({ balloon, busy, onSubmit }: {
    balloon?: RegisteredBalloon;
    busy: boolean;
    onSubmit: (input: BalloonSettings) => Promise<void>;
}) {
    const [radios, setRadios] = useState(() => {
        const saved = balloon ? savedRegionalEuis(balloon) : {};
        const rows = radioRegions.filter(region => saved[region.value]).map(region => ({ region: region.value, eui: saved[region.value]! }));
        return rows.length || balloon ? rows : [{ region: 'northAmerica' as RadioRegion, eui: '' }];
    });
    const [error, setError] = useState('');
    const [saved, setSaved] = useState(false);
    const callsign = useRef<HTMLInputElement>(null);
    const errorId = useId();
    useEffect(() => { if (!balloon) callsign.current?.focus({ preventScroll: true }); }, [balloon]);
    async function submit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault(); setError(''); setSaved(false);
        const data = new FormData(event.currentTarget);
        try {
            await onSubmit({
                callsign: String(data.get('callsign')).trim(),
                plannedLaunchDate: String(data.get('plannedLaunchDate')) || null,
                regionalEuis: Object.fromEntries(radios.map(radio => [radio.region, radio.eui.trim()])),
                shareResearchData: data.get('shareResearchData') === 'on',
            });
            setSaved(true);
        } catch (error) { setError(error instanceof Error ? error.message : 'Unable to save balloon. Please try again.'); }
    }
    return <form className="community-registration-form" onSubmit={submit} onChange={() => setSaved(false)}>
        <fieldset disabled={busy} aria-describedby={error ? errorId : undefined}>
            <label className="community-field">Callsign<input ref={callsign} name="callsign" defaultValue={balloon?.callsign} placeholder="Your balloon’s name" required minLength={2} maxLength={40} pattern="[A-Za-z0-9][A-Za-z0-9 ._\-]{1,39}" autoComplete="off" /></label>
            <label className="community-field"><span>Planned launch <span className="community-optional">Optional</span> <FieldTip label="Planned launch date">An approximate date for the public planned-launch list. You can change or clear it later.</FieldTip></span><input type="date" aria-label="Planned launch date" name="plannedLaunchDate" defaultValue={balloon?.plannedLaunchDate ?? ''} min="2020-01-01" max="2100-12-31" /></label>
            <div className="community-field-heading">Regional DevEUIs <FieldTip label="Regional DevEUIs">Add the regions configured on your payload. Copy each 16-character DevEUI from TTN. If your regions use the same DevEUI, repeat it. You will verify each TTN application after registration.</FieldTip></div>
            <div className="community-radios">{radios.map((radio, index) => <div className="community-radio" key={index}>
                <label className="community-field"><span className="sr-only">Radio region {index + 1}</span><select value={radio.region} onChange={event => setRadios(current => current.map((row, i) => i === index ? { ...row, region: event.target.value as RadioRegion } : row))}>
                    {radioRegions.map(region => <option key={region.value} value={region.value} disabled={radios.some((row, i) => i !== index && row.region === region.value)}>{region.label}</option>)}
                </select></label>
                <label className="community-field"><span className="sr-only">{radioRegions.find(region => region.value === radio.region)?.label} DevEUI</span><input name={`eui-${radio.region}`} value={radio.eui} onChange={event => setRadios(current => current.map((row, i) => i === index ? { ...row, eui: event.target.value } : row))} placeholder="16-character DevEUI" required maxLength={32} autoComplete="off" autoCapitalize="characters" spellCheck={false} /></label>
                <button className="community-remove-radio" type="button" aria-label={`Remove ${radioRegions.find(region => region.value === radio.region)?.label} region`} onClick={() => setRadios(current => current.filter((_, i) => i !== index))}><FontAwesomeIcon icon={faXmark} /></button>
            </div>)}</div>
            {radios.length < radioRegions.length && <button className="community-text-button community-add-radio" type="button" onClick={() => {
                const next = radioRegions.find(region => !radios.some(row => row.region === region.value))!;
                setRadios(current => [...current, { region: next.value, eui: '' }]);
            }}><FontAwesomeIcon icon={faPlus} />Add a region</button>}
            <label className="community-sharing"><input type="checkbox" name="shareResearchData" defaultChecked={balloon ? balloon.shareResearchData === true : true} /><span>Share data with Stratolink research collaborators <FieldTip label="Research sharing">Allow Stratolink to include this balloon’s telemetry in datasets shared with research collaborators. You can change this later.</FieldTip></span></label>
            {!balloon && <p className="community-registration-note">Starts as Planned. Edit your launch date and settings in Your balloons.</p>}
            <div className="community-form-actions"><button className="community-primary" type="submit">{busy ? (balloon ? 'Saving…' : 'Registering…') : balloon ? 'Save changes' : 'Register balloon'}</button>{balloon && saved && <span role="status">Saved</span>}</div>
        </fieldset>
        {error && <p className="community-error" id={errorId} role="alert">{error}</p>}
    </form>;
}
