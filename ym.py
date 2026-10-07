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
_src_cache = {}  # (etype, entity_id) -> (заголовок, время кэша)

_SRC_LABELS = {
    1: "Исполнитель",   # ARTIST
    2: "Плейлист",      # PLAYLIST
    3: "Альбом",        # ALBUM
    4: "Радио",         # RADIO
    5: "Подборка",      # VARIOUS
    6: "Микс",          # GENERATIVE
    7: "FM-радио",      # FM_RADIO
    9: "Локальные треки",
}


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


def _queue_title(etype, eid):
    """Заголовок источника очереди (REST, кэш; ошибки — на 5 минут)."""
    key = (etype, eid)
    hit = _src_cache.get(key)
    if hit is not None:
        title, ts = hit
        if title or time.time() - ts < 300:
            return title
    title = ""
    try:
        global _client
        if _client is None:
            from yandex_music import Client
            _client = Client(_load_token())
        if etype == 2:
            obj = _client.playlist(eid)
            title = obj.title if obj else ""
        elif etype == 3:
            obj = _client.album(eid)
            title = obj.title if obj else ""
        elif etype == 1:
            obj = _client.artist(eid)
            title = obj.name if obj else ""
    except Exception:
        title = ""
    _src_cache[key] = (title, time.time())
    return title


def _queue_src(q):
    """Источник очереди -> 'Плейлист: Название' | 'Радио' | None."""
    if q is None or not q.entity_id:
        return None
    try:
        et = int(q.entity_type or 0)
    except Exception:
        return None
    label = _SRC_LABELS.get(et, "Источник")
    if et in (1, 2, 3):
        title = _queue_title(et, q.entity_id)
        return f"{label}: {title}" if title else f"{label}: —"
    return label


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
    info = {
        "app": APP_NAME,
        "id": pid,
        "track": pl.title or "",
        "artist": artist,
        "album": album,
        "cover": cover_url(pl.cover_url_optional),
    }
    src = _queue_src(getattr(ps, "player_queue", None))
    if src:
        info["src"] = src
    return info


def fetch_now(seed="fetch"):
    """Разовый снимок: info | None.

    None также в случае, когда плеер неактивен: ws поднимается, но кадр
    состояния не приходит (YnisonTimeoutError «начального состояния») —
    это не ошибка, а «ничего не играет».
    """
    from yandex_music.exceptions import YnisonTimeoutError
    from yandex_music.ynison import messages, simple

    dev = messages.generate_device_id(
        seed=f"ym-{seed}:{socket.gethostname()}")
    try:
        state = simple.get_state(_load_token(), device_id=dev)
    except YnisonTimeoutError as e:
        if "начального состояния" in str(e):
            return None
        raise
    return _parse(state)


class MusicMonitor:
    """Фоновый поток с долгоживущим Ynison-соединением.

    on_change(info|None) зовётся на смену трека / паузу / воспроизведение.
    Сторож (отдельный поток): если ws молчит дольше silent_restart секунд —
    обрыв без ошибки, соединение рвётся через disconnect() и цикл сам
    переподключается (иначе connect() виснет в мёртвом recv навсегда).
    """

    def __init__(self, on_change, seed, title=None, silent_restart=60, log=None):
        self.on_change = on_change
        self.seed = seed
        self.title = title or seed
        self.silent_restart = silent_restart
        self.log = log or (lambda msg: print(msg, flush=True))
        self._last = "<init>"
        self._stop = False
        self._client = None
        self._last_msg = 0.0
        self._idle_streak = 0   # рестартов подряд без единого состояния
        self.thread = None
        self.watchdog = None

    def start(self):
        self.thread = threading.Thread(
            target=self._run, name=f"ym-{self.seed}", daemon=True)
        self.thread.start()
        self.watchdog = threading.Thread(
            target=self._watch, name=f"ym-{self.seed}-watch", daemon=True)
        self.watchdog.start()
        return self

    def stop(self):
        self._stop = True
        c = self._client
        if c is not None:
            try:
                c.disconnect()
            except Exception:
                pass

    def _watch(self):
        while not self._stop:
            time.sleep(5)
            c = self._client
            if c is None:
                continue
            silent = time.time() - self._last_msg
            # плеер неактивен (ни одного состояния с момента подключения) —
            # переподключения вхолостую ни к чему не ведут, порог растёт:
            # 60 -> 120 -> 240 -> 300... Как только придёт состояние, сброс.
            thr = min(self.silent_restart * (2 ** min(self._idle_streak, 10)),
                      300)
            if silent > thr:
                self._idle_streak += 1
                self.log(f"ym[{self.seed}]: тишина {int(silent)}с "
                         f"(порог {thr}с) -> рестарт ws")
                self._last_msg = time.time()  # не спамить, пока идёт реконнект
                try:
                    c.disconnect()
                except Exception:
                    pass

    def _run(self):
        from yandex_music.ynison import YnisonClient, messages

        delay = 3
        while not self._stop:
            ok = False
            try:
                client = YnisonClient(
                    _load_token(),
                    device_id=messages.generate_device_id(
                        seed=f"ym-{self.seed}"),
                    device_title=self.title,
                )
                self._client = client
                self._last_msg = time.time()

                @client.on_state
                def _state(state):
                    self._last_msg = time.time()
                    self._idle_streak = 0
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
                ok = True
                if not self._stop:
                    self.log(f"ym[{self.seed}]: ws закрыт -> переподключение")
            except Exception as e:
                if self._stop:
                    return
                self.log(f"ym[{self.seed}]: {e} -> повтор через {delay}с")
            finally:
                self._client = None
            if self._stop:
                return
            if ok:
                delay = 3
                time.sleep(1)
            else:
                time.sleep(delay)
                delay = min(delay * 2, 60)
