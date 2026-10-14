#!/usr/bin/env python3
"""Build the two animated SVG widgets for the yashkhou profile README, light and dark.

  assets/lab-{light,dark}.svg  live lab card: real numbers from the GitHub and npm APIs
  assets/run-{light,dark}.svg  one agent run through the stack (an illustration, not data)

Stdlib only. Fonts and the avatar come pre-baked from tools/src/pack.json
(rebuild that with tools/build_pack.py), so output is byte-identical wherever this runs.

Every data section is fetched on its own. If one fails, the last good value from
data/lab.json is kept and the run still succeeds. The "updated" date only moves when a
number changes, so the scheduled Action commits only when the card really changed.

  python3 tools/build_assets.py            fetch live data, write SVGs and data/lab.json
  python3 tools/build_assets.py --offline  render from data/lab.json only

Token: GITHUB_TOKEN or GH_TOKEN, else `gh auth token` if the GitHub CLI is logged in.
Animation is CSS only (no JS, no SMIL), and switched off under prefers-reduced-motion.
"""
import argparse, datetime as dt, hashlib, json, os, subprocess, sys, unicodedata
import urllib.error, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC, OUT, CACHE = ROOT / "tools" / "src", ROOT / "assets", ROOT / "data" / "lab.json"
PACK = json.loads((SRC / "pack.json").read_text())

USER = "yashkhou"
PROFILE_REPO = "yashkhou"  # this repo; the Action pushes to it daily, so never "latest"
NPM_PACKAGES = ["yashkhou-artifact-verify", "yashkhou-repo-verify", "yashkhou-action-guard"]
WEEKS = 8
# Tutorial repos that merge every first PR. Left out of the upstream count on purpose.
UPSTREAM_SKIP = {"firstcontributions/first-contributions", "udit-001/Collaboration-For-Beginners"}

LIGHT = dict(name="light", bg="#F6F3EE", card="#FFFDF9", ink="#1E1B18", ink2="#463F38", mute="#72695F",
             line="#E3D9CB", faint="#EDE5D9", acc="#E5533D", accSoft="#FBE3DB", green="#2C7A50",
             greenSoft="#E1F1E6", avaBg="#E5533D")
DARK = dict(name="dark", bg="#0D1117", card="#161B22", ink="#E6EDF3", ink2="#C9D1D9", mute="#8B949E",
            line="#30363D", faint="#21262D", acc="#F0705A", accSoft="#3A1E1A", green="#3FB950",
            greenSoft="#13281A", avaBg="#E5533D")

MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


# ---------------------------------------------------------------- text
def clean(s):
    """Map text onto the baked charset so every glyph renders in the embedded fonts."""
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if c in PACK["charset"]).strip()


def width(face, text, size):
    adv = PACK["faces"][face]["adv"]
    return sum(adv.get(c, adv["?"]) for c in text) * size / 1000


def fit(face, text, size, max_w):
    if width(face, text, size) <= max_w:
        return text
    while text and width(face, text + "…", size) > max_w:
        text = text[:-1]
    return text.rstrip(" ,.;:-") + "…"


def wrap(face, text, size, max_w, max_lines=2):
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if cur and width(face, trial, size) > max_w:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines - 1] + [fit(face, " ".join(lines[max_lines - 1:]), size, max_w)]
    return [fit(face, l, size, max_w) for l in lines]


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def font_css(faces):
    return "".join(f"@font-face{{font-family:yk-{k};src:url(data:font/woff2;base64,{PACK['faces'][k]['woff2']}) format('woff2')}}"
                   for k in faces)


def day(iso):
    d = dt.date.fromisoformat(iso[:10])
    return f"{d.day} {MONTHS[d.month - 1]}"


def mix(a, b, k):
    """Blend hex colour a over b with opacity k."""
    ca, cb = (tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) for c in (a, b))
    return "#" + "".join(f"{round(x * k + y * (1 - k)):02X}" for x, y in zip(ca, cb))


def pencil(x, y, col, bg, r=9):
    """Small round badge with a pencil: marks an edit."""
    k = r / 9
    return (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{col}"/>'
            f'<path d="M{x - 3.6 * k:.1f} {y + 3.6 * k:.1f}l{1 * k:.1f}-{3.2 * k:.1f} {4.4 * k:.1f}-{4.4 * k:.1f} {2.2 * k:.1f} {2.2 * k:.1f}-{4.4 * k:.1f} {4.4 * k:.1f}z" fill="{bg}"/>')


def check(x, y, s, col, w=2.2):
    return f'<path d="M{x - s * .5:.1f} {y:.1f}l{s * .34:.1f} {s * .34:.1f} {s * .66:.1f}-{s * .68:.1f}" fill="none" stroke="{col}" stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round"/>'


def cross(x, y, s, col, w=2.2):
    h = s * .4
    return f'<path d="M{x - h:.1f} {y - h:.1f}l{2 * h:.1f} {2 * h:.1f}m0-{2 * h:.1f}-{2 * h:.1f} {2 * h:.1f}" fill="none" stroke="{col}" stroke-width="{w}" stroke-linecap="round"/>'


# ---------------------------------------------------------------- data
def token():
    for k in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(k):
            return os.environ[k]
    try:
        return subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=10).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def http_json(url, tok=None, body=None):
    h = {"User-Agent": f"{USER}-profile-widgets", "Accept": "application/vnd.github+json"}
    if tok and "github.com" in url:
        h["Authorization"] = f"Bearer {tok}"
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None, headers=h)
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)


def graphql(tok, query):
    if not tok:
        raise RuntimeError("GraphQL needs a token")
    out = http_json("https://api.github.com/graphql", tok, {"query": query})
    if out.get("errors"):
        raise RuntimeError(out["errors"][0].get("message"))
    return out["data"]


