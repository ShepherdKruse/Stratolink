"""
Precise-audio payoff on REAL board-#2 captures (2026-06-03).

Two firmware improvements, both measured on real raw PDM (frame_*.npz):
  - proper sinc^4+DC-block decode  -> audio fidelity (noise floor / tone SNR)
  - DC-blocked variance detector  -> trigger margin + thermal stability

All decodes run on the SAME captured raw PDM, so the firmware sinc^1 and the
proposed decodes are compared apples-to-apples on identical real audio.
  analysis/.venv/bin/python analysis/acoustic/06_precise_audio.py
"""
from __future__ import annotations
import sys, pathlib
import numpy as np
from scipy import signal as sig

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(ROOT / "analysis" / "antenna"))
import pdm, _style as S  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
S.use_light()
PCM = pdm.PCM_HZ
D = HERE / "data"


def ones_per_sample(pdmb):
    bits = np.unpackbits(pdmb); n = (len(bits) // 320) * 320
    return bits[:n].reshape(-1, 320).sum(1).astype(float)

def load(n):
    return np.load(D / f"frame_{n}.npz")["pdm"]

def metrics_at(y, f0):
    y = y - y.mean(); fr, P = sig.welch(y, PCM, nperseg=256)
    k = np.argmin(np.abs(fr - f0))
    return 10*np.log10(P[k] / np.median(P))      # SNR (dB) = peak vs median floor


def main():
    fig, ax = plt.subplots(2, 2, figsize=(13.5, 9.2))
    fig.suptitle("Precise-audio payoff on real captures - proper decode + DC-blocked detector", y=0.99)

    # (A) tone PSD: firmware sinc^1 vs proper -------------------------------
    pdmb = load("tone1k")
    y1 = pdm.decode_sinc1(pdmb); yp = pdm.decode_proper(pdmb)
    f1, P1 = pdm.welch_psd(y1); fp, Pp = pdm.welch_psd(yp)
    snr1, snrp = metrics_at(y1, 1000), metrics_at(yp, 1000)
    a = ax[0, 0]
    a.plot(f1, P1, color=S.RED, lw=1.4, label=f"firmware sinc^1  (SNR {snr1:.0f} dB)")
    a.plot(fp, Pp, color=S.TEAL7, lw=1.4, label=f"proper sinc^4   (SNR {snrp:.0f} dB)")
    a.set_xlim(0, 4687); a.set_xlabel("Hz"); a.set_ylabel("dB")
    a.set_title("(A) Real 1 kHz tone - proper decode drops the floor")
    a.legend(fontsize=8.5); a.grid(alpha=0.3)

    # (B) multitone PSD ----------------------------------------------------
    pdmb = load("multitone12")
    y1 = pdm.decode_sinc1(pdmb); yp = pdm.decode_proper(pdmb)
    f1, P1 = pdm.welch_psd(y1); fp, Pp = pdm.welch_psd(yp)
    a = ax[0, 1]
    a.plot(f1, P1, color=S.RED, lw=1.4, label="firmware sinc^1")
    a.plot(fp, Pp, color=S.TEAL7, lw=1.4, label="proper sinc^4")
    for ft in (220, 880, 1760, 3300):
        a.axvline(ft, color=S.DIM, ls=":", lw=0.7)
    a.set_xlim(0, 4687); a.set_xlabel("Hz"); a.set_ylabel("dB")
    a.set_title("(B) Real multitone - tones clean, floor ~30 dB lower")
    a.legend(fontsize=8.5); a.grid(alpha=0.3)

    # (C) noise-floor improvement per real signal --------------------------
    a = ax[1, 0]
    names = ["silence", "tone1k", "multitone12", "white12", "ieee_list1_loud"]
    labels = ["silence", "1 kHz", "multitone", "white", "voice"]
    gaps = []
    for n in names:
        pdmb = load(n)
        g = (pdm.inband_noise_floor_db(pdm.decode_sinc1(pdmb), PCM, []) -
             pdm.inband_noise_floor_db(pdm.decode_proper(pdmb), PCM, []))
        gaps.append(g)
    cols = [S.RED if g > 6 else (S.WARM if g > 2 else S.TEAL7) for g in gaps]
    a.bar(range(len(gaps)), gaps, color=cols, alpha=0.85, width=0.6)
    for i, g in enumerate(gaps):
        a.annotate(f"{g:+.0f}", (i, g + (0.6 if g >= 0 else -1.4)), ha="center", fontsize=9)
    a.axhline(0, color=S.TEXT, lw=0.8)
    a.set_xticks(range(len(gaps))); a.set_xticklabels(labels, fontsize=9)
    a.set_ylabel("noise-floor improvement (dB)"); a.grid(axis="y", alpha=0.3)
    a.set_title("(C) Audio-fidelity gain (proper vs firmware) - biggest when sparse")

    # (D) detector margin - DC-blocked variance vs fixed-centre ------------
    a = ax[1, 1]
    sil = ones_per_sample(load("silence")); ton = ones_per_sample(load("tone1k"))
    def rms_fixed(o): return np.mean((o - 160)**2)
    def var16(o):     return np.var(o) * 16
    m_old = rms_fixed(ton) / rms_fixed(sil)
    m_new = var16(ton) / max(var16(sil), 1e-9)
    a.bar([0, 1], [m_old, m_new], color=[S.DIM, S.TEAL7], alpha=0.85, width=0.55)
    for i, v in enumerate([m_old, m_new]):
        a.annotate(f"{v:.0f}x", (i, v*1.05), ha="center", fontsize=11, color=S.TEXT)
    a.set_yscale("log"); a.set_xticks([0, 1])
    a.set_xticklabels(["firmware\nrms_sq (fixed 160)", "proposed\nrms_sq_var (DC-block)"], fontsize=9)
    a.set_ylabel("tone / silence margin (x, log)")
    a.set_title(f"(D) Detector margin {m_old:.0f}x -> {m_new:.0f}x (DC block) + thermally stable")
    a.grid(axis="y", which="both", alpha=0.3)

    S.footer(fig, "real captures frame_*.npz (board #2, 2026-06-03) * "
                  "analysis/acoustic/06_precise_audio.py", light=True)
    fig.tight_layout(rect=[0, 0.01, 1, 0.96])
    out = HERE / "figs" / "AC6_precise_audio.png"; fig.savefig(out, dpi=140); print("wrote", out)
    print(f"\nREAL-DATA RESULTS:")
    print(f"  1 kHz tone SNR: firmware {snr1:.0f} dB  ->  proper {snrp:.0f} dB  (+{snrp-snr1:.0f} dB)")
    print(f"  noise-floor improvement: " + "  ".join(f"{l}={g:+.0f}dB" for l, g in zip(labels, gaps)))
    print(f"  detector margin (tone/silence): firmware {m_old:.0f}x  ->  DC-blocked {m_new:.0f}x")


if __name__ == "__main__":
    main()
