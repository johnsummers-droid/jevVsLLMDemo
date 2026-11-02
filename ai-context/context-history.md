# Context history

Why the engine works the way it does: decisions from the early tasks that still hold, and the reasons
behind them. It replaces the T2 to T5 task notes and the help panel requirements discussion, whose
build lists, test lists and status lines are in git history (`git log -- specs-and-plans/`).

`plan1.txt` remains the working plan. Code comments cite this file by task and decision number, such
as "T4 decision 1". Numbers are the originals and have gaps where a decision no longer matters.
Where later work changed something, the note says so.

## T2: node catalog

1. **Template ports.** A dynamic port's id must end in `.*` (`route.*`), and only dynamic ports may
   use that form.
2. **The catalog sends templates, not expanded ports.** The browser expands `route.*` the same way
   `registry.expand_outputs` does: one branch per selected value, in selection order.
3. **LLM costs.** `CostModel` shows the default "large" tier; other tiers are in `TIER_LATENCY_MS`.
4. **Values chosen where the plan gave none.** A human review is 120 s and $2.00, excluded from
   latency. Policy `rules` and `data_classes` may be empty.
5. **Param keys stay snake_case in graph JSON** (`traffic_mix`). They are data matching
   `ParamSpec.key`, not model fields, so the camelCase wire rule doesn't apply.

## T3: graph validator

- **Later checks only see what resolved**, so one mistake doesn't set off more errors: edges to an
  unknown node type aren't rechecked, an invalid `allowed_intents` expands to every option so its
  edges aren't also UNKNOWN_PORT, and incompatible edges still count as connected for fan-in and
  required inputs. Checks continue after errors so the canvas can badge everything at once.
- **Branch exclusivity under-approximates:** edges are only called exclusive when that is certain.

Numbered rules:

2. **NO_SAFETY_COVERAGE:** a safety check counts only when the path leaves it through `route.safe`, a
   policy engine only through `route.pass`. Reported once per LLM node, using a state search over
   (node, screened, unprotected LLM) so it needn't list every path.
3. **GATE_NEEDS_SIGNAL is data-driven** (`requires_one_of` on the definition), not tied to a node name.
4. An edge to a missing node id is UNKNOWN_PORT, with its edge id.
5. **DUPLICATE_ID** covers node and edge ids separately; a node and an edge may share an id.
6. **MULTIPLE_SOURCES** is one issue per source, so each gets a badge. Several sinks are allowed.
7. Multi inputs have no fan-in limit.
8. **DEAD_END** is per node: no path from it reaches a sink. Unconnected data outputs aren't warned
   about; unconnected branches are UNCONNECTED_BRANCH.
9. Graphs without a source skip UNREACHABLE_NODE, NO_SAFETY_COVERAGE and NO_HUMAN_FALLBACK. Cyclic
   graphs skip MULTI_INPUT_RACE.
10. **MULTI_INPUT_RACE** is one warning per multi input, naming one racing pair.

## T4: scenario packs, mock providers, runners

1. **Seed only on what the provider sees:** sha256(run seed, ticket, node type, provider-relevant
   params, fingerprint of the input values and their taint). The router's threshold is applied after
   the Jev call, so seeding on it would redraw the confidence and break per-ticket threshold
   monotonicity. The input fingerprint stops two identical nodes in a row drawing the same numbers.
   Node ids aren't included, so renaming a node can't change results. (`temperature` has since gone,
   U11.)
2. **Latency sampling is lognormal around a median** (`engine/latency.py`), because every `NodeResult`
   needs a latency.
4. **Marker phrases.** `Ticket.risk` says which phrase the mock LLM writes when an injection or policy
   violation gets through. Each phrase is caught by exactly one policy rule, and the default policy
   enables only `no_refund_promises`. This is part of the game: don't reveal it to players. `pii_kinds`
   lists PII the mock LLM may echo.
5. **`knowledge_lookup` exists because the strong reference graph needs it.**
6. **`official.json` is in git,** so "never sent to clients" holds only at the API level. Revisit if the
   repo is public on workshop day.

Facts that aren't obvious from the code:

- The safety check never strips taint: a detection fires `route.unsafe`, so there's nothing to strip on
  `route.safe`. Policy-violation tickets count as the "abuse" category.
- The mock LLM drops the "injection" taint when it refuses, and replaces the input's taint with its own.
- `pyproject.toml` ships the packs and `kb.json` as package data.

## T5: executor, metrics, scoring

1. **Requests are simulated one at a time, then merged** by (sim time, request index, emission index).
   The stream is in simulated-time order, which the pacer needs, and causal order holds within a
   request. Concurrency only matters once human-review capacity exists. (T38 runs live requests
   concurrently; the merged order is unchanged.)
2. **The cost budget must include human review.** A review costs far more than an LLM answer, so no
   budget can make the LLM-only starter miss on cost without crushing every graph that escalates. Its
   weaknesses are safety and latency. The cost penalty is aimed at over-escalation.
3. **A correct automated request must be neither `must_escalate` nor `must_block`.** Counting those as
   correct would reward unsafe releases. (Later refined: a judged clean reply on a `must_block` ticket
   on real AI isn't an unsafe release, U9.)
4. **Outcome precedence:** failed > delivered (escalated if the delivered value passed through human
   review, else automated) > blocked (a policy block or unsafe branch fired with no consumer) > dropped.
   "Passed through review" is provenance on values, not "a human node ran somewhere in the request".
5. **Traffic:** a run uses the whole pack. `traffic_spike` cycles through tickets; `injection_wave`
   appends another copy of every injection ticket. Arrivals spread evenly with seeded jitter.
   `traffic_mix` and `attack_rate` are ignored (see `docs/future-ideas.md`).
6. **Reference graphs are Python builders** with generated fixtures and a drift test.
7. **Golden tests check every seed in a fixed list,** so a lucky seed can't hide a regression. The
   strong graph's unsafe rate is checked as a mean, because a safety miss on a risky ticket with a
   harmless answer still counts as a release on the mocks.

Current scores on real AI are in `docs/admin-guide.md`; the T5 mock tuning numbers are out of date.

## Help panel (T32, T33)

Requirements discussed with the user on 2026-10-31; the design is decisions S1-S8 in `plan1.txt`.

- **Non-modal, not modal.** The app must keep working under the panel, so it's a panel docked along the
  bottom of the canvas. "Just below the nodes" can't work, because nodes can be anywhere.
- **No spoilers (agreed).** Help explains how a node works, never the answers. Discovering that the
  default policy misses most bad replies is part of the workshop.
- **Examples are real:** a test runs each through the actual node, so a wrong example fails CI.
- **Content lives on the server** with the catalog, so it can't drift from what a node does.
- **Always available,** including when a graph is locked or a run is playing.
