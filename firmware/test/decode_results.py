#!/usr/bin/env python3
"""
Decode Stratolink board test results from J-Link memory dump.

Usage:
  python test/decode_results.py                     # auto-reads via J-Link
  python test/decode_results.py "04 01 01 00 ..."   # manual hex input
  python test/decode_results.py < dump.txt           # pipe from file

Requires J-Link Commander on PATH or installed at default location.
"""
import sys, struct, subprocess, shutil, os

STRUCT_SIZE = 56
JLINK_PATHS = [
    shutil.which("JLink") or "",
    shutil.which("JLink.exe") or "",
    r"C:\Program Files\SEGGER\JLink_V794e\JLink.exe",
    r"C:\Program Files (x86)\SEGGER\JLink\JLink.exe",
    r"C:\Program Files\SEGGER\JLink\JLink.exe",
]

def find_jlink():
    for p in JLINK_PATHS:
        if p and os.path.isfile(p):
            return p
    return None

def read_via_jlink():
    jlink = find_jlink()
    if not jlink:
        print("ERROR: J-Link Commander not found. Provide hex manually.")
        sys.exit(1)

    script = "r\ngo\nsleep 8000\nh\nmem8 0x200004A8 0x38\nq\n"
    tmp = os.path.join(os.path.dirname(__file__), "_tmp_read.jlink")
    with open(tmp, "w") as f:
        f.write(script)

    try:
        result = subprocess.run(
            [jlink, "-device", "STM32WLE5CC", "-if", "SWD", "-speed", "4000",
             "-autoconnect", "1", "-CommanderScript", tmp],
            capture_output=True, text=True, timeout=30
        )
        for line in result.stdout.splitlines():
            if line.strip().startswith("200004A"):
                _, _, data = line.partition("=")
                return data.strip()
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

    print("ERROR: Could not read memory from target.")
    sys.exit(1)

def parse_hex(raw_hex):
    tokens = raw_hex.replace(",", " ").replace("\n", " ").split()
    out = []
    for t in tokens:
        t = t.strip().upper()
        if len(t) == 2 and all(c in "0123456789ABCDEF" for c in t):
            out.append(int(t, 16))
    return bytes(out)

def decode(raw_hex):
    b = parse_hex(raw_hex)
    if len(b) < STRUCT_SIZE:
        print(f"ERROR: need {STRUCT_SIZE} bytes, got {len(b)}")
        return False

    b = b[:STRUCT_SIZE]
    u8  = lambda o: b[o]
    u16 = lambda o: struct.unpack_from('<H', b, o)[0]
    s16 = lambda o: struct.unpack_from('<h', b, o)[0]
    u32 = lambda o: struct.unpack_from('<I', b, o)[0]

    i2c       = u8(0)
    ms_ok     = u8(1);  lis_ok  = u8(2);  tmp_ok  = u8(3)
    pres      = u16(4);  bt     = s16(6);  tt      = s16(8)
    ax        = s16(10); ay     = s16(12); az      = s16(14)
    br_ok     = u8(16);  btr_ok = u8(17);  tr_ok   = u8(18); ar_ok = u8(19)
    pid       = u8(20);  als_en = u8(21);  als_d   = u32(22)
    uv_en     = u8(26);  uv_d   = u32(27)
    vstor     = u16(31); solar  = u16(33); vbat    = u8(35); ptier = u8(36)
    gps_rx    = u8(37);  gps_rst= u8(38); aint    = u8(39)
    spa1      = u8(40);  spa9   = u8(41); spb2    = u8(42)
    mstat     = u8(43);  mclk   = u8(44)
    m_fast    = u16(45); m_paced= u16(47); m_ext   = u16(49)
    m_total   = u16(51); m_alive= u8(53);  phase   = u8(54); done = u8(55)

    P = lambda v: "PASS" if v else "FAIL"
    amag = (ax**2 + ay**2 + az**2) ** 0.5
    tiers = ["FULL", "REDUCED", "NO_GPS", "EMERGENCY", "CRITICAL"]

    print("=" * 56)
    print("  STRATOLINK BOARD TEST RESULTS")
    print("=" * 56)

    if done == 0xAA:
        print(f"  Status: COMPLETE (phase {phase})")
    else:
        print(f"  Status: INCOMPLETE (stuck at phase {phase})")
    print()

    print(f"  1. I2C Bus")
    print(f"     Devices: {i2c}/5  {P(i2c >= 4)}")
    print()

    print(f"  2. Sensor Init")
    print(f"     MS5611:   {P(ms_ok)}")
    print(f"     LIS2DH12: {P(lis_ok)}")
    print(f"     TMP117:   {P(tmp_ok)}")
    print()

    print(f"  3. Sensor Reads")
    print(f"     Pressure:  {pres/10:.1f} hPa  {P(br_ok)}")
    print(f"     Baro temp: {bt/10:.1f} C  {P(btr_ok)}")
    print(f"     TMP117:    {tt/10:.1f} C  {P(tr_ok)}")
    print(f"     Accel:     {ax/100:.2f} {ay/100:.2f} {az/100:.2f} m/s2  |g|={amag/100:.2f}  {P(ar_ok and 800 < amag < 1100)}")
    print()

    print(f"  4. LTR-390UV")
    print(f"     Part ID: 0x{pid:02X}  {P(pid == 0xB2)}")
    print(f"     ALS: {P(als_en)} data={als_d}")
    print(f"     UV:  {P(uv_en)} data={uv_d}")
    print()

    print(f"  5. Power")
    print(f"     VSTOR: {vstor} mV  Solar: {solar} mV")
    print(f"     VBAT_OK: {P(vbat)}")
    print(f"     Tier: {tiers[ptier] if ptier < len(tiers) else ptier}")
    print()

    print(f"  6. GPS UART")
    print(f"     Bytes in 2s: {gps_rx}  {P(gps_rx > 0)}")
    print()

    print(f"  7. GPIO")
    print(f"     GPS_RESET_N: {gps_rst}  {P(gps_rst)}")
    print(f"     ACCEL_INT1:  {aint}")
    print(f"     Spare PA1/PA9/PB2: {spa1} {spa9} {spb2}")
    print()

    print(f"  8. Microphone PDM")
    print(f"     Static: 0x{mstat:02X}  CLK: {P(mclk & 1)}")
    if m_total:
        print(f"     Fast poll  (4096): {m_fast}  ({m_fast/4096*100:.0f}%)")
        print(f"     Paced poll (2048): {m_paced}  ({m_paced/2048*100:.0f}%)")
        print(f"     Extended  (32768): {m_ext}  ({m_ext/32768*100:.0f}%)")
    print(f"     Alive: {P(m_alive)}")
    print()

    results = {
        "I2C Bus":      i2c >= 4,
        "MS5611":       ms_ok and br_ok,
        "LIS2DH12":    lis_ok and ar_ok,
        "TMP117":       tmp_ok and tr_ok,
        "LTR-390UV":    pid == 0xB2 and als_en,
        "Power":        vbat == 1,
        "GPS":          gps_rx > 0,
        "GPS Reset":    gps_rst == 1,
        "Microphone":   m_alive == 1,
    }
    passed = sum(results.values())
    print("=" * 56)
    print(f"  {passed}/{len(results)} PASSED")
    for name, ok in results.items():
        print(f"    {'OK' if ok else '--'}  {name}")
    print("=" * 56)
    return passed == len(results)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        raw = " ".join(sys.argv[1:])
    elif not sys.stdin.isatty():
        raw = sys.stdin.read()
    else:
        raw = read_via_jlink()
    decode(raw)
