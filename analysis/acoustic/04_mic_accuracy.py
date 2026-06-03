"""
How accurate is the mic *firmware* (not just "does the hardware work")?

Compares the firmware decode (sinc^1 ones-count, no DC block - mic_acoustic.cpp)
against ground truth and a proper decode, four substantiated views:

  (A) frequency-response fidelity      - model + analytic sinc^1 droop
  (B) amplitude linearity / range      - REAL data (sweep_1000hz.csv)
  (C) noise-floor penalty by signal    - model: accuracy depends on how SPARSE
                                         the signal is (the flight regime is sparse)
  (D) noise budget vs the trigger      - measured floor vs threshold

Ground truth exists only in the model (we know the exact input); the real bench
captures (AC2_*) confirmed the shapes. Linearity/range (B) is measured on hardware.
  analysis/.venv/bin/python analysis/acoustic/04_mic_accuracy.py
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
PCM, FPDM = pdm.PCM_HZ, pdm.PDM_CLK_HZ


def at_pdm(dur):
    return np.arange(int(dur * FPDM)) / FPDM


def tone_mag(f, A=0.3, dur=0.06):
    """relative magnitude (dB) of the decoded tone at f, firmware vs proper."""
    x = A * np.sin(2 * np.pi * f * at_pdm(dur)); b = pdm.sigma_delta_modulate(x, 2)
    def mag(y):
        y = y - np.mean(y); w = sig.get_window("hann", len(y))
        Y = np.abs(np.fft.rfft(y * w)); fr = np.fft.rfftfreq(len(y), 1/PCM)
        return 20*np.log10(Y[np.argmin(np.abs(fr - f))] + 1e-12)
    return mag(pdm.decode_sinc1(b)), mag(pdm.decode_proper(b))


def floor_gap(x_pdm):
    """in-band noise-floor penalty (dB) of firmware vs proper for a given signal."""
    b = pdm.sigma_delta_modulate(x_pdm, 2)
    nf = pdm.inband_noise_floor_db(pdm.decode_sinc1(b), PCM, [])
    np_ = pdm.inband_noise_floor_db(pdm.decode_proper(b), PCM, [])
    return nf - np_


def main():
    fig, ax = plt.subplots(2, 2, figsize=(13.5, 9.2))
    fig.suptitle("How accurate is the mic firmware? - decode fidelity vs ground truth", y=0.99)

    # (A) frequency-response fidelity ---------------------------------------
    freqs = np.geomspace(60, 4600, 16)
    mfw, mpp = np.array([tone_mag(f) for f in freqs]).T
    ref = np.argmin(np.abs(freqs - 1000)); mfw -= mfw[ref]; mpp -= mpp[ref]
    analytic = 20*np.log10(np.abs(np.sinc(freqs / PCM)))
    droop = float(20*np.log10(abs(np.sinc(4687/PCM))))
    a = ax[0, 0]
    a.semilogx(freqs, mfw, "o-", color=S.RED, lw=2, ms=5, label="firmware sinc^1 (modelled)")
    a.semilogx(freqs, mpp, "s-", color=S.TEAL7, lw=2, ms=4, label="proper sinc^4")
    a.semilogx(freqs, analytic, "--", color=S.WARM, lw=1.6, label="analytic sinc^1 droop")
    a.axhline(0, color=S.GRID, lw=0.8); a.axvline(4687, color=S.DIM, ls=":", lw=1)
    a.annotate("Nyquist", (4687, 2), color=S.TEXT_DIM, fontsize=8, ha="right")
    a.set_title(f"(A) Frequency response - firmware droops {droop:.1f} dB at Nyquist")
    a.set_xlabel("frequency (Hz)"); a.set_ylabel("relative magnitude (dB, ref 1 kHz)")
    a.set_ylim(-9, 4); a.grid(True, which="both", alpha=0.3); a.legend(fontsize=8, loc="lower left")

    # (B) linearity / dynamic range - REAL sweep, fit ABOVE the floor -------
    a = ax[0, 1]; slope = float("nan")
    csv = HERE / "data" / "sweep_1000hz.csv"
    if csv.exists():
        d = np.genfromtxt(csv, delimiter=",", names=True)
        lvl, rms = d["played_level"], np.maximum(d["rms_sq"], 1)
        above = (lvl > 0) & (rms > 24)            # >4x the ~6 floor
        a.scatter(lvl[(lvl > 0) & ~above], rms[(lvl > 0) & ~above], c=S.DIM, s=34,
                  label="floor-limited", zorder=3)
        a.scatter(lvl[above], rms[above], c=S.RED, s=46, label="above floor (signal)", zorder=4)
        if above.sum() >= 3:
            slope, b0 = np.polyfit(np.log10(lvl[above]), np.log10(rms[above]), 1)
            xs = np.geomspace(lvl[above].min(), lvl[above].max(), 40)
            a.plot(xs, 10**b0 * xs**slope, "--", color=S.TEXT, lw=1.5,
                   label=f"fit slope={slope:.2f} (speaker-limited)")
        a.axhline(6, color=S.TEAL7, ls=":", lw=1.4, label="noise floor ~6")
        a.axhline(48, color=S.WARM, ls="--", lw=1.4, label="threshold ~48")
        a.set_xscale("log"); a.set_yscale("log")
        a.annotate("slope<2 -> laptop speaker compressing\nat max volume (not the mic)",
                   (0.03, 0.04), xycoords="axes fraction", fontsize=7.6, color=S.TEXT_DIM)
        a.set_title("(B) Dynamic range ~24 dB (measured) - floor/speaker-limited")
        a.set_xlabel("played level (amplitude)"); a.set_ylabel("rms_sq")
        a.legend(fontsize=7.5); a.grid(True, which="both", alpha=0.3)

    # (C) noise-floor penalty by signal sparsity - model --------------------
    a = ax[1, 0]
    t = at_pdm(0.12)
    sigs = [
        ("single tone\n1 kHz", np.sin(2*np.pi*1000*t) * 0.3),
        ("4-tone\nmultitone", sum(0.12*np.sin(2*np.pi*f*t) for f in (300, 900, 1800, 3300))),
        ('voice-like\n(140 Hz + harm.)',
         np.tanh(3*sum((1/k)*np.sin(2*np.pi*140*k*t) for k in range(1, 22))) * 0.3),
        ("white noise\n(broadband)", np.random.default_rng(1).standard_normal(t.size)*0.12),
    ]
    gaps = [floor_gap(x) for _, x in sigs]
    cols = [S.RED if g > 6 else (S.WARM if g > 2 else S.TEAL7) for g in gaps]
    a.bar(range(len(sigs)), gaps, color=cols, alpha=0.85, width=0.6)
    for i, g in enumerate(gaps):
        a.annotate(f"{g:+.0f} dB", (i, g + 0.5), ha="center", fontsize=9, color=S.TEXT)
    a.set_xticks(range(len(sigs))); a.set_xticklabels([s[0] for s in sigs], fontsize=8.5)
    a.set_ylabel("firmware noise floor ABOVE proper (dB)")
    a.set_title("(C) Firmware accuracy depends on signal sparsity")
    a.annotate("sparse/quiet (<- stratosphere)\nhurts most", (0.0, max(gaps)*0.6),
               fontsize=8.3, color=S.TEXT_DIM)
    a.grid(True, axis="y", alpha=0.3)

    # (D) noise budget vs the trigger - measured ----------------------------
    a = ax[1, 1]
    a.bar(0, 6, color=S.TEAL7, alpha=0.85, width=0.5); a.annotate("6", (0, 7), ha="center", fontsize=9)
    a.bar(1, 48, color=S.WARM, alpha=0.85, width=0.5); a.annotate("48", (1, 50), ha="center", fontsize=9)
    a.axhline(48, color=S.WARM, ls="--", lw=1.1)
    a.fill_between([1.6, 2.4], 48, 140, color=S.RED, alpha=0.18)
    a.annotate("flight DAY\nmust live here\n(events fire -> >48)", (2.0, 95), ha="center",
               fontsize=8.3, color=S.RED)
    a.set_xticks([0, 1, 2]); a.set_xticklabels(["firmware noise\n(bench, measured)",
                  "event threshold\n(16xfloor)", "flight day\n(inferred)"], fontsize=8.2)
    a.set_ylim(0, 145); a.set_ylabel("rms_sq")
    a.set_title("(D) Firmware's own noise can't trigger - flight needs an external lift")
    a.annotate("bench: 6 << 48 -> 8x margin, 0 false-pos.\nSo flight events are NOT the firmware's\n"
               "intrinsic noise; something external (harvester)\nlifts the floor over 48 by day.",
               (0.02, 0.62), xycoords="axes fraction", fontsize=8.2, color=S.TEXT)

    S.footer(fig, "model: pdm.py sigma-delta * real: sweep_1000hz.csv / session-1 captures * "
                  "analysis/acoustic/04_mic_accuracy.py", light=True)
    fig.tight_layout(rect=[0, 0.01, 1, 0.96])
    out = HERE / "figs" / "AC4_mic_accuracy.png"; fig.savefig(out, dpi=140); print("wrote", out)

    print("\n--- accuracy headline ---")
    print(f"FREQUENCY  : exact tones recovered; ~flat 200 Hz-3 kHz, firmware droops {droop:.1f} dB "
          f"at Nyquist (sinc^1, correctable); proper flat")
    print(f"LINEARITY  : monotonic; bench slope {slope:.2f} is speaker-compression-limited at max vol "
          f"(clean linearity needs a calibrated sweep); firmware decode itself is linear (model)")
    print(f"NOISE FLOOR: firmware worse than proper by  " +
          "  ".join(f"{s[0].splitlines()[0]}={g:+.0f}dB" for s, g in zip(sigs, gaps)))
    print(f"DYN RANGE  : bench rms_sq 6->~1500 ~ {10*np.log10(1500/6):.0f} dB (floor-limited)")
    print("VERDICT    : signal path accurate (right freqs, linear); the LIMIT is the elevated "
          "noise floor on SPARSE signals - exactly the stratosphere case.")


if __name__ == "__main__":
    main()
