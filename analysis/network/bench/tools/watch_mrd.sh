#!/usr/bin/env bash
# Live-watch the `mrd` diagnostic struct on stratolink-2 over J-Link.
# One JLink snapshot per tick (brief ~ms halt to read, then resumes), decoded to a
# CSV row by mrd_decode.py. Robust + dependency-light; no GDB session to babysit.
#
# Usage:  ./watch_mrd.sh [out.csv] [period_s]
# Watch the `phase` column and read the PSU current display during each phase
# (SLEEP/STANDBY/RX/TXBEACON/RELAY/BW500) -> that's the T5 current table.
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
ADDR=0x200003F8          # &mrd (from `nm`); re-check if firmware changes
NBYTES=0x48              # sizeof(MeshRelayDiag) = 72
CSV="${1:-$HERE/../T5_power/mrd_log.csv}"
PERIOD="${2:-3}"
SCRIPT=$(mktemp); trap 'rm -f "$SCRIPT"' EXIT
cat > "$SCRIPT" <<EOF
si SWD
speed 4000
device STM32WLE5CC
connect
mem $ADDR $NBYTES
go
exit
EOF
echo "ts,uptime_s,phase,vstor_mv,solar_mv,begin,rx,crc_err,fwd,dedup,hop0,last_from,last_hop,last_rssi,last_snr,txc,toa_us,msw_us,bw500_us" | tee "$CSV"
while true; do
  JLinkExe -CommanderScript "$SCRIPT" -ExitOnError 1 -nogui 1 2>/dev/null \
    | python3 "$HERE/mrd_decode.py" | tee -a "$CSV" || echo "[watch_mrd] read failed (target connected? firmware flashed?)"
  sleep "$PERIOD"
done
