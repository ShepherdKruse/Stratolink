"""PART B-0 — Payload attitude from the onboard accelerometer.

Before modeling antenna patterns we must know how the payload was ORIENTED in
flight, because the radiated pattern is fixed to the body and the body's tilt
sets where the pattern's lobes point on the sky.

The LIS2DH12 MEMS accelerometer reads the gravity vector in the board frame on
every uplink. At float the balloon is in quasi-free-fall translationally but
gravity still defines "down", so the steady accel vector = the board's tilt.

KEY EMPIRICAL RESULT (this run): at float the gravity vector sits in a very
tight attitude (z-tilt std ~2.5deg) -> the payload HANGS STABLY and spins about
the near-vertical axis, rather than tumbling. Consequences:
  * Reception azimuth is uniform (A3) because the payload yaws through all
    headings while keeping a fixed tilt -> spin, not tumble.
  * The antenna's ELEVATION pointing is stable and therefore CONTROLLABLE by how
    we mount it. Part D (mounting/angle) is a real design lever.
  * Part B Monte-Carlo should sample "fixed tilt + uniform yaw (+ small swing)",
    NOT "uniform over a tumbling sphere".

Sampling caveat: telemetry is one sample per ~5 min, far slower than any
pendulum period (seconds), so we capture the SWING ENVELOPE's marginal
distribution, not its time history. A fast tumble would alias to a BROAD tilt
spread; the tight cluster we see can only come from a genuinely stable mean
attitude. We quantify the residual spread as the swing amplitude proxy.

Run:  analysis/.venv/bin/python analysis/antenna/50_attitude.py
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

import _style as S
from _gps import classify_uplinks, LAUNCH_UTC

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
FIGS = HERE / "figs"
FLOAT_ALT_M = 8000.0


def load_accel():
    df = pd.read_parquet(DATA / "telemetry_raw.parquet")
    df = classify_uplinks(df)
    for c in ("mems_accel_x", "mems_accel_y", "mems_accel_z"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["mems_accel_x", "mems_accel_y", "mems_accel_z"]).copy()
    df["amag"] = np.sqrt(df.mems_accel_x**2 + df.mems_accel_y**2 + df.mems_accel_z**2)
    df = df[df["amag"] > 5.0].copy()  # drop all-zero dropout / ground-handling rows
    # angle of each body axis from the gravity (down) vector
    for ax in ("x", "y", "z"):
        df[f"tilt_{ax}"] = np.degrees(np.arccos((df[f"mems_accel_{ax}"] / df["amag"]).clip(-1, 1)))
    df["flight"] = df["time"] >= LAUNCH_UTC
    df["float"] = df["flight"] & (df["altitude_m"] >= FLOAT_ALT_M)
    return df


def plot_b0(df, fig_path):
    S.use_light()
    fl = df[df["float"]]
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # --- left: distribution of the three body-axis tilts at float ---
    ax = axes[0]
    colors = {"x": S.WARM, "y": S.MINT, "z": S.TEAL7}
    for a in ("x", "y", "z"):
        t = fl[f"tilt_{a}"]
        ax.hist(t, bins=np.arange(0, 181, 4), color=colors[a], alpha=0.6,
                label=f"body-{a}: median {t.median():.0f}°, σ={t.std():.1f}°")
    ax.axvline(90, color=S.TEXT_DIM, ls=":", lw=1)
    ax.set_xlabel("angle of body axis from gravity / down (°)")
    ax.set_ylabel("uplinks at float")
    ax.set_title("B0a · Body attitude at float is TIGHT\n"
                 "narrow clusters ⇒ stable hang, not tumble")
    ax.legend(loc="upper center", fontsize=9)
    ax.set_xlim(0, 180)

    # --- right: what a stable-hang-with-spin vs a tumble would look like ---
    # Reference: if tumbling (isotropic), tilt-from-down is distributed as
    # p(theta) = sin(theta)/2  -> median 60deg, broad. Overlay it to contrast.
    ax = axes[1]
    zt = fl["tilt_z"]
    ax.hist(zt, bins=np.arange(60, 121, 2), color=S.TEAL7, density=True,
            alpha=0.85, label=f"measured body-z tilt (σ={zt.std():.1f}°)")
    th = np.linspace(0, 180, 361)
    ax.plot(th, np.sin(np.radians(th)) / 2 * (np.pi/180) * 100, color=S.RED, lw=2,
            ls="--", label="if tumbling (isotropic): sin θ/2")
    ax.set_xlim(60, 120)
    ax.set_xlabel("body-z axis tilt from down (°)")
    ax.set_ylabel("probability density")
    ax.set_title("B0b · Spin (fixed tilt) vs tumble (isotropic)\n"
                 "data is a sharp spike at ~91° — board-z rides horizontal, payload yaw-spins")
    ax.legend(loc="upper right", fontsize=9)

    S.footer(fig, "Stratolink-3 · LIS2DH12 accel, float uplinks · analysis/antenna/50_attitude.py")
    fig.tight_layout()
    fig.savefig(fig_path, dpi=190)
    plt.close(fig)


def main():
    df = load_accel()
    fl = df[df["float"]]
    print("=== Float attitude (gravity vector in board frame) ===")
    print(f"float uplinks with usable accel: {len(fl)}")
    for a in ("x", "y", "z"):
        t = fl[f"tilt_{a}"]
        print(f"  body-{a} tilt-from-down: median {t.median():5.1f}°  "
              f"IQR [{t.quantile(.25):.1f}, {t.quantile(.75):.1f}]  σ {t.std():4.1f}°  "
              f"range [{t.min():.1f}, {t.max():.1f}]")
    zt = fl["tilt_z"]
    print(f"\nInterpretation: body-z σ = {zt.std():.1f}° "
          f"({'STABLE HANG + yaw spin' if zt.std() < 10 else 'TUMBLING'}).")
    print("A fast tumble sampled at 5-min cadence would alias to a BROAD spread "
          "(isotropic median ~60°); the sharp ~91° spike cannot come from tumbling.")
    print("Swing-amplitude proxy (residual tilt spread): "
          f"±{zt.std()*1.0:.1f}° (1σ), ±{ (zt.quantile(.95)-zt.quantile(.05))/2:.1f}° (5–95%).")

    df.to_parquet(DATA / "attitude.parquet")
    plot_b0(df, FIGS / "B0_attitude.png")
    print("\nwrote figs/B0_attitude.png and data/attitude.parquet")


if __name__ == "__main__":
    main()
