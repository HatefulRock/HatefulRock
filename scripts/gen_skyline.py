#!/usr/bin/env python3
"""Generate an isometric contribution skyline SVG, self-scaled to the user's
own max-activity day so it stays legible at any contribution volume."""
import json
import math
import os
import sys
import urllib.request

W, H = 900, 480
TILE_W, TILE_H = 18, 9           # iso tile half-extents
MAX_BUILDING_H = 150
MIN_BUILDING_H = 6
TOP_MARGIN = MAX_BUILDING_H + 24
SIDE_MARGIN = 40
BOTTOM_MARGIN = 30

NIGHT_BG = "#050b1a"
PALETTE = ["#0a1128", "#123a5c", "#1f8a94", "#f4b400", "#ef3340"]  # low -> high

def fetch_calendar(login, token):
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays { contributionCount date }
            }
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

def shade(hexcolor, factor):
    hexcolor = hexcolor.lstrip("#")
    r, g, b = int(hexcolor[0:2], 16), int(hexcolor[2:4], 16), int(hexcolor[4:6], 16)
    r = max(0, min(255, int(r * factor)))
    g = max(0, min(255, int(g * factor)))
    b = max(0, min(255, int(b * factor)))
    return f"#{r:02x}{g:02x}{b:02x}"

def iso_building(cx, cy, height, color):
    """cx,cy = center of the tile's top face (ground level)."""
    hw, hh = TILE_W / 2, TILE_H / 2
    top = [(cx, cy - hh), (cx + hw, cy), (cx, cy + hh), (cx - hw, cy)]
    top_lifted = [(x, y - height) for x, y in top]
    left = [top[3], top[0], top_lifted[0], top_lifted[3]]
    right = [top[0], top[1], top_lifted[1], top_lifted[0]]
    out = [
        poly(left, shade(color, 0.55)),
        poly(right, shade(color, 0.85)),
        poly(top_lifted, shade(color, 1.2)),
    ]
    return "\n".join(out)

def render(weeks, total, out_path):
    n_weeks = len(weeks)
    max_r = max(len(w["contributionDays"]) for w in weeks) - 1 if weeks else 6

    # analytic bounds of the iso-diamond in local (unshifted) coords
    min_x = (0 - max_r) * (TILE_W / 2)
    max_x = (n_weeks - 1 - 0) * (TILE_W / 2)
    min_y = 0
    max_y = (n_weeks - 1 + max_r) * (TILE_H / 2)

    diamond_w = max_x - min_x
    diamond_h = max_y - min_y
    avail_w = W - 2 * SIDE_MARGIN
    scale = min(1.0, avail_w / diamond_w) if diamond_w > 0 else 1.0

    offset_x = W / 2 - (min_x + max_x) / 2 * scale
    offset_y = TOP_MARGIN - min_y * scale

    def to_screen(c, r):
        x = (c - r) * (TILE_W / 2) * scale + offset_x
        y = (c + r) * (TILE_H / 2) * scale + offset_y
        return x, y

    parts = []
    parts.append(f'''<defs>
  <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stop-color="#020610"/>
    <stop offset="60%" stop-color="{NIGHT_BG}"/>
    <stop offset="100%" stop-color="#0a1830"/>
  </linearGradient>
</defs>
<rect x="0" y="0" width="{W}" height="{H}" fill="url(#sky)"/>''')

    import random
    random.seed(3)
    stars = []
    for _ in range(50):
        sx, sy = random.uniform(0, W), random.uniform(10, TOP_MARGIN - 10)
        r = random.choice([0.6, 0.8, 1.0])
        stars.append(f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="{r}" fill="#e8f1ff" opacity="{random.uniform(0.3,0.9):.2f}"/>')
    parts.append("\n".join(stars))

    all_counts = [d["contributionCount"] for w in weeks for d in w["contributionDays"]]
    max_count = max(all_counts) if all_counts else 0

    buildings = []
    for c, w in enumerate(weeks):
        for r, d in enumerate(w["contributionDays"]):
            count = d["contributionCount"]
            color = PALETTE[bucket(count, max_count)]
            if max_count > 0 and count > 0:
                h = MIN_BUILDING_H + (count / max_count) * (MAX_BUILDING_H - MIN_BUILDING_H)
            else:
                h = MIN_BUILDING_H
            h *= scale
            cx, cy = to_screen(c, r)
            buildings.append((c + r, cx, cy, h, color))

    buildings.sort(key=lambda t: t[0])
    for _, cx, cy, h, color in buildings:
        parts.append(iso_building(cx, cy, h, color))

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
    print(f"wrote {out_path} ({len(svg)} bytes), max_count={max_count}, total={total}, scale={scale:.2f}")

if __name__ == "__main__":
    demo = "--demo" in sys.argv
    out_path = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "profile-3d-contrib/profile-singapore.svg"
    if demo:
        import random
        random.seed(11)
        weeks = []
        total = 0
        for wk in range(53):
            days = []
            for d in range(7):
                roll = random.random()
                if roll < 0.55:
                    c = 0
                elif roll < 0.85:
                    c = random.randint(1, 3)
                elif roll < 0.97:
                    c = random.randint(4, 8)
                else:
                    c = random.randint(9, 15)
                total += c
                days.append({"contributionCount": c, "date": ""})
            weeks.append({"contributionDays": days})
        render(weeks, total, out_path)
    else:
        login = os.environ["USERNAME"]
        token = os.environ["GITHUB_TOKEN"]
        weeks, total = fetch_calendar(login, token)
        render(weeks, total, out_path)
