#!/usr/bin/env python3
"""Lanyard WS (Discord) + Яндекс.Музыка Ynison (треки) >> перегенерация SVG.

Использование:
  python github-readme-bot.py            # слушать, при изменении писать SVG
  python github-readme-bot.py --push     # + git commit/push в ветку output (для VPS)

Источники:
  * Discord (статус/платформы/игры/кастомный статус) - Lanyard WebSocket.
  * Музыка (трек/исполнитель/обложка) - Яндекс.Музыка, Ynison (ym.py);
    смена трека приходит отдельным потоком MusicMonitor.
"""
import asyncio
import hashlib
import json
import re
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import websockets

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import update  # noqa: E402
import ym  # noqa: E402

LANYARD_ID = "505825418624892939"
WS_URL = "wss://api.lanyard.rest/socket"
OUT_WORKTREE = Path("/opt/profile_out")
README = HERE / "README.md"
RAW_BASE = "https://raw.githubusercontent.com/yegorovi/yegorovi/output/"
_last_fp = None  # отпечаток активности: регенерируем только при её смене


def log(msg):
	"""Печатает строку со временем в stdout и в ws.log."""
	line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}"
	print(line, flush=True)
	try:
		with open(HERE / "ws.log", "a", encoding="utf-8") as fh:
			fh.write(line + "\n")
	except Exception:
		pass


def _git(worktree, *args):
	"""git-команда в worktree, при ошибке падает."""
	subprocess.run(["git", "-C", str(worktree), *args], check=True)


def _has_changes(worktree):
	"""Ставит всё в индекс и проверяет, есть ли что коммитить."""
	subprocess.run(["git", "-C", str(worktree), "add", "-A"], check=True)
	r = subprocess.run(
		["git", "-C", str(worktree), "diff", "--cached", "--quiet"])
	return r.returncode != 0


def _push(worktree, branch, tries=3):
	"""Пуш с повторами: tries попыток с растущей паузой, итог True/False."""
	for attempt in range(1, tries + 1):
		try:
			_git(worktree, "push", "-q", "origin", branch)
			return True
		except subprocess.CalledProcessError as exc:
			log(f"push {branch} attempt {attempt}/{tries} failed: {exc}")
			if attempt < tries:
				time.sleep(2 * attempt)
	return False


def publish(dark: bytes, light: bytes):
	"""Версионированные имена в output + переписанный README в main.

    raw.githubusercontent кэширует URL 5 минут (max-age=300) и игнорирует
    query-string в ключе кэша, поэтому обход - каждый раз НОВОЕ имя файла.
    HTML профиля github.com подхватывает README за ~1 секунду.
    """
	ver = hashlib.md5(dark + light).hexdigest()[:8]
	names = {
		"neofetch-dark.svg": f"neofetch-{ver}-dark.svg",
		"neofetch-light.svg": f"neofetch-{ver}-light.svg",
	}
	payload = {
		names["neofetch-dark.svg"]: dark,
		names["neofetch-light.svg"]: light,
	}
	# raw.githubusercontent кэширует URL 5 минут и игнорирует
	# query-string, поэтому имя файла каждый раз новое; старые
	# удалять нельзя - закэшированные README (github.com и raw)
	# ссылаются на прежние имена и дают битую картинку.
	# Оставляем имена из текущего README и его прошлой версии
	# (два поколения назад переживают любой разумный кэш),
	# остальные старые вычищаем, чтобы ветка не разрасталась.
	# remote main может уехать вперёд (правки в вебе) - сначала
	# синхронизация (заодно откатывает неудачный прошлый push):
	_git(HERE, "fetch", "-q", "origin", "main")
	_git(HERE, "reset", "-q", "--hard", "origin/main")
	text = README.read_text(encoding="utf-8")
	keep = set(re.findall(
		r"neofetch(?:-[0-9a-f]{8})?-(?:dark|light)\.svg", text))
	prev = subprocess.run(
		["git", "-C", str(HERE), "show", "HEAD~1:README.md"],
		capture_output=True, text=True)
	if prev.returncode == 0:
		keep |= set(re.findall(
			r"neofetch(?:-[0-9a-f]{8})?-(?:dark|light)\.svg",
			prev.stdout))

	# ветка output: пишем актуальные имена, чистим только лишние
	changed = False
	for f in OUT_WORKTREE.glob("neofetch*.svg"):
		if f.name not in payload and f.name not in keep:
			f.unlink()
			changed = True
	for name, data in payload.items():
		dst = OUT_WORKTREE / name
		if not dst.exists() or dst.read_bytes() != data:
			dst.write_bytes(data)
			changed = True
	if changed and _has_changes(OUT_WORKTREE):
		_git(OUT_WORKTREE, "commit", "-q", "-m", f"update {ver}")
		log(f"output committed ({ver})")
	# push, если лок впереди remote (в т.ч. после прошлой неудачи):
	# README не должен обновляться раньше, чем файлы в output
	_git(OUT_WORKTREE, "fetch", "-q", "origin", "output")
	ahead = subprocess.run(
		["git", "-C", str(OUT_WORKTREE), "rev-list", "--count",
         "origin/output..HEAD"],
		capture_output=True, text=True)
	if ahead.stdout.strip() != "0":
		if not _push(OUT_WORKTREE, "output"):
			log("output push failed, readme publish skipped")
			return
		log(f"pushed output ({ver})")

	# main: README ссылается на свежие имена
	new_text = re.sub(
		r"neofetch(?:-[0-9a-f]{8})?-(dark|light)\.svg",
		lambda m: names[f"neofetch-{m.group(1)}.svg"],
		text,
	)
	if new_text != text:
		README.write_text(new_text, encoding="utf-8", newline="\n")
		_git(HERE, "add", "README.md")
		staged = subprocess.run(
			["git", "-C", str(HERE), "diff", "--cached", "--quiet"])
		if staged.returncode != 0:
			_git(HERE, "commit", "-q", "-m", "изменение статуса карточки")
			if _push(HERE, "main"):
				log(f"pushed readme ({ver})")
			else:
				_git(HERE, "reset", "-q", "--hard", "origin/main")
				log("readme push failed, rolled back "
					"(will retry on next event)")


