"""Derive an efficient mobile crop of the existing licensed Amaris hero art.

Uses the existing desktop WebP source; no external assets, services or API keys.
CSS object-position 62% center on the desktop hero corresponds to the
ImageOps centering fraction for the portrait crop.
"""
from pathlib import Path

from PIL import Image, ImageOps

ASSETS = Path(__file__).resolve().parents[2] / "public"
source = ASSETS / "amaris-math-hero.webp"
destination = ASSETS / "amaris-math-hero-mobile.webp"

with Image.open(source) as original:
    if original.format != "WEBP":
        raise SystemExit("Expected a genuine WebP source")
    crop = ImageOps.fit(
        original.convert("RGB"),
        (640, 1240),
        method=Image.Resampling.LANCZOS,
        centering=(0.62, 0.5),
    )
    crop.save(destination, "WEBP", quality=66, method=6)

original_size = source.stat().st_size
mobile_size = destination.stat().st_size
print(f"Hero mobile WebP: {mobile_size} bytes from {original_size}-byte original")
if mobile_size >= original_size:
    raise SystemExit("Mobile hero must be smaller than the source")
with Image.open(destination) as preview:
    if preview.size != (640, 1240) or preview.format != "WEBP":
        raise SystemExit("Invalid mobile hero image output")
