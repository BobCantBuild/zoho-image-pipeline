"""
Entry point for Streamlit Cloud deployment.
Streamlit Cloud recognizes this filename automatically.
Runs the dashboard application.
"""

from __future__ import annotations

import runpy
from pathlib import Path


def main() -> None:
    app_dir = Path(__file__).parent
    runpy.run_path(str(app_dir / "dashboard.py"), run_name="__main__")


if __name__ == "__main__":
    main()
