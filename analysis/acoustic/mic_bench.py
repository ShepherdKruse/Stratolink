#!/usr/bin/env python3
"""
Stratolink mic bench harness - play a known sound on the laptop, capture the
mic's view over J-Link, compare spectrograms, iterate.

Pipeline: laptop speaker --acoustic--> T3902 mic --PDM--> firmware (env:mic_test)
captures into RAM --J-Link savebin--> here --> decode + spectrogram compare.

Subcommands
  gen                 write the stimulus battery (sweeps/noise/clicks) to stimuli/
  flash               pio run -e mic_test -t upload   (flash the capture build)
  monitor             poll the header live (rms_sq / noise_floor / event)
  grab  [--out f.npz] read ONE frame (header + pcm + raw pdm) over J-Link
  probe <wav>         play <wav>, grab a frame mid-playback, compare -> figs/
  sim   <wav>         NO HARDWARE: model the mic (sigma-delta) from <wav> and run
                      the exact same analysis - validates the pipeline + shows the
                      firmware-decimator penalty.  Works today.

Deps: numpy/scipy/matplotlib only. Playback = macOS `afplay`; J-Link = `JLinkExe`.
"""
from __future__ import annotations
import argparse, os, pathlib, subprocess, sys, tempfile, time, wave
import numpy as np
from scipy import signal

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(ROOT / "analysis" / "antenna"))
import pdm  # noqa: E402
import _style as S  # noqa: E402
S.use_light()

ELF = ROOT / "firmware" / ".pio" / "build" / "mic_test" / "firmware.elf"
NM = pathlib.Path.home() / ".platformio/packages/toolchain-gccarmnoneeabi/bin/arm-none-eabi-nm"
STIM = HERE / "stimuli"; FIGS = HERE / "figs"
DEVICE, IFACE, SPEED = "STM32WLE5CC", "SWD", 4000
PCM_HZ = pdm.PCM_HZ
HDR_WORDS = 11  # mic_test_t = 11 x uint32