def fetch_activity(tok):
    q = f'query{{user(login:"{USER}"){{contributionsCollection{{contributionCalendar{{totalContributions weeks{{contributionDays{{date contributionCount}}}}}}}}}}}}'
    cal = graphql(tok, q)["user"]["contributionsCollection"]["contributionCalendar"]
    days = [[d["date"], d["contributionCount"]] for w in cal["weeks"] for d in w["contributionDays"]]
    if len(days) < WEEKS * 7:
        raise RuntimeError("calendar too short")
    return {"days": days[-WEEKS * 7:], "year_total": cal["totalContributions"]}


def fetch_repos(tok):
    q = (f'query{{user(login:"{USER}"){{contributionsCollection{{commitContributionsByRepository(maxRepositories:12)'
         f'{{repository{{name owner{{login}} isPrivate}} contributions{{totalCount}}}}}}}}}}')
    rows = graphql(tok, q)["user"]["contributionsCollection"]["commitContributionsByRepository"]
    top = [{"name": r["repository"]["name"], "commits": r["contributions"]["totalCount"]} for r in rows
           if not r["repository"]["isPrivate"] and r["repository"]["owner"]["login"] == USER
           and r["repository"]["name"] != PROFILE_REPO]
    top.sort(key=lambda r: (-r["commits"], r["name"]))
    if not top:
        raise RuntimeError("no public repos with commits")
    return top[:5]


def fetch_prs(tok):
    def search(q, page=1):
        return http_json("https://api.github.com/search/issues?per_page=100&page=%d&q=%s" % (page, urllib.parse.quote(q)), tok)
    own = search(f"is:pr is:merged is:public author:{USER} user:{USER}")["total_count"]
    up = search(f"is:pr is:merged is:public author:{USER} -user:{USER}")
    repos = [i["repository_url"].split("/repos/")[1] for i in up["items"]]
    if up["total_count"] > len(repos):
        raise RuntimeError("upstream PRs exceed one page; add pagination")
    upstream = [r for r in repos if r not in UPSTREAM_SKIP]
    return {"own": own, "upstream": len(upstream), "upstream_repos": sorted(set(upstream))}


def fetch_npm(_tok):
    out = http_json("https://api.npmjs.org/downloads/point/last-month/" + ",".join(NPM_PACKAGES))
    pk = {p: out[p]["downloads"] for p in NPM_PACKAGES}  # KeyError if npm drops one: keep cache
    any_p = out[NPM_PACKAGES[0]]
    return {"start": any_p["start"], "end": any_p["end"], "packages": pk}


def fetch_latest(tok):
    repos = http_json(f"https://api.github.com/users/{USER}/repos?type=owner&sort=pushed&per_page=12", tok)
    cands = [r for r in repos if not r["archived"] and not r["private"] and r["name"] != PROFILE_REPO][:6]
    best = None
    for r in cands:
        c = http_json(f"https://api.github.com/repos/{USER}/{r['name']}/commits?author={USER}&per_page=1", tok)
        if not c:
            continue
        when = c[0]["commit"]["committer"]["date"]
        if best is None or when > best["date"]:
            best = {"repo": r["name"], "date": when, "sha": c[0]["sha"][:7],
                    "subject": c[0]["commit"]["message"].splitlines()[0]}
    if not best:
        raise RuntimeError("no recent commits found")
    return best


SECTIONS = {"activity": fetch_activity, "repos": fetch_repos, "prs": fetch_prs, "npm": fetch_npm, "latest": fetch_latest}


def collect(offline):
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    data, status = {}, {}
    tok = None if offline else token()
    for key, fn in SECTIONS.items():
        if not offline:
            try:
                data[key] = fn(tok)
                status[key] = "live"
                continue
            except (urllib.error.URLError, OSError, KeyError, ValueError, RuntimeError, TypeError) as e:
                print(f"warn: {key}: {type(e).__name__}: {e}; keeping cached value", file=sys.stderr)
        data[key] = cache.get(key)
        status[key] = "cache" if data[key] is not None else "missing"
    return cache, data, status


# ---------------------------------------------------------------- shared svg bits
BASE_CSS = """
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
.fb{transform-box:fill-box;transform-origin:50% 50%}
"""


def frame(t, W, H, label, css, faces, body, defs=""):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="{esc(label)}">'
            f'<title>{esc(label)}</title>'
            f'<style>{font_css(faces)}{BASE_CSS}{css}</style>'
            f'<defs><clipPath id="cardclip"><rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="14"/></clipPath>{defs}</defs>'
            f'<rect x=".75" y=".75" width="{W - 1.5}" height="{H - 1.5}" rx="14" fill="{t["bg"]}" stroke="{t["line"]}" stroke-width="1.5"/>'
            f'<g clip-path="url(#cardclip)">{body}</g></svg>')


# ---------------------------------------------------------------- lab card
def odometer(uid, value, x, base, size, fill, delay, face="display"):
    """Number whose digits roll into place (CSS). Static fallback = final value."""
    s = f"{value:,}"
    lh = size * 1.1
    asc = PACK["faces"][face]["cap"] * size / 1000
    clip = f'<clipPath id="{uid}"><rect x="{x - 4}" y="{base - asc - size * .22:.1f}" width="{width(face, s, size) + 8:.1f}" height="{asc + size * .44:.1f}"/></clipPath>'
    cols, cx = [], x
    digits = [i for i, c in enumerate(s) if c.isdigit()]
    for i, c in enumerate(s):
        w = width(face, c, size)
        if c.isdigit():
            n = 10 + int(c)
            rank = len(digits) - digits.index(i)  # 1 = rightmost
            tsp = "".join(f'<tspan x="{cx:.1f}" y="{base + k * lh:.1f}">{k % 10}</tspan>' for k in range(n + 1))
            d = delay + (len(digits) - rank) * .07
            dur = 1.1 + rank * .12
            cols.append(f'<g class="roll" style="transform:translateY({-n * lh:.1f}px);animation-delay:{d:.2f}s;animation-duration:{dur:.2f}s">'
                        f'<text class="{face}" fill="{fill}" style="font-size:{size}px">{tsp}</text></g>')
        else:
            cols.append(f'<text x="{cx:.1f}" y="{base}" class="{face}" fill="{fill}" style="font-size:{size}px">{esc(c)}</text>')
        cx += w
    return clip, f'<g clip-path="url(#{uid})">{"".join(cols)}</g>', width(face, s, size)


