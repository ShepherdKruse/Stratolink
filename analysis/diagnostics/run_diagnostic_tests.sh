#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../.." && pwd)"
project_python="$repo_root/analysis/.venv/bin/python"

if [[ -n "${ANALYSIS_PYTHON:-}" ]]; then
    python_bin="$ANALYSIS_PYTHON"
elif [[ -x "$project_python" ]]; then
    python_bin="$project_python"
else
    python_bin=python3
fi

for test_path in "$script_dir"/*_test.py; do
    test_name="$(basename -- "$test_path")"
    # Despite its historical name, this is a live TTN downlink operator tool.
    # It must never be invoked as part of an unattended regression run.
    if [[ "$test_name" == "ttn_downlink_test.py" ]]; then
        continue
    fi
    # This test intentionally binds the current build output to the last
    # immutable candidate's exact ELF. During reviewed source development the
    # current output must differ, so callers may skip exactly this stale
    # identity check while still running every source/parser/policy regression.
    # The next candidate freeze must update and re-enable it.
    if [[ "${SKIP_STALE_CANDIDATE_VERIFICATION:-0}" == "1" &&
          "$test_name" == "dynamic_memory_audit_test.py" ]]; then
        echo "SKIP $test_name (intentionally stale frozen-candidate ELF binding)"
        continue
    fi
    echo "RUN $test_name"
    "$python_bin" "$test_path"
done

echo "PASS: all non-mutating diagnostic regressions"
