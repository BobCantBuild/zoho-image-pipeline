# =============================================================
#  sync_to_github.py  —  Auto-push latest DB data to GitHub
#
#  Called automatically at the END of pipeline.py after processing.
#  Exports SQLite → data/zoho_latest.csv → git commit → git push
#
#  ONE-TIME SETUP (run once, then never again):
#    1. Ensure `git` is installed and available on PATH
#    2. Make sure `git push` works from this repo without password
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
from config import DB_PATH as CONFIG_DB_PATH

logger = logging.getLogger(__name__)

# ── CONFIG ────────────────────────────────────────────────────
DB_PATH = os.environ.get("ZOHOPIPE_DB_PATH") or str(CONFIG_DB_PATH)
REPO_PATH = os.environ.get("ZOHOPIPE_REPO_PATH") or str(Path(__file__).resolve().parent)
CSV_EXPORT_DIR = "data"  # subfolder inside repo
CSV_FILENAME = "zoho_latest.csv"
# Remote that Streamlit Cloud deploys from — must match the repo in streamlit.io settings
GIT_REMOTE = os.environ.get("ZOHOPIPE_GIT_REMOTE", "origin")
# ─────────────────────────────────────────────────────────────


def export_db_to_csv(csv_path: Path):
    """Export full SQLite table to CSV."""
    import csv

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT
            sno,
            added_time,
            branch,
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


def _run_git(repo: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Git command failed: git {' '.join(args)}\n"
            f"{(result.stderr or result.stdout).strip()}"
        )
    return (result.stdout or "").strip()


def git_push(repo: Path, csv_rel: str, row_count: int):
    """Stage the CSV, commit, push."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    msg       = f"auto: update dashboard data — {row_count} records [{timestamp}]"

    # Refuse to commit/push from a detached HEAD (common cause of "pushed but not deployed")
    branch = _run_git(repo, ["rev-parse", "--abbrev-ref", "HEAD"])
    if branch.strip().upper() == "HEAD":
        raise RuntimeError(
            "Repo is in detached HEAD state. Checkout your deployment branch "
            "(e.g. `main`) before running the pipeline sync."
        )

    _run_git(repo, ["add", csv_rel])

    # Check if there's actually a diff before committing
    status = _run_git(repo, ["diff", "--cached", "--name-only"]).strip()

    if not status:
        logger.info("sync_to_github: CSV unchanged — skipping commit")
        return

    _run_git(repo, ["commit", "-m", msg])
    _run_git(repo, ["push", GIT_REMOTE, branch])
    logger.info("sync_to_github: pushed %d rows to GitHub (%s)", row_count, GIT_REMOTE)
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
