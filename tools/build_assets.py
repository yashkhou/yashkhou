#!/usr/bin/env python3
"""Build the animated SVGs for the profile README, in light and dark versions.

Fonts are pinned to static instances, subset to the glyphs each SVG uses and embedded,
so GitHub renders them without loading anything external. Animation is SMIL only (no JS).
Run: python3 tools/build_assets.py
"""
import base64, io, math
from pathlib import Path
from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC, OUT = ROOT / "tools" / "src", ROOT / "assets"

LIGHT = dict(name="light", bg="#FBF8F3", ink="#1E1B18", ink2="#463F38", mute="#6A6158", line="#E4DACB",
             card="#FFFEFC", acc="#E5533D", accSoft="#FCE3DA", green="#2C7A50", greenSoft="#DFF1E5",
             glow="#F2A93B", grain=(0, .07), pill="#1E1B18", pillText="#FBF8F3")
DARK = dict(name="dark", bg="#181614", ink="#F6F0E7", ink2="#D8CFC3", mute="#A3998D", line="#3A352F",
            card="#221F1C", acc="#EF6A52", accSoft="#3B231D", green="#5DB887", greenSoft="#1B2D22",
            glow="#E0892F", grain=(1, .08), pill="#F6F0E7", pillText="#181614")

# ---------- fonts ----------
FACES = {
    "display": ("fraunces-normal.woff2", {"opsz": 144, "wght": 420, "SOFT": 100, "WONK": 1}),
    "displayItalic": ("fraunces-italic.woff2", {"opsz": 144, "wght": 400, "SOFT": 100, "WONK": 1}),
    "serif": ("fraunces-normal.woff2", {"opsz": 48, "wght": 450, "SOFT": 100, "WONK": 0}),
    "sans": ("onest-normal.woff2", {"wght": 450}),
    "sansBold": ("onest-normal.woff2", {"wght": 620}),
}
_inst = {}


def face(key):
    if key not in _inst:
        file, axes = FACES[key]
        _inst[key] = instantiateVariableFont(TTFont(SRC / file), axes)
    return _inst[key]


def width(key, text, size):
    f = face(key)
    cmap, hmtx, upm = f.getBestCmap(), f["hmtx"], f["head"].unitsPerEm
    return sum(hmtx[cmap.get(ord(c), cmap[ord("?")])][0] for c in text) * size / upm


def wrap(key, text, size, max_w):
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if cur and width(key, trial, size) > max_w:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    return lines + [cur]


