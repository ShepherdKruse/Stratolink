#!/usr/bin/env python3
"""
Capture audio from Stratolink T3902 microphone via J-Link.

Expects audio_capture.cpp firmware to be running on the target.
Reads the decimated PCM buffer from RAM and saves as a WAV file.

Usage:
  1. Copy test/audio_capture.cpp to src/main.cpp
  2. pio run -t upload
  3. python test/capture_audio.py [output.wav]
"""
import sys, os, struct, subprocess, shutil, wave, array

CAPTURE_MAGIC  = 0x41554449   # "AUDI" — must match firmware
HEADER_SIZE    = 20           # magic(4) + rate(4) + total(4) + captured(4) + done(1) + pad(3)
RAM_BASE       = 0x20000000
RAM_SIZE       = 0x10000      # 64 KB
OUTPUT_DEFAULT = "stratolink_mic.wav"

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


def jlink_run(script_text, timeout=30):
    jlink = find_jlink()
    if not jlink:
        print("ERROR: J-Link Commander not found.")
        sys.exit(1)
    tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp_audio.jlink")
    with open(tmp, "w") as f:
        f.write(script_text)
    try:
        return subprocess.run(
            [jlink, "-device", "STM32WLE5CC", "-if", "SWD", "-speed", "4000",
             "-autoconnect", "1", "-CommanderScript", tmp],
            capture_output=True, text=True, timeout=timeout
        )
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def parse_mem8(stdout, count):
    """Parse J-Link mem8 hex output into bytes."""
    out = []
    for line in stdout.splitlines():
        line = line.strip()
        if "=" not in line:
            continue
        addr_part, _, data_part = line.partition("=")
        try:
            int(addr_part.strip(), 16)
        except ValueError:
            continue
        for tok in data_part.split():
            tok = tok.strip().upper()
            if len(tok) == 2 and all(c in "0123456789ABCDEF" for c in tok):
                out.append(int(tok, 16))
    return bytes(out[:count])


def main():
    output_path = sys.argv[1] if len(sys.argv) > 1 else OUTPUT_DEFAULT

    print("Resetting target and waiting for capture...")

    # Reset, run for 8s (5s capture + 3s margin), halt, dump full RAM
    wait_ms = 8000
    result = jlink_run(
        f"r\ngo\nsleep {wait_ms}\nh\n"
        f"mem8 0x{RAM_BASE:08X} 0x{RAM_SIZE:X}\n"
        f"q\n",
        timeout=wait_ms // 1000 + 15
    )

    ram = parse_mem8(result.stdout, RAM_SIZE)
    if len(ram) < 1024:
        print(f"ERROR: Only read {len(ram)} bytes from RAM.")
        sys.exit(1)

    # Find capture header by magic value
    magic_bytes = struct.pack('<I', CAPTURE_MAGIC)
    hdr_offset = ram.find(magic_bytes)
    if hdr_offset < 0:
        print("ERROR: Capture header (magic 0x41554449) not found in RAM.")
        print("Ensure audio_capture firmware is loaded and target ran to completion.")
        sys.exit(1)

    # Parse header
    magic, sample_rate, total_samples, samples_captured, done = struct.unpack_from(
        '<IIIIB', ram, hdr_offset
    )

    print(f"Header at 0x{RAM_BASE + hdr_offset:08X}: "
          f"{sample_rate} Hz, {total_samples} samples, "
          f"captured {samples_captured}, done=0x{done:02X}")

    if done != 0xAA:
        print(f"WARNING: Capture incomplete ({samples_captured}/{total_samples} samples)")

    # Audio buffer follows header
    buf_offset = hdr_offset + HEADER_SIZE
    avail = min(total_samples, len(ram) - buf_offset)
    if avail < total_samples:
        print(f"WARNING: Audio buffer truncated ({avail}/{total_samples} bytes in dump)")
        total_samples = avail

    raw = ram[buf_offset:buf_offset + total_samples]

    # Convert to float, remove DC offset
    samples = [float(b) for b in raw]
    dc = sum(samples) / len(samples)
    samples = [s - dc for s in samples]

    # Normalize to ~90% of int16 range
    peak = max(abs(s) for s in samples) if samples else 0
    if peak < 1.0:
        print("WARNING: Audio appears silent (constant value).")
        scale = 1.0
    else:
        scale = 29000.0 / peak

    # Convert to signed 16-bit PCM
    pcm = array.array('h', [
        max(-32768, min(32767, int(s * scale))) for s in samples
    ])

    # Write WAV
    with wave.open(output_path, 'w') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())

    duration = total_samples / sample_rate
    print(f"Saved {output_path}: {duration:.1f}s, {sample_rate} Hz, 16-bit mono")
    print(f"DC offset: {dc:.1f} (removed)")
    print(f"Peak: {peak:.1f} -> scale {scale:.1f}x")


if __name__ == "__main__":
    main()
