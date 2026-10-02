#!/usr/bin/env python3
"""Lanyard WebSocket -> перегенерация SVG по событиям (без опроса).

Использование:
  python ws_watch.py            # слушать, при изменении присутствия писать SVG
  python ws_watch.py --push     # + git commit/push в ветку output (для VPS)

Протокол Lanyard: op1=hello(heartbeat_interval), op2=identify,
op3=heartbeat, op0=t(PRESENCE_UPDATE|INIT_STATE).
"""
import asyncio
import hashlib
import json
import re
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
README = HERE / "README.md"
RAW_BASE = "https://raw.githubusercontent.com/yegorovi/yegorovi/output/"


def log(msg):
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    try:
        with open(HERE / "ws.log", "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def _git(worktree, *args):
    subprocess.run(["git", "-C", str(worktree), *args], check=True)


def _has_changes(worktree):
    subprocess.run(["git", "-C", str(worktree), "add", "-A"], check=True)
    r = subprocess.run(
        ["git", "-C", str(worktree), "diff", "--cached", "--quiet"])
    return r.returncode != 0


def publish(dark: bytes, light: bytes):
    """Версионированные имена в output + переписанный README в main.

    raw.githubusercontent кэширует URL 5 минут (max-age=300) и игнорирует
    query-string в ключе кэша, поэтому обход — каждый раз НОВОЕ имя файла.
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

    # --- ветка output: один набор файлов с актуальным версионным именем
    changed = False
    for f in OUT_WORKTREE.glob("neofetch*.svg"):
        if f.name not in payload:
            f.unlink()
            changed = True
    for name, data in payload.items():
        dst = OUT_WORKTREE / name
        if not dst.exists() or dst.read_bytes() != data:
            dst.write_bytes(data)
            changed = True
    if changed and _has_changes(OUT_WORKTREE):
        _git(OUT_WORKTREE, "commit", "-q", "-m", f"update {ver}")
        _git(OUT_WORKTREE, "push", "-q", "origin", "output")
        log(f"pushed output ({ver})")

    # --- main: README ссылается на свежие имена
    text = README.read_text(encoding="utf-8")
    new_text = re.sub(
        r"neofetch(?:-[0-9a-f]{8})?-(dark|light)\.svg",
        lambda m: names[f"neofetch-{m.group(1)}.svg"],
        text,
    )
    if new_text != text:
        README.write_text(new_text, encoding="utf-8", newline="\n")
        if _has_changes(HERE):
            _git(HERE, "commit", "-q", "-m", f"readme {ver}")
            _git(HERE, "push", "-q", "origin", "main")
            log(f"pushed readme ({ver})")


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
        publish(
            (update.DIST / "neofetch-dark.svg").read_bytes(),
            (update.DIST / "neofetch-light.svg").read_bytes(),
        )
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
