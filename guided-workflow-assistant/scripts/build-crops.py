"""build-crops.py — cut full-body guide character art into UI crop presets.

Usage:
    pip install Pillow
    python build-crops.py --src resources/guide --out public/guide --name guide

Reads transparent PNG masters named <name>-<pose>.png from --src and writes,
for each pose in CROPS, WebP files to --out:

    <name>-<pose>-avatar.webp    square around the head
    <name>-<pose>-closeup.webp   head and shoulders
    <name>-<pose>-chest.webp     to mid-chest, keeping the hand gesture
    <name>-<pose>-half.webp      to the waist
    <name>-<pose>-full.webp      whole figure, margin trimmed

plus <name>-manifest.json with each file's pixel size (use it for width/height
attributes, to avoid layout shift).

Every crop is measured from the figure's own alpha bounding box, not the
canvas, so a pose that reaches further to one side is still cut in the right
place. Fractions are tuned per pose so the gesture a crop exists to show
survives the cut: tweak CROPS after looking at the output.
"""

import argparse
import glob
import json
import os

from PIL import Image

# Fraction of the figure's height each crop keeps, from the top of the figure,
# and the vertical band (as fractions) where the head sits — used to centre the
# avatar. On a pose with raised arms the head is not the topmost thing, so the
# band moves down.
CROPS = {
    #               closeup  chest   half    head band
    "welcome":     (0.40,   0.52,   0.66,   (0.02, 0.18)),
    "pointing":    (0.34,   0.46,   0.62,   (0.02, 0.18)),
    "explaining":  (0.38,   0.50,   0.64,   (0.02, 0.18)),
    "tablet":      (0.38,   0.52,   0.68,   (0.02, 0.18)),
    "thumbs-up":   (0.34,   0.46,   0.62,   (0.02, 0.18)),
    "celebration": (0.38,   0.54,   0.72,   (0.11, 0.28)),
}

# Longest edge of each output: about twice the largest size it is displayed at.
WIDTHS = {"closeup": 360, "chest": 520, "half": 700}
AVATAR_PX = 192
FULL_HEIGHT = 900
AVATAR_SIDE = 0.26  # avatar square side, as a fraction of figure height


def figure_box(image):
    """The figure's own bounds, ignoring transparent margin."""
    return image.getbbox() or (0, 0, image.width, image.height)


def head_center_x(image, box, band):
    """Horizontal centre of the head, from the alpha inside its band."""
    x0, y0, x1, y1 = box
    height = y1 - y0
    strip = image.crop((x0, y0 + int(height * band[0]), x1, y0 + int(height * band[1])))
    strip_box = strip.getbbox()
    if not strip_box:
        return (x0 + x1) // 2
    return x0 + (strip_box[0] + strip_box[2]) // 2


def save(image, path, longest_edge, by_height=False):
    copy = image.copy()
    size = (longest_edge * 10, longest_edge) if by_height else (longest_edge, longest_edge * 10)
    copy.thumbnail(size, Image.LANCZOS)
    copy.save(path, "WEBP", quality=88, method=6)
    return {"width": copy.width, "height": copy.height, "bytes": os.path.getsize(path)}


def build(src, out, name):
    os.makedirs(out, exist_ok=True)
    manifest = {}
    prefix = f"{name}-"

    for master in sorted(glob.glob(os.path.join(src, f"{name}-*.png"))):
        pose = os.path.basename(master)[len(prefix):-len(".png")]
        if pose not in CROPS:
            print(f"skip {os.path.basename(master)}: no CROPS entry for pose '{pose}'")
            continue

        image = Image.open(master).convert("RGBA")
        x0, y0, x1, y1 = figure_box(image)
        height = y1 - y0
        closeup, chest, half, head_band = CROPS[pose]
        files = {}

        def target(crop):
            return os.path.join(out, f"{name}-{pose}-{crop}.webp")

        files["full"] = save(image.crop((x0, y0, x1, y1)), target("full"), FULL_HEIGHT, by_height=True)

        for crop, fraction in (("closeup", closeup), ("chest", chest), ("half", half)):
            cut = image.crop((x0, y0, x1, y0 + int(height * fraction)))
            box = cut.getbbox()
            if box:
                cut = cut.crop(box)
            files[crop] = save(cut, target(crop), WIDTHS[crop])

        centre = head_center_x(image, (x0, y0, x1, y1), head_band)
        side = int(height * AVATAR_SIDE)
        top = max(0, y0 + int(height * head_band[0]) - int(height * 0.02))
        avatar = image.crop((
            max(0, centre - side // 2),
            top,
            min(image.width, centre + side // 2),
            min(image.height, top + side),
        ))
        files["avatar"] = save(avatar, target("avatar"), AVATAR_PX)

        manifest[pose] = files
        print(f"built {pose}")

    with open(os.path.join(out, f"{name}-manifest.json"), "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)

    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--src", required=True, help="folder with <name>-<pose>.png masters")
    parser.add_argument("--out", required=True, help="folder to write WebP crops into")
    parser.add_argument("--name", default="guide", help="file name prefix (default: guide)")
    args = parser.parse_args()
    build(args.src, args.out, args.name)
