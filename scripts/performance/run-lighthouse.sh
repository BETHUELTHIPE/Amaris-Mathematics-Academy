#!/usr/bin/env bash
set -uo pipefail

rm -rf .lighthouseci

set +e
./node_modules/.bin/lhci autorun --config=lighthouserc.json
lhci_status=$?
set -e

report_status=0
node scripts/performance/report-lighthouse.mjs || report_status=$?

if [[ "$lhci_status" -ne 0 ]]; then
  exit "$lhci_status"
fi

exit "$report_status"
