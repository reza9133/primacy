#!/usr/bin/env bash
# One-time setup for GitHub Codespaces or any fresh checkout.
set -euo pipefail
cd "$(dirname "$0")/.."

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# Warm the GenVM download used by the Direct Mode tests so the first test run is fast.
export GENVM_VERSION="${GENVM_VERSION:-v0.2.16}"
python -m pytest tests/direct/test_smoke.py -q -p no:cacheprovider

echo
echo "Setup complete. Next:"
echo "  python scripts/run_report.py            # static checks, all tests, live Studionet run, one report"
echo "  python scripts/run_report.py --fast     # same, without the time-gated phase (saves roughly 20 minutes)"
echo "  python scripts/run_report.py --no-live  # no network needed"
