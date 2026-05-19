# =============================================================
#  sync_to_github.py  —  Auto-push latest DB data to GitHub
#
#  Called automatically at the END of pipeline.py after processing.
#  Exports SQLite → data/zoho_latest.csv → git commit → git push
#
#  ONE-TIME SETUP (run once, then never again):
#    1. pip install gitpython
#    2. Set GITHUB_REPO_PATH below to your local repo folder
#    3. Make sure `git push` works from that folder without password
#       (use a Personal Access Token saved in Windows Credential Manager)
#
#  After that: runs silently every time pipeline finishes. No human needed.
# =============================================================

import sqlite3
import subprocess
import logging
import os
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

# ── CONFIG ────────────────────────────────────────────────────
DB_PATH        = r"C:\myfiles\IFB\Project\IT\Zoho-Forms\zoho_pipeline.db"
REPO_PATH      = r"C:\myfiles\IFB\Project\IT\Zoho-Code-Claude-WithoutGem"
CSV_EXPORT_DIR = "data"          # subfolder inside repo
CSV_FILENAME   = "zoho_latest.csv"
# ─────────────────────────────────────────────────────────────


def export_db_to_csv(csv_path: Path):
    """Export full SQLite table to CSV."""
    import csv

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT
            sno,
            ticket_id,
            csv_order_id        AS Zoho_order_ID,
            file_order_id,
            file_star,
            file_name,
            flag                AS pipeline_flag,
            remarks_file_order_id,
            remarks_file_star
        FROM zoho_records
        ORDER BY sno
    """).fetchall()
    conn.close()

    if not rows:
        logger.warning("sync_to_github: DB is empty — nothing to export")
        return 0

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows([dict(r) for r in rows])

    return len(rows)


def git_push(repo: Path, csv_rel: str, row_count: int):
    """Stage the CSV, commit, push."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    msg       = f"auto: update dashboard data — {row_count} records [{timestamp}]"

    def run(cmd):
        result = subprocess.run(
            cmd, cwd=str(repo), capture_output=True, text=True, shell=True
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Git command failed: {cmd}\n{result.stderr.strip()}"
            )
        return result.stdout.strip()

    run(f'git add "{csv_rel}"')

    # Check if there's actually a diff before committing
    status = subprocess.run(
        "git diff --cached --name-only",
        cwd=str(repo), capture_output=True, text=True, shell=True
    ).stdout.strip()

    if not status:
        logger.info("sync_to_github: CSV unchanged — skipping commit")
        return

    run(f'git commit -m "{msg}"')
    run("git push")
    logger.info("sync_to_github: pushed %d rows to GitHub", row_count)
    print(f"  [GitHub] Synced {row_count:,} records → public dashboard updated ✓")


def sync():
    """Main entry point — export DB and push to GitHub."""
    repo     = Path(REPO_PATH)
    csv_rel  = f"{CSV_EXPORT_DIR}/{CSV_FILENAME}"
    csv_path = repo / csv_rel

    if not Path(DB_PATH).exists():
        logger.warning("sync_to_github: DB not found at %s", DB_PATH)
        return

    try:
        row_count = export_db_to_csv(csv_path)
        if row_count > 0:
            git_push(repo, csv_rel, row_count)
    except Exception as e:
        # Never crash the pipeline — sync is best-effort
        logger.error("sync_to_github failed: %s", e)
        print(f"  [GitHub] Sync failed (non-critical): {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(message)s")
    sync()