def fitsize(value, size, max_w, face="display"):
    """Shrink a big number's font size so it fits max_w (keeps tiles from overflowing)."""
    w = width(face, f"{value:,}", size)
    return size if w <= max_w else max(28, round(size * max_w / w, 1))


def lab(t, d, stamp):
    W, H, P = 980, 486, 28
    defs, body = [], []
    used = set()
    A = body.append

    def txt(x, y, s, cls, fill, anchor="start", extra="", size=None):
        used.update(s)
        st = f' style="font-size:{size}px"' if size else ""
        return f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}" fill="{fill}" text-anchor="{anchor}"{st}{extra}>{esc(s)}</text>'

    def eyebrow(x, y, s, anchor="start"):
        return txt(x, y, s.upper(), "eb", t["mute"], anchor)

    def rise(delay):
        return f' class="rise" style="animation-delay:{delay:.2f}s"'

    # header
    defs.append(f'<clipPath id="ava"><circle cx="54" cy="56" r="25"/></clipPath>')
    A(f'<g{rise(0)}><circle cx="54" cy="56" r="25" fill="{t["avaBg"]}"/>'
      f'<image href="data:image/webp;base64,{PACK["avatar"]}" x="29" y="31" width="50" height="50" clip-path="url(#ava)"/>'
      f'{txt(92, 55, "Josh Khoury", "display", t["ink"], size=28)}'
      f'{txt(92, 79, "Live lab card. Real numbers from the GitHub and npm APIs, refreshed daily.", "sans", t["mute"], size=14)}</g>')
    up = f"updated {day(stamp)} {stamp[:4]}"
    pw = width("sans", up, 13.5) + 44
    px = W - P - pw
    A(f'<g{rise(.1)}><rect x="{px:.1f}" y="37" width="{pw:.1f}" height="30" rx="15" fill="{t["card"]}" stroke="{t["line"]}"/>'
      f'<circle cx="{px + 18:.1f}" cy="52" r="4" fill="{t["green"]}"/>'
      f'<circle class="pulse fb" cx="{px + 18:.1f}" cy="52" r="4" fill="none" stroke="{t["green"]}" stroke-width="2"/>'
      f'{txt(px + 30, 56.5, up, "sans", t["ink2"], size=13.5)}</g>')
    A(f'<path d="M{P} 102H{W - P}" stroke="{t["line"]}"/>')

    # activity: daily bars over the last WEEKS weeks
    act = d.get("activity")
    LX, LW, top, base = P, 520, 204, 278
    A(eyebrow(LX, 133, f"Contributions · last {WEEKS} weeks"))
    if act:
        days = act["days"]
        total = sum(c for _, c in days)
        c_, g_, nw = odometer("o1", total, LX, 184, 46, t["ink"], .25)
        defs.append(c_)
        A(g_)
        A(txt(LX + nw + 12, 184, "public contributions", "sans", t["mute"], size=14))
        peak = max(c for _, c in days) or 1
        step = LW / len(days)
        bw = step * .62
        A(f'<path d="M{LX} {base + .5}H{LX + LW}" stroke="{t["line"]}"/>')
        for frac in (.5, 1):
            y = base - (base - top) * frac
            A(f'<path d="M{LX} {y:.1f}H{LX + LW}" stroke="{t["faint"]}" stroke-dasharray="2 4"/>')
        for i, (date, c) in enumerate(days):
            x = LX + i * step + (step - bw) / 2
            if c == 0:
                A(f'<circle cx="{x + bw / 2:.1f}" cy="{base - 2}" r="1.4" fill="{t["mute"]}" opacity=".45"/>')
                continue
            h = max(3, (base - top) * c / peak)
            A(f'<rect class="grow fb" x="{x:.1f}" y="{base - h:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="{min(2, bw / 2):.1f}" fill="{t["acc"]}" style="animation-delay:{.35 + i * .012:.3f}s"/>')
        pi = max(range(len(days)), key=lambda i: (days[i][1], i))
        pxx = LX + pi * step + step / 2
        lab_ = f"peak {days[pi][1]} · {day(days[pi][0])}"
        anchor = "end" if pxx > LX + LW - 80 else "start"
        A(f'<g{rise(1.3)}>{txt(pxx + (-8 if anchor == "end" else 8), top + 9, lab_, "mono", t["ink2"], anchor, size=12.5)}</g>')
        # axis: first day of each month in the window, plus the last day
        for i, (date, _) in enumerate(days):
            dd = dt.date.fromisoformat(date)
            if dd.day == 1 and 2 < i < len(days) - 6:
                x = LX + i * step + step / 2
                A(f'<path d="M{x:.1f} {base + 1}v5" stroke="{t["line"]}"/>' + txt(x, base + 20, MONTHS[dd.month - 1], "sans", t["mute"], "middle", size=12.5))
        A(txt(LX, base + 20, day(days[0][0]), "sans", t["mute"], "start", size=12.5))
        A(txt(LX + LW, base + 20, day(days[-1][0]), "sans", t["mute"], "end", size=12.5))
    else:
        A(txt(LX, 184, "unavailable", "sans", t["mute"], size=15))

    # where the commits went
    RX, RW = 584, W - P - 584
    A(eyebrow(RX, 133, "Where the commits went · 12 months"))
    repos = d.get("repos") or []
    if repos:
        mx = max(r["commits"] for r in repos)
        bx0, bmax = RX + 188, RW - 188 - 50
        for k, r in enumerate(repos):
            y = 166 + k * 26.5
            ncommits = f"{r['commits']:,}"
            name = fit("mono", r["name"], 13.5, 180)
            bwid = max(4, bmax * r["commits"] / mx)
            A(f'<g{rise(.45 + k * .07)}>{txt(RX, y, name, "mono", t["ink"], size=13.5)}'
              f'<rect x="{bx0}" y="{y - 9}" width="{bmax}" height="8" rx="4" fill="{t["faint"]}"/>'
              f'<rect class="growx fb" x="{bx0}" y="{y - 9}" width="{bwid:.1f}" height="8" rx="4" fill="{t["ink2"] if k else t["acc"]}" style="animation-delay:{.6 + k * .08:.2f}s"/>'
              f'{txt(W - P, y, ncommits, "mono", t["ink2"], "end", size=13.5)}</g>')
    else:
        A(txt(RX, 184, "unavailable", "sans", t["mute"], size=15))
    A(f'<path d="M{P} 318H{W - P}" stroke="{t["line"]}"/>')

    # tiles
    TY, TH, gap = 334, 124, 15
    TW = (W - 2 * P - 2 * gap) / 3
    tx = [P + i * (TW + gap) for i in range(3)]
    for i, x in enumerate(tx):
        A(f'<rect x="{x:.1f}" y="{TY}" width="{TW:.1f}" height="{TH}" rx="10" fill="{t["card"]}" stroke="{t["line"]}"{rise(.5 + i * .12)}/>')

    # tile 1: merged PRs
    x = tx[0] + 18
    A(eyebrow(x, TY + 27, "Merged pull requests"))
    prs = d.get("prs")
    if prs:
        own, upn = prs["own"], prs["upstream"]
        c_, g_, nw = odometer("o2", own + upn, x, TY + 78, fitsize(own + upn, 42, 110), t["ink"], .7)
        defs.append(c_)
        A(g_)
        lx = x + max(nw, 40) + 20
        A(f'<g{rise(.9)}><circle cx="{lx + 4}" cy="{TY + 54}" r="4" fill="{t["ink2"]}"/>{txt(lx + 14, TY + 58.5, f"{own:,} in my repos", "sans", t["ink2"], size=14)}'
          f'<circle cx="{lx + 4}" cy="{TY + 76}" r="4" fill="{t["acc"]}"/>{txt(lx + 14, TY + 80.5, f"{upn:,} upstream", "sans", t["ink2"], size=14)}</g>')
        bw_ = TW - 36
        ow = bw_ * own / max(1, own + upn)
        A(f'<rect x="{x}" y="{TY + 98}" width="{bw_:.1f}" height="8" rx="4" fill="{t["faint"]}"/>'
          f'<rect class="growx fb" x="{x}" y="{TY + 98}" width="{ow:.1f}" height="8" rx="4" fill="{t["ink2"]}" style="animation-delay:1s"/>'
          f'<rect class="growx fb" x="{x + ow + 2:.1f}" y="{TY + 98}" width="{max(0, bw_ - ow - 2):.1f}" height="8" rx="4" fill="{t["acc"]}" style="animation-delay:1.25s"/>')
    else:
        A(txt(x, TY + 76, "unavailable", "sans", t["mute"], size=15))

    # tile 2: npm
    x = tx[1] + 18
    A(eyebrow(x, TY + 27, "npm downloads · 30 days"))
    npm = d.get("npm")
    if npm:
        pk = {p: npm["packages"][p] for p in NPM_PACKAGES if p in npm["packages"]}  # fixed order
        c_, g_, nw = odometer("o3", sum(pk.values()), x, TY + 78, fitsize(sum(pk.values()), 42, 96), t["ink"], .85)
        defs.append(c_)
        A(g_)
        A(txt(x, TY + 104, f"to {day(npm['end'])}", "sans", t["mute"], size=12.5))
        rx0 = x + max(nw, 60) + 24
        rw = tx[1] + TW - 18 - rx0
        mx = max(pk.values()) or 1
        for k, (name, n) in enumerate(pk.items()):
            y = TY + 50 + k * 26
            cnt = f"{n:,}"
            short = fit("sans", name.replace("yashkhou-", ""), 13, rw - width("mono", cnt, 12.5) - 10)
            A(f'<g{rise(1 + k * .08)}>{txt(rx0, y, short, "sans", t["ink2"], size=13)}{txt(rx0 + rw, y, cnt, "mono", t["ink2"], "end", size=12.5)}</g>'
              f'<rect x="{rx0:.1f}" y="{y + 8}" width="{rw:.1f}" height="3" rx="1.5" fill="{t["faint"]}"/>'
              f'<rect class="growx fb" x="{rx0:.1f}" y="{y + 8}" width="{max(2, rw * n / mx):.1f}" height="3" rx="1.5" fill="{t["acc"]}" style="animation-delay:{1.1 + k * .1:.2f}s"/>')
    else:
        A(txt(x, TY + 76, "unavailable", "sans", t["mute"], size=15))

    # tile 3: latest push
    x = tx[2] + 18
    A(eyebrow(x, TY + 27, "Latest push"))
    lt = d.get("latest")
    if lt:
        A(txt(tx[2] + TW - 18, TY + 27, f"{day(lt['date'])} · {lt['sha']}", "mono", t["mute"], "end", size=12))
        A(f'<g{rise(1.05)}>{txt(x, TY + 56, fit("mono", lt["repo"], 15.5, TW - 36), "mono", t["acc"], size=15.5)}')
        for k, line in enumerate(wrap("sans", clean(lt["subject"]), 14, TW - 36, 2)):
            A(txt(x, TY + 81 + k * 20, line, "sans", t["ink2"], size=14))
        A('</g>')
    else:
        A(txt(x, TY + 76, "unavailable", "sans", t["mute"], size=15))

    css = f"""
.display{{font-family:yk-display;letter-spacing:-.5px}}.sans{{font-family:yk-sans}}.mono{{font-family:yk-mono}}
.eb{{font-family:yk-sansBold;font-size:11.5px;letter-spacing:1.1px}}
.rise{{animation:rise .7s cubic-bezier(.2,.8,.2,1) both}}
.roll{{animation:roll 1.3s cubic-bezier(.16,.84,.24,1) both}}
.grow{{transform-origin:50% 100%;animation:grow .6s cubic-bezier(.2,.8,.2,1) both}}
.growx{{transform-origin:0 50%;animation:growx .9s cubic-bezier(.2,.8,.2,1) both}}
.pulse{{transform-origin:50% 50%;animation:pulse 2.4s ease-out infinite}}
@keyframes rise{{from{{opacity:0;transform:translateY(8px)}}}}
@keyframes roll{{from{{transform:translateY(0)}}}}
@keyframes grow{{from{{transform:scaleY(0)}}}}
@keyframes growx{{from{{transform:scaleX(0)}}}}
@keyframes pulse{{0%{{transform:scale(1);opacity:.9}}70%,100%{{transform:scale(2.4);opacity:0}}}}
"""
    bits = []
    if act:
        bits.append(f"{sum(c for _, c in act['days'])} public contributions in the last {WEEKS} weeks")
    if prs:
        bits.append(f"{prs['own'] + prs['upstream']} merged pull requests ({prs['own']} in his repos, {prs['upstream']} upstream)")
    if npm:
        bits.append(f"{sum(npm['packages'].values())} npm downloads in 30 days")
    if lt:
        bits.append(f"latest push to {lt['repo']}")
    label = f"Josh Khoury, live lab card (updated {day(stamp)} {stamp[:4]}): " + "; ".join(bits) + "."
    return frame(t, W, H, label, css, ["display", "sans", "sansBold", "mono"], "".join(body), "".join(defs))