def fingerprint(data):
	"""Отпечаток того, что видно на карточке: статус + активности.

    presence шлётся каждые ~3-10 с даже без изменений - regen/push делаем
    только когда трек/игра/статус реально сменились (появился/пропал).
    """
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


_regen_lock = threading.Lock()
_regen_pending = threading.Event()  # событие пришло во время регенерации


def regenerate():
	"""Перегенерирует SVG и публикует (под замком).

    Если событие пришло, пока идёт регенерация, - оно НЕ теряется:
    помечается в _regen_pending и отрабатывает повтором сразу после.
    Раньше такое событие выкидывалось (lock без ожидания), а fingerprint
    уже был запомнен - карточка обновлялась только со следующим событием
    ("иногда с большой задержкой меняет").
    """
	if not _regen_lock.acquire(blocking=False):
		_regen_pending.set()
		return
	try:
		while True:
			_regen_pending.clear()
			try:
				update.main_once()
			except Exception as exc:
				log(f"update error: {exc}")
				return
			log("svg regenerated")
			if "--push" not in sys.argv or not OUT_WORKTREE.exists():
				if not _regen_pending.is_set():
					return
				continue
			try:
				publish(
					(update.DIST / "neofetch-dark.svg").read_bytes(),
					(update.DIST / "neofetch-light.svg").read_bytes(),
				)
			except Exception as exc:
				log(f"push error: {exc}")
				return
			if not _regen_pending.is_set():
				return
	finally:
		_regen_lock.release()


async def heartbeat(ws, interval_ms):
	"""Шлёт сердцебиение в websocket раз в interval_ms."""
	while True:
		await asyncio.sleep(interval_ms / 1000)
		await ws.send(json.dumps({"op": 3, "d": None}))


async def listen():
	"""Держит websocket: события активности и реконнект с бэкоффом."""
	global _last_fp
	delay = 1
	while True:
		try:
			async with websockets.connect(
				WS_URL, max_size=2 * 1024 * 1024, open_timeout=15
			) as ws:
				hello = json.loads(await asyncio.wait_for(ws.recv(), 15))
				if hello.get("op") != 1:
					raise RuntimeError(f"unexpected hello: {hello}")
				interval = hello["d"].get("heartbeat_interval", 45000)
				await ws.send(json.dumps(
					{"op": 2, "d": {"subscribe_to_id": LANYARD_ID}}))
				hb = asyncio.create_task(heartbeat(ws, interval))
				delay = 1
				log("connected, waiting for events")
				try:
					async for raw in ws:
						msg = json.loads(raw)
						if msg.get("op") != 0:
							continue
						kind = msg.get("t")
						if kind not in ("INIT_STATE", "PRESENCE_UPDATE"):
							continue
						data = msg.get("d") or {}
						fp, blob = fingerprint(data)
						if fp == _last_fp:
							continue
						prev = _last_fp
						_last_fp = fp
						log(f"event {kind} -> activity changed ({fp[:8]}) "
							f"prev={prev and prev[:8]}")
						log(f"  slim={blob[:600]}")
						regenerate()
				finally:
					hb.cancel()
		except asyncio.CancelledError:
			raise
		except Exception as exc:
			log(f"ws error: {exc}; reconnect in {delay}s")
			await asyncio.sleep(delay)
			delay = min(delay * 2, 60)


def _set_title():
	"""Показывать процесс как github-readme-bot.py в htop/ps."""
	try:
		import setproctitle
		setproctitle.setproctitle("github-readme-bot.py")
	except Exception:
		pass


def main():
	"""Стартует монитор музыки и слушает Lanyard до Ctrl+C."""
	_set_title()
	update.DIST.mkdir(exist_ok=True)
	regenerate()
	# смена трека в Яндекс.Музыке >> регенерация (Lanyard об этом не знает)
	ym.MusicMonitor(lambda info: (log(f"ymusic -> {info}"), regenerate()),
					seed="readme", title="profile-readme").start()
	try:
		asyncio.run(listen())
	except KeyboardInterrupt:
		log("stopped")


if __name__ == "__main__":
	main()
