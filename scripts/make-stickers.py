#!/usr/bin/env python3
"""
Cut transparent stickers from launch photos using rembg.

Setup (once, not committed):
  python3 -m venv .venv-stickers
  .venv-stickers/bin/pip install 'rembg[cpu]' Pillow

Usage:
  .venv-stickers/bin/python scripts/make-stickers.py
  .venv-stickers/bin/python scripts/make-stickers.py --only payload
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image
from rembg import remove

ROOT = Path(__file__).resolve().parents[1]
SRC = Path("/Users/shepherdkruse/Desktop/Stratolink Images")
OUT = ROOT / "web" / "public" / "stickers"
MAX_EDGE = 1400

# name -> (source file, optional crop box as fractions L,T,R,B of width/height)
JOBS: dict[str, tuple[str, tuple[float, float, float, float] | None]] = {
    # Clean payload on desk — Meet Stratolink
    "payload": ("IMG_0054.jpeg", (0.28, 0.18, 0.78, 0.88)),
    # Dual payloads on mat — crop left unit
    "payload-pair": ("IMG_0919.jpg", (0.02, 0.18, 0.52, 0.82)),
    # Held translucent balloon at golden hour
    "balloon-held": ("IMG_3458.jpeg", (0.28, 0.02, 0.78, 0.72)),
    # Balloon ascending over park
    "balloon-ascent": ("launch.jpeg", (0.18, 0.0, 0.55, 0.55)),
    # Prep: person holding clear balloon
    "balloon-prep": ("IMG_4860.jpeg", (0.22, 0.0, 0.78, 0.78)),
    # Launch team looking up
    "launch-team": ("launch.jpeg", (0.28, 0.42, 0.78, 0.98)),
    # Classroom / group with balloon
    "classroom-launch": ("IMG_4856.jpeg", (0.28, 0.08, 0.72, 0.92)),
    # Hand holding thin PCB
    "pcb-hand": ("IMG_9487.jpeg", (0.0, 0.15, 0.72, 0.85)),
}


def frac_crop(im: Image.Image, box: tuple[float, float, float, float]) -> Image.Image:
    w, h = im.size
    l, t, r, b = box
    return im.crop((int(l * w), int(t * h), int(r * w), int(b * h)))


def tight_alpha(im: Image.Image, pad: int = 12) -> Image.Image:
    if im.mode != "RGBA":
        im = im.convert("RGBA")
    alpha = im.split()[-1]
    bbox = alpha.getbbox()
    if not bbox:
        return im
    l, t, r, b = bbox
    l = max(0, l - pad)
    t = max(0, t - pad)
    r = min(im.width, r + pad)
    b = min(im.height, b + pad)
    return im.crop((l, t, r, b))


def downscale(im: Image.Image, max_edge: int = MAX_EDGE) -> Image.Image:
    w, h = im.size
    m = max(w, h)
    if m <= max_edge:
        return im
    scale = max_edge / m
    return im.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)


def process(name: str, filename: str, crop: tuple[float, float, float, float] | None) -> Path:
    src = SRC / filename
    if not src.exists():
        raise FileNotFoundError(src)
    im = Image.open(src).convert("RGB")
    if crop:
        im = frac_crop(im, crop)
    # Shrink before rembg for speed on huge phone photos
    im = downscale(im, 2000)
    cut = remove(im)
    if not isinstance(cut, Image.Image):
        cut = Image.open(cut).convert("RGBA")
    else:
        cut = cut.convert("RGBA")
    cut = tight_alpha(cut)
    cut = downscale(cut, MAX_EDGE)
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / f"{name}.png"
    cut.save(dest, "PNG", optimize=True)
    print(f"wrote {dest.relative_to(ROOT)} ({cut.size[0]}x{cut.size[1]})")
    return dest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*", help="Only process these sticker names")
    args = parser.parse_args()
    names = args.only or list(JOBS.keys())
    for name in names:
        if name not in JOBS:
            print(f"unknown job: {name}", file=sys.stderr)
            return 1
        filename, crop = JOBS[name]
        process(name, filename, crop)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
