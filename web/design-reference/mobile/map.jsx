// Mobile Screen 3: Live map — fullscreen map with bottom sheet
function MMap() {
  const latest = MT[MT.length - 1];
  return (
    <div style={{ width: 402, height: 874, background: 'var(--bg)', color: 'var(--text)', fontFamily: 'var(--sans)', overflow: 'hidden', display: 'flex', flexDirection: 'column', position: 'relative' }} data-screen-label="03 Map">

      {/* Full map */}
      <div style={{ position: 'absolute', inset: 0 }}>
        <svg width="402" height="874" viewBox="0 0 402 874" preserveAspectRatio="xMidYMid slice" style={{ display: 'block' }}>
          <rect width="402" height="874" fill="var(--bg-1)" />
          {/* grid */}
          {Array.from({ length: 12 }, (_, i) => (
            <line key={'v'+i} x1={(i/12)*402} y1="0" x2={(i/12)*402} y2="874" stroke="var(--grid)" />
          ))}
          {Array.from({ length: 20 }, (_, i) => (
            <line key={'h'+i} x1="0" y1={(i/20)*874} x2="402" y2={(i/20)*874} stroke="var(--grid)" />
          ))}
          {/* abstract terrain */}
          <path d="M -10 600 Q 80 580, 160 590 T 320 580 T 410 605" stroke="var(--border-hi)" fill="none" />
          <path d="M -10 720 Q 80 710, 160 720 T 320 710 T 410 740" stroke="var(--border-hi)" fill="none" />

          {/* concentric range rings around device */}
          {[60, 120, 180, 240].map(r => (
            <circle key={r} cx="201" cy="400" r={r} fill="none" stroke="var(--ok)" strokeOpacity="0.08" strokeDasharray="3 5" />
          ))}

          {/* device track (simple loop) */}
          <path d="M 190 480 Q 200 460, 210 420 T 215 380 Q 210 360, 205 340" stroke="var(--ok-mute)" strokeWidth="1.5" fill="none" />

          {/* focus marker */}
          <g transform="translate(201, 400)">
            <line x1="-20" y1="0" x2="-8" y2="0" stroke="var(--ok)" strokeWidth="1.2" />
            <line x1="8" y1="0" x2="20" y2="0" stroke="var(--ok)" strokeWidth="1.2" />
            <line x1="0" y1="-20" x2="0" y2="-8" stroke="var(--ok)" strokeWidth="1.2" />
            <line x1="0" y1="8" x2="0" y2="20" stroke="var(--ok)" strokeWidth="1.2" />
            <rect x="-4" y="-4" width="8" height="8" fill="var(--ok)" />
          </g>
          <text x="218" y="395" fontFamily="var(--mono)" fontSize="10" fill="var(--ok)" style={{ letterSpacing: '0.04em' }}>stratolink-3</text>

          {/* secondary marker - landed device */}
          <g transform="translate(310, 520)">
            <rect x="-3" y="-3" width="6" height="6" fill="var(--text-dim2)" />
          </g>
          <text x="318" y="525" fontFamily="var(--mono)" fontSize="9" fill="var(--text-dim)">stratolink-1</text>
        </svg>
      </div>

      {/* top floating header */}
      <div style={{ position: 'absolute', top: 56, left: 16, right: 16, display: 'flex', gap: 10, alignItems: 'center', zIndex: 20 }}>
        <div style={{ flex: 1, padding: '12px 16px', background: 'rgba(11, 14, 19, 0.78)', backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)', border: '1px solid var(--border-hi)', display: 'flex', alignItems: 'center', gap: 10 }}>
          <span className="dot teal" style={{ width: 7, height: 7 }} />
          <div style={{ flex: 1 }}>
            <div style={{ fontFamily: 'var(--mono)', fontSize: 13, color: 'var(--text-hi)', fontWeight: 500 }}>stratolink-3</div>
            <div style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--text-dim2)' }}>37.7785° N, −122.3979° W</div>
          </div>
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M 4 5 L 7 9 L 10 5" stroke="var(--text-dim)" strokeWidth="1.5" />
          </svg>
        </div>
        <div style={{ width: 44, height: 44, background: 'rgba(11, 14, 19, 0.78)', backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)', border: '1px solid var(--border-hi)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <rect x="2" y="2" width="14" height="14" stroke="var(--text-dim)" strokeWidth="1.5" fill="none" />
            <line x1="2" y1="9" x2="16" y2="9" stroke="var(--text-dim)" strokeWidth="1.5" />
            <line x1="9" y1="2" x2="9" y2="16" stroke="var(--text-dim)" strokeWidth="1.5" />
          </svg>
        </div>
      </div>

      {/* right side floating buttons */}
      <div style={{ position: 'absolute', right: 16, top: 200, display: 'flex', flexDirection: 'column', gap: 8, zIndex: 20 }}>
        <div style={{ width: 44, height: 44, background: 'rgba(11, 14, 19, 0.78)', backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)', border: '1px solid var(--border-hi)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><line x1="9" y1="3" x2="9" y2="15" stroke="var(--text)" strokeWidth="1.5" /><line x1="3" y1="9" x2="15" y2="9" stroke="var(--text)" strokeWidth="1.5" /></svg>
        </div>
        <div style={{ width: 44, height: 44, background: 'rgba(11, 14, 19, 0.78)', backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)', border: '1px solid var(--border-hi)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><line x1="3" y1="9" x2="15" y2="9" stroke="var(--text)" strokeWidth="1.5" /></svg>
        </div>
        <div style={{ width: 44, height: 44, background: 'rgba(11, 14, 19, 0.78)', backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)', border: '1px solid var(--border-hi)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
              <circle cx="9" cy="9" r="3" fill="var(--ok)" />
              <line x1="9" y1="2" x2="9" y2="5" stroke="var(--text)" strokeWidth="1.5" />
              <line x1="9" y1="13" x2="9" y2="16" stroke="var(--text)" strokeWidth="1.5" />
              <line x1="2" y1="9" x2="5" y2="9" stroke="var(--text)" strokeWidth="1.5" />
              <line x1="13" y1="9" x2="16" y2="9" stroke="var(--text)" strokeWidth="1.5" />
            </svg>
        </div>
      </div>

      {/* bottom sheet with vitals */}
      <div style={{
        position: 'absolute', left: 0, right: 0, bottom: 80,
        background: 'rgba(11, 14, 19, 0.88)',
        backdropFilter: 'blur(24px)', WebkitBackdropFilter: 'blur(24px)',
        borderTop: '1px solid var(--border-hi)',
        zIndex: 30,
      }}>
        {/* drag handle */}
        <div style={{ display: 'flex', justifyContent: 'center', padding: '8px 0 4px' }}>
          <div style={{ width: 36, height: 4, background: 'var(--text-dim3)', borderRadius: 2 }} />
        </div>
        <div style={{ padding: '8px 20px 16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 12 }}>
            <span style={{ fontFamily: 'var(--sans)', fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--text-dim2)', fontWeight: 500 }}>LIVE VITALS</span>
            <MAge t={MFRESHNESS.packet} compact dot={true} />
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
            <div>
              <div style={{ fontFamily: 'var(--sans)', fontSize: 9, color: 'var(--text-dim2)', letterSpacing: '0.10em', textTransform: 'uppercase' }}>Alt</div>
              <div style={{ fontFamily: 'var(--mono)', fontSize: 15, color: 'var(--text-hi)', fontWeight: 500, marginTop: 4 }}>{MLAST.alt !== null ? MLAST.alt : '—'}<span style={{ fontSize: 10, color: 'var(--text-dim3)', marginLeft: 2 }}>m</span></div>
            </div>
            <div>
              <div style={{ fontFamily: 'var(--sans)', fontSize: 9, color: 'var(--text-dim2)', letterSpacing: '0.10em', textTransform: 'uppercase' }}>Batt</div>
              <div style={{ fontFamily: 'var(--mono)', fontSize: 15, color: 'var(--text-hi)', fontWeight: 500, marginTop: 4 }}>{Mfmt.num(latest.batt, 2)}<span style={{ fontSize: 10, color: 'var(--text-dim3)', marginLeft: 2 }}>V</span></div>
            </div>
            <div>
              <div style={{ fontFamily: 'var(--sans)', fontSize: 9, color: 'var(--text-dim2)', letterSpacing: '0.10em', textTransform: 'uppercase' }}>RSSI</div>
              <div style={{ fontFamily: 'var(--mono)', fontSize: 15, color: 'var(--text-hi)', fontWeight: 500, marginTop: 4 }}>{latest.rssi}<span style={{ fontSize: 10, color: 'var(--text-dim3)', marginLeft: 2 }}>dBm</span></div>
            </div>
            <div>
              <div style={{ fontFamily: 'var(--sans)', fontSize: 9, color: 'var(--text-dim2)', letterSpacing: '0.10em', textTransform: 'uppercase' }}>Sats</div>
              <div style={{ fontFamily: 'var(--mono)', fontSize: 15, color: MLAST.sats > 0 ? 'var(--text-hi)' : 'var(--alert)', fontWeight: 500, marginTop: 4 }}>{MLAST.sats !== null ? MLAST.sats : '—'}</div>
            </div>
          </div>
        </div>
      </div>

      <MTabBar active="map" />
    </div>
  );
}

window.MMap = MMap;
