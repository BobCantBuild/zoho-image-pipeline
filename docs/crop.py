"""Crop the full dashboard screenshot into clean labeled sections."""
from PIL import Image
from pathlib import Path

SRC = Path(__file__).parent / "screenshots" / "01_full_dashboard.png"
OUT = Path(__file__).parent / "screenshots"

img = Image.open(SRC)
W, H = img.size
print("Source:", W, "x", H)

# Each box: (left, top, right, bottom)
crops = {
    "header.png":   (0, 0,    W,  165),
    "metrics.png":  (0, 190,  W,  335),
    "progress.png": (0, 348,  W,  415),
    "filters.png":  (0, 435,  W,  555),
    "table.png":    (0, 560,  W,  H),
}

for name, box in crops.items():
    crop = img.crop(box)
    out = OUT / name
    # Upscale 2x for sharper embedding in docs
    new_size = (crop.size[0]*2, crop.size[1]*2)
    crop = crop.resize(new_size, Image.LANCZOS)
    crop.save(out)
    print(f"  {name}: {crop.size}")
