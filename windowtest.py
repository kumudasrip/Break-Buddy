import time
import pygetwindow as gw

while True:
    w = gw.getActiveWindow()
    print(w.title if w else "(no active window)")
    time.sleep(2)