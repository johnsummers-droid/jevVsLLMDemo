"""Help panel content for the customer_message node. The rules are in __init__.py."""

from app.models import HelpExample, NodeHelp

CUSTOMER_MESSAGE_HELP = NodeHelp(
    summary="The start of every pipeline. Each request in a run is one customer support "
            "ticket, and this node hands its text to the rest of the graph.",
    placement="Exactly one per graph, on the far left. Connect its Text output to the first "
              "node that should read the message, such as a router or a safety check.",
    how_it_works=[
        "A run sends a stream of tickets through the graph; this node emits one per request.",
        "Text is the customer's message.",
        "Some tickets are routine, some are complex or vague, and some try to trick the "
        "pipeline into doing something it shouldn't.",
    ],
    params={
        "traffic_mix": "The intended mix of tickets: realistic, mostly routine, or "
                       "adversarial. Not used yet: every run draws from the scenario pack's "
                       "own mix.",
        "language": "The language of the tickets. Only English for now.",
        "attack_rate": "The intended share of manipulative tickets. Not used yet, like the "
                       "traffic mix.",
    },
    outputs={
        "text": "The customer's message, passed on word for word.",
        "meta": "The ticket's channel, as JSON.",
    },
    example=HelpExample(
        ticket_id="p-01",
        outputs={
            "text": "I was charged twice for my March invoice. Can you check what happened?",
            "meta": {"channel": "chat"},
        },
        explanation="A billing ticket arrives. Its text goes to whatever the Text output is "
                    "connected to.",
    ),
    tips=[
        "Practice runs use the practice tickets; the official run uses a different, hidden "
        "set, so don't tune your graph to individual practice tickets.",
    ],
)
