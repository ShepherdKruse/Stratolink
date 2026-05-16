// Mobile Screen 4: Telemetry — stacked charts
function MTelemetry() {
  const latest = MT[MT.length - 1];
  return (
    <div style={{ width: 402, height: 874, background: 'var(--bg)', color: 'var(--text)', fontFamily: 'var(--sans)', overflow: 'hidden', display: 'flex', flexDirection: 'column', position: 'relative' }} data-screen-label="04 Telemetry">

      <MHeader
        sub="stratolink-3"
        title="Telemetry"
        right={<span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--text-dim)' }}>7h 42m</span>}
      />

      {/* range selector */}
      <div style={{ padding: '12px 20px', display: 'flex', gap: 4, borderBottom: '1px solid var(--border)' }}>
        {['1H', '6H', '12H', 'ALL'].map(r => (
          <div key={r} style={{
            flex: 1, textAlign: 'center', padding: '8px 0',
            border: '1px solid ' + (r === 'ALL' ? 'var(--ok)' : 'var(--border-hi)'),
            background: r === 'ALL' ? 'var(--ok-soft)' : 'transparent',
            color: r === 'ALL' ? 'var(--ok)' : 'var(--text-dim)',
            fontFamily: 'var(--sans)', fontSize: 11, fontWeight: 500, letterSpacing: '0.08em',
          }}>{r}</div>
        ))}
      </div>

      <div style={{ flex: 1, overflow: 'auto', paddingBottom: 88 }}>
        <MMetricChart title="Altitude" value={MLAST.alt !== null ? MLAST.alt : '—'} unit="m" color="var(--ok)" data={MT} getY={r => r.alt} />
        <MMetricChart title="Battery" value={Mfmt.num(latest.batt, 2)} unit="V" color="var(--ok-mute)" data={MT} getY={r => r.batt} min={3.2} max={5.6} />
        <MMetricChart title="Solar" value={Mfmt.num(latest.sol, 2)} unit="V" color="var(--ok-mute)" data={MT} getY={r => r.sol} min={0} max={6} />
        <MMetricChart title="Temperature" value={Mfmt.num(latest.temp, 1)} unit="°C" color="var(--ok-mute)" data={MT} getY={r => r.temp} />
        <MMetricChart title="Ambient lux" value={latest.lux} unit="lx" color="var(--neutral)" data={MT} getY={r => r.lux} />
        <MMetricChart title="RSSI" value={latest.rssi} unit="dBm" color="var(--ok-mute)" data={MT} getY={r => r.rssi} />
        <MMetricChart title="GPS satellites" value={MLAST.sats !== null ? MLAST.sats : '—'} unit="" color="var(--ok-mute)" data={MT} getY={r => r.sats} min={0} max={28} />

        <div style={{ padding: '20px 20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontFamily: 'var(--sans)', fontSize: 11, color: 'var(--text-dim)' }}>
          <span>140 packets · 30 no-fix</span>
          <span style={{ color: 'var(--ok)', letterSpacing: '0.08em', fontWeight: 500 }}>EXPORT CSV →</span>
        </div>
      </div>

      <MTabBar active="telemetry" />
    </div>
  );
}

window.MTelemetry = MTelemetry;
