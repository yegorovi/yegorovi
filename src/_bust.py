import importlib
import sys
sys.argv = ["x", "--push"]
ws_watch = importlib.import_module("github-readme-bot")

d = open("dist/neofetch-dark.svg", "rb").read() + b" "
l = open("dist/neofetch-light.svg", "rb").read() + b" "
ws_watch.publish(d, l)
