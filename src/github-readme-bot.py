#!/usr/bin/env python3
"""github-readme-bot.py - Lanyard WS + Яндекс.Музыка >> перегенерация SVG.

Использование:
  python github-readme-bot.py            # слушать, при изменении писать SVG
  python github-readme-bot.py --push     # + git commit/push в ветку output

Источники:
  * Discord (статус/платформы/игры/кастомный статус) - Lanyard WebSocket.
  * Музыка (трек/исполнитель/обложка) - Яндекс.Музыка, Ynison (ym.py);
    смена трека приходит отдельным потоком MusicMonitor.
"""
import asyncio
import json
import sys
import threading

import websockets

import update
import ym
from publish import fingerprint, log, publish
from settings import settings

try:
	import setproctitle
except ImportError:
	setproctitle = None

_last_fp = None  # отпечаток активности: регенерируем только при её смене

_regen_lock = threading.Lock()
_regen_pending = threading.Event()  # событие пришло во время регенерации


def regenerate():
	"""Перегенерирует SVG и публикует (с --push)."""
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
			if "--push" not in sys.argv or not settings.out_worktree.exists():
				if not _regen_pending.is_set():
					return
				continue
			try:
				publish(
					(settings.dist / "neofetch-dark.svg").read_bytes(),
					(settings.dist / "neofetch-light.svg").read_bytes(),
				)
			except Exception as exc:
				log(f"push error: {exc}")
				return
			if not _regen_pending.is_set():
				return
	finally:
		_regen_lock.release()


async def heartbeat(ws, interval_ms: float):
	"""Heartbeat в websocket."""
	while True:
		await asyncio.sleep(interval_ms / 1000)
		await ws.send(json.dumps({"op": 3, "d": None}))


async def listen():
	"""Держит websocket Lanyard."""
	global _last_fp
	delay = 1
	while True:
		try:
			async with websockets.connect(
				settings.ws_url, max_size=2 * 1024 * 1024, open_timeout=15
			) as ws:
				hello = json.loads(await asyncio.wait_for(ws.recv(), 15))
				if hello.get("op") != 1:
					raise RuntimeError(f"unexpected hello: {hello}")
				interval = hello["d"].get("heartbeat_interval", 45000)
				await ws.send(json.dumps(
					{"op": 2, "d": {"subscribe_to_id": settings.lanyard_id}}))
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


def main():
	"""Старт мониторов и слушатель."""
	if setproctitle is not None:
		setproctitle.setproctitle("github-readme-bot.py")
	settings.dist.mkdir(exist_ok=True)
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