# ---------------------------------------------------------------- run diagram
T = 22.0  # loop length, seconds


class Timeline:
    """One @keyframes block per element over the shared T-second loop.

    Methods return a CSS declaration ("animation:..."), to be placed inside a style attribute.
    Elements are drawn in their end-of-story state, so with animation off (reduced motion)
    the diagram is a complete static picture: blocked call, broken chain, flagged run.
    """

    def __init__(self):
        self.rules, self.n = [], 0

    def __call__(self, frames, ease="linear"):
        """frames: [(seconds, 'css decls'), ...]"""
        self.n += 1
        name = f"k{self.n}"
        fr = sorted(frames, key=lambda f: f[0])
        if fr[0][0] > 0:
            fr.insert(0, (0, fr[0][1]))
        if fr[-1][0] < T:
            fr.append((T, fr[-1][1]))
        body = "".join(f"{100 * s / T:.3f}%{{{css}}}" for s, css in fr)
        self.rules.append(f"@keyframes {name}{{{body}}}")
        return f"animation:{name} {T}s {ease} infinite"

    def show(self, t_in, dur=.35, move="translateY(6px)", t_out=None):
        f = [(0, f"opacity:0;transform:{move}"), (t_in, f"opacity:0;transform:{move}"),
             (t_in + dur, "opacity:1;transform:none")]
        if t_out is not None:
            f += [(t_out, "opacity:1;transform:none"), (t_out + dur, "opacity:0;transform:none")]
        return self(f, "ease-out")

    def window(self, t_in, t_out, dur=.3):
        """Visible only between t_in and t_out (hidden in the static picture)."""
        return self([(0, "opacity:0"), (t_in, "opacity:0"), (t_in + dur, "opacity:1"),
                     (t_out, "opacity:1"), (t_out + dur, "opacity:0")])

    def until(self, t_out, dur=.3):
        """Visible from the start of the loop until t_out (hidden in the static picture)."""
        return self([(0, "opacity:1"), (t_out, "opacity:1"), (t_out + dur, "opacity:0")])


