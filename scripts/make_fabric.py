"""Build a seamless damask albedo + normal + roughness from a phone close-up of the real fabric."""
import sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "refs" / "IMG20260917171719.jpg"
OUT = ROOT / "tex" / "fabric"

img = Image.open(SRC).convert("RGB")
W, H = img.size
cx = int(0.615 * W)            # motif symmetry axis in the photo
half = min(cx, W - cx) - 8
top, bottom = 10, int(0.635 * H)  # stop above the gimp trim
left_half = img.crop((cx - half, top, cx, bottom))

# remove the photo's lighting gradient: divide by a very blurred copy
arr = np.asarray(left_half).astype(np.float32) / 255.0
blur = np.asarray(left_half.filter(ImageFilter.GaussianBlur(90))).astype(np.float32) / 255.0
mean = arr.reshape(-1, 3).mean(0)
flat = np.clip(arr / np.maximum(blur, 1e-3) * mean, 0, 1)

# gentle clean-up: lift toward a fresh cream, keep the gold/olive motif contrast
lum = flat.mean(2, keepdims=True)
flat = np.clip((flat - lum) * 1.15 + lum, 0, 1)
flat = np.clip(flat * np.array([1.04, 1.02, 0.97], np.float32) * 1.06, 0, 1)

half_img = flat
row = np.concatenate([half_img, half_img[:, ::-1]], axis=1)   # mirror X -> symmetric motif
tile = np.concatenate([row, row[::-1]], axis=0)               # mirror Y -> seamless vertically

def save(a, name, size):
    Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8)).resize(size, Image.LANCZOS).save(OUT / name, quality=92)

SIZE = (1024, 2048)
save(tile, "damask_albedo.jpg", SIZE)

# height: bright raised pattern yarns + fine weave detail already present in the photo
g = tile.mean(2)
g_img = Image.fromarray((g * 255).astype(np.uint8)).resize(SIZE, Image.LANCZOS)
fine = np.asarray(g_img).astype(np.float32) / 255.0
soft = np.asarray(g_img.filter(ImageFilter.GaussianBlur(3))).astype(np.float32) / 255.0
height = soft * 0.7 + (fine - soft) * 1.6
gy, gx = np.gradient(height)
strength = 6.0
nx, ny, nz = -gx * strength, gy * strength, np.ones_like(height)
ln = np.sqrt(nx * nx + ny * ny + nz * nz)
normal = np.stack([nx / ln, ny / ln, nz / ln], 2) * 0.5 + 0.5
Image.fromarray((normal * 255).astype(np.uint8)).save(OUT / "damask_normal.png")

# roughness: satin-weave pattern areas are a touch shinier than the matte ground
rough = np.clip(0.92 - (soft - soft.mean()) * 0.9, 0.55, 1.0)
Image.fromarray((rough * 255).astype(np.uint8)).save(OUT / "damask_roughness.png")
print("OK", tile.shape, "mean", tile.reshape(-1, 3).mean(0))
