"""Run the current source-bound v1.1 review verifier."""
import runpy
from pathlib import Path

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    runpy.run_path(str(root / "analysis/v1_1_final_sweep_20261016/verify.py"), run_name="__main__")