def chain(steps):
    """Real SHA-256 hash chain over the illustrative steps."""
    prev, out = "0" * 64, []
    for i, (tool, arg, decision) in enumerate(steps):
        rec = json.dumps({"seq": i + 1, "tool": tool, "args": arg, "decision": decision, "prev": prev}, sort_keys=True)
        prev = hashlib.sha256(rec.encode()).hexdigest()
        out.append(prev)
    return out


def run(t):
    W, H, P = 980, 640, 28
    tl = Timeline()
    body = []
    A = body.append

    def txt(x, y, s, face, size, fill, anchor="start", anim=None, hidden=False):
        st = f"font-size:{size}px" + (f";{anim}" if anim else "")
        op = ' opacity="0"' if hidden else ""
        return f'<text x="{x:.1f}" y="{y:.1f}" class="{face}" fill="{fill}" text-anchor="{anchor}"{op} style="{st}">{esc(s)}</text>'

    def pill(x, y, label, ok):
        col, soft = (t["green"], t["greenSoft"]) if ok else (t["acc"], t["accSoft"])
        pw = width("sansBold", label, 13) + 40
        return (f'<rect x="{x - pw / 2:.1f}" y="{y - 14}" width="{pw:.1f}" height="28" rx="14" fill="{soft}" stroke="{col}" stroke-width="1.2"/>'
                + (check(x - pw / 2 + 17, y + 1, 10, col, 2) if ok else cross(x - pw / 2 + 17, y, 10, col, 2))
                + txt(x - pw / 2 + 29, y + 4.5, label, "sansBold", 13, col))

    # ---- timing (seconds)
    starts = [1.6, 4.0, 6.4, 8.8, 11.2]
    V = 230.0  # token speed, px/s
    TAMPER, BREAK, FLAG, FADE = 14.4, 14.9, 16.3, 21.0

    # ---- grid
    LANES = [("Commander Plus", "MCP control plane"), ("ActionMesh", "typed contracts"),
             ("RunLedger", "hash chain"), ("BrowserProof", "browser state"), ("Verify", "output check")]
    Y0, LH = 104, 84
    cy = [Y0 + i * LH + LH / 2 for i in range(5)]
    CX0 = P + 156
    colw = [156, 156, 156, 156, W - P - CX0 - 4 * 156]
    cx = [CX0 + sum(colw[:i]) + colw[i] / 2 for i in range(5)]
    bwid = [128, 128, 128, 128, colw[4] - 18]  # ledger block widths
    CHH = 50

    # ---- header
    A(txt(P, 44, "ONE AGENT RUN, END TO END", "sansBold", 11.5, t["mute"]).replace("<text ", '<text letter-spacing="1.1" '))
    tw = width("mono", "task", 13) + 18
    A(f'<g style="{tl.show(.2, .5)}"><rect x="{P}" y="58" width="{tw:.1f}" height="24" rx="6" fill="{t["card"]}" stroke="{t["line"]}"/>'
      + txt(P + 9, 74.5, "task", "mono", 13, t["mute"])
      + txt(P + tw + 12, 78, "Save October’s invoice as a PDF", "italic", 25, t["ink"]) + '</g>')
    bx, bw = W - P - 170, 170  # loop progress
    A('<g class="loopbar">')
    A(txt(bx - 10, 74, "loop", "mono", 12, t["mute"], "end"))
    A(f'<rect x="{bx}" y="67" width="{bw}" height="4" rx="2" fill="{t["faint"]}"/>')
    A(f'<rect x="{bx + bw * TAMPER / T - 1:.1f}" y="63" width="2" height="12" rx="1" fill="{t["acc"]}"/>')
    A(f'<rect class="fb" x="{bx}" y="67" width="{bw}" height="4" rx="2" fill="{t["ink2"]}" style="transform-origin:0 50%;animation:prog {T}s linear infinite"/></g>')

    # ---- lanes
    for i, (name, role) in enumerate(LANES):
        if i % 2 == 0:
            A(f'<rect x="{P - 12}" y="{Y0 + i * LH}" width="{W - 2 * P + 24}" height="{LH}" rx="8" fill="{t["card"]}" opacity=".75"/>')
        A(txt(P, cy[i] - 2, name, "sansBold", 16, t["ink"]))
        A(txt(P, cy[i] + 17, role, "sans", 13, t["mute"]))

    steps = [("browser_navigate", "billing/invoices", "allowed"), ("browser_click", "October PDF", "allowed"),
             ("write_file", "~/.ssh/config", "denied"), ("write_file", "invoices/oct.pdf", "allowed"),
             ("result", "saved oct.pdf", "end")]
    hashes = chain(steps)
    forged = chain([(a, b, "allowed" if i == 2 else c) for i, (a, b, c) in enumerate(steps)])
    lowest = [3, 3, 2, 4, 2]  # deepest lane each trace reaches

    for i, (tool, arg, dec) in enumerate(steps):
        s, x = starts[i], cx[i]
        w = 142 if i < 4 else colw[4] - 18
        blocked = dec == "denied"
        y_top, y_end = cy[0] + CHH / 2, cy[lowest[i]]
        stop = (cy[1] - y_top) / V

        def at(lane):  # when this call's token reaches a lane
            if blocked and lane >= 2:
                return s + .75 + stop + (cy[lane] - cy[1]) / V
            return s + .3 + (cy[lane] - y_top) / V

        # trace line and travelling token
        tcol = t["acc"] if blocked else t["mute"]
        dash = ' stroke-dasharray="3 4"' if blocked else ""
        A(f'<path class="fb" d="M{x} {y_top}V{y_end}" stroke="{tcol}" stroke-width="1.5"{dash} opacity=".6" '
          f'style="transform-origin:50% 0;{tl([(0, "transform:scaleY(0)"), (s + .3, "transform:scaleY(0)"), (at(lowest[i]), "transform:scaleY(1)")])}"/>')
        dy = lambda lane: f"{cy[lane] - y_top:.1f}px"
        if blocked:  # halts at the contract check, shakes, then is logged as denied
            frames = [(0, "opacity:0;transform:translateY(0)"), (s + .2, "opacity:0;transform:translateY(0)"), (s + .3, "opacity:1;transform:translateY(0)"),
                      (at(1), f"opacity:1;transform:translateY({dy(1)})"),
                      (at(1) + .15, f"opacity:1;transform:translate(-5px,{dy(1)})"),
                      (at(1) + .3, f"opacity:1;transform:translate(5px,{dy(1)})"),
                      (at(1) + .45, f"opacity:1;transform:translateY({dy(1)})"),
                      (at(2), f"opacity:1;transform:translateY({dy(2)})"),
                      (at(2) + .25, f"opacity:0;transform:translateY({dy(2)})")]
        else:
            frames = [(0, "opacity:0;transform:translateY(0)"), (s + .2, "opacity:0;transform:translateY(0)"), (s + .3, "opacity:1;transform:translateY(0)"),
                      (at(lowest[i]), f"opacity:1;transform:translateY({dy(lowest[i])})"),
                      (at(lowest[i]) + .25, f"opacity:0;transform:translateY({dy(lowest[i])})")]
        A(f'<circle cx="{x}" cy="{y_top}" r="5" fill="{t["acc"] if blocked else t["ink"]}" opacity="0" style="{tl(frames)}"/>')

        # Commander Plus: the tool call
        fs = 14
        while width("mono", tool, fs) > w - 16 and fs > 11:
            fs -= .5
        A(f'<g class="fb" style="{tl.show(s, .3, "scale(.92)")}"><rect x="{x - w / 2:.1f}" y="{cy[0] - CHH / 2}" width="{w:.1f}" height="{CHH}" rx="9" fill="{t["bg"]}" stroke="{t["line"]}" stroke-width="1.3"/>'
          + txt(x, cy[0] - 3, tool, "mono", fs, t["ink"], "middle")
          + txt(x, cy[0] + 15, fit("mono", arg, 12, w - 14), "mono", 12, t["mute"], "middle") + '</g>')
        if blocked:
            A(f'<rect x="{x - w / 2:.1f}" y="{cy[0] - CHH / 2}" width="{w:.1f}" height="{CHH}" rx="9" fill="none" stroke="{t["acc"]}" stroke-width="2" style="{tl.show(at(1), .25, "none")}"/>')

        # ActionMesh: contract check per tool call
        if i < 4:
            g = pill(x, cy[1], "in contract" if not blocked else "blocked", not blocked)
            if blocked:
                g += txt(x, cy[1] + 31, "path not in contract", "sans", 12, t["acc"], "middle")
            A(f'<g class="fb" style="{tl.show(at(1), .25, "scale(.85)")}">{g}</g>')

        # RunLedger: append a block, link it to the previous one
        tb = at(2)
        bx0, by0 = x - bwid[i] / 2, cy[2] - 26
        dcol = t["acc"] if blocked else t["mute"]
        A(f'<g style="{tl.show(tb, .3, "translateY(-8px)")}">'
          f'<rect x="{bx0:.1f}" y="{by0:.1f}" width="{bwid[i]}" height="52" rx="8" fill="{t["bg"]}" stroke="{t["ink2"]}" stroke-width="1.3"/>'
          + txt(bx0 + 11, by0 + 20, f"#{i + 1}", "sansBold", 13, t["ink2"])
          + txt(bx0 + bwid[i] - 11, by0 + 20, dec, "sans", 12.5, dcol, "end",
                anim=tl.until(TAMPER + .4) if i == 2 else None, hidden=i == 2)
          + txt(bx0 + 11, by0 + 40, hashes[i][:8], "mono", 13.5, t["ink"], anim=tl.until(BREAK + (i - 2) * .38 + .3) if i >= 2 else None, hidden=i >= 2)
          + '</g>')
        if i > 0:
            lx0 = cx[i - 1] + bwid[i - 1] / 2
            A(f'<path class="fb" d="M{lx0:.1f} {cy[2]}H{bx0:.1f}" stroke="{t["ink2"]}" stroke-width="1.5" '
              f'style="transform-origin:0 50%;{tl([(0, "transform:scaleX(0)"), (tb, "transform:scaleX(0)"), (tb + .3, "transform:scaleX(1)")])}"/>')
            A(f'<circle cx="{bx0:.1f}" cy="{cy[2]}" r="2.6" fill="{t["ink2"]}" style="{tl.show(tb + .25, .1, "none")}"/>')

        # BrowserProof: did the browser land where the agent says it did?
        if i in (0, 1):
            A(f'<g class="fb" style="{tl.show(at(3), .25, "scale(.85)")}">' + pill(x, cy[3] - 6, "page matches", True)
              + txt(x, cy[3] + 25, "/invoices" if i == 0 else "/invoices/oct", "mono", 12, t["mute"], "middle") + '</g>')
        # Verify: check the file the agent wrote
        if i == 3:
            A(f'<g class="fb" style="{tl.show(at(4), .25, "scale(.85)")}">' + pill(x, cy[4] - 6, "valid PDF", True)
              + txt(x, cy[4] + 25, "oct.pdf · 2 pages", "mono", 12, t["mute"], "middle") + '</g>')

    band = mix(t["card"], t["bg"], .75)  # ledger lane colour, to mask the old link
    # ---- tamper: block #3 is rewritten from "denied" to "allowed" after the run
    for i in range(2, 5):
        tb = BREAK + (i - 2) * .38
        bx0, by0 = cx[i] - bwid[i] / 2, cy[2] - 26
        shake = [(0, "transform:none"), (tb, "transform:none"), (tb + .08, "transform:translateX(-3px)"),
                 (tb + .16, "transform:translateX(3px)"), (tb + .24, "transform:none")] if i == 2 else None
        A(f'<g style="{tl.show(tb, .3, "none")}"><g style="{tl(shake) if shake else ""}">'
          f'<rect x="{bx0:.1f}" y="{by0:.1f}" width="{bwid[i]}" height="52" rx="8" fill="{t["accSoft"]}" stroke="{t["acc"]}" stroke-width="2"/>'
          + txt(bx0 + 11, by0 + 20, f"#{i + 1}", "sansBold", 13, t["acc"])
          + (txt(bx0 + bwid[i] - 11, by0 + 20, steps[i][2] if i > 2 else "allowed", "sans", 12.5, t["acc"], "end"))
          + txt(bx0 + 11, by0 + 40, forged[i][:8], "mono", 13.5, t["acc"]) + '</g></g>')
        if i > 2:  # broken link: the stored prev hash no longer matches
            lx0 = cx[i - 1] + bwid[i - 1] / 2
            mid = (lx0 + bx0) / 2
            A(f'<g style="{tl.show(tb - .15, .2, "none")}"><rect x="{lx0 + 1:.1f}" y="{cy[2] - 8}" width="{bx0 - lx0 - 2:.1f}" height="16" fill="{band}"/>'
              f'<path d="M{lx0:.1f} {cy[2]}H{mid - 6:.1f}M{mid + 6:.1f} {cy[2]}H{bx0:.1f}" stroke="{t["acc"]}" stroke-width="2"/>'
              + cross(mid, cy[2], 8, t["acc"], 2) + '</g>')
    ex, ey = cx[2] + bwid[2] / 2 - 2, cy[2] - 26  # pencil badge: the edit lands on block #3
    A(f'<g class="fb" style="{tl.show(TAMPER, .3, "scale(.6)")}">' + pencil(ex, ey, t["acc"], t["bg"]) + '</g>')
    # "allowed" on #3 appears before the block turns red: the edit, then the consequence
    A(txt(cx[2] + bwid[2] / 2 - 11, cy[2] - 6, "allowed", "sans", 12.5, t["acc"], "end",
          anim=tl([(0, "opacity:0"), (TAMPER + .45, "opacity:0"), (TAMPER + .75, "opacity:1"), (BREAK + .2, "opacity:1"), (BREAK + .35, "opacity:0")]), hidden=True))

    # ---- status bar: running -> complete -> broken and flagged
    SY, SH = 540, 46
    mid = SY + SH / 2
    done_t = at(2) + .4  # the "result" block lands
    A(f'<rect x="{P}" y="{SY}" width="{W - 2 * P}" height="{SH}" rx="12" fill="{t["card"]}" stroke="{t["line"]}"/>')
    A(f'<g opacity="0" style="{tl.until(done_t)}"><circle cx="{P + 24}" cy="{mid}" r="5" fill="{t["ink2"]}"/>'
      f'<circle class="pulse fb" cx="{P + 24}" cy="{mid}" r="5" fill="none" stroke="{t["ink2"]}" stroke-width="1.6"/>'
      + txt(P + 40, mid + 5, "Running. Each call is checked against its contract and written to the ledger.", "sans", 14.5, t["ink2"]) + '</g>')
    A(f'<g opacity="0" style="{tl.window(done_t + .2, TAMPER - .1)}"><circle cx="{P + 24}" cy="{mid}" r="10" fill="{t["greenSoft"]}" stroke="{t["green"]}" stroke-width="1.2"/>'
      + check(P + 24, mid + 1, 9, t["green"], 2) + txt(P + 44, mid + 5, "Run complete. Ledger verifies, page and file checked.", "sans", 14.5, t["ink"]) + '</g>')
    A(f'<g opacity="0" style="{tl.window(TAMPER + .15, FLAG - .3)}">' + pencil(P + 24, mid, t["acc"], t["bg"], 10)
      + txt(P + 44, mid + 5, "Someone edits block #3 after the run: denied → allowed.", "sans", 14.5, t["ink"]) + '</g>')
    px_ = W - P - 26
    A(f'<g style="{tl.show(FLAG, .35, "none")}"><circle cx="{P + 24}" cy="{mid}" r="10" fill="{t["accSoft"]}" stroke="{t["acc"]}" stroke-width="1.2"/>'
      + cross(P + 24, mid, 9, t["acc"], 2) + txt(P + 44, mid + 5, "Block #3 was edited after the run. Chain broken from #3, run flagged for a person.", "sansBold", 14.5, t["acc"])
      + f'<circle cx="{px_}" cy="{mid}" r="15" fill="{t["acc"]}"/><circle cx="{px_}" cy="{mid - 4}" r="4.6" fill="{t["bg"]}"/>'
      f'<path d="M{px_ - 8} {mid + 9.5}a8 7 0 0 1 16 0z" fill="{t["bg"]}"/></g>')

    A(txt(P, H - 22, "An illustration of how my tools fit together in one agent run. Not a recording.", "sans", 13, t["mute"]))
    A(txt(W - P, H - 22, "short hashes: real SHA-256 of each step", "mono", 12, t["mute"], "end"))

    fade = tl([(0, "opacity:1"), (FADE, "opacity:1"), (FADE + .6, "opacity:0"), (T - .05, "opacity:0"), (T, "opacity:1")])
    css = (".sans{font-family:yk-sans}.sansBold{font-family:yk-sansBold}.mono{font-family:yk-mono}.italic{font-family:yk-italic;letter-spacing:-.3px}"
           ".pulse{animation:pulse 1.6s ease-out infinite}"
           "@keyframes pulse{0%{transform:scale(1);opacity:.8}80%,100%{transform:scale(2.6);opacity:0}}"
           "@keyframes prog{from{transform:scaleX(0)}to{transform:scaleX(1)}}"
           "@media (prefers-reduced-motion:reduce){.loopbar{display:none}}" + "".join(tl.rules))
    label = ("Animated illustration of one agent run: a task enters Commander Plus; ActionMesh checks each tool call against its contract "
             "and blocks a write to ~/.ssh/config; every call is appended to a RunLedger hash chain; BrowserProof confirms the browser "
             "landed on the claimed page; Verify checks the saved PDF. Then someone edits ledger block 3 from denied to allowed, "
             "the chain turns red from that block on, and the run is flagged for a person.")
    return frame(t, W, H, label, css, ["sans", "sansBold", "mono", "italic"], f'<g style="{fade}">{"".join(body)}</g>')


