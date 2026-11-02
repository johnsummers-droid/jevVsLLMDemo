"""Help panel content for the human_review_queue node. The rules are in __init__.py."""

from app.models import HelpExample, NodeHelp

HUMAN_REVIEW_QUEUE_HELP = NodeHelp(
    summary="A person reviews the request and approves or fixes the answer. The safest step "
            "in the catalog, and by far the slowest and most expensive.",
    placement="On the branches you don't trust to automation: a router's low-confidence "
              "branch, a safety check's unsafe branch, or a policy engine's block branch. "
              "Connect its output to the customer response.",
    how_it_works=[
        "A reviewer reads what arrives and almost always catches and removes any problem in "
        "it.",
        "Every request that passes through a human counts as escalated, not automated.",
        "Review time is counted separately: it doesn't count towards the automated latency "
        "metrics.",
        "Each review has a fixed cost, which adds up quickly against the cost budget.",
    ],
    inputs={
        "text": "The request or draft reply for a person to review.",
        "context": "Optional. The reviewer doesn't use it yet.",
    },
    params={
        "capacity": "How many reviewers work this queue. Queueing isn't simulated yet, so "
                    "it doesn't change a run today.",
        "reviewer_latency_s": "How long a typical review takes, in seconds.",
    },
    outputs={
        "text": "The reviewed text, almost always safe to send.",
    },
    example=HelpExample(
        ticket_id="p-11",
        input_text=("Something is wrong with my account and the numbers don't add "
                    "up."),
        outputs={"text": "Something is wrong with my account and the numbers don't add up."},
        explanation="A vague complaint goes to a person, who handles it. The request counts "
                    "as escalated, and the review adds its cost.",
    ),
    tips=[
        "Escalating everything is safe but expensive and drags the automation rate down; "
        "send only the cases automation can't handle well.",
    ],
)
