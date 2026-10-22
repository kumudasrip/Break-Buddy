"""
breakbuddy.py - background reminders written by a local model, aware of what you are doing

First create your settings:  python setup.py
Then run the app:            python breakbuddy.py

Needs:  pip install ollama pydantic pygetwindow pystray pillow
"""
import ctypes
import json
import os
import queue
import re
import threading
import time
import tkinter as tk
import winsound
from datetime import datetime
from typing import Literal

import ollama
import pygetwindow as gw
from pydantic import BaseModel

import popup_ui   # the pixel-hero popup (popup_ui.py, same folder)

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)   # correct sizes and crisp text on high-DPI screens
except Exception:
    pass

MODEL = "gemma4:e4b"
CONFIG_FILE = "config.json"
TEST_MODE = False   # True: "minutes" become seconds, thresholds shrink, active hours ignored. False for real use.
USE_HERO = True    # True: pixel hero + chat box popup. False: plain popup.

if TEST_MODE:
    SAMPLE_SEC = 5            # how often to look at the active window
    LONG_AFTER_SEC = 120      # continuous screen time before a "long break" nudge
    IDLE_RESET_SEC = 30       # no keyboard/mouse for this long counts as a break
    SNOOZE_SEC = 10           # snooze length
    SNOOZE_LABEL = "10 sec"
else:
    SAMPLE_SEC = 15
    LONG_AFTER_SEC = 2 * 3600
    IDLE_RESET_SEC = 300
    SNOOZE_SEC = 600
    SNOOZE_LABEL = "10 min"
BATCH_SEC = 3                 # reminders that become due within this window share one popup

DEFAULT_CONFIG = {
    "personality": "friendly",
    "active_from": "00:00",
    "active_to": "23:59",
    "reminders": [
        {"name": "Water", "every_min": 45, "task": "drink a glass of water"},
        {"name": "Eyes", "every_min": 20, "task": "look 20 feet away for 20 seconds"},
        {"name": "Stretch", "every_min": 60, "task": "stand up and stretch"},
    ],
}


def load_config():
    if not os.path.exists(CONFIG_FILE):
        print(f"No {CONFIG_FILE} found, using defaults. Run 'python setup.py' to customize.")
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Could not read {CONFIG_FILE} ({e}), using defaults.")
        return DEFAULT_CONFIG


CONFIG = load_config()
q = queue.Queue()                 # popups waiting to be shown: (title, message, items)
paused = threading.Event()        # set while reminders are paused (tray menu)
quit_event = threading.Event()    # set when the tray menu asks to quit


# ---------------------------------------------------------------- activity awareness

class Activity(BaseModel):
    category: Literal["coding", "video", "meeting", "documents", "browsing", "social", "other"]


CLASSIFY_SYSTEM = """You label what a person is doing on their computer, using only the title of their active window.
Categories:
- coding: code editors (Visual Studio Code, PyCharm), terminals, GitHub, programming docs
- video: YouTube, Netflix, Prime Video, video players
- meeting: Zoom, Google Meet, Microsoft Teams, Webex, video calls, webinars
- documents: PDFs, Word, Excel, PowerPoint, Notion, notes, Acrobat Reader
- browsing: general web pages, new tab, search results, shopping, news
- social: WhatsApp, Instagram, X/Twitter, Discord, Telegram, Reddit, other chat apps
- other: File Explorer, settings, AI chat assistants, anything unclear
Examples:
"windowtest.py - break-buddy - Visual Studio Code" -> coding
"YouTube - Google Chrome" -> video
"Weekly standup - Zoom Meeting" -> meeting
"report.pdf - Adobe Acrobat Reader" -> documents"""

title_cache = {}        # window title -> category, so each new title is classified only once

# Windows that are not "what you are doing": our own popups and system pop-ups.
IGNORED_TITLES = {"", "tk", "New notification", "Task Switching", "Search"}

