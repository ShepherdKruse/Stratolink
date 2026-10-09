import { useId, useRef, useState, type CSSProperties } from 'react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faChevronDown, faMagnifyingGlass } from '@fortawesome/free-solid-svg-icons';
import { defaultFleetFilters, type FleetFilters as Filters } from '@/lib/telemetry/fleetFilters';
import { useDashboardTheme } from './dashboard-theme';
export default function FleetFilters({ value, onChange, signedIn, count }: { value: Filters; onChange: (value: Filters) => void; signedIn: boolean; count: number }) {
    const id = useId(); const name = useId(); const trigger = useRef<HTMLButtonElement>(null);
    const {theme} = useDashboardTheme();
    const [open, setOpen] = useState(false);
    const [position, setPosition] = useState({top:100,left:180});
    const changed = value.sort !== 'alphabetical' || !value.active || !value.inactive || value.mine || value.planned;
    return <div className="fleet-toolbar">
        <label className="fleet-search"><FontAwesomeIcon icon={faMagnifyingGlass} aria-hidden /><input aria-label="Search balloons" placeholder="Search balloons" value={value.query} onChange={event => onChange({...value,query:event.target.value})} /></label>
        <button ref={trigger} type="button" className="fleet-filter-trigger" popoverTarget={id} aria-expanded={open} aria-controls={id}>Filters{changed && <span className="filter-applied" aria-label="Filters applied" />}<FontAwesomeIcon icon={faChevronDown} /></button>
        <span className="sr-only" role="status">{count} balloons shown</span>
        <div id={id} popover="auto" className="fleet-filter-menu" data-theme={theme} style={{'--filter-top':`${position.top}px`,'--filter-left':`${position.left}px`} as CSSProperties}
            onBeforeToggle={event => { if (event.newState === 'open') { const rect = trigger.current?.getBoundingClientRect(); if (rect) setPosition({top:rect.bottom+8,left:Math.max(12,rect.right-236)}); } }}
            onToggle={event => setOpen(event.newState === 'open')}>
            <fieldset><legend>Sort by</legend>{([['alphabetical','Alphabetical'],['newest','Most recently launched'],['oldest','Earliest launched']] as const).map(([sort,label]) => <label key={sort}>{label}<input type="radio" name={name} checked={value.sort === sort} onChange={() => onChange({...value,sort})} /></label>)}</fieldset>
            <fieldset><legend>Show</legend><label>Active balloons<input type="checkbox" checked={value.active} onChange={event => onChange({...value,active:event.target.checked})} /></label><label>Inactive balloons<input type="checkbox" checked={value.inactive} onChange={event => onChange({...value,inactive:event.target.checked})} /></label>
                <label>Planned balloons<input type="checkbox" checked={value.planned} onChange={event => onChange({...value,planned:event.target.checked})} /></label>
                {signedIn && <label>Only my balloons<input type="checkbox" checked={value.mine} onChange={event => onChange({...value,mine:event.target.checked})} /></label>}
            </fieldset>
            {changed && <button className="community-text-button" onClick={() => onChange({...defaultFleetFilters,query:value.query})}>Reset filters</button>}
        </div>
    </div>;
}
