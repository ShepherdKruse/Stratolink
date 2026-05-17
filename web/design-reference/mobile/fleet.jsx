// Mobile Screen 1: Fleet (home)
function MFleet() {
  const latest = MT[MT.length - 1];
  return (
    <div style={{ width: 402, height: 874, background: 'var(--bg)', color: 'var(--text)', fontFamily: 'var(--sans)', overflow: 'hidden', display: 'flex', flexDirection: 'column', position: 'relative' }} data-screen-label="01 Fleet">
      <MHeader
        sub="GROUND STATION"
        title="Stratolink"
        right={
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 2 }}>
            <span style={{ fontFamily: 'var(--sans)', fontSize: 9, letterSpacing: '0.10em', color: 'var(--ok)', textTransform: 'uppercase', fontWeight: 500 }}>● LIVE</span>
            <MAge t={MFRESHNESS.packet} compact dot={false} />
          </div>
        }
      />

      <div style={{ flex: 1, overflow: 'auto', paddingBottom: 88 }}>
        {/* fleet summary stat strip */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', borderBottom: '1px solid var(--border)' }}>
          <div style={{ padding: '18px 16px', borderRight: '1px solid var(--border)' }}>
            <div style={{ fontFamily: 'var(--sans)', fontSize: 9, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--text-dim2)', fontWeight: 500 }}>Active</div>
            <div style={{ fontFamily: 'var(--mono)', fontSize: 26, fontWeight: 500, color: 'var(--text-hi)', marginTop: 6, lineHeight: 1 }}>3</div>
          </div>
          <div style={{ padding: '18px 16px', borderRight: '1px solid var(--border)' }}>
            <div style={{ fontFamily: 'var(--sans)', fontSize: 9, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--text-dim2)', fontWeight: 500 }}>Tracked</div>
            <div style={{ fontFamily: 'var(--mono)', fontSize: 26, fontWeight: 500, color: 'var(--text-hi)', marginTop: 6, lineHeight: 1 }}>12</div>
          </div>
          <div style={{ padding: '18px 16px' }}>
            <div style={{ fontFamily: 'var(--sans)', fontSize: 9, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--text-dim2)', fontWeight: 500 }}>Alerts</div>
            <div style={{ fontFamily: 'var(--mono)', fontSize: 26, fontWeight: 500, color: 'var(--alert)', marginTop: 6, lineHeight: 1 }}>2</div>
          </div>
        </div>

        <MSectionLabel right={<span style={{ fontFamily: 'var(--mono)', fontSize: 9, color: 'var(--text-dim2)' }}>3 devices</span>}>FLEET</MSectionLabel>

        <MDeviceCard
          id="stratolink-3"
          status="TRACKING"
          statusColor="teal"
          alt={MLAST.alt !== null ? `${MLAST.alt} m` : '—'}
          batt={`${Mfmt.num(latest.batt, 2)} V`}
          rssi={`${latest.rssi} dBm`}
          lastT={MFRESHNESS.packet}
          primary={true}
        />
        <MDeviceCard
          id="stratolink-2"
          status="NO GPS"
          statusColor="amber"
          alt="—"
          batt="4.12 V"
          rssi="−78 dBm"
          lastT={MNOW - 28 * 60 * 1000}
        />
        <MDeviceCard
          id="stratolink-1"
          status="LANDED"
          statusColor="dim"
          alt="1,612 m"
          batt="3.42 V"
          rssi="−101 dBm"
          lastT={MNOW - 14 * 3600 * 1000}
        />

        <MSectionLabel>SYSTEM</MSectionLabel>
        <div style={{ paddingLeft: 20, paddingRight: 20 }}>
          <div className="kv-row"><span className="k">Database</span><span className="v teal">CONNECTED</span></div>
          <div className="kv-row"><span className="k">Packet rate</span><span className="v">18.2/min</span></div>
          <div className="kv-row"><span className="k">Last uplink</span><span className="v"><MAge t={MFRESHNESS.packet} compact dot={false} /></span></div>
          <div className="kv-row"><span className="k">Last GPS fix</span><span className="v"><MAge t={MLAST_FIX_T} compact dot={false} /></span></div>
        </div>
      </div>

      <MTabBar active="fleet" />
    </div>
  );
}

window.MFleet = MFleet;
