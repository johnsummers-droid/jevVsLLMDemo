#!/usr/bin/env bash
# Read-only facts for the /project-status skill. Never exits non-zero: a missing tool
# or a sleeping service is reported as a line of output, not a failure.
# The one thing it writes is git's remote-tracking refs (git fetch).
set -u

root=$(git rev-parse --show-toplevel 2>/dev/null) || { echo "not a git repository"; exit 0; }
cd "$root" || exit 0

section() { printf '\n=== %s ===\n' "$1"; }

section "Git"
git fetch origin --quiet 2>/dev/null || echo "(fetch failed: remote comparison may be stale)"
branch=$(git branch --show-current)
echo "branch: ${branch:-detached}"
echo "commits not on origin/main: $(git rev-list --count origin/main..HEAD 2>/dev/null || echo unknown)"
echo "commits behind origin/main: $(git rev-list --count HEAD..origin/main 2>/dev/null || echo unknown)"
if git rev-parse --abbrev-ref '@{u}' >/dev/null 2>&1; then
  echo "unpushed commits: $(git rev-list --count '@{u}..HEAD')"
else
  echo "unpushed commits: no upstream"
fi
echo "uncommitted files:"
git status --short | sed 's/^/  /'
echo "latest on origin/main:"
git log --format='  %h %cs %s' -5 origin/main 2>/dev/null

section "GitHub"
if command -v gh >/dev/null 2>&1; then
  echo "open PRs:"
  gh pr list --state open --limit 10 --json number,title,headRefName \
    --template '{{range .}}  #{{.number}} {{.title}} ({{.headRefName}}){{"\n"}}{{end}}' 2>&1
  echo "recently merged PRs:"
  gh pr list --state merged --limit 3 --json number,title,mergedAt \
    --template '{{range .}}  #{{.number}} {{.title}} (merged {{.mergedAt}}){{"\n"}}{{end}}' 2>&1
  echo "latest CI on main:"
  gh run list --branch main --limit 1 --json conclusion,status,displayTitle \
    --template '{{range .}}  {{.status}} {{.conclusion}}: {{.displayTitle}}{{"\n"}}{{end}}' 2>&1
else
  echo "gh is not installed"
fi

section "Deployed"
probe() {
  code=$(curl -s -o /dev/null -m 20 -w '%{http_code}' "$2" 2>/dev/null) || code="no answer in 20 s"
  echo "$1: $code"
}
probe "web" "https://jev-vs-llm-demo-delta.vercel.app"
probe "api" "https://pipeline-sim-api.onrender.com/api/health"

section "To-do list (saved notes; may be out of date)"
notes="$HOME/.claude/projects/$(printf '%s' "$root" | sed 's#/#-#g')/memory/session-start-reminders.md"
if [ -f "$notes" ]; then
  sed -n '/^State at end/,/^Keep this list/p' "$notes"
else
  echo "no notes file at $notes"
fi

section "Plan"
grep -o 'Next: [^.]*\.' CLAUDE.md 2>/dev/null | tail -1
exit 0
