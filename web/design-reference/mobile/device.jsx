// Mobile Screen 2: Device detail
function MDevice() {
  const latest = MT[MT.length - 1];
  return (
    <div style={{ width: 402, height: 874, background: 'var(--bg)', color: 'var(--text)', fontFamily: 'var(--sans)', overflow: 'hidden', display: 'flex', flexDirection: 'column', position: 'relative' }} data-screen-label="02 Device">
      <MHeader
        back
        sub="DEVICE"
        title="stratolink-3"
        right={<span className="pill teal" style={{ fontSize: 9 }}>TRACKING</span>}
      />

      <div style={{ flex: 1, overflow: 'auto', paddingBottom: 88 }}>
        {/* Stat grid */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', borderBottom: '1px solid var(--border)' }}>
          <div style={{ padding: '20px 18px', borderRight: '1px solid var(--border)', borderBottom: '1px solid var(--border)' }}>
            <div style={{ fontFamily: 'var(--sans)', fontSize: 9, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--text-dim2)', fontWeight: 500, marginBottom: 8 }}>Altitude</div>
            <div style={{ fontFamily: 'var(--mono)', fontSize: 26, fontWeight: 500, color: 'var(--text-hi)', lineHeight: 1, fontVariantNumeric: 'tabular-nums' }}>{MLAST.alt !== null ? MLAST.alt : '—'}<span style={{ fontSize: 12, color: 'var(--text-dim3)', marginLeft: 4 }}>m</span></div>
            <div style={{ marginTop: 8 }}><MAge t={MLAST_FIX_T} compact dot={true} /></div>
          </div>
          <div style={{ padding: '20px 18px', borderBottom: '1px solid var(--border)' }}>
            <div style={{ fontFamily: 'var(--sans)', fontSize: 9, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--text-dim2)', fontWeight: 500, marginBottom: 8 }}>Battery</div>
            <div style={{ fontFamily: 'var(--mono)', fontSize: 26, fontWeight: 500, color: 'var(--text-hi)', lineHeight: 1, fontVariantNumeric: 'tabular-nums' }}>{Mfmt.num(latest.batt, 2)}<span style={{ fontSize: 12, color: 'var(--text-dim3)', marginLeft: 4 }}>V</span></div>
            <div style={{ marginTop: 8 }}><MAge t={MFRESHNESS.battery} compact dot={true} /></div>
          </div>
          <div style={{ padding: '20px 18px', borderRight: '1px solid var(--border)' }}>
            <div style={{ fontFamily: 'var(--sans)', fontSize: 9, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--text-dim2)', fontWeight: 500, marginBottom: 8 }}>Signal</div>
            <div style={{ fontFamily: 'var(--mono)', fontSize: 26, fontWeight: 500, color: 'var(--text-hi)', lineHeight: 1, fontVariantNumeric: 'tabular-nums' }}>{latest.rssi}<span style={{ fontSize: 12, color: 'var(--text-dim3)', marginLeft: 4 }}>dBm</span></div>
            <div style={{ marginTop: 8 }}><MAge t={MFRESHNESS.rssi} compact dot={true} /></div>
          </div>
          <div style={{ padding: '20px 18px' }}>
            <div style={{ fontFamily: 'var(--sans)', fontSize: 9, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--text-dim2)', fontWeight: 500, marginBottom: 8 }}>GPS Sats</div>
            <div style={{ fontFamily: 'var(--mono)', fontSize: 26, fontWeight: 500, color: MLAST.sats > 0 ? 'var(--text-hi)' : 'var(--alert)', lineHeight: 1, fontVariantNumeric: 'tabular-nums' }}>{MLAST.sats !== null ? MLAST.sats : '—'}<span style={{ fontSize: 12, color: 'var(--text-dim3)', marginLeft: 4 }}>/ 24</span></div>
            <div style={{ marginTop: 8 }}><MAge t={MLAST_FIX_T} compact dot={true} /></div>
          </div>
        </div>

        <MSectionLabel right={<span style={{ fontFamily: 'var(--sans)', fontSize: 10, color: 'var(--ok)', letterSpacing: '0.08em' }}>OPEN FULL MAP →</span>}>POSITION</MSectionLabel>
        <div style={{ position: 'relative', borderTop: '1px solid var(--border)', borderBottom: '1px solid var(--border)' }}>
          <MMapMini width={402} height={200} />
          <div style={{ position: 'absolute', bottom: 12, left: 16, fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-hi)', textShadow: '0 0 4px rgba(0,0,0,0.8)' }}>
            37.778467° N, −122.397934° W
          </div>
        </div>

        <MSectionLabel right={<span style={{ fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--text-dim2)' }}>last 7h 42m</span>}>TELEMETRY</MSectionLabel>
        <MMetricChart title="Battery" value={Mfmt.num(latest.batt, 2)} unit="V" color="var(--ok-mute)" data={MT} getY={r => r.batt} min={3.2} max={5.6} />
        <MMetricChart title="Temperature" value={Mfmt.num(latest.temp, 1)} unit="°C" color="var(--ok-mute)" data={MT} getY={r => r.temp} />
        <MMetricChart title="Solar" value={Mfmt.num(latest.sol, 2)} unit="V" color="var(--ok-mute)" data={MT} getY={r => r.sol} min={0} max={6} />

        <MSectionLabel>DATA FRESHNESS</MSectionLabel>
        <div style={{ paddingLeft: 20, paddingRight: 20 }}>
          {[
            ['Position', MFRESHNESS.position],
            ['Altitude', MFRESHNESS.altitude],
            ['Battery', MFRESHNESS.battery],
            ['Temperature', MFRESHNESS.temperature],
            ['RSSI / SNR', MFRESHNESS.rssi],
          ].map(([label, t]) => (
            <div key={label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 0', borderBottom: '1px solid var(--divider)', fontFamily: 'var(--sans)', fontSize: 12 }}>
              <span style={{ color: 'var(--text-dim)' }}>{label}</span>
              <MAge t={t} compact dot={true} />
            </div>
          ))}
        </div>
      </div>

      <MTabBar active="fleet" />
    </div>
  );
}

window.MDevice = MDevice;
