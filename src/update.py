#!/usr/bin/env python3
"""update.py - рисует neofetch-карточку GitHub-профиля в dist/ (тёмная и светлая).

Независим от github-readme-bot.py (его можно запустить руками).

Команды:
python update.py             - один раз нарисовать обе темы
python update.py --watch [N] - перерисовывать каждые N сек (по умолчанию 15)
python update.py --quiet     - не печатать пути к файлам
"""
import sys
import time
from datetime import datetime

from card import build_rows, render
from data import fetch, fetch_image_url, get_music
from settings import settings


def main_once() -> list:
	"""Один прогон карточки: обе темы в dist/."""
	data = fetch()
	music = get_music()
	image_data = None
	if music:
		image_data = fetch_image_url(music.get("cover"))
	settings.dist.mkdir(exist_ok=True)
	written = []
	for name, pal, theme in (("neofetch-dark.svg", settings.dark, "dark"),
                             ("neofetch-light.svg", settings.light, "light")):
		path = settings.dist / name
		path.write_text(
			render(build_rows(data, theme, image_data, music), pal),
			encoding="utf-8")
		written.append(str(path))
	return written


def main():
	"""Разовый запуск либо --watch."""
	if "--watch" in sys.argv:
		idx = sys.argv.index("--watch")
		interval = 15
		if idx + 1 < len(sys.argv) and sys.argv[idx + 1].isdigit():
			interval = int(sys.argv[idx + 1])
		watch_log = settings.logs / "watch.log"
		print(f"[watch] каждые {interval} сек, log: {watch_log}",
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
				with open(watch_log, "a", encoding="utf-8") as fh:
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
