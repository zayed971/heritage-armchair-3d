"""Remove embedded text/EXIF metadata from the final PNG renders, keeping pixels and file timestamps."""
import os
from pathlib import Path
from PIL import Image

FINAL = Path(__file__).resolve().parents[1] / "out" / "final"
for png in sorted(FINAL.glob("*.png")):
    st = png.stat()
    im = Image.open(png)
    had = len(getattr(im, "text", {}) or {}) + len(im.getexif())
    im.load()
    clean = Image.new(im.mode, im.size)
    clean.paste(im)
    clean.save(png, format="PNG", optimize=True)
    os.utime(png, (st.st_atime, st.st_mtime))
    print(f"{png.name}: removed {had} tags")
