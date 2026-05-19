"""
Entry point for Streamlit Cloud deployment.
Streamlit Cloud recognizes this filename automatically.
Runs the dashboard application.
"""

import runpy
import sys
from pathlib import Path

# Get the directory of this file
app_dir = Path(__file__).parent

# Run dashboard.py in current namespace
runpy.run_path(str(app_dir / "dashboard.py"), run_name="__main__")