# Safety rule: interrupting a meeting is worse than missing a reminder, so real meeting windows
# are recognised by fixed patterns BEFORE the model is asked. A text file named
# "Zoom meeting.txt" does not match these.
MEETING_RE = re.compile(
    r"^zoom( meeting| workplace)?$"          # Zoom app window
    r"|^meet\s*[-–—]\s*"                      # Google Meet tab: "Meet - abc-defg-hij - Google Chrome"
    r"|^[a-z]{3}-[a-z]{4}-[a-z]{3}\b"         # Google Meet tab that shows only the meeting code
    r"|meeting.*\|\s*microsoft teams"         # Microsoft Teams meeting
    r"|webex",
    re.IGNORECASE,
)


def keyword_fallback(title):
    t = title.lower()
    if MEETING_RE.search(title):
        return "meeting"
    if any(k in t for k in ("visual studio code", "pycharm", "github", "terminal")):
        return "coding"
    if any(k in t for k in ("youtube", "netflix", "prime video", "vlc")):
        return "video"
    if any(k in t for k in (".pdf", "word", "excel", "powerpoint", "acrobat")):
        return "documents"
    return "other"


def classify(title):
    if not title:
        return "other"
    if title in title_cache:
        return title_cache[title]
    if MEETING_RE.search(title):
        title_cache[title] = "meeting"
        return "meeting"
    try:
        r = ollama.chat(
            model=MODEL,
            messages=[
                {"role": "system", "content": CLASSIFY_SYSTEM},
                {"role": "user", "content": title},
            ],
            format=Activity.model_json_schema(),
            think=False,
            options={"temperature": 0},
        )
        cat = Activity.model_validate_json(r.message.content).category
    except Exception:
        cat = keyword_fallback(title)       # Ollama off or bad output: simple rules instead
    title_cache[title] = cat
    return cat


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


ctypes.windll.kernel32.GetTickCount.restype = ctypes.c_uint


def idle_seconds():
    """Seconds since the last keyboard or mouse input."""
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(info)
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info))
    return (ctypes.windll.kernel32.GetTickCount() - info.dwTime) / 1000.0


def active_title():
    try:
        w = gw.getActiveWindow()
        return w.title if w else ""
    except Exception:
        return ""


lock = threading.Lock()
state = {"cat": "other", "streak": 0.0, "by_cat": {}, "last_long": 0.0}


def current_cat():
    with lock:
        return state["cat"]


def context():
    """(minutes at the computer, main activity, current activity)"""
    with lock:
        mins = max(1, round(state["streak"] / 60))
        top = max(state["by_cat"], key=state["by_cat"].get) if state["by_cat"] else state["cat"]
        return mins, top, state["cat"]


def watcher():
    last_printed = None
    while True:
        time.sleep(SAMPLE_SEC)
        if idle_seconds() > IDLE_RESET_SEC:             # you were away: that counts as a break
            with lock:
                state["streak"] = 0.0
                state["by_cat"] = {}
                state["last_long"] = 0.0
            continue
        title = active_title()
        if title.startswith("BreakBuddy") or title in IGNORED_TITLES:
            cat = current_cat()          # our own popup or a system pop-up: keep the previous activity
        else:
            cat = classify(title)
            if title != last_printed:
                print(f"[{datetime.now():%H:%M:%S}] {cat:<9} | {title}")
                last_printed = title
        with lock:
            state["cat"] = cat
            state["streak"] += SAMPLE_SEC
            state["by_cat"][cat] = state["by_cat"].get(cat, 0) + SAMPLE_SEC
            due = ((state["streak"] - state["last_long"] >= LONG_AFTER_SEC)
                   and cat != "meeting" and not paused.is_set())
            if due:
                state["last_long"] = state["streak"]
        if due:
            add_pending({"name": "Long break", "task": "", "long": True})


# ---------------------------------------------------------------- reminders

pending = {}                # reminders waiting to be shown, keyed by name (so a reminder is never listed twice)
plock = threading.Lock()


def add_pending(item):
    """Queue a reminder. If it is already waiting, it is not added again."""
    if paused.is_set():
        return
    with plock:
        if item["name"] not in pending:
            pending[item["name"]] = {"name": item["name"], "task": item["task"],
                                     "long": item["long"], "t": time.time()}


