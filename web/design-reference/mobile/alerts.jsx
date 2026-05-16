// Mobile Screen 5: Alerts — list grouped by recency
function MAlerts() {
  return (
    <div style={{ width: 402, height: 874, background: 'var(--bg)', color: 'var(--text)', fontFamily: 'var(--sans)', overflow: 'hidden', display: 'flex', flexDirection: 'column', position: 'relative' }} data-screen-label="05 Alerts">

      <MHeader
        sub="LAST 24H"
        title="Alerts"
        right={<span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--alert)', fontWeight: 500 }}>2 active</span>}
      />

      <div style={{ flex: 1, overflow: 'auto', paddingBottom: 88 }}>

        <MSectionLabel>ACTIVE</MSectionLabel>
        <AlertRow severity="WARN" device="stratolink-3" title="GPS dropout" message="5 consecutive packets without GPS fix" time="21:48 UTC" age={MNOW - 3 * 60 * 1000} />
        <AlertRow severity="WARN" device="stratolink-2" title="No uplink" message="No telemetry received for 28 minutes" time="21:23 UTC" age={MNOW - 28 * 60 * 1000} />

        <MSectionLabel>RESOLVED · TODAY</MSectionLabel>
        <AlertRow severity="INFO" device="stratolink-3" title="Battery recovery" message="Solar charging restored, V_bat back above 4.5V" time="18:02 UTC" age={MNOW - 4 * 3600 * 1000} resolved />
        <AlertRow severity="INFO" device="stratolink-3" title="Telemetry packet TX" message="seq=1847 — uplink complete" time="17:35 UTC" age={MNOW - 4.5 * 3600 * 1000} resolved />
        <AlertRow severity="INFO" device="stratolink-1" title="Geofence exit" message="Device entered northern California region" time="13:11 UTC" age={MNOW - 9 * 3600 * 1000} resolved />

        <MSectionLabel>SETTINGS</MSectionLabel>
        <div>
          {[
            ['Push notifications', 'On'],
            ['Critical alerts', 'SMS · m.chen'],
            ['Webhook', 'discord.gg/...'],
            ['Quiet hours', '22:00–07:00'],
          ].map(([k, v]) => (
            <div key={k} style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '14px 20px', borderTop: '1px solid var(--border)',
              fontFamily: 'var(--sans)', fontSize: 13,
            }}>
              <span style={{ color: 'var(--text)' }}>{k}</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--text-dim)' }}>{v}</span>
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none" style={{ opacity: 0.4 }}>
                  <path d="M 4 3 L 8 6 L 4 9" stroke="var(--text-dim)" strokeWidth="1.5" />
                </svg>
              </div>
            </div>
          ))}
        </div>
      </div>

      <MTabBar active="alerts" />
    </div>
  );
}

function AlertRow({ severity, device, title, message, time, age, resolved }) {
  const severityColor = severity === 'WARN' ? 'var(--alert)' : 'var(--ok)';
  return (
    <div style={{
      padding: '16px 20px',
      borderBottom: '1px solid var(--border)',
      borderLeft: '2px solid ' + (resolved ? 'transparent' : severityColor),
      opacity: resolved ? 0.7 : 1,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontFamily: 'var(--sans)', fontSize: 9, letterSpacing: '0.14em', textTransform: 'uppercase', color: severityColor, fontWeight: 500 }}>{severity}</span>
          <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-dim)' }}>{device}</span>
        </div>
        <span style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--text-dim3)' }}>{time}</span>
      </div>
      <div style={{ fontFamily: 'var(--sans)', fontSize: 14, color: 'var(--text-hi)', fontWeight: 500, marginBottom: 4 }}>{title}</div>
      <div style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--text-dim)', marginBottom: 8 }}>{message}</div>
      <MAge t={age} compact dot={true} />
    </div>
  );
}

window.MAlerts = MAlerts;