def font_css(used):
    """used: {face_key: text}. Returns @font-face rules with subset woff2 embedded."""
    rules = []
    for key, text in used.items():
        f = TTFont()
        buf = io.BytesIO()
        face(key).save(buf)
        buf.seek(0)
        f = TTFont(buf)
        opts = subset.Options()
        opts.flavor, opts.layout_features, opts.name_IDs = "woff2", ["kern", "liga", "calt"], []
        s = subset.Subsetter(opts)
        s.populate(text=text + " ")
        s.subset(f)
        out = io.BytesIO()
        f.flavor = "woff2"
        f.save(out)
        b64 = base64.b64encode(out.getvalue()).decode()
        rules.append(f"@font-face{{font-family:jk-{key};src:url(data:font/woff2;base64,{b64}) format('woff2')}}")
    return "".join(rules)


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def photo_b64(w):
    im = Image.open(SRC / "josh-cutout.png").convert("RGBA")
    im = im.resize((w, round(im.height * w / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=86, method=6)
    return im.size, base64.b64encode(buf.getvalue()).decode()


def grain(t, w, h, rx):
    return (f'<filter id="grain"><feTurbulence type="fractalNoise" baseFrequency=".9" numOctaves="2" stitchTiles="stitch"/>'
            f'<feColorMatrix values="0 0 0 0 {t["grain"][0]}  0 0 0 0 {t["grain"][0]}  0 0 0 0 {t["grain"][0]}  0 0 0 {t["grain"][1]:.2f} 0"/></filter>'), \
           f'<rect width="{w}" height="{h}" rx="{rx}" filter="url(#grain)"/>'


# ---------- blob ----------
def blob_path(cx, cy, r, phase, n=10, a1=.04, a2=.028):
    pts = []
    for k in range(n):
        th = 2 * math.pi * k / n - math.pi / 2
        rr = r * (1 + a1 * math.sin(2 * th + phase) + a2 * math.sin(3 * th - 1.7 * phase))
        pts.append((cx + rr * math.cos(th), cy + rr * math.sin(th)))
    d = f"M{pts[0][0]:.1f} {pts[0][1]:.1f}"
    for i in range(n):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d += f"C{c1[0]:.1f} {c1[1]:.1f} {c2[0]:.1f} {c2[1]:.1f} {p2[0]:.1f} {p2[1]:.1f}"
    return d + "Z"


def morph(cx, cy, r, dur, offset=0.0, **kw):
    frames = [blob_path(cx, cy, r, offset + p, **kw) for p in (0, 2.1, 4.2, 0)]
    return frames[0], (f'<animate attributeName="d" dur="{dur}s" repeatCount="indefinite" calcMode="spline" '
                       f'keyTimes="0;.33;.66;1" keySplines=".45 0 .55 1;.45 0 .55 1;.45 0 .55 1" values="{";".join(frames)}"/>')


def rise(delay, dist=36, dur=1.1):
    """Entrance: starts hidden at t=0 so there is no flash, then rises into place."""
    k = delay / (delay + dur)
    total = delay + dur
    return (f'<animate attributeName="opacity" dur="{total:.2f}s" values="0;0;1" keyTimes="0;{k:.3f};1" fill="freeze"/>'
            f'<animateTransform attributeName="transform" type="translate" dur="{total:.2f}s" values="0 {dist};0 {dist};0 0" '
            f'keyTimes="0;{k:.3f};1" calcMode="spline" keySplines="0 0 1 1;.2 .9 .2 1" fill="freeze"/>')


# ---------- banner ----------
def banner(t):
    W, H, RX = 1280, 560, 28
    hi, im, josh = "Hi,", "I'm", "Josh."
    size = 136
    x0, base = 80, 250
    sp = width("display", " ", size)
    x_im = x0 + width("display", hi, size) + sp
    x_josh = x_im + width("display", im, size) + sp
    lede = "I build AI agents that take care of the routine work, and know when to hand over to a person."
    lsz, lmax = 29, 560
    lines = wrap("sans", lede, lsz, lmax)
    cta, link = "See my work", "yashkhou.com"
    cta_w = width("sansBold", cta, 21) + 28 + 58

    cx, cy, R = 990, 300, 196
    (pw, ph), pb = photo_b64(440)
    px, py = cx - pw * 0.49, 58
    blob0, blob_anim = morph(cx, cy, R, 7)
    echo0, echo_anim = morph(cx + 6, cy + 4, R + 18, 9, offset=1.3, a1=.05, a2=.03)
    gdef, grect = grain(t, W, H, RX)

    lede_svg = "".join(f'<text x="{x0}" y="{318 + i * 42}" class="lede">{esc(l)}</text>' for i, l in enumerate(lines))
    cy_cta = 318 + len(lines) * 42 + 26
    dots = "".join(
        f'<circle cx="{cx + 182 + i * 15}" cy="{cy - 166}" r="4.5" fill="{t["mute"]}">'
        f'<animate attributeName="opacity" values=".25;1;.25" dur="1.4s" begin="{i * .2:.1f}s" repeatCount="indefinite"/>'
        f'<animateTransform attributeName="transform" type="translate" values="0 0;0 -4;0 0" dur="1.4s" begin="{i * .2:.1f}s" repeatCount="indefinite"/></circle>'
        for i in range(3))
    css = font_css({"display": hi + im, "displayItalic": josh, "sans": lede + link, "sansBold": cta + "→"})
    hx, hy = x0 + 40, base + 4  # wave pivot: bottom of "Hi,"

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="Hi, I'm Josh. I build AI agents that take care of the routine work, and know when to hand over to a person.">
<style>{css}
.h{{font-family:jk-display;font-size:{size}px;fill:{t["ink"]};letter-spacing:-4px}}
.j{{font-family:jk-displayItalic;font-size:{size}px;fill:{t["acc"]};letter-spacing:-3px}}
.lede{{font-family:jk-sans;font-size:{lsz}px;fill:{t["ink2"]};letter-spacing:-.2px}}
.cta{{font-family:jk-sansBold;font-size:21px;fill:{t["pillText"]}}}
.link{{font-family:jk-sans;font-size:21px;fill:{t["ink"]}}}
</style>
<defs>
<radialGradient id="glow"><stop offset="0" stop-color="{t["glow"]}" stop-opacity=".42"/><stop offset=".5" stop-color="{t["acc"]}" stop-opacity=".14"/><stop offset="1" stop-color="{t["acc"]}" stop-opacity="0"/></radialGradient>
<clipPath id="card"><rect width="{W}" height="{H}" rx="{RX}"/></clipPath>
<clipPath id="pclip"><path d="{blob0}">{blob_anim}</path><rect x="{cx - 260}" y="0" width="520" height="{cy - 40}"/></clipPath>
{gdef}
</defs>
<g clip-path="url(#card)">
<rect width="{W}" height="{H}" fill="{t["bg"]}"/>
<circle cx="{cx}" cy="{cy}" r="330" fill="url(#glow)"><animate attributeName="r" values="310;350;310" dur="6s" repeatCount="indefinite" calcMode="spline" keyTimes="0;.5;1" keySplines=".45 0 .55 1;.45 0 .55 1"/></circle>
{grect}
<g>{rise(0.0)}
<g><animateTransform attributeName="transform" type="rotate" begin="1.6s" dur="7s" repeatCount="indefinite" values="0 {hx} {hy};-9 {hx} {hy};7 {hx} {hy};-4 {hx} {hy};0 {hx} {hy};0 {hx} {hy}" keyTimes="0;.05;.1;.15;.2;1"/>
<text x="{x0}" y="{base}" class="h">{hi}</text></g></g>
<g>{rise(0.12)}<text x="{x_im:.0f}" y="{base}" class="h">{im}</text></g>
<g>{rise(0.24)}<text x="{x_josh:.0f}" y="{base}" class="j">{josh}</text></g>
<g>{rise(0.42, 24)}{lede_svg}</g>
<g>{rise(0.6, 20)}
<rect x="{x0}" y="{cy_cta}" width="{cta_w:.0f}" height="56" rx="28" fill="{t["pill"]}"/>
<text x="{x0 + 28}" y="{cy_cta + 35}" class="cta">{cta}</text>
<path d="M{x0 + cta_w - 46:.0f} {cy_cta + 28}h16m-6-6 6 6-6 6" fill="none" stroke="{t["pillText"]}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>
<text x="{x0 + cta_w + 26:.0f}" y="{cy_cta + 35}" class="link">{link}</text>
<rect x="{x0 + cta_w + 26:.0f}" y="{cy_cta + 44}" width="{width("sans", link, 21):.0f}" height="2.5" rx="1" fill="{t["acc"]}"/>
</g>
<g>{rise(0.3, 30, 1.3)}
<path d="{echo0}" fill="none" stroke="{t["ink"]}" stroke-width="1.6" opacity=".38">{echo_anim}</path>
<path d="M{cx - 128} {cy + 140}L{cx - 196} {cy + 214}L{cx - 66} {cy + 176}Z" fill="{t["acc"]}"/>
<path d="{blob0}" fill="{t["acc"]}">{blob_anim}</path>
<image href="data:image/webp;base64,{pb}" x="{px:.0f}" y="{py}" width="{pw}" height="{ph}" clip-path="url(#pclip)"/>
<rect x="{cx + 164}" y="{cy - 186}" width="80" height="40" rx="20" fill="{t["card"]}" stroke="{t["line"]}" stroke-width="1.5"/>
{dots}
</g>
</g>
</svg>'''


# ---------- decision diagram ----------
MSGS = [
    ("Where's my order?", "ok", None, "It left the warehouse this morning. It'll be with you Thursday."),
    ("Can you change my refund bank account?", "hand", 1, "Wants to change refund account. Identity not verified."),
    ("My blender arrived cracked.", "ok", None, "Sorry about that. Your refund is on its way, 3–5 days."),
    ("I'm thinking of cancelling everything.", "hand", 2, "Long-time customer, sounds unhappy. Call today."),
]
STEPS = ["Read", "Protect data", "Understand", "Look up", "Check rules", "Decide"]


def windows(intervals, T):
    """Opacity animation that is 1 inside the given (start, end) seconds and 0 elsewhere, fading .35s."""
    f = .35
    kt, vals = [0.0], ["0"]
    for s, e in intervals:
        for tt, v in ((s, "0"), (s + f, "1"), (e - f, "1"), (e, "0")):
            kt.append(tt / T)
            vals.append(v)
    kt.append(1.0)
    vals.append("0")
    return f'<animate attributeName="opacity" dur="{T}s" repeatCount="indefinite" keyTimes="{";".join(f"{k:.4f}" for k in kt)}" values="{";".join(vals)}"/>'


def diagram(t):
    W, H, RX = 1280, 640, 28
    T, SLOT = 22.0, 5.5
    gdef, grect = grain(t, W, H, RX)
    track_y, x1, x6 = 300, 120, 1160
    xs = [x1 + i * (x6 - x1) / 5 for i in range(6)]
    card_y, card_h = 420, 176
    cards = {"ok": (60, 600), "hand": (680, 1220)}

    sans, bold, serif = set(), set(), set()
    out = []

    # customer bubble (top)
    bub_x, bub_y, bub_w, bub_h = 60, 70, 720, 92
    out.append(f'<text x="{bub_x}" y="{bub_y - 18}" class="lbl">Customer</text>')
    out.append(f'<path d="M{bub_x} {bub_y + 24}a24 24 0 0 1 24-24h{bub_w - 48}a24 24 0 0 1 24 24v{bub_h - 48}a24 24 0 0 1-24 24H{bub_x + 70}l-30 26 4-26h-20a24 24 0 0 1-24-24z" fill="{t["card"]}" stroke="{t["line"]}" stroke-width="1.6"/>')
    for i, (m, *_rest) in enumerate(MSGS):
        s = i * SLOT
        out.append(f'<text x="{bub_x + 30}" y="{bub_y + 57}" class="msg" opacity="0">{esc(m)}{windows([(s, s + SLOT - .1)], T)}</text>')
        serif.update(m)
    sans.update("Customer")

    # track and nodes
    out.append(f'<path d="M{x1} {track_y}H{x6}" stroke="{t["mute"]}" stroke-opacity=".5" stroke-width="3" stroke-linecap="round" stroke-dasharray="2 10"/>')
    out.append(f'<path d="M{bub_x + 60} {bub_y + bub_h + 26}V{track_y - 26}" stroke="{t["mute"]}" stroke-opacity=".5" stroke-width="3" stroke-linecap="round" stroke-dasharray="2 10"/>')
    for (lo, hi) in cards.values():
        mid = (lo + hi) / 2
        out.append(f'<path d="M{x6} {track_y}C{x6} {track_y + 60} {mid} {card_y - 70} {mid} {card_y - 8}" fill="none" stroke="{t["mute"]}" stroke-opacity=".5" stroke-width="3" stroke-linecap="round" stroke-dasharray="2 10"/>')

    t0o, t1o, t2o = .5, 2.9, 3.6  # within a slot: start track, reach Decide, land in card
    for j, x in enumerate(xs):
        times = []
        for i, (_, kind, flag, _) in enumerate(MSGS):
            tj = i * SLOT + t0o + (x - x1) / (x6 - x1) * (t1o - t0o)
            times.append((tj, "hand" if flag is not None and j >= flag else "ok"))
        # pulse ring per pass
        for tj, k in times:
            col = t["acc"] if k == "hand" else t["green"]
            a, b = tj / T, min((tj + .9) / T, .9999)
            out.append(f'<circle cx="{x:.0f}" cy="{track_y}" r="14" fill="none" stroke="{col}" stroke-width="3" opacity="0">'
                       f'<animate attributeName="r" dur="{T}s" repeatCount="indefinite" keyTimes="0;{a:.4f};{b:.4f};1" values="14;14;38;38"/>'
                       f'<animate attributeName="opacity" dur="{T}s" repeatCount="indefinite" keyTimes="0;{a:.4f};{b:.4f};1" values="0;.7;0;0"/></circle>')
        out.append(f'<circle cx="{x:.0f}" cy="{track_y}" r="13" fill="{t["card"]}" stroke="{t["ink"]}" stroke-width="2.4"/>')
        flags = [i for i, m in enumerate(MSGS) if m[2] == j]
        if flags:
            iv = [(i * SLOT + t0o + (x - x1) / (x6 - x1) * (t1o - t0o), i * SLOT + SLOT - .2) for i in flags]
            out.append(f'<circle cx="{x:.0f}" cy="{track_y}" r="6" fill="{t["acc"]}" opacity="0">{windows(iv, T)}</circle>')
        out.append(f'<text x="{x:.0f}" y="{track_y + 50}" class="step" text-anchor="middle">{STEPS[j]}</text>')
        sans.update(STEPS[j])

    # outcome cards
    for kind, (lo, hi) in cards.items():
        active = [(i * SLOT + t2o - .1, i * SLOT + SLOT - .05) for i, m in enumerate(MSGS) if m[1] == kind]
        col, soft = (t["green"], t["greenSoft"]) if kind == "ok" else (t["acc"], t["accSoft"])
        title = "Answered" if kind == "ok" else "Handed to a person"
        bold.update(title)
        out.append(f'<rect x="{lo}" y="{card_y}" width="{hi - lo}" height="{card_h}" rx="22" fill="{t["card"]}" stroke="{t["line"]}" stroke-width="1.6"/>')
        out.append(f'<rect x="{lo}" y="{card_y}" width="{hi - lo}" height="{card_h}" rx="22" fill="{soft}" stroke="{col}" stroke-width="2.4" opacity="0">{windows(active, T)}</rect>')
        out.append(f'<circle cx="{lo + 36}" cy="{card_y + 42}" r="8" fill="{col}"/>')
        out.append(f'<text x="{lo + 56}" y="{card_y + 50}" class="ttl">{title}</text>')
        if kind == "hand":
            out.append(f'<g clip-path="url(#ava)"><circle cx="{hi - 46}" cy="{card_y + 44}" r="24" fill="{t["acc"]}"/>'
                       f'<image href="data:image/webp;base64,{AVA}" x="{hi - 74}" y="{card_y + 18}" width="56" height="56"/></g>')
        for i, (_, k, _, body) in enumerate(MSGS):
            if k != kind:
                continue
            s = i * SLOT
            prefix = "Note: " if kind == "hand" else ""
            ls = wrap("sans", prefix + body, 25, hi - lo - 72)
            tsp = "".join(f'<tspan x="{lo + 36}" dy="{0 if n == 0 else 36}">{esc(l)}</tspan>' for n, l in enumerate(ls))
            out.append(f'<text y="{card_y + 102}" class="body" opacity="0">{tsp}{windows([(s + t2o, s + SLOT - .05)], T)}</text>')
            sans.update(prefix + body)

    # tokens
    for i, (_, kind, flag, _) in enumerate(MSGS):
        lo, hi = cards[kind]
        mid = (lo + hi) / 2
        s = i * SLOT
        path = f"M{x1} {track_y}H{x6}C{x6} {track_y + 60} {mid} {card_y - 70} {mid} {card_y - 8}"
        L1 = x6 - x1
        L2 = 330 if kind == "ok" else 200
        p1 = L1 / (L1 + L2)
        a, b, c = (s + t0o) / T, (s + t1o) / T, (s + t2o) / T
        col0 = t["green"] if flag is None else t["ink"]
        flip = None if flag is None else (s + t0o + (xs[flag] - x1) / (x6 - x1) * (t1o - t0o)) / T
        color = (f'<animate attributeName="fill" dur="{T}s" repeatCount="indefinite" keyTimes="0;{flip:.4f};{flip + .0005:.4f};1" '
                 f'values="{col0};{col0};{t["acc"]};{t["acc"]}"/>' if flip else "")
        out.append(f'<circle r="11" fill="{col0}" opacity="0">{color}'
                   f'<animateMotion dur="{T}s" repeatCount="indefinite" path="{path}" calcMode="linear" keyPoints="0;0;{p1:.4f};1;1" keyTimes="0;{a:.4f};{b:.4f};{c:.4f};1"/>'
                   f'{windows([(s + t0o - .3, s + t2o + .4)], T)}</circle>')

    sans.update("A simplified demo of how my agents decide.")
    out.append(f'<text x="{W - 60}" y="{H - 22}" class="lbl" text-anchor="end">A simplified demo of how my agents decide.</text>')
    css = font_css({"serif": "".join(serif), "sans": "".join(sans), "sansBold": "".join(bold)})
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="Animated diagram: customer messages pass through six steps (read, protect data, understand, look up, check rules, decide). Routine ones are answered; the rest are handed to a person with a note.">
<style>{css}
.lbl{{font-family:jk-sans;font-size:21px;fill:{t["mute"]}}}
.msg{{font-family:jk-serif;font-size:34px;fill:{t["ink"]};letter-spacing:-.4px}}
.step{{font-family:jk-sans;font-size:23px;fill:{t["ink2"]}}}
.ttl{{font-family:jk-sansBold;font-size:25px;fill:{t["ink"]}}}
.body{{font-family:jk-sans;font-size:25px;fill:{t["ink2"]}}}
</style>
<defs><clipPath id="card"><rect width="{W}" height="{H}" rx="{RX}"/></clipPath>
<clipPath id="ava"><circle cx="{cards["hand"][1] - 46}" cy="{card_y + 44}" r="24"/></clipPath>{gdef}</defs>
<g clip-path="url(#card)"><rect width="{W}" height="{H}" fill="{t["bg"]}"/>{grect}
{"".join(out)}
</g></svg>'''


def avatar_b64():
    im = Image.open(SRC / "josh-cutout.png").convert("RGBA")
    w, h = im.size
    im = im.crop((int(w * .2), 0, int(w * .8), int(w * .6))).resize((112, 112), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


AVA = avatar_b64()

if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for t in (LIGHT, DARK):
        for name, fn in (("hello", banner), ("decide", diagram)):
            p = OUT / f"{name}-{t['name']}.svg"
            p.write_text(fn(t))
            print(p.relative_to(ROOT), f"{p.stat().st_size / 1024:.0f} KB")
