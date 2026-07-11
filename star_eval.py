#!/usr/bin/env python3
# =============================================================
#  STAR DETECTION EVALUATION
#  Validate against ground-truth dataset
# =============================================================

import pandas as pd
import numpy as np
from pathlib import Path
import time
import sys
from collections import defaultdict, Counter
from star_detection import extract_star_rating

# Load ground truth
DATASET_PATH = Path(__file__).parent / "Data-Training.xlsx"


def load_ground_truth():
    """Load Excel dataset and find actual image files."""
    df = pd.read_excel(DATASET_PATH, sheet_name='Sheet1')

    # Excel lists directories, but images are inside them
    # Find the first image file in each directory
    df['image_file'] = df['File location'].apply(_find_image_file)
    return df


def _find_image_file(dir_path):
    """Find first image file in directory (jpg/jpeg/png)."""
    import glob
    p = Path(dir_path)
    if not p.exists():
        return None

    # Look for image files
    for ext in ['*.jpg', '*.jpeg', '*.png', '*.JPG', '*.JPEG', '*.PNG']:
        files = list(p.glob(ext))
        if files:
            return str(files[0])
    return None


def evaluate():
    """Run evaluation on all images in dataset."""
    print("\n" + "="*70)
    print("  STAR DETECTION EVALUATION v3")
    print("="*70)

    df = load_ground_truth()
    total_images = len(df)

    print(f"\n[Dataset] {total_images} images")
    print(f"   Ground truth distribution:")
    for stars in sorted(df['Actual Stars Present'].unique()):
        count = (df['Actual Stars Present'] == stars).sum()
        pct = 100 * count / total_images
        print(f"   {int(stars):1d}star : {count:2d} images ({pct:5.1f}%)")

    # Run extraction on each image
    results = []
    strategy_counts = Counter()
    errors = []

    print(f"\n[Processing] {total_images} images...")
    start_time = time.time()

    for idx, row in df.iterrows():
        img_path = row['image_file']
        actual_stars = row['Actual Stars Present']
        remarks = row['Remarks']

        if img_path is None:
            strategy_counts['missing'] += 1
            results.append({
                'idx': idx + 1,
                'image': Path(row['File location']).parent.name,
                'actual': int(actual_stars),
                'predicted': None,
                'match': False,
                'strategy': 'missing',
                'engine': 'error',
                'remark_file': remarks,
                'remark_detected': 'Image file not found'
            })
            errors.append({
                'idx': idx + 1,
                'image': Path(row['File location']).parent.name,
                'actual': int(actual_stars),
                'predicted': 'MISSING',
                'strategy': 'missing',
                'remarks': 'Image file not found in directory'
            })
            continue

        try:
            predicted_stars, remark, engine = extract_star_rating(img_path)

            # Extract strategy from engine string
            if engine.startswith("opencv_"):
                strategy = engine.split("_")[1]
            elif engine == "ocr_label":
                strategy = "ocr_label"
            else:
                strategy = "none"

            strategy_counts[strategy] += 1

            match = (predicted_stars == actual_stars) if predicted_stars is not None else False

            results.append({
                'idx': idx + 1,
                'image': Path(img_path).parent.name,
                'actual': int(actual_stars),
                'predicted': int(predicted_stars) if predicted_stars else None,
                'match': match,
                'strategy': strategy,
                'engine': engine,
                'remark_file': remarks,
                'remark_detected': remark
            })

            if not match:
                errors.append({
                    'idx': idx + 1,
                    'image': Path(img_path).parent.name,
                    'actual': int(actual_stars),
                    'predicted': int(predicted_stars) if predicted_stars else 'None',
                    'strategy': strategy,
                    'remarks': remarks
                })

        except Exception as e:
            strategy_counts['error'] += 1
            results.append({
                'idx': idx + 1,
                'image': Path(img_path).parent.name,
                'actual': int(actual_stars),
                'predicted': None,
                'match': False,
                'strategy': 'error',
                'engine': 'error',
                'remark_file': remarks,
                'remark_detected': str(e)
            })
            errors.append({
                'idx': idx + 1,
                'image': Path(img_path).parent.name,
                'actual': int(actual_stars),
                'predicted': 'ERROR',
                'strategy': 'error',
                'remarks': str(e)
            })

    elapsed = time.time() - start_time

    # Compute metrics
    df_results = pd.DataFrame(results)
    correct = df_results['match'].sum()
    accuracy = 100 * correct / len(results)

    print(f"[Done] Completed in {elapsed:.1f}s\n")

    # ──────────────────────────────────────────────────────
    #  RESULTS SUMMARY
    # ──────────────────────────────────────────────────────

    print("RESULTS")
    print("="*70)
    print(f"Overall Accuracy: {correct}/{total_images} = {accuracy:.1f}%\n")

    # Confusion matrix
    print("Confusion Matrix (Predicted vs Actual)")
    print("-" * 70)

    # Create matrix
    confusion = np.zeros((6, 6), dtype=int)
    for _, row in df_results.iterrows():
        if row['predicted'] is not None and pd.notna(row['predicted']):
            actual = int(row['actual'])
            pred = int(row['predicted'])
            if 0 <= actual <= 5 and 0 <= pred <= 5:
                confusion[actual, pred] += 1

    print("\n     Predicted [0 1 2 3 4 5]")
    print("      ", end="")
    for p in range(6):
        print(f"{p:3d}", end=" ")
    print()

    for a in range(6):
        print(f"A  {a} | ", end="")
        for p in range(6):
            val = confusion[a, p]
            if val == 0:
                print(f"  .", end=" ")
            else:
                print(f"{val:3d}", end=" ")
        print()

    # Per-star accuracy
    print("\n\nPer-Star Accuracy")
    print("-" * 70)
    for stars in sorted(df['Actual Stars Present'].unique()):
        mask = df_results['actual'] == stars
        star_correct = (df_results[mask]['match']).sum()
        star_total = mask.sum()
        star_acc = 100 * star_correct / star_total if star_total > 0 else 0
        print(f"{int(stars)}star : {star_correct:2d}/{star_total:2d} correct ({star_acc:5.1f}%)")

    # Strategy distribution
    print("\n\nStrategy Usage")
    print("-" * 70)
    for strategy, count in sorted(strategy_counts.items(), key=lambda x: -x[1]):
        pct = 100 * count / total_images
        print(f"{strategy:18s} : {count:2d} ({pct:5.1f}%)")

    # Error details
    if errors:
        print("\n\nMisclassifications")
        print("-" * 70)
        print(f"Total errors: {len(errors)}\n")

        # Group by type
        for actual_star in sorted(set(e['actual'] for e in errors)):
            matching_errors = [e for e in errors if e['actual'] == actual_star]
            if matching_errors:
                print(f"\n{int(actual_star)}star actual (misdetected as):")
                pred_dist = Counter(e['predicted'] for e in matching_errors)
                for pred, count in sorted(pred_dist.items(), key=lambda x: -x[1]):
                    print(f"   -> {pred}: {count} times")
                    # Show first example
                    example = matching_errors[[e['predicted'] for e in matching_errors].index(pred)]
                    print(f"      Example: {example['image']} ({example['strategy']})")

    # Save detailed results to CSV
    csv_path = Path(__file__).parent / "star_eval_results.csv"
    df_results.to_csv(csv_path, index=False)
    print(f"\n\n[SAVED] Detailed results: {csv_path}")

    # Error details CSV
    if errors:
        errors_df = pd.DataFrame(errors)
        errors_csv = Path(__file__).parent / "star_eval_errors.csv"
        errors_df.to_csv(errors_csv, index=False)
        print(f"[SAVED] Error details: {errors_csv}")

    print("\n" + "="*70)
    print(f"[DONE] Evaluation complete. Accuracy: {accuracy:.1f}%")
    print("="*70 + "\n")

    return accuracy, len(errors)


if __name__ == "__main__":
    try:
        accuracy, error_count = evaluate()
        sys.exit(0 if accuracy >= 85 else 1)
    except Exception as e:
        print(f"\n❌ Evaluation failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
