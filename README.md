# Zoho Forms Pipeline  —  Tesseract + OpenCV

## Why Tesseract? (vs EasyOCR / Gemini)

| Engine      | RAM      | Load time | Per image | Your laptop |
|-------------|----------|-----------|-----------|-------------|
| EasyOCR     | ~1.5 GB  | 15–30 s   | 3–8 s     | Overheats   |
| Gemini API  | 0 MB     | —         | 2–5 s     | Rate-limited|
| **Tesseract** | **~50 MB** | **0.1 s** | **0.3–1 s** | **Cool + fast** |

5321 folders × 2 images = ~10,642 images  
Tesseract at 1 image/sec × 4 workers = **~45 minutes total**

---

## Step 1 — Install Tesseract Binary (one time)

1. Go to: https://github.com/UB-Mannheim/tesseract/wiki
2. Download: `tesseract-ocr-w64-setup-5.x.x.exe`
3. Install to: `C:\Program Files\Tesseract-OCR\`  (default path — keep it)
4. During install, check **"Add to PATH"** ✓

Verify it works:
```
tesseract --version
```
You should see: `tesseract 5.x.x`

---

## Step 2 — Install Python packages

```bash
pip install pytesseract opencv-python-headless openpyxl
```

That's it. No PyTorch. No 1.5GB download. No GPU needed.

---

## Step 3 — Run

```bash
# Test with 5 folders first
python pipeline.py --limit 5

# If order ID not showing — see exactly what Tesseract read
python pipeline.py --limit 5 --fresh --debug

# Full run (auto-resumes if interrupted)
python pipeline.py

# Export results to Excel
python pipeline.py --export
```

---

## Database Location

```
C:\myfiles\IFB\Project\IT\Zoho-Forms\zoho_pipeline.db
```

View live with **DB Browser for SQLite** (free): https://sqlitebrowser.org/dl/

---

## Flag Reference

| Flag             | Meaning                                        | Excel colour  |
|------------------|------------------------------------------------|---------------|
| OK               | Both Order ID and Star found                   | Green         |
| NO_ORDER_ID      | Could not find Order ID in either image        | Orange        |
| NO_STAR          | Could not find star rating in either image     | Orange        |
| LOW_CONF_ORDER   | Order ID found but prefix digits uncertain     | Light blue    |
| MISSING_IMG1     | ImageUpload folder had no image                | Grey          |
| MISSING_IMG2     | ImageUpload1 folder had no image               | Grey          |
| ERROR            | Unexpected crash on this record                | Red           |

---

## Order ID Logic

1. Try **Image1** — 5-strategy cascade:
   - S1: Amazon `405-1234567-7654321` pattern
   - S2: Clean `OD` + 18 digits
   - S3: Per-character OCR correction (O→0, D→d, I→1, l→1, S→5…)
   - S4: Stitch whitespace away, re-match
   - S5: 15-18 digit block near keyword → prepend OD (flagged LOW_CONF)
2. Not found → try **Image2**
3. Still not found → `"Order ID not found in files"`

## Star Rating Logic

1. Try **Image2**:
   - Tesseract text: "4.5 out of 5", "4 stars", "★★★★☆", "rating: 4"
   - OpenCV colour blobs: find horizontal strip of uniform yellow/green blobs
2. Not found → try **Image1**
3. Still not found → `"Stars not found in files"`

Remark format:
- `4` — normal
- `Single - 4` — only the 4th star was coloured (rest black)
- `Dark - 4` — dark mode screenshot
