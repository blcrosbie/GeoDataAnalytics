#!/usr/bin/env python3
"""
Generate a LUT gradient PNG from a list of hex colors.

- Produces a horizontal gradient of size (width x height)
- Uses gamma-correct interpolation (sRGB <-> linear) for smoother gradients
- Great for Mapbox LUT-style workflows
"""

from __future__ import annotations
from PIL import Image
import math

# -----------------------------
# CONFIG
# -----------------------------
OUT_PATH = "neutral.png"

# Typical LUT width: 256, 512, 1024
WIDTH  = 1024
HEIGHT = 32  # 1 is fine for a LUT; taller is easier to preview

# Your gradient "stops" (edit these)
HEX_STOPS = [
    "#14b8a6", # font
    "#171557", # space
    "#fafafa", # major roads
    "#ea580c", # int'l borderlines
    "#006527", # map greenery
    "#FFEB9B", # map deserty
    "#0ef4f8"  # Ocean
]

# Attempt 4
# HEX_STOPS = [
#     "#02285D", # font
#     "#030432", # space
#     "#5eead4",
#     "#f6b645", # borderlines
#     "#14b8a6", 
#     "#0d4f4f",
#     "#303030"  # Ocean
# ]

# Attempt 3
# HEX_STOPS = [
#     "#02285D", # font
#     "#030432", # space
#     "#5eead4",
#     "#f6b645", 
#     "#ea580c", 
#     "#6ee7b7",
#     "#bdbdbd"  # Ocean
# ]

# Attempt 2
# HEX_STOPS = [
#     "#14b8a6", # Ocean
#     "#0d4f4f", # space ?
#     "#5eead4",
#     "#f6b645", 
#     "#ea580c", 
#     "6ee7b7",
#     "#14b8a6"  # font?
# ]

# Attempt 1
# HEX_STOPS = [
#     "#0d4f4f", # Ocean
#     "#14b8a6", # space ?
#     "#5eead4",
#     "#f6b645", 
#     "#ea580c", 
#     "6ee7b7",
#     "#0d4f4f"  # font?
# ]

# If True, treat stops as evenly spaced.
# If False, you can provide explicit positions via STOPS_WITH_POS below.
EVEN_SPACING = True

# Optional explicit positions (0..1). Only used if EVEN_SPACING = False.
# Example:
# STOPS_WITH_POS = [
#   (0.0, "#000000"), (0.2, "#2b2bff"), (0.55, "#00ff88"), (1.0, "#ffffff")
# ]
STOPS_WITH_POS = []


# -----------------------------
# COLOR HELPERS
# -----------------------------
def hex_to_srgb01(h: str) -> tuple[float, float, float]:
    h = h.strip().lstrip("#")
    if len(h) != 6:
        raise ValueError(f"Expected #RRGGBB, got: {h}")
    r = int(h[0:2], 16) / 255.0
    g = int(h[2:4], 16) / 255.0
    b = int(h[4:6], 16) / 255.0
    return (r, g, b)

def srgb_to_linear(c: float) -> float:
    # sRGB transfer function
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4

def linear_to_srgb(c: float) -> float:
    c = max(0.0, min(1.0, c))
    if c <= 0.0031308:
        return 12.92 * c
    return 1.055 * (c ** (1.0 / 2.4)) - 0.055

def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t

def interp_gamma_correct(c0_srgb: tuple[float,float,float],
                         c1_srgb: tuple[float,float,float],
                         t: float) -> tuple[int,int,int]:
    # Convert to linear-light space
    c0_lin = tuple(srgb_to_linear(x) for x in c0_srgb)
    c1_lin = tuple(srgb_to_linear(x) for x in c1_srgb)

    # Interpolate in linear
    out_lin = (
        lerp(c0_lin[0], c1_lin[0], t),
        lerp(c0_lin[1], c1_lin[1], t),
        lerp(c0_lin[2], c1_lin[2], t),
    )

    # Convert back to sRGB and quantize
    out_srgb = tuple(linear_to_srgb(x) for x in out_lin)
    return tuple(int(round(max(0,min(1,x)) * 255.0)) for x in out_srgb)


# -----------------------------
# BUILD STOPS
# -----------------------------
if EVEN_SPACING:
    if len(HEX_STOPS) < 2:
        raise ValueError("Need at least 2 colors in HEX_STOPS.")
    stops = [(i / (len(HEX_STOPS)-1), HEX_STOPS[i]) for i in range(len(HEX_STOPS))]
else:
    if not STOPS_WITH_POS or len(STOPS_WITH_POS) < 2:
        raise ValueError("Provide at least 2 (pos,color) entries in STOPS_WITH_POS.")
    stops = sorted(STOPS_WITH_POS, key=lambda x: x[0])
    if stops[0][0] != 0.0 or stops[-1][0] != 1.0:
        raise ValueError("Explicit stops should start at 0.0 and end at 1.0.")

# Pre-convert stop colors
stops_rgb = [(pos, hex_to_srgb01(h)) for pos, h in stops]


# -----------------------------
# RENDER GRADIENT
# -----------------------------
img = Image.new("RGB", (WIDTH, HEIGHT))
px = img.load()

# Walk through pixels, find which segment we're in, interpolate
j = 0
for x in range(WIDTH):
    u = x / (WIDTH - 1)

    # Advance segment pointer
    while j < len(stops_rgb) - 2 and u > stops_rgb[j + 1][0]:
        j += 1

    p0, c0 = stops_rgb[j]
    p1, c1 = stops_rgb[j + 1]

    # Normalize t within this segment
    if p1 == p0:
        t = 0.0
    else:
        t = (u - p0) / (p1 - p0)

    rgb = interp_gamma_correct(c0, c1, t)

    for y in range(HEIGHT):
        px[x, y] = rgb

img.save(OUT_PATH, "PNG")
print(f"Saved {OUT_PATH} ({WIDTH}x{HEIGHT}) with {len(stops)} stops.")
