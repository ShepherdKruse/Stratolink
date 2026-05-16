// Mobile components — single-column, larger type, tap-friendly
// Reuses --ok, --alert, --bg tokens from styles.css and the global TELEMETRY data

const MT = window.TELEMETRY || [];
const MD = window.DEVICE_INFO || {};
const Mfmt = window.fmt;
const MFRESHNESS = window.FRESHNESS;
const MNOW = window.NOW;
const MLAST_FIX_T = window.LAST_FIX_T;
const MLAST = window.LAST;             // last-known non-null GPS values
const MAge = window.Age;
const Mstaleness = window.staleness;

// ─────────────────────────────────────────
// Header bar — sits below status bar / dynamic island
// ─────────────────────────────────────────
function MHeader({ title, sub, back, right, dense }) {
  return (
    <div style={{
      paddingTop: 56, paddingBottom: dense ? 12 : 18,
      paddingLeft: 20, paddingRight: 20,
      borderBottom: '1px solid var(--border)',
      background: 'var(--bg)',
      display: 'flex', alignItems: 'center', gap: 14, flexShrink: 0,
    }}>
      {back && (
        <div style={{ width: 32, height: 32, marginLeft: -8, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M 13 4 L 6 10 L 13 16" stroke="var(--text)" strokeWidth="1.5" />
          </svg>
        </div>
      )}
      <div style={{ flex: 1, minWidth: 0 }}>
        {sub && <div style={{ fontFamily: 'var(--sans)', fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--text-dim2)', fontWeight: 500, marginBottom: 2 }}>{sub}</div>}
        <div style={{ fontFamily: 'var(--sans)', fontSize: dense ? 16 : 18, color: 'var(--text-hi)', fontWeight: 500, letterSpacing: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{title}</div>
      </div>
      {right}
    </div>
  );
}

// ─────────────────────────────────────────
// Bottom tab bar — 5 tabs
// ─────────────────────────────────────────
function MTabBar({ active }) {
  const tabs = [
    { id: 'fleet',     label: 'Fleet',     icon: IconFleet },
    { id: 'map',       label: 'Map',       icon: IconMap },
    { id: 'telemetry', label: 'Telemetry', icon: IconChart },
    { id: 'alerts',    label: 'Alerts',    icon: IconAlert, badge: 2 },
    { id: 'more',      label: 'More',      icon: IconMore },
  ];
  return (
    <div style={{
      position: 'absolute', bottom: 0, left: 0, right: 0,
      paddingBottom: 34, paddingTop: 8,
      borderTop: '1px solid var(--border)',
      background: 'rgba(11, 14, 19, 0.94)',
      backdropFilter: 'blur(20px)',
      WebkitBackdropFilter: 'blur(20px)',
      display: 'flex',
      zIndex: 50,
    }}>
      {tabs.map(t => {
        const isActive = t.id === active;
        const Icon = t.icon;
        return (
          <div key={t.id} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, padding: '4px 0', position: 'relative' }}>
            <div style={{ position: 'relative' }}>
              <Icon color={isActive ? 'var(--ok)' : 'var(--text-dim2)'} />
              {t.badge && (
                <div style={{ position: 'absolute', top: -2, right: -6, minWidth: 14, height: 14, padding: '0 4px', background: 'var(--alert)', color: '#0b0e13', fontSize: 9, fontFamily: 'var(--sans)', fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: 7 }}>
                  {t.badge}
                </div>
              )}
            </div>
            <span style={{ fontFamily: 'var(--sans)', fontSize: 9, letterSpacing: '0.08em', textTransform: 'uppercase', fontWeight: 500, color: isActive ? 'var(--ok)' : 'var(--text-dim2)' }}>
              {t.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// tab icons (flat, single stroke)
function IconFleet({ color }) {
  return (
    <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
      <rect x="3" y="4" width="16" height="2" fill={color} />
      <rect x="3" y="10" width="16" height="2" fill={color} />
      <rect x="3" y="16" width="16" height="2" fill={color} />
    </svg>
  );
}
function IconMap({ color }) {
  return (
    <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
      <path d="M 4 6 L 8 4 L 14 6 L 18 4 L 18 16 L 14 18 L 8 16 L 4 18 Z" stroke={color} strokeWidth="1.5" fill="none" />
      <line x1="8" y1="4" x2="8" y2="16" stroke={color} strokeWidth="1.5" />
      <line x1="14" y1="6" x2="14" y2="18" stroke={color} strokeWidth="1.5" />
    </svg>
  );
}
function IconChart({ color }) {
  return (
    <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
      <rect x="3" y="13" width="3" height="6" fill={color} />
      <rect x="9" y="8" width="3" height="11" fill={color} />
      <rect x="15" y="3" width="3" height="16" fill={color} />
    </svg>
  );
}
function IconAlert({ color }) {
  return (
    <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
      <path d="M 11 3 L 19 18 L 3 18 Z" stroke={color} strokeWidth="1.5" fill="none" />
      <rect x="10" y="9" width="2" height="5" fill={color} />
      <rect x="10" y="15" width="2" height="2" fill={color} />
    </svg>
  );
}
function IconMore({ color }) {
  return (
    <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
      <rect x="4" y="10" width="3" height="3" fill={color} />
      <rect x="10" y="10" width="3" height="3" fill={color} />
      <rect x="16" y="10" width="3" height="3" fill={color} />
    </svg>
  );
}

// ─────────────────────────────────────────
// Stat card — label + big value + small subtitle
// ─────────────────────────────────────────
function MStat({ label, value, unit, sub, accent, t }) {
  return (
    <div style={{ padding: '14px 16px', border: '1px solid var(--border)' }}>
      <div style={{ fontFamily: 'var(--sans)', fontSize: 9, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--text-dim2)', fontWeight: 500, marginBottom: 8 }}>{label}</div>
      <div style={{ fontFamily: 'var(--mono)', fontSize: 22, fontWeight: 500, color: accent ? `var(--${accent})` : 'var(--text-hi)', lineHeight: 1, fontVariantNumeric: 'tabular-nums' }}>
        {value}{unit && <span style={{ fontSize: 11, color: 'var(--text-dim3)', marginLeft: 3 }}>{unit}</span>}
      </div>
      {t !== undefined ? (
        <div style={{ marginTop: 8 }}><MAge t={t} compact dot={true} /></div>
      ) : sub ? (
        <div style={{ fontFamily: 'var(--sans)', fontSize: 10, color: 'var(--text-dim2)', marginTop: 8 }}>{sub}</div>
      ) : null}
    </div>
  );
}

// ─────────────────────────────────────────
// Fleet device card — single tappable row
// ─────────────────────────────────────────
function MDeviceCard({ id, status, statusColor, alt, batt, rssi, lastT, primary }) {
  return (
    <div style={{
      padding: '16px 20px',
      borderBottom: '1px solid var(--border)',
      background: primary ? 'var(--ok-soft)' : 'transparent',
      borderLeft: primary ? '2px solid var(--ok)' : '2px solid transparent',
      position: 'relative',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <div style={{ fontFamily: 'var(--mono)', fontSize: 14, fontWeight: 500, color: 'var(--text-hi)' }}>{id}</div>
        <span className={"pill " + (statusColor || 'teal')} style={{ fontSize: 9 }}>{status}</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 10 }}>
        <MKV k="ALT" v={alt} />
        <MKV k="BATT" v={batt} />
        <MKV k="RSSI" v={rssi} />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 10 }}>
        <MAge t={lastT} compact dot={true} prefix="last" />
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none" style={{ opacity: 0.4 }}>
          <path d="M 5 3 L 9 7 L 5 11" stroke="var(--text-dim)" strokeWidth="1.5" />
        </svg>
      </div>
    </div>
  );
}

function MKV({ k, v }) {
  return (
    <div>
      <div style={{ fontFamily: 'var(--sans)', fontSize: 9, letterSpacing: '0.12em', color: 'var(--text-dim2)', textTransform: 'uppercase', marginBottom: 3, fontWeight: 500 }}>{k}</div>
      <div style={{ fontFamily: 'var(--mono)', fontSize: 13, color: 'var(--text)', fontVariantNumeric: 'tabular-nums', fontWeight: 500 }}>{v}</div>
    </div>
  );
}

// ─────────────────────────────────────────
// Mini chart row for telemetry list
// ─────────────────────────────────────────
function MMetricChart({ title, value, unit, color, data, getY, min, max }) {
  const W = 360, H = 60;
  const padL = 0, padR = 0, padT = 4, padB = 4;
  const valid = data.map(getY).filter(v => v !== null && !isNaN(v));
  if (!valid.length) return null;
  const lo = min !== undefined ? min : Math.min(...valid);
  const hi = max !== undefined ? max : Math.max(...valid);
  const r = hi - lo || 1;
  const t0 = data[0].t, t1 = data[data.length - 1].t, span = t1 - t0 || 1;
  const xOf = (t) => padL + ((t - t0) / span) * (W - padL - padR);
  const yOf = (v) => padT + (H - padT - padB) - ((v - lo) / r) * (H - padT - padB);

  let d = '', started = false;
  data.forEach(row => {
    const v = getY(row);
    if (v === null || isNaN(v)) { started = false; return; }
    d += (started ? 'L' : 'M') + xOf(row.t).toFixed(1) + ' ' + yOf(v).toFixed(1) + ' ';
    started = true;
  });

  return (
    <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 8 }}>
        <div style={{ fontFamily: 'var(--sans)', fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--text-dim)', fontWeight: 500 }}>{title}</div>
        <div style={{ fontFamily: 'var(--mono)', fontSize: 16, color: 'var(--text-hi)', fontVariantNumeric: 'tabular-nums', fontWeight: 500 }}>
          {value}<span style={{ fontSize: 10, color: 'var(--text-dim3)', marginLeft: 3 }}>{unit}</span>
        </div>
      </div>
      <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ display: 'block' }}>
        <path d={d} stroke={color || 'var(--ok-mute)'} strokeWidth="1.4" fill="none" vectorEffect="non-scaling-stroke" />
      </svg>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, color: 'var(--text-dim3)', fontFamily: 'var(--mono)', marginTop: 4 }}>
        <span>{lo.toFixed(lo < 10 && Math.abs(lo) < 100 ? 1 : 0)}</span>
        <span>{hi.toFixed(hi < 10 && Math.abs(hi) < 100 ? 1 : 0)}</span>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────
// Mobile map snippet — small map with marker
// ─────────────────────────────────────────
function MMapMini({ width = 360, height = 180, focus, track }) {
  return (
    <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="xMidYMid slice" style={{ display: 'block', background: 'var(--bg-1)' }}>
      {/* grid */}
      {Array.from({ length: 8 }, (_, i) => (
        <line key={'v'+i} x1={(i/8)*width} y1="0" x2={(i/8)*width} y2={height} stroke="var(--grid)" />
      ))}
      {Array.from({ length: 4 }, (_, i) => (
        <line key={'h'+i} x1="0" y1={(i/4)*height} x2={width} y2={(i/4)*height} stroke="var(--grid)" />
      ))}
      {/* abstract landmass squiggle */}
      <path d={`M 0 ${height*0.6} Q ${width*0.2} ${height*0.5}, ${width*0.4} ${height*0.55} T ${width} ${height*0.7}`} stroke="var(--border-hi)" fill="none" />
      {/* focus marker */}
      <g transform={`translate(${width/2}, ${height/2})`}>
        <line x1="-14" y1="0" x2="-6" y2="0" stroke="var(--ok)" strokeWidth="1.2" />
        <line x1="6" y1="0" x2="14" y2="0" stroke="var(--ok)" strokeWidth="1.2" />
        <line x1="0" y1="-14" x2="0" y2="-6" stroke="var(--ok)" strokeWidth="1.2" />
        <line x1="0" y1="6" x2="0" y2="14" stroke="var(--ok)" strokeWidth="1.2" />
        <rect x="-3" y="-3" width="6" height="6" fill="var(--ok)" />
      </g>
    </svg>
  );
}

// ─────────────────────────────────────────
// Section header — small dim label above a group
// ─────────────────────────────────────────
function MSectionLabel({ children, right }) {
  return (
    <div style={{ padding: '24px 20px 10px', display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
      <div style={{ fontFamily: 'var(--sans)', fontSize: 10, letterSpacing: '0.16em', textTransform: 'uppercase', color: 'var(--text-dim2)', fontWeight: 500 }}>{children}</div>
      {right}
    </div>
  );
}

Object.assign(window, {
  MHeader, MTabBar, MStat, MDeviceCard, MKV, MMetricChart, MMapMini, MSectionLabel,
});