# ---------------------------------------------------------------- main
def render_all(data, stamp):
    out = {f"{name}-{t['name']}.svg": fn(t) for t in (LIGHT, DARK)
           for name, fn in (("lab", lambda t: lab(t, data, stamp)), ("run", run))}
    for fname, svg in out.items():
        ET.fromstring(svg)  # GitHub shows a broken image for malformed XML; fail here instead
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--offline", action="store_true", help="render from data/lab.json without network")
    a = ap.parse_args()

    cache, data, status = collect(a.offline)
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    old = {k: cache.get(k) for k in SECTIONS}
    stamp = cache.get("updated") if (old == data and cache.get("updated")) else today

    OUT.mkdir(exist_ok=True)
    changed = []
    for fname, svg in render_all(data, stamp).items():
        p = OUT / fname
        if not p.exists() or p.read_text() != svg:
            p.write_text(svg)
            changed.append(fname)
        print(f"{fname:16s} {len(svg.encode()) / 1024:6.1f} KB{'  (changed)' if fname in changed else ''}")

    if not a.offline and (old != data or not CACHE.exists() or cache.get("updated") != stamp):
        CACHE.parent.mkdir(exist_ok=True)
        CACHE.write_text(json.dumps({"updated": stamp, **data}, indent=1, sort_keys=True) + "\n")
    summary = {k: status[k] for k in SECTIONS}
    print("sources:", ", ".join(f"{k}={v}" for k, v in summary.items()), "| updated", stamp)
    if all(v == "missing" for v in summary.values()):
        sys.exit("error: no live data and no cache")


if __name__ == "__main__":
    main()
