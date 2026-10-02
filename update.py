#!/usr/bin/env python3
import base64
import hashlib
import io
import json
import random
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

LANYARD_ID = "505825418624892939"
HERE = Path(__file__).resolve().parent
DIST = HERE / "dist"

FONT = "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace"
FS = 16
LH = 20
PAD = 24
CHARW = 9.6
WIDTH = 760
KV_COL = 24
MAXCOL = int((WIDTH - 2 * PAD) / CHARW)

DARK = {
    "bg": "#161b22", "border": "#30363d", "text": "#c9d1d9", "key": "#ffa657",
    "value": "#a5d6ff", "cc": "#6e7681", "green": "#3fb950", "warn": "#d29922",
}
LIGHT = {
    "bg": "#ffffff", "border": "#d0d7de", "text": "#1f2328", "key": "#953800",
    "value": "#0550ae", "cc": "#656d76", "green": "#1a7f37", "warn": "#9a6700",
}

STATUS = {
    "online": ("🟢", "Online"),
    "idle": ("🟡", "Idle"),
    "dnd": ("🔴", "Do Not Disturb"),
    "offline": ("⚫", "Offline"),
}

SYSTEM = [
    ("CPU", "AMD Ryzen 9 9950X3D"),
    ("GPU", "AMD Radeon RX 9070 XT"),
    ("RAM", "64 GB"),
]

LANGUAGES = [
    ("Python", "#3572A5", "#3572A5"),
    ("Java", "#b07219", "#b07219"),
    ("C++", "#f34b7d", "#f34b7d"),
    ("C#", "#178600", "#178600"),
    ("JavaScript", "#f1e05a", "#7a6e00"),
    ("Assembly", "#6E4C1E", "#6E4C1E"),
]

IMG_SIZE = 112
THUMB = 16
THUMB_COLS = 3
BIRTH = date(2005, 9, 15)

HOBBIES = [
    ("Shooting", "Tactical & clay"),
    ("Coding", "Game servers & mods"),
    ("Embedded", "Microcontrollers"),
]

NAMES = ["yegorovi", "ivan", "\u30bf\u30af\u30e9\u206c", "takura", "0xdead.moscow"]

PROJECTS = [
    ("DayZ", "Last-Breath"),
]


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def age():
    today = date.today()
    return today.year - BIRTH.year - ((today.month, today.day) < (BIRTH.month, BIRTH.day))


def trim(segs, limit):
    total = sum(len(t) for t, _ in segs)
    if total <= limit:
        return segs
    out = []
    left = limit - 1
    for text, cls in segs:
        if left <= 0:
            break
        if len(text) <= left:
            out.append((text, cls))
            left -= len(text)
        else:
            out.append((text[:left], cls))
            left = 0
    out.append(("…", "cc"))
    return out


