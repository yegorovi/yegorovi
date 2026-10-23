#!/usr/bin/env python3
"""settings.py - параметры github-карточки: темы, шрифты, данные профиля."""
import json
from datetime import date
from pathlib import Path


class Settings:
	"""Параметры карточки и путей в одном объекте."""

	def __init__(self, root: Path):
		self.root = root
		self.src = root / "src"
		self.config = root / "config"
		self.data = root / "data"
		self.logs = root / "logs"
		self.dist = root / "dist"
		self.readme = root / "README.md"      # readme репо = профиль на гитхабе
		self.image_cache = self.data / "image_cache"

		self.lanyard_id = "505825418624892939"
		self.ws_url = "wss://api.lanyard.rest/socket"
		self.out_worktree = Path("/opt/profile_out")
		self.raw_base = (
			"https://raw.githubusercontent.com/yegorovi/yegorovi/output/")
		# флаг !сброс музыки общий со статусом телеграма
		self.no_music_file = Path("/opt/tg_bot/data/no_music")
		self.no_music_window = 900

		# вёрстка карточки
		self.font = ("ui-monospace, SFMono-Regular, Menlo, Consolas, "
			"'Liberation Mono', monospace")
		self.fs = 16
		self.lh = 20
		self.pad = 24
		self.charw = 9.6
		self.width = 760
		self.kv_col = 24
		self.maxcol = int((self.width - 2 * self.pad) / self.charw)

		self.dark = {
			"bg": "#161b22", "border": "#30363d", "text": "#c9d1d9",
			"key": "#ffa657", "value": "#a5d6ff", "cc": "#6e7681",
			"green": "#3fb950", "warn": "#d29922",
		}
		self.light = {
			"bg": "#ffffff", "border": "#d0d7de", "text": "#1f2328",
			"key": "#953800", "value": "#0550ae", "cc": "#656d76",
			"green": "#1a7f37", "warn": "#9a6700",
		}
		self.status = {
			"online": ("🟢", "Online"),
			"idle": ("🟡", "Idle"),
			"dnd": ("🔴", "Do Not Disturb"),
			"offline": ("⚫", "Offline"),
		}

		self.system = [
			("CPU", "AMD Ryzen 9 9950X3D"),
			("GPU", "AMD Radeon RX 9070 XT"),
			("RAM", "32 GB"),
		]
		self.languages = [
			("Python", "#3572A5", "#3572A5"),
			("Java", "#b07219", "#b07219"),
			("C++", "#f34b7d", "#f34b7d"),
			("C#", "#178600", "#178600"),
			("JavaScript", "#f1e05a", "#7a6e00"),
			("Assembly", "#6E4C1E", "#6E4C1E"),
		]
		self.hobbies = [
			("Shooting", "Tactical & clay"),
			("Coding", "Game servers & mods"),
			("Embedded", "Microcontrollers"),
		]
		self.names = ["yegorovi", "ivan", "\u30bf\u30af\u30e9\u206c",
			"takura", "0xdead.moscow"]
		self.projects = [
			("DayZ", "Last-Breath"),
		]

		self.img_size = 112
		self.thumb = 16
		self.thumb_cols = 3
		self.birth = date(2005, 9, 15)


settings = Settings(Path(__file__).resolve().parent.parent)
