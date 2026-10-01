#!/usr/bin/env python3
"""Lanyard WebSocket -> перегенерация SVG по событиям (без опроса).

Использование:
  python ws_watch.py            # слушать, при изменении присутствия писать SVG
  python ws_watch.py --push     # + git commit/push в ветку output (для VPS)

Протокол Lanyard: op1=hello(heartbeat_interval), op2=identify,
op3=heartbeat, op0=t(PRESENCE_UPDATE|INIT_STATE).
"""
import asyncio
import json
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

import websockets

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import update  # noqa: E402

LANYARD_ID = "505825418624892939"
WS_URL = "wss://api.lanyard.rest/socket"
OUT_WORKTREE = Path("/opt/profile_out")


def log(msg):
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    try:
        with open(HERE / "ws.log", "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def regenerate():
    try:
        update.main_once()
    except Exception as exc:
        log(f"update error: {exc}")
        return
    log("svg regenerated")
    if "--push" not in sys.argv or not OUT_WORKTREE.exists():
        return
    try:
        changed = False
        for name in ("neofetch-dark.svg", "neofetch-light.svg"):
            src = update.DIST / name
            dst = OUT_WORKTREE / name
            if not dst.exists() or src.read_bytes() != dst.read_bytes():
                dst.write_bytes(src.read_bytes())
                changed = True
        if not changed:
            return
        subprocess.run(["git", "-C", str(OUT_WORKTREE), "add", "-A"],
                       check=True)
        diff = subprocess.run(
            ["git", "-C", str(OUT_WORKTREE), "diff", "--cached", "--quiet"])
        if diff.returncode == 0:
            return
        subprocess.run(
            ["git", "-C", str(OUT_WORKTREE), "commit", "-q", "-m", "update"],
            check=True)
        subprocess.run(["git", "-C", str(OUT_WORKTREE), "push", "-q",
                        "origin", "output"], check=True, timeout=60)
        log("pushed to output")
    except Exception as exc:
        log(f"push error: {exc}")


async def heartbeat(ws, interval_ms):
    while True:
        await asyncio.sleep(interval_ms / 1000)
        await ws.send(json.dumps({"op": 3, "d": None}))


async def listen():
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
                        if kind in ("INIT_STATE", "PRESENCE_UPDATE"):
                            log(f"event {kind}")
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
    update.DIST.mkdir(exist_ok=True)
    regenerate()
    try:
        asyncio.run(listen())
    except KeyboardInterrupt:
        log("stopped")


if __name__ == "__main__":
    main()
