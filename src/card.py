#!/usr/bin/env python3
"""card.py - сборка строк карточки и рендер SVG."""
import random
from datetime import date

from data import clean_text, pick_activity
from settings import settings


def esc(s: str) -> str:
	"""Экранирует xml-символы для svg-текста."""
	return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def age() -> int:
	"""Возраст по дате рождения."""
	today = date.today()
	born = settings.birth
	res = today.year - born.year
	if (today.month, today.day) < (born.month, born.day):
		res -= 1
	return res


def trim(segs, limit: int) -> list:
	"""Обрезает строки по лимиту колонки."""
	total = 0
	for text, _ in segs:
		total += len(text)
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


def build_rows(data: dict, theme: str, image_data=None, music=None) -> list:
	"""Строки карточки."""
	_, game, custom = pick_activity(data)
	rows = [("hdr", "yegorovi@github")]
	icon, label = settings.status.get(data.get("discord_status", "offline"),
                                      settings.status["offline"])
	platforms = []
	for key, name in (("active_on_discord_desktop", "desktop"),
                      ("active_on_discord_mobile", "mobile"),
                      ("active_on_discord_web", "web")):
		if data.get(key):
			platforms.append(name)
	where = ""
	if platforms:
		where = " \u00b7 " + ", ".join(platforms)
	rows.append(("line", [("  " + icon + " " + label + where, "value")]))
	rows.append(("blank",))
	rows.append(("kv", "Name", random.choice(settings.names)))
	rows.append(("kv", "Age", str(age())))
	rows.append(("blank",))

	has_activity = False
	if music and (music.get("track") or music.get("artist")
                  or music.get("app")):
		app = clean_text(music.get("app"))
		track = clean_text(music.get("track"))
		artist = clean_text(music.get("artist"))
		album = clean_text(music.get("album"))
		if not has_activity:
			rows.append(("sec_r", "Activity", "yegorovi"))
			has_activity = True
		if app:
			rows.append(("blank",))
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
		if not has_activity:
			rows.append(("sec_r", "Activity", "yegorovi"))
			has_activity = True
		segs = [("  ▶ ", "key"), (game["name"], "value")]
		if game.get("details"):
			segs.append((" - " + game["details"], "value"))
		rows.append(("line", segs))

	if custom:
		ctext = custom.get("state") or custom.get("details")
		if ctext:
			if not has_activity:
				rows.append(("sec_r", "Activity", "yegorovi"))
				has_activity = True
			cemoji = (custom.get("emoji") or {}).get("name") or ""
			prefix = "  "
			if cemoji:
				prefix = f"  {cemoji} "
			rows.append(("line", [(prefix, "key"), (ctext, "value")]))

	rows.append(("blank",))
	rows.append(("sec", "System"))
	rows.extend(("kv", k, v) for k, v in settings.system)

	rows.append(("blank",))
	rows.append(("sec", "Languages"))
	color_idx = 1
	if theme != "dark":
		color_idx = 2
	lang_segs = []
	for i, item in enumerate(settings.languages):
		if i:
			lang_segs.append((", ", "cc"))
		lang_segs.append((item[0], f"lang:{item[color_idx]}"))
	rows.append(("line", [("  ", "cc")] + lang_segs))

	rows.append(("blank",))
	rows.append(("sec", "Hobbies"))
	rows.extend(("kv", k, v) for k, v in settings.hobbies)

	rows.append(("blank",))
	rows.append(("sec", "Projects"))
	rows.extend(("kv", k, v) for k, v in settings.projects)

	rows.append(("blank",))
	rows.append(("sep",))
	rows.append(("prompt",))
	return rows


def seg_fill(seg_cls: str, pal: dict) -> str:
	"""Цвет сегмента."""
	if seg_cls.startswith("lang:"):
		return seg_cls[5:]
	if seg_cls.startswith("#"):
		return seg_cls
	return pal.get(seg_cls, pal["text"])


