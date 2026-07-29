"""LoRa link-budget + time-on-air primitives for the SF/airtime/range study.

All formulas are the canonical Semtech ones (SX1276/126x datasheet, AN1200.13),
so results are reproducible and auditable.

Time-on-air (explicit header, CR 4/5, 8-symbol preamble, CRC on) for the current
40-byte Stratolink observability payload. Sensitivity from kTB + NF + SNR.
"""
from __future__ import annotations
import math

# --- our radio config (firmware/src/lorawan.cpp, telemetry.cpp) -------------
PAYLOAD_B = 40          # telemetry_pack v2 writes offsets 0..39 = 40 bytes
BW_HZ = 125_000         # all regions use BW125
CR_DENOM = 5            # coding rate 4/5  -> CR=1 in Semtech formula
PREAMBLE_SYM = 8        # setPreambleLength(8)
EXPLICIT_HEADER = True  # LoRaWAN uses explicit header
CRC_ON = True
LORAWAN_OVERHEAD_B = 13 # MHDR+FHDR+FPort+MIC ≈ 13 B added to app payload by MAC
TX_DBM = 14.0           # radio->begin(power=14) fixed all regions

# --- Semtech SF -> required SNR (dB) and resulting sensitivity (dBm) --------
# SNR_lim from datasheet; sensitivity S = -174 + 10log10(BW) + NF + SNR_lim.
NF_DB = 6.0
SNR_LIM = {7: -7.5, 8: -10.0, 9: -12.5, 10: -15.0, 11: -17.5, 12: -20.0}

# --- regional max-range data rate (lowest SF allowed for uplinks) -----------
# US915/AU915 cap uplinks at DR0 = SF10/BW125; EU868/AS923 reach DR0 = SF12/BW125.
REGION_MAX_SF = {"US915": 10, "AU915": 10, "EU868": 12, "AS923": 12}
REGION_FREQ_MHZ = {"US915": 904.5, "AU915": 917.5, "EU868": 868.1, "AS923": 923.3}


def sensitivity_dbm(sf: int, bw_hz: float = BW_HZ, nf_db: float = NF_DB) -> float:
    """Receiver sensitivity floor (dBm) for a given SF/BW."""
    return -174.0 + 10.0 * math.log10(bw_hz) + nf_db + SNR_LIM[sf]


def time_on_air_s(sf: int, payload_b: int = PAYLOAD_B, bw_hz: float = BW_HZ,
                  cr_denom: int = CR_DENOM, n_preamble: int = PREAMBLE_SYM,
                  explicit_header: bool = EXPLICIT_HEADER, crc: bool = CRC_ON,
                  lorawan_overhead_b: int = LORAWAN_OVERHEAD_B) -> float:
    """Semtech LoRa time-on-air (seconds). Includes LoRaWAN MAC overhead bytes.

    T_sym = 2^SF / BW
    Low-data-rate optimize (LDRO) mandatory when T_sym > 16 ms (SF11/12 @125k).
    n_payload = 8 + max( ceil((8*PL - 4*SF + 28 + 16*CRC - 20*IH)
                              / (4*(SF - 2*DE))) * (CR+4), 0 )
    T_packet = (n_preamble + 4.25 + n_payload) * T_sym
    """
    pl = payload_b + lorawan_overhead_b
    t_sym = (2 ** sf) / bw_hz
    de = 1 if t_sym > 0.016 else 0           # low-data-rate optimize
    ih = 0 if explicit_header else 1
    cr = cr_denom - 4                         # CR 4/5 -> 1
    num = 8 * pl - 4 * sf + 28 + (16 if crc else 0) - 20 * ih
    den = 4 * (sf - 2 * de)
    n_payload = 8 + max(math.ceil(num / den) * (cr + 4), 0)
    t_preamble = (n_preamble + 4.25) * t_sym
    t_payload = n_payload * t_sym
    return t_preamble + t_payload


def fspl_db(d_km: float, f_mhz: float) -> float:
    """Free-space path loss (dB). PL = 20log10(d_km) + 20log10(f_MHz) + 32.45."""
    return 20 * math.log10(d_km) + 20 * math.log10(f_mhz) + 32.45


def radio_horizon_km(h_m: float, k: float = 4.0 / 3.0) -> float:
    """Radio horizon (km) for height h_m, gateway at sea level. k=4/3 refraction."""
    Re = 6371.0 * k
    return math.sqrt(2 * Re * (h_m / 1000.0) + (h_m / 1000.0) ** 2)


def max_range_km(sf: int, f_mhz: float, tx_dbm: float = TX_DBM,
                 g_tx_dbi: float = 2.0, g_rx_dbi: float = 3.0,
                 l_pol_db: float = 1.5, l_atm_db: float = 0.1,
                 fade_db: float = 0.0) -> float:
    """Link-budget-limited max range (km): the distance where received power
    equals the sensitivity floor. Solves FSPL for d.
      RSSI = Ptx + Gtx + Grx - Lpol - Latm - PL_FS  >=  S_min
      PL_FS_max = Ptx+Gtx+Grx-Lpol-Latm-fade - S_min
    """
    s = sensitivity_dbm(sf)
    pl_max = tx_dbm + g_tx_dbi + g_rx_dbi - l_pol_db - l_atm_db - fade_db - s
    # invert FSPL: 20log10(d) = pl_max - 20log10(f) - 32.45
    log_d = (pl_max - 20 * math.log10(f_mhz) - 32.45) / 20.0
    return 10 ** log_d


def fup_msgs_per_day(sf: int, **toa_kw) -> float:
    """TTN Fair-Use Policy: 30 s airtime/device/day -> max uplinks/day."""
    return 30.0 / time_on_air_s(sf, **toa_kw)


if __name__ == "__main__":
    print(f"Stratolink payload {PAYLOAD_B} B app + {LORAWAN_OVERHEAD_B} B MAC; BW{BW_HZ//1000}k CR4/{CR_DENOM}")
    print(f"{'SF':>3} {'ToA(ms)':>8} {'sens(dBm)':>10} {'FUP/day':>8} {'maxRange(km)':>12}")
    for sf in range(7, 13):
        toa = time_on_air_s(sf)
        print(f"{sf:>3} {toa*1000:8.1f} {sensitivity_dbm(sf):10.1f} "
              f"{fup_msgs_per_day(sf):8.0f} {max_range_km(sf, 904.5):12.0f}")
    print(f"\nradio horizon @10 km (4/3-earth): {radio_horizon_km(10000):.0f} km")
    print(f"radio horizon @12 km: {radio_horizon_km(12000):.0f} km")