def in_active_hours():
    """True if the current time is inside the allowed window."""
    if TEST_MODE:
        return True
    now = datetime.now().strftime("%H:%M")
    a, b = CONFIG["active_from"], CONFIG["active_to"]
    if a <= b:
        return a <= now <= b
    return now >= a or now <= b   # window that crosses midnight, e.g. 22:00 to 06:00


def make_message(tasks, long_break=False):
    style = CONFIG.get("personality", "friendly")
    mins, top, cat = context()
    if long_break:
        prompt = (f"Write ONE short sentence (max 20 words) in this style: {style}. "
                  f"Tell the person they have been at the computer for about {mins} minutes, "
                  f"mostly {top}, and should take a proper 10 minute break away from the screen. "
                  f"No emojis, no quotes.")
    elif len(tasks) == 1:
        prompt = (f"Write ONE short sentence (max 15 words) in this style: {style}. "
                  f"Remind me to {tasks[0]}. "
                  f"Context, to use only if it fits naturally: I am doing {cat} and have been at "
                  f"the computer about {mins} minutes. "
                  f"No emojis, no quotes.")
    else:
        prompt = (f"Write one or two short sentences (max 30 words total) in this style: {style}. "
                  f"Remind me to do ALL of these: {'; '.join(tasks)}. "
                  f"Context, to use only if it fits naturally: I am doing {cat} and have been at "
                  f"the computer about {mins} minutes. "
                  f"No emojis, no quotes.")
    try:
        r = ollama.chat(model=MODEL, messages=[{"role": "user", "content": prompt}], think=False)
        return r.message.content.strip()
    except Exception:
        if long_break:
            return "Take a proper break away from the screen!"
        return "Time to " + " and ".join(tasks) + "!"


def deliver(items):
    """Turn waiting reminders into popups: all normal ones share ONE popup, a long break gets its own."""
    normal = [i for i in items if not i["long"]]
    long_items = [i for i in items if i["long"]]
    if normal:
        title = " + ".join(i["name"] for i in normal)
        q.put((title, make_message([i["task"] for i in normal]), normal))
    if long_items:
        q.put(("Long break", make_message([], long_break=True), long_items))


def scheduler(rem):
    interval = rem["every_min"] * (1 if TEST_MODE else 60)
    while True:
        time.sleep(interval)
        if in_active_hours():
            add_pending({"name": rem["name"], "task": rem["task"], "long": False})


def dispatcher():
    """Hands waiting reminders to the popup queue: holds them during meetings, batches ones that coincide."""
    held_shown = 0
    while True:
        time.sleep(1)
        if paused.is_set():
            continue
        with plock:
            n = len(pending)
            oldest = min((v["t"] for v in pending.values()), default=None)
        if n == 0:
            held_shown = 0
            continue
        if current_cat() == "meeting":
            if n != held_shown:                     # print only when the count changes
                print(f"   ({n} reminder(s) held back: you are in a meeting)")
                held_shown = n
            continue
        held_shown = 0
        if time.time() - oldest < BATCH_SEC:        # wait a moment so coinciding reminders share a popup
            continue
        with plock:
            items = list(pending.values())
            pending.clear()
        if items:
            deliver(items)


# ---------------------------------------------------------------- popups

open_popups = []   # visible popups, oldest first (oldest sits at the bottom)
TITLEBAR = 45      # extra pixels for the title bar of the plain popup (the hero popup has none)
GAP = 12           # space between stacked popups


def layout_popups():
    """Place every open popup in the bottom-right corner, stacked upwards using each one's real height."""
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    y = sh - 80                               # leave room for the taskbar
    for p in open_popups:
        if not p.winfo_exists():
            continue
        p.update_idletasks()
        w_px = max(p.winfo_reqwidth(), 360)
        h_px = p.winfo_reqheight() + getattr(p, "_bb_titlebar", TITLEBAR)
        y -= h_px + GAP
        p.geometry(f"{w_px}x{p.winfo_reqheight()}+{sw - w_px - 20}+{y}")


