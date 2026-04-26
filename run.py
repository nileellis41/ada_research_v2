"""Run Ada Research without installing the package.

    python run.py

Opens a Dash/Plotly web UI at http://localhost:8050

For an installed entry point (after `pip install -e .`), use:

    ada-research
"""
import sys
from pathlib import Path

# Make the src/ layout importable without `pip install -e .`
SRC = Path(__file__).parent / "src"
sys.path.insert(0, str(SRC))

from ada_research.app import main

if __name__ == "__main__":
    main()
