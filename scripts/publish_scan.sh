#!/usr/bin/env bash
set -euo pipefail
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
python scripts/job_schema.py data/jobs.json
git add data/jobs.json
if git diff --cached --quiet; then exit 0; fi
git commit -m "Alice Radar: persist scan checkpoint"
if git push origin HEAD:main; then exit 0; fi
snapshot=$(mktemp)
trap 'rm -f "$snapshot"' EXIT
cp data/jobs.json "$snapshot"
for attempt in 1 2 3; do
  git fetch origin main
  git reset --hard origin/main
  python scripts/merge_scan_result.py "$snapshot" data/jobs.json
  python scripts/job_schema.py data/jobs.json
  git add data/jobs.json
  if git diff --cached --quiet; then exit 0; fi
  git commit -m "Alice Radar: merge concurrent scan checkpoint"
  if git push origin HEAD:main; then exit 0; fi
  sleep 2
done
echo "Scan publication failed after conflict-safe retries" >&2
exit 1
