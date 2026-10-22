"""
make_sprite.py - draws a 16-bit style pixel-art hero (hooded, caped night guardian) with Python.

Run:  python make_sprite.py
Makes: hero.png          (native pixel size, used by breakbuddy.py)
       hero_preview.png  (8x zoom on a dark background so you can look at it)
Needs: pip install pillow
"""
import math
import os
from PIL import Image, ImageDraw

W, H = 50, 64
TIP = (47, 7)        # fingertip position (x, y) in sprite pixels - breakbuddy.py aims the chat box here

C = {
    "outline": (13, 15, 31, 255),
    "cape": (44, 47, 110, 255),
    "cape_sh": (31, 34, 82, 255),
    "lining": (106, 63, 160, 255),
    "lining_hi": (134, 88, 190, 255),
    "hood": (29, 32, 64, 255),
    "hood_hi": (46, 51, 90, 255),
    "suit": (58, 64, 102, 255),
    "suit_hi": (80, 88, 135, 255),
    "suit_sh": (42, 47, 77, 255),
    "skin": (233, 185, 143, 255),
    "skin_sh": (201, 143, 102, 255),
    "eye": (95, 245, 228, 255),
    "gold": (255, 226, 122, 255),
    "belt": (201, 162, 39, 255),
    "glove": (106, 63, 160, 255),
    "boot": (32, 35, 74, 255),
    "boot_hi": (52, 56, 108, 255),
}


def build():
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def rect(x0, y0, x1, y1, c):
        d.rectangle([x0, y0, x1, y1], fill=C[c])

    def poly(pts, c):
        d.polygon(pts, fill=C[c])

    # ---- cape (behind everything), scalloped bottom edge
    poly([(15, 16), (11, 18), (8, 27), (5, 40), (4, 56), (7, 53), (10, 58), (13, 54),
          (16, 59), (19, 53), (20, 22)], "cape")
    poly([(8, 27), (5, 40), (4, 56), (7, 53), (9, 40), (10, 28)], "cape_sh")
    poly([(15, 24), (18, 26), (18, 52), (16, 58), (13, 53), (13, 38)], "lining")
    poly([(14, 28), (15, 28), (15, 46), (14, 44)], "lining_hi")
    poly([(29, 20), (33, 26), (35, 40), (36, 56), (33, 52), (30, 58), (27, 52), (26, 24)], "cape")
    poly([(33, 26), (35, 40), (36, 56), (33, 52), (33, 40)], "cape_sh")

    # ---- legs and boots
    rect(17, 31, 28, 35, "suit")
    rect(17, 36, 21, 51, "suit")
    rect(24, 36, 28, 51, "suit")
    rect(17, 36, 17, 50, "suit_hi")
    rect(28, 36, 28, 50, "suit_sh")
    rect(21, 36, 21, 50, "suit_sh")
    for bx0, bx1 in ((15, 21), (24, 30)):
        rect(bx0, 52, bx1, 58, "boot")
        rect(bx0, 52, bx1, 53, "glove")                  # purple boot cuff
        rect(bx0, 54, bx0, 57, "boot_hi")
        rect(bx0 - 1, 57, bx1 + 1, 59, "boot")           # toe and sole stick out a little
        rect(bx0 - 1, 59, bx1 + 1, 59, "outline")

    # ---- torso
    poly([(13, 17), (32, 17), (30, 23), (28, 30), (18, 30), (15, 23)], "suit")
    rect(15, 19, 16, 27, "suit_hi")
    rect(29, 19, 29, 27, "suit_sh")
    # crescent moon emblem
    cx, cy = 22.5, 22.0
    for y in range(H):
        for x in range(W):
            in_a = (x - cx) ** 2 + (y - cy) ** 2 <= 3.6 ** 2
            in_b = (x - (cx + 1.9)) ** 2 + (y - (cy - 0.8)) ** 2 <= 3.1 ** 2
            if in_a and not in_b:
                img.putpixel((x, y), C["gold"])
    # belt
    rect(18, 30, 28, 31, "belt")
    rect(22, 30, 24, 31, "gold")

    # ---- hanging arm (viewer's left)
    rect(10, 18, 14, 29, "suit")
    rect(10, 18, 10, 28, "suit_hi")
    rect(14, 20, 14, 28, "suit_sh")
    rect(15, 21, 15, 29, "hood")                                   # shadow line between arm and body
    rect(10, 29, 14, 33, "glove")
    rect(10, 29, 10, 32, "lining_hi")

    # ---- pointing arm (viewer's right): up and out toward the chat box
    d.line([(29, 21), (37, 15)], fill=C["suit"], width=5)
    d.line([(29, 19), (37, 13)], fill=C["suit_hi"], width=1)
    d.line([(30, 24), (38, 18)], fill=C["suit_sh"], width=1)
    # fist
    rect(39, 9, 41, 9, "glove")
    rect(38, 10, 42, 13, "glove")
    rect(39, 14, 41, 14, "glove")
    rect(38, 10, 38, 12, "lining_hi")                              # highlight on the knuckles
    rect(40, 8, 41, 8, "glove")                                    # thumb
    # index finger pointing up and to the right
    for fx, fy in ((43, 10), (43, 9), (44, 9), (44, 8), (45, 8), (46, 8), (46, 7), (47, 7)):
        img.putpixel((fx, fy), C["glove"])
    img.putpixel((45, 7), C["glove"])
    img.putpixel((44, 10), C["glove"])

    # ---- head: hood with a pointed crest
    poly([(22, 0), (28, 6), (28, 13), (26, 15), (19, 15), (17, 13), (17, 6)], "hood")
    rect(18, 6, 19, 12, "hood_hi")
    poly([(19, 10), (26, 10), (26, 13), (25, 14), (20, 14), (19, 13)], "skin")
    rect(25, 10, 26, 14, "skin_sh")
    rect(21, 13, 24, 13, "skin_sh")                               # mouth line
    rect(19, 9, 20, 9, "eye")                                      # glowing eyes
    rect(24, 9, 25, 9, "eye")
    rect(19, 8, 25, 8, "hood")
    rect(19, 16, 26, 17, "hood")                                   # collar

    # ---- automatic dark outline around the whole silhouette
    px = img.load()
    out = []
    for y in range(H):
        for x in range(W):
            if px[x, y][3] == 0:
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < W and 0 <= ny < H and px[nx, ny][3] > 0 and px[nx, ny] != C["outline"]:
                        out.append((x, y))
                        break
    for p in out:
        px[p] = C["outline"]
    return img


def main(folder=None):
    folder = folder or os.path.dirname(os.path.abspath(__file__))
    img = build()
    img.save(os.path.join(folder, "hero.png"))
    scale = 8
    big = img.resize((W * scale, H * scale), Image.NEAREST)
    bg = Image.new("RGBA", big.size, (20, 22, 43, 255))
    bg.alpha_composite(big)
    bg.save(os.path.join(folder, "hero_preview.png"))
    return img


if __name__ == "__main__":
    main()
    print("Saved hero.png and hero_preview.png")
