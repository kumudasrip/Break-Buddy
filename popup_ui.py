"""
popup_ui.py - the pixel-hero + retro chat-box popup used by breakbuddy.py (pure tkinter)

The hero (hero.png, made by make_sprite.py) stands on the left, points at an RPG-style
message box on the right, bobs up and down, and the message is typed out letter by letter.
On Windows the background is see-through, so only the hero and the box show on your screen.
"""
import os
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))

HERO_TIP = (47, 7)          # fingertip in sprite pixels - keep in sync with TIP in make_sprite.py
TRANSP = "#ff00ff"          # this exact colour becomes see-through on Windows
BOX_BORDER = "#e8e6ff"
BOX_FILL = "#14162b"
BOX_SHADOW = "#05060f"
TITLE_COLOR = "#5ff5e4"
TEXT_COLOR = "#ffffff"
BTN_BG = "#5ff5e4"
BTN_FG = "#0d0f1f"
BTN_ACTIVE = "#ffe27a"
FONT = "Consolas"           # falls back to a default font if missing
TYPE_MS = 22                # milliseconds per typed letter
BOB_MS = 450                # how often the hero bobs

_hero_cache = {}


def ensure_hero():
    """Return the path to hero.png, drawing it first with make_sprite.py if it does not exist yet."""
    path = os.path.join(HERE, "hero.png")
    if not os.path.exists(path):
        import make_sprite
        make_sprite.main(HERE)
    return path


def load_hero(root, scale):
    if scale not in _hero_cache:
        base = tk.PhotoImage(master=root, file=ensure_hero())
        _hero_cache[scale] = base.zoom(scale)         # zoom() keeps hard pixel edges
    return _hero_cache[scale]


def _notched(x0, y0, x1, y1, n):
    """Rectangle with stair-step (chamfered) corners, the classic 16-bit RPG box shape."""
    return [x0 + n, y0, x1 - n, y0, x1 - n, y0 + n, x1, y0 + n,
            x1, y1 - n, x1 - n, y1 - n, x1 - n, y1, x0 + n, y1,
            x0 + n, y1 - n, x0, y1 - n, x0, y0 + n, x0 + n, y0 + n]


def build_popup(root, title, msg, items, snooze_label, on_snooze):
    """Create the popup window and return it. on_snooze() is called after the Snooze button closes it."""
    w = tk.Toplevel(root)
    try:
        w.overrideredirect(True)                       # no title bar or borders
        w.attributes("-topmost", True)
        try:
            w.attributes("-transparentcolor", TRANSP)   # Windows only
        except tk.TclError:
            pass
        w.configure(bg=TRANSP)

        s = max(3, min(6, round(root.winfo_screenheight() / 300)))   # pixel size, scales with the screen
        hero = load_hero(root, s)
        hw, hh = hero.width(), hero.height()
        fs = max(9, round(s * 2.2))
        pad = 3 * s
        text_w = 70 * s

        cv = tk.Canvas(w, bg=TRANSP, highlightthickness=0, bd=0)
        cv.pack()

        # --- measure the text first so the box can be sized to fit it
        t_id = cv.create_text(0, 0, text=title.upper(), anchor="nw", fill=TITLE_COLOR,
                              font=(FONT, fs, "bold"))
        m_id = cv.create_text(0, 0, text=msg, anchor="nw", fill=TEXT_COLOR,
                              font=(FONT, fs), width=text_w)
        tb, mb = cv.bbox(t_id), cv.bbox(m_id)
        title_w, title_h = tb[2] - tb[0], tb[3] - tb[1]
        msg_w, msg_h = mb[2] - mb[0], mb[3] - mb[1]

        # --- buttons
        def snooze():
            w.destroy()
            on_snooze()

        fr = tk.Frame(cv, bg=BOX_FILL)
        for label, cmd in ((f"Snooze {snooze_label}", snooze), ("Done", w.destroy)):
            tk.Button(fr, text=label, command=cmd, font=(FONT, max(8, fs - 1), "bold"),
                      bg=BTN_BG, fg=BTN_FG, activebackground=BTN_ACTIVE, activeforeground=BTN_FG,
                      relief="flat", bd=0, padx=s * 2, pady=max(2, s // 2), cursor="hand2"
                      ).pack(side="left", padx=(0, s * 2))
        fr.update_idletasks()
        btn_w, btn_h = fr.winfo_reqwidth(), fr.winfo_reqheight()

        # --- box size and position (aimed at the hero's fingertip)
        inner_w = max(msg_w, title_w, btn_w)
        box_w = inner_w + 2 * pad + 2 * s
        box_h = pad + title_h + s * 2 + msg_h + pad + btn_h + pad + 2 * s
        tip_y = s + HERO_TIP[1] * s
        box_x0 = hw + s
        box_y0 = max(s, int(tip_y - box_h * 0.3))
        total_w = box_x0 + box_w + s * 2
        total_h = max(hh + 2 * s, box_y0 + box_h + 2 * s)
        cv.configure(width=total_w, height=total_h)

        # --- draw: shadow, border, fill
        x0, y0, x1, y1 = box_x0, box_y0, box_x0 + box_w, box_y0 + box_h
        cv.create_polygon(_notched(x0 + s, y0 + s, x1 + s, y1 + s, s), fill=BOX_SHADOW, outline="")
        cv.create_polygon(_notched(x0, y0, x1, y1, s), fill=BOX_BORDER, outline="")
        cv.create_polygon(_notched(x0 + s, y0 + s, x1 - s, y1 - s, s), fill=BOX_FILL, outline="")

        # --- text, buttons, hero
        tx, ty = x0 + s + pad, y0 + s + pad
        cv.coords(t_id, tx, ty)
        cv.coords(m_id, tx, ty + title_h + s * 2)
        cv.tag_raise(t_id)
        cv.tag_raise(m_id)
        cv.create_window(tx, ty + title_h + s * 2 + msg_h + pad, anchor="nw", window=fr)
        hero_id = cv.create_image(0, total_h - hh - s, anchor="nw", image=hero)

        # --- typewriter effect
        cv.itemconfigure(m_id, text="")

        def type_next(i=0):
            try:
                if not cv.winfo_exists():
                    return
                cv.itemconfigure(m_id, text=msg[:i])
                if i < len(msg):
                    cv.after(TYPE_MS, type_next, i + 1)
            except tk.TclError:
                pass

        # --- gentle bobbing
        bob = {"up": False}

        def bob_tick():
            try:
                if not cv.winfo_exists():
                    return
                cv.move(hero_id, 0, s if bob["up"] else -s)
                bob["up"] = not bob["up"]
                cv.after(BOB_MS, bob_tick)
            except tk.TclError:
                pass

        type_next()
        cv.after(BOB_MS, bob_tick)
        return w
    except Exception:
        w.destroy()
        raise
