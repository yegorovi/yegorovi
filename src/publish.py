#!/usr/bin/env python3
"""publish.py - публикация SVG и readme на гитхабе."""
import hashlib
import json
import re
import subprocess
import time
from datetime import datetime

from settings import settings


def log(msg: str) -> None:
	"""Печатает строку со временем и пишет в ws.log."""
	line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}"
	print(line, flush=True)
	try:
		with open(settings.logs / "ws.log", "a", encoding="utf-8") as fh:
			fh.write(line + "\n")
	except Exception:
		pass


def git(worktree, *args):
	"""git-команда в worktree, при ошибке падает."""
	subprocess.run(["git", "-C", str(worktree), *args], check=True)


def has_changes(worktree) -> bool:
	"""Есть ли что коммитить."""
	git(worktree, "add", "-A")
	r = subprocess.run(
		["git", "-C", str(worktree), "diff", "--cached", "--quiet"])
	return r.returncode != 0


def push(worktree, branch: str, tries: int = 3) -> bool:
	"""Пуш с повторами."""
	for attempt in range(1, tries + 1):
		try:
			git(worktree, "push", "-q", "origin", branch)
			return True
		except subprocess.CalledProcessError as exc:
			log(f"push {branch} attempt {attempt}/{tries} failed: {exc}")
			if attempt < tries:
				time.sleep(2 * attempt)
	return False


def publish(dark: bytes, light: bytes):
	"""Публикует SVG в output и readme в main."""
	ver = hashlib.md5(dark + light).hexdigest()[:8]
	names = {
		"neofetch-dark.svg": f"neofetch-{ver}-dark.svg",
		"neofetch-light.svg": f"neofetch-{ver}-light.svg",
	}
	payload = {
		names["neofetch-dark.svg"]: dark,
		names["neofetch-light.svg"]: light,
	}
	# имя файла каждый раз новое: raw.githubusercontent кэширует URL
	# 5 минут и игнорирует query-string. Старые имена удалять нельзя -
	# закэшированный readme на них ссылается и даст битую картинку;
	# держим два поколения имён, остальное вычищаем
	# remote main может уехать вперёд (правки в вебе) - сначала
	# синхронизация (заодно откатывает неудачный прошлый push)
	git(settings.root, "fetch", "-q", "origin", "main")
	git(settings.root, "reset", "-q", "--hard", "origin/main")
	text = settings.readme.read_text(encoding="utf-8")
	keep = set(re.findall(
		r"neofetch(?:-[0-9a-f]{8})?-(?:dark|light)\.svg", text))
	prev = subprocess.run(
		["git", "-C", str(settings.root), "show", "HEAD~1:README.md"],
		capture_output=True, text=True)
	if prev.returncode == 0:
		keep |= set(re.findall(
			r"neofetch(?:-[0-9a-f]{8})?-(?:dark|light)\.svg",
			prev.stdout))

	# ветка output: пишем актуальные имена, чистим только лишние
	changed = False
	for f in settings.out_worktree.glob("neofetch*.svg"):
		if f.name not in payload and f.name not in keep:
			f.unlink()
			changed = True
	for name, data in payload.items():
		dst = settings.out_worktree / name
		if not dst.exists() or dst.read_bytes() != data:
			dst.write_bytes(data)
			changed = True
	if changed and has_changes(settings.out_worktree):
		git(settings.out_worktree, "commit", "-q", "-m", f"update {ver}")
		log(f"output committed ({ver})")
	# push, если лок впереди remote (в т.ч. после прошлой неудачи):
	# readme не должен обновляться раньше, чем файлы в output
	git(settings.out_worktree, "fetch", "-q", "origin", "output")
	ahead = subprocess.run(
		["git", "-C", str(settings.out_worktree), "rev-list", "--count",
         "origin/output..HEAD"],
		capture_output=True, text=True)
	if ahead.stdout.strip() != "0":
		if not push(settings.out_worktree, "output"):
			log("output push failed, readme publish skipped")
			return
		log(f"pushed output ({ver})")

	# main: readme ссылается на свежие имена
	new_text = re.sub(
		r"neofetch(?:-[0-9a-f]{8})?-(dark|light)\.svg",
		lambda m: names[f"neofetch-{m.group(1)}.svg"],
		text,
	)
	if new_text != text:
		settings.readme.write_text(new_text, encoding="utf-8", newline="\n")
		git(settings.root, "add", "README.md")
		staged = subprocess.run(
			["git", "-C", str(settings.root), "diff", "--cached", "--quiet"])
		if staged.returncode != 0:
			git(settings.root, "commit", "-q", "-m",
				"изменение статуса карточки")
			if push(settings.root, "main"):
				log(f"pushed readme ({ver})")
			else:
				git(settings.root, "reset", "-q", "--hard", "origin/main")
				log("readme push failed, rolled back "
					"(will retry on next event)")


def fingerprint(data: dict) -> tuple:
	"""Отпечаток активности: регенерируем только при её смене."""
	acts = []
	for act in data.get("activities") or []:
		assets = act.get("assets") or {}
		image = assets.get("large_image") or ""
		if image:
			# CDN-подпись (ex=..&hm=..) ротируется каждые секунды - режем
			image = image.split("?")[0]
		acts.append({
			"type": act.get("type"),
			"name": act.get("name"),
			"details": act.get("details"),
			"state": act.get("state"),
			"large_image": image,
			"large_text": assets.get("large_text"),
		})
	slim = {
		"status": data.get("discord_status"),
		"desktop": data.get("active_on_discord_desktop"),
		"mobile": data.get("active_on_discord_mobile"),
		"web": data.get("active_on_discord_web"),
		"spotify": bool(data.get("spotify")),
		"activities": acts,
	}
	blob = json.dumps(slim, sort_keys=True, ensure_ascii=False)
	return hashlib.md5(blob.encode()).hexdigest(), blob
