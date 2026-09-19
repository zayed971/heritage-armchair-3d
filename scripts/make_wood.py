"""Stain the light cherry texture to the chair's dark red-brown lacquer tone."""
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter
T = Path(__file__).resolve().parents[1] / "tex" / "wood"
im = Image.open(T / "albedo.jpg").convert("RGB").resize((1024, 1024), Image.LANCZOS)
a = np.asarray(im).astype(np.float32) / 255.0
lum = a.mean(2)
blur = np.asarray(Image.fromarray((lum * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(40))).astype(np.float32) / 255.0
grain = np.clip((lum - blur) * 5.0, -0.5, 0.5)          # boosted grain figure
base = np.array([0.285, 0.122, 0.070], np.float32)        # stained cherry / mahogany
out = base[None, None, :] * (1.0 + grain[..., None] * 1.0)
out = np.clip(out * (0.9 + 0.2 * (blur / blur.mean())[..., None]), 0, 1)
Image.fromarray((out * 255).astype(np.uint8)).save(T / "wood_stained_albedo.jpg", quality=92)
Image.open(T / "normal.png").convert("RGB").resize((1024, 1024), Image.LANCZOS).save(T / "wood_normal_1k.png")
print("ok", out.reshape(-1, 3).mean(0))
