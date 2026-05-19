"""
star_scan.py — scan a folder of screenshots/images and extract star ratings.

Usage:
  python star_scan.py --path "C:\\path\\to\\images" --out "data\\star_scan.csv"

Notes:
  - Uses `ocr_engine.extract_star_rating` (pure OpenCV, no OCR calls for stars).
  - Intended for quick validation/debug on arbitrary folders (not Zoho folder layout).
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Iterable

import cv2

from ocr_engine import extract_star_rating
from image_preprocess import preprocess_for_stars


_DEFAULT_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff")


def _iter_images(root: Path, recursive: bool, exts: tuple[str, ...]) -> Iterable[Path]:
    if root.is_file():
        yield root
        return
    if not root.exists():
        return
    if recursive:
        it = root.rglob("*")
    else:
        it = root.glob("*")
    for p in it:
        if p.is_file() and p.suffix.lower() in exts:
            yield p


def _write_debug(debug_dir: Path, image_path: Path) -> None:
    """
    Writes `<name>.mask.png` and `<name>.overlay.png` to help tune star detection.
    """
    img, meta = preprocess_for_stars(str(image_path))
    mask = meta.get("star_mask")
    if mask is None:
        return

    debug_dir.mkdir(parents=True, exist_ok=True)
    stem = image_path.stem
    mask_path = debug_dir / f"{stem}.mask.png"
    overlay_path = debug_dir / f"{stem}.overlay.png"

    cv2.imwrite(str(mask_path), mask)

    overlay = img.copy()
    # draw mask as red overlay
    red = overlay[:, :, 2]
    red = cv2.max(red, mask)
    overlay[:, :, 2] = red
    cv2.imwrite(str(overlay_path), overlay)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", required=True, help="Image file or folder to scan")
    ap.add_argument("--out", default="data/star_scan.csv", help="Output CSV path")
    ap.add_argument("--recursive", action="store_true", help="Recurse into subfolders")
    ap.add_argument("--debug-dir", default=None, help="If set, write mask/overlay PNGs here")
    args = ap.parse_args()

    root = Path(args.path)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    debug_dir = Path(args.debug_dir) if args.debug_dir else None

    rows = []
    for p in _iter_images(root, args.recursive, _DEFAULT_EXTS):
        star, remark, engine = extract_star_rating(str(p))
        rows.append(
            {
                "path": str(p),
                "star": "" if star is None else f"{star:.1f}",
                "remark": remark,
                "engine": engine,
            }
        )
        if debug_dir is not None:
            try:
                _write_debug(debug_dir, p)
            except Exception:
                # debug output must never break scanning
                pass

    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["path", "star", "remark", "engine"])
        w.writeheader()
        w.writerows(rows)

    print(f"Wrote {len(rows)} rows -> {out_path}")
    if debug_dir is not None:
        print(f"Debug images -> {debug_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