def fetch():
    req = urllib.request.Request(
        f"https://api.lanyard.rest/v1/users/{LANYARD_ID}",
        headers={"User-Agent": "profile-readme/1.0"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.load(resp)
    if not payload.get("success"):
        raise RuntimeError(f"lanyard error: {payload}")
    return payload["data"]


def pick_activity(data):
    music = game = custom = None
    for act in data.get("activities") or []:
        kind = act.get("type")
        if kind == 2 and music is None:
            music = act
        elif kind == 0 and game is None:
            game = act
        elif kind == 4 and custom is None:
            custom = act
    if music is None and data.get("spotify"):
        sp = data["spotify"]
        music = {"details": sp.get("track"), "state": sp.get("artist"),
                 "timestamps": sp.get("timestamps")}
    return music, game, custom


def progress_cells(ts):
    if not ts or not ts.get("start") or not ts.get("end"):
        return None
    span = ts["end"] - ts["start"]
    if span <= 0:
        return None
    pct = (time.time() * 1000 - ts["start"]) / span
    if pct < 0 or pct > 1:
        return None
    return round(pct * 10)


def fetch_activity_image(act):
    if not act:
        return None
    url = (act.get("assets") or {}).get("large_image")
    if not url:
        return None
    if url.startswith("mp:"):
        url = "https://media.discordapp.net/" + url[3:]
    cache = HERE / "image_cache"
    cache.mkdir(exist_ok=True)
    blob = cache / (hashlib.md5(url.encode()).hexdigest() + ".bin")
    if blob.exists():
        raw = blob.read_bytes()
    else:
        req = urllib.request.Request(url, headers={"User-Agent": "profile-readme/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
        blob.write_bytes(raw)
    try:
        from PIL import Image, ImageOps
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        im = ImageOps.fit(im, (IMG_SIZE, IMG_SIZE), Image.LANCZOS)
        out = io.BytesIO()
        im.save(out, "PNG")
        raw = out.getvalue()
    except Exception:
        return None
    return "data:image/png;base64," + base64.b64encode(raw).decode()


def clean_text(s):
    if not s:
        return ""
    if "{{" in s or "}}" in s:
        return ""
    return s.strip()


def build_rows(data, theme, image_data=None):
    music, game, custom = pick_activity(data)
    rows = [("hdr", "yegorovi@github"), ("blank",)]
    rows.append(("kv", "Name", random.choice(NAMES)))
    rows.append(("kv", "Age", str(age())))
    rows.append(("blank",))

    rows.append(("sec_r", "Discord Activity", "yegorovi"))
    icon, label = STATUS.get(data.get("discord_status", "offline"), STATUS["offline"])
    platforms = [name for key, name in (
        ("active_on_discord_desktop", "desktop"),
        ("active_on_discord_mobile", "mobile"),
        ("active_on_discord_web", "web"),
    ) if data.get(key)]
    where = " \u00b7 " + ", ".join(platforms) if platforms else ""
    rows.append(("line", [("  " + icon + " " + label + where, "value")]))

    if music and (music.get("details") or music.get("state")
                  or music.get("name")):
        artist = clean_text(music.get("state"))
        track = clean_text(music.get("details"))
        app = clean_text(music.get("name"))
        album = clean_text((music.get("assets") or {}).get("large_text"))
        if app:
            rows.append(("line", [("Listining: " + app, "value")]))
        lines = []
        if track:
            lines.append([(track, "green")])
        if artist:
            lines.append([(artist, "text")])
        if album:
            lines.append([(album, "cc")])
        if not lines:
            lines = [[("\u266a нет данных", "cc")]]
        rows.append(("player", image_data, lines))

    if game and game.get("name"):
        segs = [("  ▶ ", "key"), (game["name"], "value")]
        if game.get("details"):
            segs.append((" \u2014 " + game["details"], "value"))
        rows.append(("line", segs))

    if custom:
        ctext = custom.get("state") or custom.get("details")
        if ctext:
            cemoji = (custom.get("emoji") or {}).get("name") or ""
            prefix = f"  {cemoji} " if cemoji else "  "
            rows.append(("line", [(prefix, "key"), (ctext, "value")]))

    rows.append(("blank",))
    rows.append(("sec", "System"))
    rows.extend(("kv", k, v) for k, v in SYSTEM)

    rows.append(("blank",))
    rows.append(("sec", "Languages"))
    color_idx = 1 if theme == "dark" else 2
    lang_segs = []
    for i, item in enumerate(LANGUAGES):
        if i:
            lang_segs.append((", ", "cc"))
        lang_segs.append((item[0], f"lang:{item[color_idx]}"))
    rows.append(("line", [("  ", "cc")] + lang_segs))

    rows.append(("blank",))
    rows.append(("sec", "Hobbies"))
    rows.extend(("kv", k, v) for k, v in HOBBIES)

    rows.append(("blank",))
    rows.append(("sec", "Projects"))
    rows.extend(("kv", k, v) for k, v in PROJECTS)

    rows.append(("blank",))
    rows.append(("sep",))
    rows.append(("prompt",))
    return rows


def seg_fill(seg_cls, pal):
    if seg_cls.startswith("lang:"):
        return seg_cls[5:]
    if seg_cls.startswith("#"):
        return seg_cls
    return pal.get(seg_cls, pal["text"])


def render(rows, pal):
    y = 40
    text_parts = []
    rects = []
    thumbs = []
    defs = []
    max_y = y

    for row in rows:
        kind = row[0]
        segs = None
        if kind == "blank":
            y += LH
            continue
        limit = MAXCOL
        if kind == "hdr":
            title = row[1]
            dashes = "─" * max(4, limit - len(title) - 1)
            segs = [(title, "text"), (" " + dashes, "cc")]
        elif kind == "sec":
            title = row[1]
            dashes = "─" * max(4, limit - len(title) - 1)
            segs = [(title, "text"), (" " + dashes, "cc")]
        elif kind == "sec_r":
            title, suffix = row[1], row[2]
            dashes = "─" * max(4, limit - len(title) - len(suffix) - 2)
            segs = [(title, "text"), (" " + dashes + " ", "cc"),
                    (suffix, "cc")]
        elif kind == "kv":
            key, val = row[1], row[2]
            dots = max(2, KV_COL - (len(key) + 2))
            segs = trim([
                ("  " + key + ":", "key"),
                (" " + "." * dots, "cc"),
                (" " + val, "value"),
            ], limit)
        elif kind == "line":
            segs = trim(row[1], limit)
        elif kind == "player":
            uri, lines = row[1], row[2]
            n = len(lines)
            block_h = (n - 1) * LH
            x_text = PAD
            if uri:
                size = 50
                iy = y - 10
                cid = f"playclip{len(thumbs)}"
                defs.append(
                    f'<clipPath id="{cid}"><rect x="{PAD}" y="{iy}" '
                    f'width="{size}" height="{size}" rx="6"/></clipPath>'
                )
                thumbs.append(
                    f'<image href="{uri}" x="{PAD}" y="{iy}" '
                    f'width="{size}" height="{size}" '
                    f'preserveAspectRatio="xMidYMid slice" clip-path="url(#{cid})"/>'
                )
                thumbs.append(
                    f'<rect x="{PAD}.5" y="{iy}.5" width="{size - 1}" '
                    f'height="{size - 1}" rx="6" fill="none" '
                    f'stroke="{pal["border"]}"/>'
                )
                x_text = PAD + size + 8
            limit = int((WIDTH - PAD - x_text) / CHARW)
            for i, segs in enumerate(lines):
                yy = y + i * LH
                out = [f'<tspan x="{x_text}" y="{yy}">']
                for s in trim(segs, limit):
                    out.append(
                        f'<tspan fill="{seg_fill(s[1], pal)}">{esc(s[0])}</tspan>'
                    )
                out.append("</tspan>")
                text_parts.append("".join(out))
                max_y = max(max_y, yy)
            y = y + n * LH
            continue
        elif kind == "sep":
            segs = [("─" * limit, "cc")]
        elif kind == "prompt":
            segs = [("visitor@", "cc"), ("yegorovi", "key"), (":", "cc"),
                    ("~", "value"), ("$ ", "cc")]
            cursor = ("█", "key", True)
            out = [f'<tspan x="{PAD}" y="{y}">']
            for s in segs:
                out.append(f'<tspan fill="{seg_fill(s[1], pal)}">{esc(s[0])}</tspan>')
            out.append(
                f'<tspan fill="{pal["key"]}">█'
                '<animate attributeName="fill-opacity" dur="1.06s" '
                'keyTimes="0;0.5;0.5;1" repeatCount="indefinite" '
                'values="1;1;0;0" /></tspan></tspan>'
            )
            text_parts.append("".join(out))
            max_y = y
            y += LH
            continue
        elif kind == "bar":
            colors = row[1]
            total = WIDTH - 2 * PAD
            seg_w = total / len(colors)
            for i, color in enumerate(colors):
                rects.append(
                    f'<rect x="{PAD + i * seg_w:.2f}" y="{y - 13}" '
                    f'width="{seg_w:.2f}" height="13" fill="{color}"/>'
                )
            max_y = y
            y += LH
            continue

        out = [f'<tspan x="{PAD}" y="{y}">']
        for s in segs:
            out.append(f'<tspan fill="{seg_fill(s[1], pal)}">{esc(s[0])}</tspan>')
        out.append("</tspan>")
        text_parts.append("".join(out))
        max_y = y
        y += LH

    height = max_y + PAD
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" '
        f'height="{height}" viewBox="0 0 {WIDTH} {height}" '
        f'font-family="{FONT}" font-size="{FS}px">',
        f'<rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{height - 1}" '
        f'rx="15" fill="{pal["bg"]}" stroke="{pal["border"]}"/>',
        "<defs>", *defs, "</defs>",
        *thumbs,
        f'<text fill="{pal["text"]}">',
        *text_parts,
        "</text>",
        *rects,
        "</svg>",
    ]
    return "\n".join(svg) + "\n"


def main_once():
    data = fetch()
    music, _, _ = pick_activity(data)
    image_data = fetch_activity_image(music)
    DIST.mkdir(exist_ok=True)
    written = []
    for name, pal, theme in (("neofetch-dark.svg", DARK, "dark"),
                             ("neofetch-light.svg", LIGHT, "light")):
        path = DIST / name
        path.write_text(render(build_rows(data, theme, image_data), pal),
                        encoding="utf-8")
        written.append(str(path))
    return written


def main():
    if "--watch" in sys.argv:
        from datetime import datetime
        idx = sys.argv.index("--watch")
        interval = 15
        if idx + 1 < len(sys.argv) and sys.argv[idx + 1].isdigit():
            interval = int(sys.argv[idx + 1])
        print(f"[watch] каждые {interval} сек, log: {DIST / 'watch.log'}",
              flush=True)
        while True:
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            try:
                main_once()
                msg = f"{stamp} ok"
            except Exception as exc:
                msg = f"{stamp} error: {exc}"
            print(msg, flush=True)
            try:
                with open(DIST / "watch.log", "a", encoding="utf-8") as fh:
                    fh.write(msg + "\n")
            except Exception:
                pass
            time.sleep(interval)
    written = main_once()
    if "--quiet" not in sys.argv:
        for path in written:
            print(path)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
