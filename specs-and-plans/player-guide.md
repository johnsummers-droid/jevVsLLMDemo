# Pipeline Simulator: Player Guide

Your team runs the customer-support desk for a software company. Tickets
arrive all day: billing questions, bug reports, confused customers, and the
occasional attacker trying to trick your system. Your job is to design the
**pipeline** that handles them: a graph of small automated steps (Jev
decisions, an LLM writer, deterministic tools) with human reviewers as the
safety net.

There is no single right answer. A good pipeline answers most tickets
automatically, quickly and cheaply, sends the hard or risky ones to a person,
and never lets an unsafe reply reach a customer.

> **What works today.** Join with the session code from the screen and a
> team name at `/join`. The canvas, palette, inspector and live validation
> work, and your graph is saved on the server a second after each change
> (the header says **Saved**), so a refresh loses nothing. **Run traffic**
> runs your pipeline on practice tickets and shows the results live.
>
> Edit on **one laptop per team**: if two edit at once, one of them gets
> "Your graph was changed elsewhere; reloaded." and loses its last change.
> When the facilitator calls **pencils down**, the workbench turns read-only
> with a banner. Lost your browser? Join again with the same team name.

---

## 1. The screen

| Area | What it does |
|------|--------------|
| **Header** (top) | Your team and session, the save status (Saved / Saving… / Offline – retrying / Locked), **Reset graph** (back to the starter graph, after a confirm) and **Sign out**. |
| **Palette** (left) | Every node type you can use, grouped by category. Click a card to add that node at the centre of the canvas, or drag it to where you want it. |
| **Canvas** (middle) | Your pipeline. Drag nodes to move them, scroll to zoom, drag the background to pan. |
| **Inspector** (right) | With one node selected: its description, settings (params), ports, cost and latency assumptions, problems, and a **Delete node** button. With nothing selected: the **Pipeline check**, a list of every problem in the graph. |
| **Help panel** (bottom of the canvas) | Click the **?** on any node (in the palette, on the canvas, or in the inspector header) to open its help: what it does, where it goes, every setting and output, a worked example and tips. One panel at a time: another **?** swaps it, the same **?**, **×** or **Esc** closes it. Drag its top edge to resize it. You can keep working while it is open. |

You start with the **starter graph**. It works, but it has deliberate
weaknesses for you to find and fix (see section 7).

---

## 2. How tickets flow

Every ticket enters at **Customer message** and should end at **Customer
response**. In between, each node takes values in on its **input ports**
(left side) and sends values out on its **output ports** (right side). You
connect an output to an input with an **edge**.

Some nodes make a decision and have **branch ports** (shown in a different
style, named `route.something`). For each ticket **exactly one branch
fires**. The ticket's text goes out on that branch only, and everything that
sits only on the other branches is skipped for that ticket.

Example: the intent router decides a ticket is `billing`. The text leaves on
`route.billing`; the nodes connected to `route.bug_report` don't run for that
ticket.

### How a ticket can end

| Outcome | Meaning |
|---------|---------|
| **Automated** | Reached Customer response without a human. This is what you want for routine tickets. |
| **Escalated** | Reached Customer response after passing through Human review. Safe, but slow and expensive. |
| **Blocked** | Stopped on a policy block or "unsafe" branch with nothing connected after it. The customer gets nothing, but nothing unsafe was sent either. |
| **Dropped** | Fell into a dead end, such as an unconnected branch. The customer gets no reply, and this always counts as a wrong decision. |
| **Failed** | A node errored. |

---

## 3. The nodes

Costs and latencies below are the simulator's assumptions; the inspector
shows them for each node. For the full explanation of any node, click its **?**.

### Input and output

**Customer message** (source, exactly one per graph)
- Outputs: `text` (the ticket) and `meta` (json: channel and language).
- Params: traffic mix, language, attack rate. In official runs the game
  admin overrides these so every team gets identical traffic.

**Customer response** (sink, at least one per graph)
- Input: `text` (multi). Whatever arrives here is sent to the customer, so
  make sure only safe text gets here.
- Params: channel and an SLA display value (display only, not scored).

### Jev nodes: fast, cheap, bounded decisions

Jev nodes don't write text. They pick from a fixed set of answers and report
how confident they are. They are fast (tens of milliseconds) and cost a
fraction of a cent.

**Jev intent router**
- Input: `text` (multi).
- Outputs: `intent` (enum), `probabilities` (json), `confidence`
  (probability), plus one branch per allowed intent (`route.billing`,
  `route.technical_support`, ...) and `route.low_confidence`.
- Params:
  - **Allowed intents**: which intents get their own branch. Adding or
    removing one adds or removes a branch port. Removing one also deletes
    the edges on that branch.
  - **Confidence threshold** (default 0.50): when the router is less sure
    than this, the ticket goes to `route.low_confidence` instead.
- Assumptions: very accurate on routine tickets, less so on complex ones,
  close to a coin toss on ambiguous ones. Wrong answers tend to come with
  lower confidence, so the threshold is a real lever. A misrouted ticket that
  gets answered automatically counts as a wrong decision.
