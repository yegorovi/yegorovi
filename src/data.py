#!/usr/bin/env python3
"""data.py - данные профиля: lanyard, картинки, музыка."""
import base64
import hashlib
import io
import json
import sys
import time
import urllib.request

from PIL import Image, ImageOps

import ym
from settings import settings


def clean_text(s) -> str:
	"""Чистит текст от шаблонов Яндекса."""
	if not s:
		return ""
	if "{{" in s or "}}" in s:
		return ""
	return s.strip()


def no_music_active() -> bool:
	"""Флаг сброса музыки - файл свежее окна сброса."""
	try:
		age = time.time() - settings.no_music_file.stat().st_mtime
		return age < settings.no_music_window
	except OSError:
		return False


def fetch() -> dict:
	"""Данные профиля из Lanyard по HTTP."""
	req = urllib.request.Request(
		f"https://api.lanyard.rest/v1/users/{settings.lanyard_id}",
		headers={"User-Agent": "profile-readme/1.0"},
	)
	with urllib.request.urlopen(req, timeout=15) as resp:
		payload = json.load(resp)
	if not payload.get("success"):
		raise RuntimeError(f"lanyard error: {payload}")
	return payload["data"]


def pick_activity(data: dict) -> tuple:
	"""Музыка, игра и кастом из активностей."""
	music = None
	game = None
	custom = None
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
	"""Прогресс трека в клетках."""
	if not ts or not ts.get("start") or not ts.get("end"):
		return None
	span = ts["end"] - ts["start"]
	if span <= 0:
		return None
	pct = (time.time() * 1000 - ts["start"]) / span
	if pct < 0 or pct > 1:
		return None
	return round(pct * 10)


def fetch_image_url(url):
	"""Картинка >> data URI (с кэшем на диске)."""
	if not url:
		return None
	if url.startswith("mp:"):
		url = "https://media.discordapp.net/" + url[3:]
	if url.startswith("/"):
		url = "https:" + url
	cache = settings.image_cache
	cache.mkdir(exist_ok=True)
	blob = cache / (hashlib.md5(url.encode()).hexdigest() + ".bin")
	if blob.exists():
		raw = blob.read_bytes()
	else:
		req = urllib.request.Request(url,
			headers={"User-Agent": "profile-readme/1.0"})
		with urllib.request.urlopen(req, timeout=15) as resp:
			raw = resp.read()
		blob.write_bytes(raw)
	try:
		im = Image.open(io.BytesIO(raw)).convert("RGB")
		im = ImageOps.fit(im, (settings.img_size, settings.img_size),
                          Image.LANCZOS)
		out = io.BytesIO()
		im.save(out, "PNG")
		raw = out.getvalue()
	except Exception:
		return None
	return "data:image/png;base64," + base64.b64encode(raw).decode()


def fetch_activity_image(act):
	"""Обложка активности."""
	if not act:
		return None
	return fetch_image_url((act.get("assets") or {}).get("large_image"))


def get_music():
	"""Музыка из Яндекс.Музыки, фолбэк - активность Lanyard."""
	if no_music_active():
		return None
	info = None
	try:
		info = ym.fetch_now("readme")
	except Exception as exc:
		print(f"ym error: {exc}", file=sys.stderr)
	if info:
		return info
	try:
		act = pick_activity(fetch())[0]
		if act and (act.get("details") or act.get("state")):
			assets = act.get("assets") or {}
			return {"app": clean_text(act.get("name")),
				"track": clean_text(act.get("details")),
				"artist": clean_text(act.get("state")),
				"album": clean_text(assets.get("large_text")),
				"cover": assets.get("large_image")}
	except Exception:
		pass
	return None
