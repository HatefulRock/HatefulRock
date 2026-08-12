#!/usr/bin/env python3
"""Generate a night-skyline SVG from the real contribution calendar, bucketed
by week and self-scaled to the user's own busiest week -- stays legible at
any activity level instead of assuming power-user commit volumes."""
import json
import os
import sys
import urllib.request

W, H = 900, 340
GROUND = 250
MAX_BUILDING_H = 190
MIN_BUILDING_H = 10
SIDE_MARGIN = 30
DX, DY = 5, -4  # extrusion for the 3D side/top faces

NIGHT_BG = "#050b1a"
PALETTE = ["#0a1128", "#123a5c", "#1f8a94", "#f4b400", "#ef3340"]  # low -> high

def fetch_calendar(login, token):
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            totalContributions
            weeks { contributionDays { contributionCount date } }
          }
        }
      }
    }
    """
    body = json.dumps({"query": query, "variables": {"login": login}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "profile-skyline-script",
        },
    )
    with urllib.request.urlopen(req) as resp:
        data = json.load(resp)
    cal = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    return cal["weeks"], cal["totalContributions"]

def bucket(count, max_count):
    if count == 0 or max_count <= 0:
        return 0
    ratio = count / max_count
    if ratio < 0.25:
        return 1
    if ratio < 0.5:
        return 2
    if ratio < 0.75:
        return 3
    return 4

def poly(pts, fill, opacity=1.0):
    p = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    op = f' fill-opacity="{opacity:.2f}"' if opacity != 1.0 else ""
    return f'<polygon points="{p}" fill="{fill}"{op}/>'

def box(x, y, w, h, color):
    """Extruded block: (x, y) = top-left of the front face."""
    front = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    side = [(x + w, y), (x + w + DX, y + DY), (x + w + DX, y + h + DY), (x + w, y + h)]
    top = [(x, y), (x + DX, y + DY), (x + w + DX, y + DY), (x + w, y)]
    return "\n".join([
        poly(side, shade(color, 0.55)),
        poly(top, shade(color, 1.25)),
        poly(front, color),
    ])

def shade(hexcolor, factor):
    hexcolor = hexcolor.lstrip("#")
    r, g, b = int(hexcolor[0:2], 16), int(hexcolor[2:4], 16), int(hexcolor[4:6], 16)
    r, g, b = (max(0, min(255, int(c * factor))) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"

def render(weeks, total, out_path):
    weekly = [sum(d["contributionCount"] for d in w["contributionDays"]) for w in weeks]
    max_week = max(weekly) if weekly else 0
    n = len(weekly)

    avail_w = W - 2 * SIDE_MARGIN
    gap = 3
    bw = (avail_w - gap * (n - 1)) / n if n else 0

    parts = [f'''<defs>
  <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stop-color="#020610"/>
    <stop offset="60%" stop-color="{NIGHT_BG}"/>
    <stop offset="100%" stop-color="#0a1830"/>
  </linearGradient>
  <linearGradient id="water" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stop-color="#08131f"/>
    <stop offset="100%" stop-color="#020509"/>
  </linearGradient>
  <linearGradient id="reflFade" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stop-color="white" stop-opacity="0.28"/>
    <stop offset="100%" stop-color="white" stop-opacity="0"/>
  </linearGradient>
  <mask id="reflMask"><rect x="0" y="0" width="{W}" height="{H}" fill="url(#reflFade)"/></mask>
</defs>
<rect x="0" y="0" width="{W}" height="{H}" fill="url(#sky)"/>''']

    import random
    random.seed(4)
    stars = [
        f'<circle cx="{random.uniform(0,W):.1f}" cy="{random.uniform(6,GROUND-60):.1f}" '
        f'r="{random.choice([0.6,0.8,1.0])}" fill="#e8f1ff" opacity="{random.uniform(0.3,0.9):.2f}"/>'
        for _ in range(45)
    ]
    parts.append("\n".join(stars))
    parts.append(f'<rect x="0" y="{GROUND}" width="{W}" height="{H-GROUND}" fill="url(#water)"/>')

    def buildings_svg():
        bparts = []
        for i, wk in enumerate(weekly):
            color = PALETTE[bucket(wk, max_week)]
            if max_week > 0 and wk > 0:
                h = MIN_BUILDING_H + (wk / max_week) * (MAX_BUILDING_H - MIN_BUILDING_H)
            else:
                h = MIN_BUILDING_H
            x = SIDE_MARGIN + i * (bw + gap)
            y = GROUND - h
            bparts.append(box(x, y, bw, h, color))
        return "\n".join(bparts)

    b_svg = buildings_svg()
    parts.append(b_svg)
    parts.append(f'''<g transform="translate(0,{GROUND}) scale(1,-0.4) translate(0,{-GROUND})" opacity="0.30" mask="url(#reflMask)">
{b_svg}
</g>''')
    parts.append(f'<rect x="0" y="{GROUND-1}" width="{W}" height="2" fill="#39c3cf" opacity="0.35"/>')
    parts.append(
        f'<text x="{W-16}" y="24" text-anchor="end" font-family="Fira Code, monospace" '
        f'font-size="13" fill="#7a8bab">{total} contributions this year</text>'
    )

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
        f'role="img" aria-label="Contribution skyline, {total} contributions">\n'
        + "\n".join(parts) + "\n</svg>"
    )
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w") as f:
        f.write(svg)
    print(f"wrote {out_path} ({len(svg)} bytes), weeks={n}, max_week={max_week}, total={total}")

if __name__ == "__main__":
    demo = "--demo" in sys.argv
    out_path = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "profile-3d-contrib/profile-singapore.svg"
    if demo:
        import random
        random.seed(9)
        weeks = []
        total = 0
        for wk in range(53):
            days = []
            for d in range(7):
                roll = random.random()
                c = 0 if roll < 0.6 else random.randint(1, 3) if roll < 0.9 else random.randint(4, 7)
                total += c
                days.append({"contributionCount": c, "date": ""})
            weeks.append({"contributionDays": days})
        render(weeks, total, out_path)
    else:
        login = os.environ["USERNAME"]
        token = os.environ["GITHUB_TOKEN"]
        weeks, total = fetch_calendar(login, token)
        render(weeks, total, out_path)