- 40 ms ± 15 ms, $0.0002 per call.

**Jev safety check**
- Input: `text` (multi).
- Outputs: `is_safe` (boolean), `confidence`, `categories` (json), and the
  branches `route.safe` and `route.unsafe`.
- Params: **Categories** to look for (prompt injection, abuse, fraud, PII
  requests, self-harm) and a **Threshold**.
- Assumptions: catches roughly 9 in 10 risky messages in the enabled
  categories and wrongly flags about 3 in 100 normal ones. It labels a
  message but doesn't clean it: an unsafe message still needs to go
  somewhere safe, and a missed one carries on down `route.safe`.
- 30 ms ± 10 ms, $0.0002 per call.

### LLM node: writes the reply

**LLM answer generator**
- Inputs: `text` (multi) and an optional `context` (json docs from Knowledge
  lookup).
- Output: `text`, the drafted reply.
- Params: **Model tier** (small or large), **Temperature**, **Max tokens**,
  **System prompt** (up to 500 characters).
- Assumptions:
  - Latency is time-to-first-token (small 150 ms, large 350 ms) plus a
    per-token time (small 4 ms, large 10 ms) for every token written. Long
    answers from the large model are slow. Max tokens caps the length, and
    higher temperature makes answers wordier.
  - The large model gives better answers on complex tickets.
  - LLMs can be manipulated. If a prompt-injection message reaches the LLM,
    it may follow the attacker's instructions (the small model more often
    than the large one). The wording of your system prompt matters.
  - Without context, an answer to a ticket that needs facts may be made up
    (ungrounded), which counts as a wrong decision.

### Tools: deterministic helpers

**Knowledge lookup**
- Input: `text` (multi). Output: `docs` (json), which plugs into the LLM's
  `context` input.
- Params: **Source** (faq, kb, tickets) and **Top k** (how many articles).
- 25 ms + 5 ms per article, about $0.00001 per call.

**Policy engine**
- Inputs: `text` (multi), optional `context` (json).
- Outputs: `passed` (boolean), `report` (json), and the branches `route.pass`
  and `route.block`.
- Params: **Rules** (no refund promises, no legal advice, no internal URLs,
  no credentials), your own **Blocked phrases**, and **Data classes** to
  detect (email, phone, card number, SSN).
- Assumptions: plain pattern rules with no judgement. It catches a problem
  only if a matching rule is switched on, so it catches some unsafe output
  but not all of it.
- 10 ms ± 3 ms, free.

### Human

**Human review queue**
- Inputs: `text` (multi), optional `context` (json). Output: `text`.
- Params: **Reviewers** and **Review time**.
- Assumptions: a person fixes almost every problem (98%), but each review
  costs **$2.00**, which is thousands of times more than an automated step.
  Every ticket through here counts as **escalated**, not automated. Review
  time is not counted in the latency score.

---

## 4. Building and linking

**Add a node:** click its card in the palette, or drag the card onto the
canvas. New nodes get the default settings and an id like `policy_engine`,
`policy_engine_2`, ...

**Connect two nodes:** press on an output handle (right side of a node) and
drag to an input handle (left side of another node). If the link isn't
allowed, nothing is created and a short notice explains why.

**Change settings:** click a node and edit its params in the inspector. An
invalid value stays in the field with an error message and isn't applied
until you fix it.

**Delete:** select a node or an edge and press **Backspace**, or use **Delete
node** in the inspector. Deleting a node removes its edges too. Ctrl-click
(Cmd-click on a Mac) selects several items, or hold Shift and drag a box
around them. If Backspace does nothing, click the canvas
first: while a text field has focus, the key edits the field instead.

### Port types

Each handle's colour and shape shows its type. An edge must connect matching
types.

| Type | Carries | Colour |
|------|---------|--------|
| text | message or reply text (every branch port is text) | blue circle |
| json | structured data (docs, reports, metadata) | amber square |
| enum | one value from a fixed list (e.g. an intent) | purple diamond |
| probability | a confidence between 0 and 1 | pink ring |
| boolean | true/false | green |
| score | a 1–5 rating | red |
| any | anything | grey dashed |

### Linking rules

These are checked as you drag; a refused link shows the reason:

1. **Types must match.** text→text, json→json and so on. An input of type
   `any` accepts everything. An `any` output into a typed input is allowed
   but flagged as a warning.
2. **No self-loops and no cycles.** Tickets flow one way, from source to
   sink.
3. **One edge per single input.** Most inputs marked *multi* accept several
   edges; the first value to arrive wins and later ones are ignored. A
   non-multi input accepts only one edge.
4. **At most 4 edges out of one output port.**
5. **No duplicate edges** between the same two ports.

Enum→enum links also need the source's values to be a subset of the
target's; the server checks that.

### Graph rules

- Exactly **one Customer message** and at least **one Customer response**.
- Every **required input** must be connected (optional inputs such as
  `context` are marked).
- At most **40 nodes** and **80 edges**.

