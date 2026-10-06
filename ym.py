#!/usr/bin/env python3
"""Монитор «сейчас играет» Яндекс.Музыки через Ynison (ws-протокол плеера).

Два способа:
    fetch_now(seed)             — разовый снимок (открывает ws, читает, закрывает)
    MusicMonitor(on_change, seed) — долгоживущее ws в фоновом потоке;
                                    on_change(info|None) при смене трека/паузы

info (dict) | None (пауза, стоп, нет устройства):
    {"app": "Яндекс Музыка", "id": "95341995:19422901", "track": "Спутник 420",
     "artist": "OM.", "album": "BACKGROUND", "cover": "https://avatars..."}

У каждого вызова свой device_id (seed) — иначе Ynison вытесняет соседа.
Токен: ym_config.json рядом с файлом или /opt/ym_config.json.
"""
import json
import socket
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

APP_NAME = "Яндекс Музыка"

_token = None
_client = None
_cache = {}  # track_id -> (artist, album) успешные ответы


def _load_token():
    global _token
    if _token:
        return _token
    for p in (HERE / "ym_config.json", Path("/opt/ym_config.json")):
        if p.exists():
            _token = json.loads(p.read_text(encoding="utf-8"))["token"]
            return _token
    raise FileNotFoundError("ym_config.json не найден")


def cover_url(uri, size="400x400"):
    if not uri:
        return None
    if uri.startswith("http"):
        return uri
    return "https://" + uri.replace("%%", size)


def _resolve(pid):
    """(artist, album) через REST, с кэшем по id трека."""
    if pid in _cache:
        return _cache[pid]
    artist = album = ""
    try:
        global _client
        if _client is None:
            from yandex_music import Client
            _client = Client(_load_token())
        tracks = _client.tracks([pid])
        if tracks:
            t = tracks[0]
            artist = ", ".join(a.name for a in t.artists)
            album = t.albums[0].title if t.albums else ""
    except Exception:
        return "", ""
    _cache[pid] = (artist, album)
    return artist, album


def _parse(state):
    """Состояние Ynison → info | None (ничего не играет)."""
    from yandex_music.ynison import utils

    ps = getattr(state, "player_state", None)
    if ps is None:
        return None
    st = ps.status
    pl = utils.get_current_playable(state)
    if pl is None or st is None or st.paused:
        return None
    pid = f"{pl.playable_id}:{pl.album_id_optional or ''}"
    artist, album = _resolve(pid)
    return {
        "app": APP_NAME,
        "id": pid,
        "track": pl.title or "",
        "artist": artist,
        "album": album,
        "cover": cover_url(pl.cover_url_optional),
    }


def fetch_now(seed="fetch"):
    """Разовый снимок: info | None."""
    from yandex_music.ynison import messages, simple

    dev = messages.generate_device_id(
        seed=f"ym-{seed}:{socket.gethostname()}")
    state = simple.get_state(_load_token(), device_id=dev)
    return _parse(state)


class MusicMonitor:
    """Фоновый поток с долгоживущим Ynison-соединением."""

    def __init__(self, on_change, seed, title=None):
        self.on_change = on_change
        self.seed = seed
        self.title = title or seed
        self._last = "<init>"
        self._stop = False
        self.thread = None

    def start(self):
        self.thread = threading.Thread(
            target=self._run, name=f"ym-{self.seed}", daemon=True)
        self.thread.start()
        return self

    def stop(self):
        self._stop = True

    def _run(self):
        from yandex_music.ynison import YnisonClient, messages

        delay = 3
        while not self._stop:
            try:
                client = YnisonClient(
                    _load_token(),
                    device_id=messages.generate_device_id(
                        seed=f"ym-{self.seed}"),
                    device_title=self.title,
                )

                @client.on_state
                def _state(state):
                    try:
                        info = _parse(state)
                    except Exception:
                        return
                    if info == self._last:
                        return
                    self._last = info
                    try:
                        self.on_change(info)
                    except Exception:
                        pass

                client.connect()  # блокируется до disconnect
                delay = 3
            except Exception:
                if self._stop:
                    return
                time.sleep(delay)
                delay = min(delay * 2, 60)
