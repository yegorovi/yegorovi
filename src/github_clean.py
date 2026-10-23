#!/usr/bin/env python3
"""github_clean.py - чистка истории коммитов github-карточки.

Ветки output и main репо yegorovi/yegorovi копят коммиты при каждой
смене трека - за сутки сотни, история засоряется. Скрипт сжимает каждую
ветку до одного коммита: берёт дерево HEAD, собирает новый коммит без
родителя (git commit-tree) и пушит его с force поверх ветки, затем
сбрасывает локальный ворктрий на новый remote. На время операции
профильный сервис останавливается (иначе гонка с его push), после -
возвращается в прежнее состояние.

Запуск: таймер github-clean.timer (каждый день в 00:00 МСК) и вручную
из Telegram командой «!очистка коммитов» у tg-restart-bot.
Двойной запуск отсекается файловым замком.
"""
import fcntl
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from settings import settings

LOCK = Path("/tmp/github_clean.lock")


def log(msg: str) -> None:
	"""Печатает строку со временем."""
	print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}", flush=True)


def git(repo, *args):
	"""Git-команда без исключений."""
	return subprocess.run(["git", "-C", str(repo), *args],
		capture_output=True, text=True, timeout=120)


def git_ok(repo, *args):
	"""Git-команда с повтором (цепляемся на index.lock)."""
	p = None
	for _ in range(4):
		p = git(repo, *args)
		if p.returncode == 0:
			return p
		if "index.lock" not in (p.stderr or ""):
			break
		time.sleep(2)
	raise RuntimeError(f"git {' '.join(args)}: "
		f"{(p.stderr or p.stdout or '').strip()[:300]}")


def squash(repo, branch: str) -> tuple:
	"""Сжимает ветку до одного коммита: (было, стало, статус)."""
	cur = git_ok(repo, "branch", "--show-current").stdout.strip()
	if cur != branch:
		raise RuntimeError(f"ворктрий на ветке {cur}, ожидалась {branch}")
	git_ok(repo, "fetch", "-q", "origin", branch)
	before = int(git_ok(repo, "rev-list", "--count",
		f"origin/{branch}").stdout)
	if before <= 1:
		return before, before, "уже чисто"
	tree = git_ok(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
	msg = f"очистка истории (сжато {before} коммитов)"
	commit = git_ok(repo, "commit-tree", tree, "-m", msg).stdout.strip()
	spec = f"{commit}:{branch}"
	for attempt in range(3):
		p = git(repo, "push", "-q", "-f", "origin", spec)
		if p.returncode == 0:
			break
		if attempt == 2:
			raise RuntimeError(f"push -f: "
				f"{(p.stderr or '').strip()[:300]}")
		time.sleep(3)
	git_ok(repo, "fetch", "-q", "origin", branch)
	git_ok(repo, "reset", "-q", "--hard", f"origin/{branch}")
	after = int(git_ok(repo, "rev-list", "--count",
		f"origin/{branch}").stdout)
	return before, after, "сжато"


def main() -> int:
	"""Замок, стоп профиля, сжатие веток, запуск."""
	with open(LOCK, "w") as fh:
		try:
			fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
		except OSError:
			log("очистка уже идёт - выхожу")
			return 0
		prev = subprocess.run(["systemctl", "is-active", "profile_readme"],
			capture_output=True, text=True).stdout.strip()
		log(f"останавливаю profile_readme (был: {prev})")
		subprocess.run(["systemctl", "stop", "profile_readme"],
			check=True, timeout=60)
		failed = False
		try:
			for repo, branch in ((settings.out_worktree, "output"),
                                 (settings.root, "main")):
				try:
					before, after, status = squash(repo, branch)
					line = (f"{branch}: {before} -> {after} коммитов"
						f" ({status})")
				except Exception as exc:
					failed = True
					line = f"{branch}: ошибка - {exc}"
				log(line)
		finally:
			if prev == "active":
				log("запускаю profile_readme")
				subprocess.run(["systemctl", "start", "profile_readme"],
					check=True, timeout=60)
			else:
				log("profile_readme был неактивен - не запускаю")
		return 1 if failed else 0


if __name__ == "__main__":
	sys.exit(main())
