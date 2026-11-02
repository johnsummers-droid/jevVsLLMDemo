# Future ideas

Ideas for the simulator that are not agreed work yet. Agreed but unbuilt features are in
`plan1.txt` section 9. Started 2026-11-02.

## Review time with a price

Show Review time and keep it editable, with quicker reviews costing more than slower ones.
Today a review has a fixed cost and its time is left out of latency, so the setting doesn't affect
metrics or score. A team could reasonably expect a faster reviewer to help.

- Teams would trade speed against cost on human review, as they already do on the LLM.
- Needs: a cost curve from review time (a `$/review` rule in the node's cost model), the Inspector
  and help panel showing the current cost, and a reason for speed to matter: either count review
  time in a metric or add a separate "time to human answer" metric. Without that, the slowest
  review would always win.
- The reference graphs and the scoring would need re-checking on the real AI (admin guide's
  calibration table), so the intended order of strong, starter, weak and escalate_all holds.

## Hidden parameters

These stay in the catalog with `hidden=True` (or one option) and in saved graphs, but the Inspector
and help panel leave them out because they do nothing yet. To bring one back: build what is below,
then remove the flag.

| Node | Parameter | What it would need |
|---|---|---|
| Customer message | Traffic mix | The traffic generator choosing tickets by mix. The pack only has one fixed mix, so it needs tagged tickets or larger packs, and new real AI calls to store. Official runs must keep one mix for every team. |
| Customer message | Attack rate | The same, drawing a set share of attack tickets. Related to the injection wave in section 9. |
| Customer message | Language | A second option (it reappears by itself), tickets and help-center articles in that language, and policy rules that work in it. Also put `language` back on the Meta output's `TicketMeta` payload, removed on 2026-11-02 because it could only ever be `en` and nothing read it. |
| Human review queue | Reviewers | A simulated queue, so that too few reviewers makes requests wait. Planned as T26 (M5, paused). |
| Customer response | Channel | Something that differs by channel, such as reply length limits or a latency target per channel. `meta` should also stop hard-coding `chat`. |
| Customer response | SLA (ms) | Showing the target against p95 in the run bar, and possibly a share of requests over the target in the metrics or the score. |

## Hidden outputs

Port `hidden=True` leaves these out of the canvas, Inspector and help panel because no node can use
them: nothing accepts their type, or the only input that does ignores them. The runners still
produce them. To bring one back, build a node or setting that reads it, then remove the flag.

| Node | Output | What could use it |
|---|---|---|
| Customer message | Meta (channel) | Show a plain Channel output instead of a JSON Meta, once something differs by channel (see Channel above). |
| Jev intent router | Intent, Probabilities, Confidence | The parked escalation gate (T25), routing on confidence, or a trace viewer showing why a message took its branch. |
| Jev safety check | Is safe, Confidence, Categories | The same gate, or routing by category, such as fraud to a different queue. |
| Policy engine | Passed, Report | A reviewer that reads the report through its Context input. |

Hidden inputs, for the same reason: Context on Policy engine (a rule that reads it, such as checking
a reply against the articles it was based on) and Context on Human review queue (a reviewer who
works better with the docs or a report).

## Leaderboard

- A small score bar in each row, extending right for positive and left for negative, to show the
  gaps between teams. Check it with the `dataviz` skill.
- Marking 2nd and 3rd place as well as the winner.
- A decision quality column, which is computed but not shown; or a slimmer `/screen` with fewer
  columns for reading across a room.
- A real bold weight of Inter: only 400 is loaded, so bold text is browser-thickened.

## Debrief

- A score breakdown per team (safety, cost, latency), to show why a team ranked where it did.
- A team's graph beside a reference graph on `/screen`.
- Which kinds of ticket each team got wrong, by category and never by ticket text, so the official
  pack stays hidden.

## Teams' understanding of a run

- After a run, show measured latency and cost next to the Inspector's "Cost and latency
  assumptions". In live mode the two can differ, and today only the assumptions are in that panel.
- Listing which practice tickets the LLM's safety filter blocked, since a prompt can change them.
- Team-chosen names for nodes (`data.label` already exists), which would help on graphs with two
  of the same node.

## Canvas

- Undo and redo.
- Warning before a change that deletes edges, such as removing an allowed intent.

## Facilitator

- Today's real AI spend against the daily cap on the facilitator page, instead of only a warning
  once the cap is reached.
- Deleting a team or a session: no API does this, so test teams stay in a session forever.