def build_classic_popup(root, title, msg, start_snooze):
    """Plain fallback popup, used when USE_HERO is False or the hero popup fails."""
    w = tk.Toplevel(root)
    w.attributes("-topmost", True)
    tk.Label(w, text=title, font=("Segoe UI", 12, "bold")).pack(padx=20, pady=(12, 2))
    tk.Label(w, text=msg, wraplength=420, font=("Segoe UI", 10)).pack(padx=20, pady=4)

    def snooze():
        w.destroy()
        start_snooze()

    buttons = tk.Frame(w)
    buttons.pack(pady=(6, 12))
    tk.Button(buttons, text=f"Snooze {SNOOZE_LABEL}", command=snooze).pack(side="left", padx=6)
    tk.Button(buttons, text="Done", command=w.destroy).pack(side="left", padx=6)
    return w


def show_popup(root, title, msg, items):
    def start_snooze():
        t = threading.Timer(SNOOZE_SEC, lambda: [add_pending(i) for i in items])
        t.daemon = True
        t.start()

    w = None
    if USE_HERO:
        try:
            w = popup_ui.build_popup(root, title, msg, items, SNOOZE_LABEL, start_snooze)
            w._bb_titlebar = 0
        except Exception as e:
            print(f"   (hero popup failed: {e}; using the plain popup instead)")
    if w is None:
        w = build_classic_popup(root, title, msg, start_snooze)
        w._bb_titlebar = TITLEBAR

    w.title(f"BreakBuddy - {title}")           # the window watcher ignores titles starting with "BreakBuddy"
    open_popups.append(w)

    def on_close(event):
        if event.widget is w and w in open_popups:
            open_popups.remove(w)
            root.after(10, layout_popups)    # slide the remaining ones down

    w.bind("<Destroy>", on_close)
    layout_popups()
    w.after(25000, lambda: w.winfo_exists() and w.destroy())   # auto-close after 25 s
    winsound.MessageBeep()


# ---------------------------------------------------------------- tray icon

def start_tray():
    """System tray icon with Pause/Resume and Quit. Skipped (with a note) if pystray is not installed."""
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        print("Tray icon disabled. Enable it with: pip install pystray pillow")
        return None

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((4, 4, 60, 60), fill=(52, 152, 219, 255))      # blue circle
    d.ellipse((22, 18, 42, 50), fill=(255, 255, 255, 255))   # white drop shape

    def toggle(icon, item):
        if paused.is_set():
            paused.clear()
        else:
            paused.set()
            with plock:
                pending.clear()                              # drop anything waiting
        icon.update_menu()

    def quit_app(icon, item):
        quit_event.set()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Pause reminders", toggle, checked=lambda item: paused.is_set()),
        pystray.MenuItem("Quit BreakBuddy", quit_app),
    )
    icon = pystray.Icon("BreakBuddy", img, "BreakBuddy", menu)
    threading.Thread(target=icon.run, daemon=True).start()
    return icon


# ---------------------------------------------------------------- main

root = tk.Tk()
root.title("BreakBuddy")
root.withdraw()                            # hide the empty main window


def poll():
    if quit_event.is_set():
        root.destroy()
        return
    while not q.empty():
        title, msg, items = q.get()
        show_popup(root, title, msg, items)
    root.after(500, poll)


def main():
    for rem in CONFIG["reminders"]:
        threading.Thread(target=scheduler, args=(rem,), daemon=True).start()
    threading.Thread(target=dispatcher, daemon=True).start()
    threading.Thread(target=watcher, daemon=True).start()
    start_tray()

    print("BreakBuddy running with:")
    print(f"  personality: {CONFIG.get('personality')}")
    print(f"  active hours: {CONFIG['active_from']} to {CONFIG['active_to']}"
          + ("  (ignored in TEST_MODE)" if TEST_MODE else ""))
    for r in CONFIG["reminders"]:
        print(f"  - {r['name']}: every {r['every_min']} {'sec (test)' if TEST_MODE else 'min'}")
    print(f"  long-break nudge after {LONG_AFTER_SEC // 60} min of continuous screen time"
          + ("  (test)" if TEST_MODE else ""))
    print(f"  popup style: {'pixel hero' if USE_HERO else 'plain'}")
    print("  tray icon: right-click it (check the ^ arrow near the clock) to pause or quit")
    print("Window log (what the model thinks you are doing):")

    poll()
    root.mainloop()


if __name__ == "__main__":
    main()
