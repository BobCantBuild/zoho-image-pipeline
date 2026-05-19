"""
Entry point for Streamlit Cloud deployment.
Streamlit Cloud recognizes this filename automatically.
"""
import sys
from pathlib import Path

# Import and run the dashboard
from dashboard import *  # noqa: F401, F403

# This ensures the app runs when deployed to Streamlit Cloud
if __name__ == "__main__":
    pass  # Dashboard runs via imports above