def render(rows: list, pal: dict) -> str:
	"""Собирает SVG."""
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
			y += settings.lh
			continue
		limit = settings.maxcol
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
			dots = max(2, settings.kv_col - (len(key) + 2))
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
			x_text = settings.pad
			if uri:
				size = 50
				iy = y - 10
				cid = f"playclip{len(thumbs)}"
				defs.append(
					f'<clipPath id="{cid}"><rect x="{settings.pad}" '
					f'y="{iy}" width="{size}" height="{size}" '
					f'rx="6"/></clipPath>'
				)
				thumbs.append(
					f'<image href="{uri}" x="{settings.pad}" y="{iy}" '
					f'width="{size}" height="{size}" '
					f'preserveAspectRatio="xMidYMid slice" '
					f'clip-path="url(#{cid})"/>'
				)
				thumbs.append(
					f'<rect x="{settings.pad}.5" y="{iy}.5" '
					f'width="{size - 1}" height="{size - 1}" rx="6" '
					f'fill="none" stroke="{pal["border"]}"/>'
				)
				x_text = settings.pad + size + 8
			lim = int((settings.width - settings.pad - x_text)
                      / settings.charw)
			for i, lsegs in enumerate(lines):
				yy = y + i * settings.lh
				out = [f'<tspan x="{x_text}" y="{yy}">']
				for s in trim(lsegs, lim):
					out.append(
						f'<tspan fill="{seg_fill(s[1], pal)}">'
						f'{esc(s[0])}</tspan>'
					)
				out.append("</tspan>")
				text_parts.append("".join(out))
				max_y = max(max_y, yy)
			y = y + n * settings.lh
			continue
		elif kind == "sep":
			segs = [("─" * limit, "cc")]
		elif kind == "prompt":
			segs = [("visitor@", "cc"), ("yegorovi", "key"), (":", "cc"),
					("~", "value"), ("$ ", "cc")]
			out = [f'<tspan x="{settings.pad}" y="{y}">']
			for s in segs:
				out.append(
					f'<tspan fill="{seg_fill(s[1], pal)}">'
					f'{esc(s[0])}</tspan>')
			out.append(
				f'<tspan fill="{pal["key"]}">█'
				'<animate attributeName="fill-opacity" dur="1.06s" '
				'keyTimes="0;0.5;0.5;1" repeatCount="indefinite" '
				'values="1;1;0;0" /></tspan></tspan>'
			)
			text_parts.append("".join(out))
			max_y = y
			y += settings.lh
			continue
		elif kind == "bar":
			colors = row[1]
			total = settings.width - 2 * settings.pad
			seg_w = total / len(colors)
			for i, color in enumerate(colors):
				rects.append(
					f'<rect x="{settings.pad + i * seg_w:.2f}" '
					f'y="{y - 13}" width="{seg_w:.2f}" height="13" '
					f'fill="{color}"/>'
				)
			max_y = y
			y += settings.lh
			continue

		out = [f'<tspan x="{settings.pad}" y="{y}">']
		for s in segs:
			out.append(
				f'<tspan fill="{seg_fill(s[1], pal)}">{esc(s[0])}</tspan>')
		out.append("</tspan>")
		text_parts.append("".join(out))
		max_y = y
		y += settings.lh

	height = max_y + settings.pad
	svg = [
		f'<svg xmlns="http://www.w3.org/2000/svg" width="{settings.width}" '
		f'height="{height}" viewBox="0 0 {settings.width} {height}" '
		f'font-family="{settings.font}" font-size="{settings.fs}px">',
		f'<rect x="0.5" y="0.5" width="{settings.width - 1}" '
		f'height="{height - 1}" rx="15" fill="{pal["bg"]}" '
		f'stroke="{pal["border"]}"/>',
		"<defs>", *defs, "</defs>",
		*thumbs,
		f'<text fill="{pal["text"]}">',
		*text_parts,
		"</text>",
		*rects,
		"</svg>",
	]
	return "\n".join(svg) + "\n"
