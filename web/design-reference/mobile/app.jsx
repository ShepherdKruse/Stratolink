// Mobile app entry — wraps 5 screens in iOS frames, laid out on design canvas

function MobileApp() {
  // Wrap each screen in an iOS device frame
  // Use dark=true and skip the title prop so our custom header renders inside
  return (
    <window.DesignCanvas>
      <window.DCSection
        id="mobile"
        title="Stratolink — mobile"
        subtitle="Companion app for the dashboard. One thing per screen, tap-friendly targets, vertical scroll. Same color/type system as the desktop build — same data freshness model, alert model, telemetry model. Bottom tab bar: Fleet / Map / Telemetry / Alerts / More."
      >
        <window.DCArtboard id="m-fleet" label="01 · Fleet (home)" width={402} height={874}>
          <window.IOSDevice dark={true} width={402} height={874}>
            <window.MFleet />
          </window.IOSDevice>
        </window.DCArtboard>

        <window.DCArtboard id="m-device" label="02 · Device detail" width={402} height={874}>
          <window.IOSDevice dark={true} width={402} height={874}>
            <window.MDevice />
          </window.IOSDevice>
        </window.DCArtboard>

        <window.DCArtboard id="m-map" label="03 · Live map" width={402} height={874}>
          <window.IOSDevice dark={true} width={402} height={874}>
            <window.MMap />
          </window.IOSDevice>
        </window.DCArtboard>

        <window.DCArtboard id="m-telemetry" label="04 · Telemetry" width={402} height={874}>
          <window.IOSDevice dark={true} width={402} height={874}>
            <window.MTelemetry />
          </window.IOSDevice>
        </window.DCArtboard>

        <window.DCArtboard id="m-alerts" label="05 · Alerts" width={402} height={874}>
          <window.IOSDevice dark={true} width={402} height={874}>
            <window.MAlerts />
          </window.IOSDevice>
        </window.DCArtboard>
      </window.DCSection>
    </window.DesignCanvas>
  );
}

const mobileRoot = ReactDOM.createRoot(document.getElementById('root'));
mobileRoot.render(<MobileApp />);
