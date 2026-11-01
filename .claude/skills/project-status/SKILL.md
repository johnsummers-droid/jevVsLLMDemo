---
name: project-status
description: 'Short summary of where this project stands: what is done, what is next, open PRs, deployment health and the user''s open to-dos. Use when the user asks for a status update, "where are we", or what is left to do. Not for a plain git status of changed files.'
---

# Project status

Run this and base the summary on its output:

```bash
bash "$(git rev-parse --show-toplevel)/.claude/skills/project-status/gather.sh"
```

The script prints live facts (git, GitHub, deployed URLs) and the saved to-do notes.

## Rules

- Live facts win. The notes can be out of date, so check each to-do against the live output. For example, a PR listed as open may have merged.
- If a to-do has clearly changed, update `session-start-reminders.md` in memory and say so. Change nothing else: no commits, no pushes, no other edits.
- A web or API line that shows `000`, or no answer, may only be the free Render service asleep. Say that rather than calling it down.
- If the script's output doesn't answer something, read `CLAUDE.md` ("Current status") or `specs-and-plans/plan1.txt` §7. Don't guess.

## Output

Keep it short enough to read at a glance, in this order:

1. **Done:** milestones and tasks, in one or two lines.
2. **Right now:** branch, uncommitted or unpushed work, open PRs, CI, deployed health. Only mention what is unusual; a line saying all is well is enough otherwise.
3. **Next:** the next task or two, with one line on what each does.
4. **Your to-dos:** things only the user can do or decide, with dates where they exist.

End with one line naming the most useful next step. Skip anything already covered above.