# ----------------------------------------------------------------- WAV helpers
def wav_write(path, x, fs):
    x = np.clip(x, -1, 1); xi = (x * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(int(fs)); w.writeframes(xi.tobytes())

def wav_read(path):
    with wave.open(str(path), "rb") as w:
        fs = w.getframerate(); n = w.getnframes(); ch = w.getnchannels()
        x = np.frombuffer(w.readframes(n), dtype="<i2").astype(np.float64) / 32768.0
    if ch > 1: x = x.reshape(-1, ch).mean(axis=1)
    return x, fs

# --------------------------------------------------------------- stimuli (gen)
def gen_stimuli(fs=48000, dur=3.0):
    STIM.mkdir(parents=True, exist_ok=True)
    t = np.arange(int(dur * fs)) / fs
    out = {}
    out["sweep_log_50_4500"] = signal.chirp(t, 50, dur, 4500, method="logarithmic") * 0.6
    rng = np.random.default_rng(7)
    out["white_noise"] = rng.standard_normal(t.size) * 0.25
    # pink: filter white with 1/sqrt(f) (Voss-ish via FFT shaping)
    w = rng.standard_normal(t.size); W = np.fft.rfft(w)
    f = np.fft.rfftfreq(t.size, 1/fs); f[0] = f[1]
    out["pink_noise"] = np.fft.irfft(W / np.sqrt(f), n=t.size); out["pink_noise"] *= 0.25/np.std(out["pink_noise"])
    clicks = np.zeros(t.size)
    for k in range(1, int(dur)):  # 1 impulse/s -> tests the event detector + 55ms window
        clicks[int(k*fs):int(k*fs)+24] = 0.9
    out["click_train"] = clicks
    out["multitone"] = sum(0.18*np.sin(2*np.pi*ft*t) for ft in (220, 880, 1760, 3300))
    for name, x in out.items():
        wav_write(STIM / f"{name}.wav", x, fs)
    print("wrote", len(out), "stimuli to", STIM)

# ------------------------------------------------------------------ J-Link I/O
def _syms():
    addr = {"mt": 0x20000030, "pcm_buf": 0x20002214, "pdm_buf": 0x20000214}  # fallback
    if NM.exists() and ELF.exists():
        out = subprocess.run([str(NM), str(ELF)], capture_output=True, text=True).stdout
        for ln in out.splitlines():
            p = ln.split()
            if len(p) == 3 and p[2] in addr:
                addr[p[2]] = int(p[0], 16)
    return addr

def _jlink(cmds, timeout=30):
    with tempfile.TemporaryDirectory() as d:
        scr = pathlib.Path(d) / "s.jlink"
        scr.write_text("\n".join(cmds) + "\nq\n")
        r = subprocess.run(["JLinkExe", "-if", IFACE, "-device", DEVICE, "-speed", str(SPEED),
                            "-NoGui", "1", "-CommanderScript", str(scr)],
                           capture_output=True, text=True, timeout=timeout, cwd=d)
        return r.stdout + r.stderr

_HKEYS = ["magic","seq","n_pcm","n_pdm","sr_hz","rms_sq","rms_sq_var","noise_floor_sq","event","err","uptime_s"]

def read_header():
    """Fast header-only read over J-Link (live, non-halting)."""
    a = _syms()
    with tempfile.TemporaryDirectory() as d:
        hp = pathlib.Path(d) / "h.bin"
        _jlink([f"savebin {hp} 0x{a['mt']:08X} 0x{HDR_WORDS*4:X}"])
        if not hp.exists():
            raise RuntimeError("J-Link read failed - board connected & flashed (env:mic_test)?")
        h = dict(zip(_HKEYS, np.fromfile(hp, dtype="<u4").tolist()))
    if h["magic"] != 0x6D696354:
        raise RuntimeError(f"bad magic 0x{h['magic']:08X} - wrong build flashed? expect env:mic_test")
    return h

def read_frame():
    """Read header (for sizes) + pcm + pdm buffers over J-Link."""
    h = read_header(); a = _syms()
    with tempfile.TemporaryDirectory() as d:
        pp = pathlib.Path(d) / "p.bin"; dp = pathlib.Path(d) / "d.bin"
        _jlink([f"savebin {pp} 0x{a['pcm_buf']:08X} 0x{h['n_pcm']*2:X}",
                f"savebin {dp} 0x{a['pdm_buf']:08X} 0x{h['n_pdm']:X}"])
        pcm = np.fromfile(pp, dtype="<i2").astype(np.float64)
        pdm_b = np.fromfile(dp, dtype="<u1")
    return {"h": h, "pcm": pcm, "pdm": pdm_b}

# ------------------------------------------------------------------- analysis
def _spec(ax, x, fs, title, vmin, vmax):
    nps = int(min(256, max(32, len(x) // 3)))
    f, tt, Sxx = signal.spectrogram(x - np.mean(x), fs=fs, nperseg=nps, noverlap=nps*3//4)
    ax.pcolormesh(tt, f, 10*np.log10(Sxx + 1e-12), shading="auto", cmap="magma",
                  vmin=vmin, vmax=vmax)
    ax.set_ylim(0, min(4687, fs/2)); ax.set_title(title, fontsize=10); ax.set_ylabel("Hz")

def analyze_and_plot(stim, stim_fs, pcm_fw, pdm_raw, title, out):
    """stim: played PCM; pcm_fw: firmware sinc1 decode @9375; pdm_raw: raw PDM bytes (or None)."""
    yp = pdm.decode_proper(pdm_raw) if pdm_raw is not None and len(pdm_raw) else None
    stim_ds = (signal.resample_poly(stim, PCM_HZ, stim_fs) if stim is not None else None)
    # shared dB color scale across panels for honest comparison
    peaks = [10*np.log10(signal.welch(s-np.mean(s), PCM_HZ, nperseg=256)[1].max()+1e-12)
             for s in (stim_ds, pcm_fw, yp) if s is not None]
    vmax = max(peaks); vmin = vmax - 70
    fig, ax = plt.subplots(2, 2, figsize=(13, 8.6))
    if stim_ds is not None:
        _spec(ax[0, 0], stim_ds, PCM_HZ, "1) stimulus (played -> 9375 Hz)", vmin, vmax)
    else:
        ax[0, 0].axis("off")
    _spec(ax[0, 1], pcm_fw, PCM_HZ, "2) mic via FIRMWARE decode (sinc^1, no DC block)", vmin, vmax)
    if yp is not None:
        _spec(ax[1, 0], yp, PCM_HZ, "3) same raw PDM via PROPER decode (sinc^4 + DC block)", vmin, vmax)
    else:
        ax[1, 0].axis("off")
    # PSD overlay - the noise-floor gap is the firmware-decimator penalty
    a = ax[1, 1]
    if stim_ds is not None:
        f0, p0 = pdm.welch_psd(stim_ds); a.plot(f0, p0, color=S.DIM, lw=1, label="stimulus")
    ff, pf = pdm.welch_psd(pcm_fw); a.plot(ff, pf, color=S.RED, lw=1.4, label="firmware sinc^1")
    if yp is not None:
        fp, pp = pdm.welch_psd(yp); a.plot(fp, pp, color=S.TEAL7, lw=1.4, label="proper sinc^4")
        pen = pdm.inband_noise_floor_db(pcm_fw, PCM_HZ, []) - pdm.inband_noise_floor_db(yp, PCM_HZ, [])
        a.set_title(f"4) PSD - firmware noise floor ~ {pen:+.0f} dB worse", fontsize=10)
    else:
        a.set_title("4) PSD", fontsize=10)
    a.set_xlim(0, 4687); a.set_xlabel("Hz"); a.set_ylabel("dB"); a.legend(fontsize=8); a.grid(alpha=0.4)
    fig.suptitle(title, y=0.995)
    S.footer(fig, "analysis/acoustic/mic_bench.py", light=True)
    fig.tight_layout(rect=[0, 0.01, 1, 0.96]); FIGS.mkdir(exist_ok=True)
    fig.savefig(out, dpi=140); print("wrote", out)

# ------------------------------------------------------------------ commands
def cmd_sim(args):
    x, fs = wav_read(args.wav)
    x = x[:int(args.sec * fs)]
    x3 = signal.resample_poly(x, pdm.PDM_CLK_HZ, fs) * args.gain
    pdm_bytes = pdm.sigma_delta_modulate(x3, order=2)
    pcm_fw = pdm.decode_sinc1(pdm_bytes)
    name = pathlib.Path(args.wav).stem
    analyze_and_plot(x, fs, pcm_fw, pdm_bytes, f"SIM (modeled mic): {name}",
                     FIGS / f"AC2_sim_{name}.png")

def cmd_grab(args):
    fr = read_frame(); h = fr["h"]
    print(f"seq={h['seq']} rms_sq={h['rms_sq']} floor={h['noise_floor_sq']} "
          f"event={h['event']} err={h['err']} up={h['uptime_s']}s magic=0x{h['magic']:08X}")
    if args.out:
        np.savez(args.out, **fr["h"], pcm=fr["pcm"], pdm=fr["pdm"]); print("saved", args.out)

def cmd_probe(args):
    proc = subprocess.Popen(["afplay", args.wav])     # play (non-blocking)
    time.sleep(args.delay)                             # let it ramp into the loud part
    fr = None                                          # grab N frames, keep the loudest
    for _ in range(args.frames):                       # (voice is intermittent - dodge pauses)
        f = read_frame()
        if fr is None or f["h"]["rms_sq"] > fr["h"]["rms_sq"]:
            fr = f
    proc.terminate()                                   # stop (no need to play the whole file)
    x, fs = wav_read(args.wav); name = pathlib.Path(args.wav).stem
    (HERE / "data").mkdir(exist_ok=True)            # keep the raw arrays for offline fidelity work
    np.savez(HERE / "data" / f"frame_{name}.npz", pcm=fr["pcm"], pdm=fr["pdm"], **fr["h"])
    print(f"loudest frame seq={fr['h']['seq']} rms_sq={fr['h']['rms_sq']} event={fr['h']['event']}")
    analyze_and_plot(x, fs, fr["pcm"], fr["pdm"], f"PROBE (real mic): {name}",
                     FIGS / f"AC2_probe_{name}.png")

def cmd_sweep(args):
    """Descending level staircase -> detector transfer curve + threshold + false-positives."""
    fs = 48000; f0 = args.freq; Ts = args.step_sec
    levels = [0.0, 0.0, 0.9, 0.5, 0.28, 0.16, 0.09, 0.05, 0.028, 0.015, 0.008, 0.0, 0.0]
    t = np.arange(int(Ts * fs)) / fs; tone = np.sin(2*np.pi*f0*t)
    wav_write("/tmp/staircase.wav", np.concatenate([a*tone for a in levels]), fs)
    total = len(levels) * Ts
    print(f"playing {f0:.0f} Hz staircase, {len(levels)} steps x {Ts}s = {total:.0f}s; polling detector...")
    rows = {}; t0 = time.time()
    proc = subprocess.Popen(["afplay", "/tmp/staircase.wav"])
    while time.time() - t0 < total + 1:
        try: h = read_header()
        except Exception: continue
        tt = time.time() - t0
        rows.setdefault(h["seq"], (tt, h["rms_sq_var"], h["noise_floor_sq"], h["event"]))
    proc.wait()
    d = np.array([[v[0], v[1], v[2], v[3]] for v in rows.values()])
    d = d[d[:, 0].argsort()]
    tt, rms, floor, ev = d[:, 0], d[:, 1], d[:, 2], d[:, 3]
    thr = 16.0 * floor
    lvl = np.array([levels[min(len(levels)-1, int(x // Ts))] for x in tt])
    np.savetxt(HERE / "data" / f"sweep_dcblock_{int(f0)}hz.csv",
               np.c_[tt, lvl, rms, floor, thr, ev], delimiter=",",
               header="t_s,played_level,rms_sq_var,noise_floor_sq,threshold,event", comments="")
    fp = int(((lvl == 0) & (ev == 1)).sum()); nq = int((lvl == 0).sum())
    print(f"frames={len(tt)}  false-positives at silence={fp}/{nq}  "
          f"floor range={floor.min():.0f}..{floor.max():.0f}")

    fig, ax = plt.subplots(1, 2, figsize=(14, 5.6))
    a = ax[0]
    a.semilogy(tt, np.maximum(rms, 1), "-o", color=S.RED, ms=4, lw=1.5, label="rms_sq_var (DC-blocked)")
    a.semilogy(tt, np.maximum(thr, 1), "--", color=S.WARM, lw=1.5, label="threshold = 16xfloor")
    a.semilogy(tt, np.maximum(floor, 1), ":", color=S.TEAL7, lw=1.5, label="noise_floor_sq")
    for k in range(len(levels)+1):
        a.axvline(k*Ts, color=S.GRID, lw=0.6)
    for x, e in zip(tt, ev):
        if e: a.axvspan(x-0.4, x+0.4, color=S.RED, alpha=0.06)
    a.set_xlabel("time (s)"); a.set_ylabel("energy (mean-square, log)")
    a.set_title(f"(a) {f0:.0f} Hz descending staircase - detector dynamics")
    a.legend(fontsize=8, loc="upper right"); a.grid(True, which="both", alpha=0.3)
    a2 = a.twinx(); a2.plot(tt, lvl, color=S.DIM, lw=1, alpha=0.5)
    a2.set_ylabel("played level", color=S.DIM); a2.set_ylim(-0.05, 1.0)

    a = ax[1]
    m = lvl > 0
    a.scatter(lvl[m & (ev == 0)], np.maximum(rms[m & (ev == 0)], 1), c=S.DIM, s=36, label="event=0")
    a.scatter(lvl[m & (ev == 1)], np.maximum(rms[m & (ev == 1)], 1), c=S.RED, s=42, marker="^", label="event=1")
    a.axhline(np.median(thr), ls="--", color=S.WARM, lw=1.4, label=f"median threshold ~ {np.median(thr):.0f}")
    qfloor = float(np.median(rms[lvl == 0])) if (lvl == 0).any() else float("nan")
    a.axhline(qfloor, ls=":", color=S.TEAL7, lw=1.4, label=f"silence rms_sq ~ {qfloor:.0f}")
    a.set_xscale("log"); a.set_yscale("log")
    a.set_xlabel("played level (amplitude, log)"); a.set_ylabel("rms_sq (log)")
    a.set_title("(b) Detector transfer curve - where the trigger flips")
    a.legend(fontsize=8); a.grid(True, which="both", alpha=0.3)
    S.footer(fig, "analysis/acoustic/mic_bench.py sweep", light=True)
    fig.suptitle(f"DC-blocked detector level sweep @ {f0:.0f} Hz (board #2)", y=0.99)
    fig.tight_layout(rect=[0, 0.01, 1, 0.95]); FIGS.mkdir(exist_ok=True)
    out = FIGS / f"AC5_sweep_dcblock_{int(f0)}hz.png"; fig.savefig(out, dpi=140); print("wrote", out)

def cmd_monitor(args):
    print("seq  rms_sq  rms_sq_var(DCblk)  noise_floor  event  err   (Ctrl-C to stop)")
    last = -1
    for _ in range(args.n):
        try:
            h = read_header()
        except Exception as e:
            print("read err:", e); time.sleep(1); continue
        if h["seq"] != last:
            last = h["seq"]
            print(f"{h['seq']:4d} {h['rms_sq']:7d} {h.get('rms_sq_var',0):14d}    "
                  f"{h['noise_floor_sq']:11d} {h['event']:5d} {h['err']:4d}")
        time.sleep(args.interval)

def cmd_flash(args):
    pio = pathlib.Path.home() / ".platformio/penv/bin/pio"
    subprocess.run([str(pio), "run", "-e", "mic_test", "-t", "upload"], cwd=ROOT / "firmware")

def main():
    import matplotlib.pyplot as _plt; globals()["plt"] = _plt
    ap = argparse.ArgumentParser(description="Stratolink mic bench harness")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("gen").set_defaults(fn=lambda a: gen_stimuli())
    sub.add_parser("flash").set_defaults(fn=cmd_flash)
    m = sub.add_parser("monitor"); m.add_argument("--n", type=int, default=10**6)
    m.add_argument("--interval", type=float, default=1.0); m.set_defaults(fn=cmd_monitor)
    g = sub.add_parser("grab"); g.add_argument("--out"); g.set_defaults(fn=cmd_grab)
    p = sub.add_parser("probe"); p.add_argument("wav"); p.add_argument("--delay", type=float, default=1.0)
    p.add_argument("--frames", type=int, default=5); p.set_defaults(fn=cmd_probe)
    s = sub.add_parser("sim"); s.add_argument("wav"); s.add_argument("--sec", type=float, default=1.0)
    s.add_argument("--gain", type=float, default=0.5); s.set_defaults(fn=cmd_sim)
    w = sub.add_parser("sweep"); w.add_argument("--freq", type=float, default=1000.0)
    w.add_argument("--step-sec", type=float, default=4.0, dest="step_sec"); w.set_defaults(fn=cmd_sweep)
    args = ap.parse_args()
    (HERE / "data").mkdir(exist_ok=True)
    args.fn(args)

if __name__ == "__main__":
    main()
