#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Use provided date arg, or default to today in Seattle time
if [[ $# -ge 1 ]]; then
  TODAY="$1"
else
  TODAY=$(TZ="America/Los_Angeles" date +%Y-%m-%d)
fi

HTML_SRC="output/report_${TODAY}.html"

echo "==> Generating report for ${TODAY}..."
python3 reporter/daily_report.py
if [[ ! -f "$HTML_SRC" ]]; then
  echo "ERROR: Expected $HTML_SRC not found after report generation." >&2
  exit 1
fi

echo "==> Switching to gh-pages branch..."
git checkout -b gh-pages 2>/dev/null || git checkout gh-pages

echo "==> Copying report to index.html..."
cp "$HTML_SRC" index.html

echo "==> Committing..."
git add index.html
git commit -m "report: ${TODAY}"

echo "==> Pushing to origin gh-pages..."
git push origin gh-pages

echo "==> Switching back to main..."
git checkout main

echo "Done. Report live at: https://$(git remote get-url origin | sed 's|.*github.com[:/]\(.*\)\.git|\1|' | sed 's|.*github.com[:/]\(.*\)|\1|').github.io"
