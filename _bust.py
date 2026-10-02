import sys
sys.argv = ["x", "--push"]
import ws_watch

d = open("dist/neofetch-dark.svg", "rb").read() + b" "
l = open("dist/neofetch-light.svg", "rb").read() + b" "
ws_watch.publish(d, l)
