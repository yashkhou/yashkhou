#!/usr/bin/env python3
"""Bake the static inputs for tools/build_assets.py into tools/src/pack.json.

Run this only when a font or the photo changes. It needs fontTools, brotli and Pillow
(pip install fonttools brotli pillow). The daily generator itself is stdlib-only: it reads
this pack instead of subsetting fonts, so the GitHub Action needs no installs and the
output is byte-identical wherever it runs.

The pack holds, per face: a pinned static instance subset to a fixed charset (printable
ASCII plus a few typographic marks) as base64 woff2, plus advance widths for measuring.
It also holds a small square avatar as base64 webp.
"""
import base64, io, json
from pathlib import Path
from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from PIL import Image

SRC = Path(__file__).resolve().parent / "src"
CHARSET = "".join(chr(c) for c in range(32, 127)) + "·…→’‘“”–—×•"
FACES = {
    # Fraunces and Onest match yashkhou.com; Geist Mono is for hashes and tool names.
    "display": ("fraunces-normal.woff2", {"opsz": 144, "wght": 420, "SOFT": 100, "WONK": 1}),
    "italic": ("fraunces-italic.woff2", {"opsz": 144, "wght": 400, "SOFT": 100, "WONK": 1}),
    "sans": ("onest-normal.woff2", {"wght": 450}),
    "sansBold": ("onest-normal.woff2", {"wght": 620}),
    "mono": ("geist-mono.woff2", {"wght": 440}),
}


def bake(file, axes):
    inst = instantiateVariableFont(TTFont(SRC / file), axes)
    buf = io.BytesIO()
    inst.save(buf)
    buf.seek(0)
    f = TTFont(buf)
    cmap, hmtx, upm = f.getBestCmap(), f["hmtx"], f["head"].unitsPerEm
    chars = "".join(c for c in CHARSET if ord(c) in cmap)
    adv = {c: round(hmtx[cmap[ord(c)]][0] * 1000 / upm) for c in chars}
    asc = round(f["hhea"].ascent * 1000 / upm)
    cap = round(getattr(f["OS/2"], "sCapHeight", 0) * 1000 / upm)
    opts = subset.Options()
    opts.flavor, opts.layout_features, opts.name_IDs = "woff2", ["kern", "liga", "calt", "tnum", "lnum"], []
    opts.notdef_outline = True
    s = subset.Subsetter(opts)
    s.populate(text=chars)
    s.subset(f)
    out = io.BytesIO()
    f.flavor = "woff2"
    f.save(out)
    return {"woff2": base64.b64encode(out.getvalue()).decode(), "adv": adv, "ascent": asc, "cap": cap}


def avatar(px=128):
    im = Image.open(SRC / "josh-cutout.png").convert("RGBA")
    w, h = im.size
    im = im.crop((int(w * .18), 0, int(w * .82), int(w * .64))).resize((px, px), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=84, method=6)
    return base64.b64encode(buf.getvalue()).decode()


if __name__ == "__main__":
    pack = {"charset": CHARSET, "faces": {k: bake(*v) for k, v in FACES.items()}, "avatar": avatar()}
    out = SRC / "pack.json"
    out.write_text(json.dumps(pack, separators=(",", ":"), sort_keys=True))
    for k, v in pack["faces"].items():
        print(f"{k:9s} {len(v['woff2']) / 1024:5.1f} KB b64, {len(v['adv'])} glyphs")
    print(f"avatar    {len(pack['avatar']) / 1024:5.1f} KB b64 -> {out.name} {out.stat().st_size / 1024:.0f} KB")
