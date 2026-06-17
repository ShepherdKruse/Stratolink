"""Dev helper: load .env.local into os.environ, then run a target script as __main__.
   Usage: python3 scripts/_run_with_env.py scripts/gfs_ingest.py stratolink-3
   Not used in production (the workflow sets env directly)."""
import os, sys, runpy

for line in open(os.path.join(os.path.dirname(__file__), "..", ".env.local")):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    os.environ[k] = v.strip().strip('"')

target = sys.argv[1]
sys.argv = [target] + sys.argv[2:]
runpy.run_path(target, run_name="__main__")
