"""Dev helper: load .env.local into os.environ, then run a target script as __main__.
   Usage: python3 scripts/_run_with_env.py scripts/gfs_ingest.py stratolink-3
   Not used in production (the workflow sets env directly)."""
import os, sys, runpy

env_path = os.path.join(os.path.dirname(__file__), "..", ".env.local")
if os.path.exists(env_path):
    for line in open(env_path):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ[k] = v.strip().strip('"')
else:
    print(f"_run_with_env: no {os.path.normpath(env_path)}; running with the current environment", file=sys.stderr)

target = sys.argv[1]
sys.argv = [target] + sys.argv[2:]
runpy.run_path(target, run_name="__main__")
