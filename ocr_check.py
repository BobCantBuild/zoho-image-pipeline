# =============================================================
#  ocr_check.py  —  Manual OCR checker (no DB writes)
#
#  Two boxes: Order-ID image and Star-rating image.
#  Each accepts: click-to-browse, drag-and-drop, or Ctrl+V paste.
#  Any image format. Nothing is saved — temp file deleted after OCR.
#  Uses the SAME engine as pipeline.py (ocr_engine.py).
#
#  Run:   python ocr_check.py        →  http://localhost:8502
# =============================================================
import json
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ocr_engine import (
    extract_order_id,
    extract_star_rating,
    classify_star_category,
    get_raw_ocr,
)

PORT = 8502

PAGE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>OCR Quick Check</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', system-ui, sans-serif; background: #f8fafc; color: #0f172a; padding: 32px; }
  h1 { font-size: 22px; margin-bottom: 24px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; max-width: 1100px; }
  .card { background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; }
  .card h2 { font-size: 16px; margin-bottom: 12px; }
  .drop { border: 2px dashed #cbd5e1; border-radius: 10px; min-height: 160px;
          display: flex; align-items: center; justify-content: center; flex-direction: column;
          cursor: pointer; color: #64748b; font-size: 14px; text-align: center; padding: 16px;
          transition: border-color .15s, background .15s; }
  .drop.active { border-color: #6366f1; background: #eef2ff; }
  .drop img { max-width: 100%; max-height: 260px; border-radius: 8px; }
  .result { margin-top: 14px; display: none; }
  .value { font-size: 24px; font-weight: 700; word-break: break-all; }
  .stars { font-size: 26px; color: #f59e0b; letter-spacing: 4px; }
  .ok  { color: #16a34a; } .bad { color: #dc2626; }
  .meta { color: #64748b; font-size: 12px; margin-top: 4px; }
  .cat  { font-size: 13px; margin-top: 4px; }
  .spin { display: none; margin-top: 14px; color: #6366f1; font-size: 14px; }
  input[type=file] { display: none; }
</style>
</head>
<body>
<h1>&#128270; OCR Quick Check</h1>
<div class="grid">

  <div class="card">
    <h2>&#128230; Order ID</h2>
    <div class="drop" id="drop-order">Click, drop or paste (Ctrl+V) an image</div>
    <input type="file" id="file-order" accept="image/*">
    <div class="spin" id="spin-order">Running OCR&#8230;</div>
    <div class="result" id="res-order"></div>
  </div>

  <div class="card">
    <h2>&#11088; Star Rating</h2>
    <div class="drop" id="drop-star">Click, drop or paste (Ctrl+V) an image</div>
    <input type="file" id="file-star" accept="image/*">
    <div class="spin" id="spin-star">Detecting stars&#8230;</div>
    <div class="result" id="res-star"></div>
  </div>

</div>

<script>
let activeKind = "order";   // paste goes to the box you clicked/hovered last

function setup(kind) {
  const drop = document.getElementById("drop-" + kind);
  const file = document.getElementById("file-" + kind);

  drop.addEventListener("click", () => { activeKind = kind; file.click(); });
  drop.addEventListener("mouseenter", () => { activeKind = kind; });
  file.addEventListener("change", () => { if (file.files[0]) send(kind, file.files[0]); });

  drop.addEventListener("dragover", e => { e.preventDefault(); drop.classList.add("active"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("active"));
  drop.addEventListener("drop", e => {
    e.preventDefault(); drop.classList.remove("active");
    if (e.dataTransfer.files[0]) send(kind, e.dataTransfer.files[0]);
  });
}

document.addEventListener("paste", e => {
  for (const item of e.clipboardData.items) {
    if (item.type.startsWith("image/")) {
      send(activeKind, item.getAsFile());
      return;
    }
  }
});

function send(kind, blob) {
  const drop = document.getElementById("drop-" + kind);
  const spin = document.getElementById("spin-" + kind);
  const res  = document.getElementById("res-" + kind);

  const url = URL.createObjectURL(blob);
  drop.innerHTML = "<img src='" + url + "'>";
  res.style.display = "none";
  spin.style.display = "block";

  fetch("/" + kind, { method: "POST", body: blob })
    .then(r => r.json())
    .then(d => {
      spin.style.display = "none";
      res.style.display = "block";
      if (kind === "order") {
        res.innerHTML = d.order_id
          ? "<div class='value ok'>" + d.order_id + "</div>"
          : "<div class='value bad'>No Order ID found</div>";
      } else {
        if (d.star !== null) {
          const n = Math.round(d.star);
          res.innerHTML =
            "<div class='value ok'>" + n + " / 5</div>" +
            "<div class='stars'>" + "\\u2605".repeat(n) + "\\u2606".repeat(5-n) + "</div>" +
            "<div class='cat'>" + d.category + "</div>";
        } else {
          res.innerHTML = "<div class='value bad'>No stars found</div>";
        }
      }
      res.innerHTML += "<div class='meta'>" + d.remark + " &middot; " + d.elapsed + "s</div>";
    })
    .catch(() => {
      spin.style.display = "none";
      res.style.display = "block";
      res.innerHTML = "<div class='value bad'>Error — try again</div>";
    });
}

setup("order");
setup("star");
</script>
</body>
</html>"""

CATEGORY_LABEL = {
    "service": "Category: Service (Installation & Demo)",
    "product": "Category: Product (Rate your experience)",
    "general": "Category: General",
}


def _analyse(kind: str, data: bytes) -> dict:
    import time as _t
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as f:
        f.write(data)
        path = f.name
    t0 = _t.time()
    try:
        if kind == "order":
            oid, remark, _ = extract_order_id(path)
            return {"order_id": oid, "remark": remark,
                    "elapsed": round(_t.time() - t0, 1)}
        star, remark, _ = extract_star_rating(path)
        category = "general"
        if star is not None:
            category = classify_star_category(get_raw_ocr(path) or "")
        return {"star": star, "remark": remark,
                "category": CATEGORY_LABEL.get(category, CATEGORY_LABEL["general"]),
                "elapsed": round(_t.time() - t0, 1)}
    finally:
        Path(path).unlink(missing_ok=True)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence per-request console noise
        pass

    def do_GET(self):
        body = PAGE.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        kind = self.path.strip("/")
        if kind not in ("order", "star"):
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        data = self.rfile.read(length)
        try:
            result = _analyse(kind, data)
        except Exception as e:
            result = {"order_id": None, "star": None,
                      "remark": f"Error: {e}", "category": "", "elapsed": 0}
        body = json.dumps(result).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"OCR Quick Check running at http://localhost:{PORT}  (Ctrl+C to stop)")
    threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    server.serve_forever()