---

## 5. The Pipeline check (validation)

The server checks your graph about half a second after each change. Problems
appear as coloured badges on nodes, ports and edges, and as a list in the
inspector. Click an item in the list to select the node it is about.

- **Errors** (red) must be fixed before the graph can run: unknown ports,
  type mismatches, cycles, missing required inputs, no source or sink, bad
  param values, too many edges on a port, and so on.
- **Warnings** (amber) still let the graph run, but they point at a likely
  weakness:

| Warning | What it means for your score |
|---------|------------------------------|
| UNCONNECTED_BRANCH | Tickets that take this branch are **dropped**. |
| DEAD_END | Something this output produces can never reach the customer. |
| UNREACHABLE_NODE | No ticket can ever reach this node. |
| NO_SAFETY_COVERAGE | Some path through the LLM has no safety check before it and no policy engine after it. |
| NO_HUMAN_FALLBACK | No path reaches human review, so there's nowhere for hard or risky tickets to go. |
| MULTI_INPUT_RACE | A multi input is fed by branches that can fire together, so which value wins depends on timing. |
| ANY_SOURCE | An untyped output feeds a typed input. |

A graph with no warnings isn't automatically a good graph, but every warning
is worth a look.

---

## 6. Objectives and scoring

Your pipeline is measured on a batch of tickets:

| Metric | Definition | You want it |
|--------|------------|-------------|
| **Automation rate** | share of tickets answered without a human | high |
| **Escalation rate** | share sent to human review | only as high as needed |
| **Unsafe-release rate** | share where something unsafe reached the customer | as close to 0 as possible |
| **Dropped rate** | share that got no reply at all | 0 |
| **p50 / p95 latency** | typical and slowest-5% response time of the **automated** replies | p95 under **800 ms** |
| **Cost per 1,000 tickets** | all node costs, including human reviews | under the **$1,000** budget |
| **Decision quality** | share of tickets handled correctly | high |

A ticket is handled **correctly** if it was answered automatically with the
right intent and a grounded, correctly routed answer, or if it was escalated
or blocked when it needed to be. A dropped ticket is always wrong.

A reply counts as an **unsafe release** if it reaches the customer carrying
an injected instruction, leaked personal data or a policy violation, or if a
ticket that had to be blocked was answered automatically.

### The score

```
score = 100 × automation rate
      +  50 × decision quality
      − 400 × unsafe-release rate
      −   1 point per 10 ms that p95 latency is over 800 ms
      −   5 points per 10% that cost is over the $1,000 budget
```

The big weight on unsafe releases is deliberate: **one unsafe reply wipes out
the benefit of automating several tickets.** Escalating everything is
perfectly safe, but it scores poorly because nothing is automated and the
cost runs over budget.

### Practice and official runs

- **Practice runs:** press **Run traffic** (above the canvas) to run your
  saved graph on the 15-ticket practice pack. It takes about 45 seconds:
  dots move along the edges as tickets flow, each node shows what it did
  (requests, average latency, cost, routing decisions, tokens, escalations,
  failures, skips), and the metrics bar shows p95 latency, cost per 1,000,
  automation and unsafe releases, green when a target is met and red when
  it isn't, plus your score at the end. The graph is read-only while it
  runs; **Stop** ends it early. The button is greyed out, with the reason
  shown, while your graph has errors or is locked. Only your team sees the
  results, and they don't go on the leaderboard.
- **Official runs:** the admin starts these for every team at once. All
  graphs are **locked** (no edits) and run on a hidden 30-ticket pack, with
  the same random seed and traffic for everyone. These results make the
  leaderboard. The official pack has the same kinds of tickets as the
  practice pack but different wording, so tune for the patterns, not for
  particular tickets.

---

## 7. Rules and assumptions

- **It's a simulation.** The Jev and LLM nodes are mocks with realistic,
  documented behaviour. No real AI service is called, and no ticket is from
  a real customer.
- **It's fair.** Results are deterministic: the same node with the same
  settings on the same ticket and seed behaves the same for every team. Node
  ids and layout don't matter; only the structure and the settings do.
- **The ticket mix** has routine, complex and ambiguous requests, policy
  violations (for example asking for a refund promise or legal advice) and
  prompt-injection attempts.
- **Latency** counts only automated replies, and follows the slowest path a
  ticket takes (the critical path).
- **One graph per team.** When saving arrives, the last save wins.
- **Edits are locked** during an official run.

### The starter graph

```
Customer message → Jev intent router ─(4 intent branches)→ LLM answer generator
                                     → Policy engine ─(pass)→ Customer response
```

It runs, but it has several deliberate weaknesses. The Pipeline check points
at some of them straight away; others show up only in the metrics. Some
questions to guide you:

- Where do tickets go when the router isn't sure?
- What happens to an answer the policy engine blocks?
- What stops an attacker's message from reaching the LLM?
- Is the LLM fast enough for an 800 ms p95, and does it have the facts it
  needs?
- Which tickets are worth $2 of human time, and which aren't?

Good luck.
