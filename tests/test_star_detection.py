import uuid
import unittest
from pathlib import Path

import cv2
import numpy as np

from ocr_engine import extract_star_rating


def _star_points(cx: int, cy: int, outer_r: int, inner_r: int, points: int = 5):
    pts = []
    angle0 = -np.pi / 2.0
    for i in range(points * 2):
        r = outer_r if i % 2 == 0 else inner_r
        a = angle0 + i * (np.pi / points)
        x = int(round(cx + r * np.cos(a)))
        y = int(round(cy + r * np.sin(a)))
        pts.append([x, y])
    return np.array([pts], dtype=np.int32)


def _write_img(path: Path, img: np.ndarray):
    path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(path), img)
    if not ok:
        raise RuntimeError(f"Failed to write image: {path}")


class StarDetectionTests(unittest.TestCase):
    def _tmp_path(self, name: str) -> Path:
        # Avoid OS temp dirs and avoid tempfile-created ACL quirks: write into repo.
        repo_root = Path(__file__).resolve().parents[1]
        base = repo_root / "data" / "_tmp_tests"
        base.mkdir(parents=True, exist_ok=True)
        return base / f"{uuid.uuid4().hex}_{name}"

    def test_detects_five_star_row(self):
        img = np.zeros((480, 720, 3), dtype=np.uint8)

        yellow = (0, 255, 255)  # BGR
        y = 120
        xs = [140, 240, 340, 440, 540]
        for x in xs:
            pts = _star_points(x, y, outer_r=28, inner_r=12)
            cv2.fillPoly(img, pts, yellow)

        p = self._tmp_path("five.png")
        try:
            _write_img(p, img)
            star, remark, engine = extract_star_rating(str(p))
        finally:
            try:
                p.unlink(missing_ok=True)
            except Exception:
                pass

        self.assertIsNotNone(star)
        self.assertEqual(float(star), 5.0)

    def test_rejects_yellow_circles(self):
        img = np.zeros((480, 720, 3), dtype=np.uint8)
        yellow = (0, 255, 255)  # BGR
        y = 120
        xs = [140, 240, 340, 440, 540]
        for x in xs:
            cv2.circle(img, (x, y), 22, yellow, thickness=-1)

        p = self._tmp_path("circles.png")
        try:
            _write_img(p, img)
            star, remark, engine = extract_star_rating(str(p))
        finally:
            try:
                p.unlink(missing_ok=True)
            except Exception:
                pass

        self.assertIsNone(star)


if __name__ == "__main__":
    unittest.main()
