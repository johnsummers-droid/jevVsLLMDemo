# Help panel UX review (2026-11-02, awaiting the user's decision)

Review of the mock `UI-mocks/Human Review Queue Infographic.png`. Nothing is built yet.
Delete this file once the panel is built and its decisions are in `plan1.txt`.

The card layout is a big improvement and I'd adopt its structure, but not as drawn. The main problems
are that it needs far more room than the panel has, and it brings back clutter that was just removed.

## What I'd keep
- **Sections as cards:** today's panel is a long run of text. Cards make it easy to scan, which is the
  biggest gain.
- **Clear reading order:** what it is and where it goes come first, then how it works, an example and
  tips, with reference details on the right.
- **Header with a mini pipeline:** it shows where the node sits at a glance.
- **Example as labelled Input and Output rows:** much clearer than the current layout.
- **Tips as a strip at the bottom,** and **cost as rows with small icons**.

## What I'd change
| In the mock | Problem | What I'd do |
|---|---|---|
| **Fits one screen** | It's 3:2. At a 1440 px window the canvas is about 850 px wide, so the mock would need about 565 px of height. The panel gets about 280 px today. | See the decision below |
| **Green for Human** | Human is blue in the app, and green means live activity and the team name | Use each node's own category colour |
| **Blue, green, purple and amber cards** | They compete with the port colours and category colours, and amber means "warning" in the app | One accent colour per panel, neutral cards |
| **`text · required`, `reviewer_latency_s`, `json`** | This is the jargon just removed from the Inspector | Drop it |
| **Context input** | It's now hidden | Follows the existing rule automatically |
| **Illustration of a person** | It would need 8 matching images, and they add weight without explaining much | A small diagram using our own icons: input → node → output |
| **Numbered "How it works"** | The numbers imply steps, but items 3 and 4 here are facts, not a sequence | Plain bullets, or numbers only where there's a real sequence |
| **Summary shown twice** | The header and "What it is" repeat the same sentence | Use the node's short description in the header |
| **"Settings", "Cost & Speed"** | The Inspector says "Parameters" and "Cost and latency assumptions" | Use the same names in both |

## This node is the easy case
The mock has one input, one output and one setting. The real panel also has to handle:
- **Router:** 5 outputs and a longer example
- **Customer message:** no inputs or settings
- **Customer response:** no outputs or example
- **Policy engine:** long descriptions of its rules

So the layout has to reflow when cards are missing or tall. Test all 8 nodes, not just this one.

**A content problem it exposes:** the example's Input and Output are the same sentence, which makes
human review look like it does nothing. A ticket where the reviewer visibly fixes a draft reply would
teach more, but tests run each example through the real node, and the human reviewer passes its text
through unchanged. Showing a real fix would therefore need changes beyond the panel.

## Decision needed: how much room should it take?
- **A. Taller docked panel, about 65% of the canvas, scrolling inside (my pick):** keeps today's
  behaviour, where the app still works underneath and you can resize it. It covers more of the graph,
  possibly including the node you clicked, but people usually read help as a deliberate pause.
- **B. Keep it short, add tabs (Overview, Example, Reference):** the graph stays visible, but you can't
  see everything at once, which loses what makes the mock appealing.
- **C. Large floating window over everything:** closest to the mock, but it covers the palette and
  Inspector and goes against the original "the app keeps working underneath" requirement.

The work is confined to the web app (`HelpPanel.tsx` and CSS), using the existing help text, with no new
dependencies.

Next step: the user picks A, B or C and says if they disagree with the table. Then build it, and show
screenshots of all 8 nodes.
