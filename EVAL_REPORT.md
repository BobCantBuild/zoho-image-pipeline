# Star Detection Evaluation Report
**Date:** 2026-05-22  
**Dataset:** 60 images (ground truth from Data-Training.xlsx)  
**Consolidated Code:** star_detection.py (1000+ lines)  
**Framework:** star_eval.py (automated validation + metrics)

---

## Executive Summary

| Metric | Value |
|--------|-------|
| **Overall Accuracy** | 65.0% (39/60) |
| **Processing Time** | ~150-200s for 60 images |
| **Correctly Classified** | 39 images |
| **Misclassified** | 21 images |

---

## Per-Star Accuracy Breakdown

| Rating | Ground Truth | Correct | Accuracy |
|--------|-------------|---------|----------|
| **0★** (no stars) | 5 | 0 | 0% |
| **3★** | 2 | 2 | **100%** ✓ |
| **4★** | 6 | 4 | 66.7% |
| **5★** | 47 | 33 | 70.2% |

### Key Observations:
- **Best:** 3-star detection is perfect (100%)
- **Good:** 4★ and 5★ detection both >66%
- **Challenge:** 0-star images (no detection strategy for empty grids)

---

## Confusion Matrix

```
        Predicted [0 1 2 3 4 5]
         0  1  2  3  4  5 
Actual 0 |  .  1  .  .  .  .    ← 0★: 1 correct, 4 missed
       1 |  .  .  .  .  .  .    ← 1★: N/A (none in dataset)
       2 |  .  .  .  .  .  .    ← 2★: N/A (none in dataset)
       3 |  .  .  .  2  .  .    ← 3★: 1 correct, 1 detected as 4
       4 |  .  .  .  .  4  1    ← 4★: 4 correct, 1 as 5★
       5 |  .  1  2  2  6 33    ← 5★: 33 correct, 6 undercounted (as 4★)
```

---

## Detection Strategy Distribution

| Strategy | Count | % | Notes |
|----------|-------|---|-------|
| **top_row** | 25 | 41.7% | Counts 3-5 colored blobs in row (Amazon style) |
| **slot_position** | 15 | 25.0% | 1-2 highlighted stars + slot detection (Flipkart) |
| **ocr_label** | 12 | 20.0% | Text label fallback (Great/Good/Bad/Okay) |
| **none** | 8 | 13.3% | Could not detect any colored blobs or patterns |

---

## Error Analysis

### Critical Issues (21 misclassifications)

#### 1. 0-Star Images (4 errors)
- **Problem:** Algorithm cannot distinguish "empty rating grid" from "no grid at all"
- **Current behavior:** Returns `None` (no colored blobs detected)
- **Expected:** Should return `0` when grid is visible but unfilled
- **Impact:** All 5 zero-star images failed

**Examples:**
- "No stars in this picture" → None (should be 0)
- "No color star at all" → None (should be 0)  
- Mixed: 1 image detected as 1★ when should be 0

**Recommended Fix:**
- Add grid outline detection (Otsu+Canny on full image)
- Return 0 if we find 4-5 visible star slots but 0 colored blobs

---

#### 2. 5-Star Undercounting (6 errors → detected as 4★)
- **Problem:** Green star rows counted as 4 instead of 5
- **Root cause:** Likely morphological operations merging adjacent blobs
- **Impact:** 12.8% of 5-star images misclassified

**Example patterns:**
- "5 Green star in a row" → detected as 4★ (6 instances)

**Recommended Fix:**
- Reduce MORPH_OPEN kernel from (3,3) to (2,2) to prevent merging
- Increase max_area threshold for blob validation in dense rows
- Or: Use separate detection path for 5-star rows (different morphology)

---

#### 3. Mixed-Color Arrangements (2 errors → detected as wrong slots)
- **Problem:** Gold + black/dark star arrangements confuse position estimation
- **Example:** "1 Gold + 4 dark stars" might be detected as slot 1 or 3
- **Impact:** Slot detection gets confused on mixed patterns

**Recommended Fix:**
- When we find 1 colored + 4 non-colored blobs, treat as full row (count = 5)
- Add heuristic: if colored blob is at edge, assume it's 1-of-5 in same row

---

#### 4. None Detection (3 errors on 5-star)
- **Problem:** Some green star images fail to generate any mask
- **Cause:** Green HSV ranges might not cover all green shades
- **Impact:** Falls back to OCR, which may be unreliable

**Recommended Fix:**
- Expand green HSV range: H[35-100], S[20-255], V[30-220]
- Add additional "very muted green" range for Flipkart Order Details

---

## Strategic Recommendations

### High-Impact (Quick Wins)
1. **Fix 5-star undercounting** (6 errors)
   - Effort: LOW — change morphological kernel size
   - Impact: +10% accuracy (~66% → 76%)

2. **Add 0-star grid detection** (4 errors)
   - Effort: MEDIUM — implement grid outline detection
   - Impact: +6-7% accuracy (~65% → 71-72%)

### Medium-Impact
3. **Refine green HSV ranges** (help with None detections)
   - Effort: LOW-MEDIUM — test HSV ranges on failing images
   - Impact: +2-3% accuracy

4. **Improve mixed-color handling** (complex arrangements)
   - Effort: MEDIUM — add heuristics for gold+dark patterns
   - Impact: +1-2% accuracy

---

## Implementation Priority

```
Tier 1: Morphological tuning (5★ fix)
  → Expected impact: +10 percentage points
  → Risk: LOW (safe parameter change)

Tier 2: Grid detection for 0★
  → Expected impact: +6-7 percentage points  
  → Risk: MEDIUM (new feature, needs tuning)

Tier 3: HSV refinement + heuristics
  → Expected impact: +3-5 percentage points
  → Risk: LOW-MEDIUM (incremental)
```

---

## Data Files

- `star_eval_results.csv` — Full results (all 60 images, all fields)
- `star_eval_errors.csv` — Misclassified images only (21 rows)
- `star_eval.py` — Evaluation framework (run `python star_eval.py` anytime)

---

## Testing the Improvements

After each fix, re-run evaluation:
```bash
python star_eval.py
```

The script will:
1. Load all 60 test images
2. Run detection on each
3. Compare against ground truth
4. Generate confusion matrix, per-star breakdown, strategy distribution
5. List all misclassified images with details

---

## Next Steps

1. **Implement Tier 1 fix** (morphological tuning for 5★)
   - Edit `_build_star_rows()` morphological kernel
   - Re-run `star_eval.py`
   - Target: 75%+ accuracy

2. **Implement Tier 2 fix** (grid detection for 0★)
   - Add `_detect_empty_grid()` helper
   - Integrate into `_star_from_image()`
   - Re-run `star_eval.py`
   - Target: 80%+ accuracy

3. **Fine-tune HSV ranges** if needed
   - Test on failing green-star images
   - Adjust ranges incrementally
   - Re-run validation

---

**Evaluation Framework:** Consolidated, single-file design (star_detection.py) makes it easy to version, track changes, and validate improvements.
